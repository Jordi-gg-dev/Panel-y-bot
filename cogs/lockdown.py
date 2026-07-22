"""
AstroCube Anti-Raid - Módulo de Lockdown (botón de pánico).

Bloquea (y desbloquea con precisión) todo el servidor: guarda el estado
anterior de cada canal antes de tocar nada, para poder revertirlo tal cual
estaba con /lockdown unpanic.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils import embeds, checks


class Lockdown(commands.Cog):
    """Bloqueo de emergencia de AstroCube Anti-Raid."""

    lockdown_group = app_commands.Group(
        name="lockdown", description="Bloqueo de emergencia del servidor",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Motor de pánico (también lo usa cogs.antiraid en oleadas de entrada)
    # ------------------------------------------------------------------
    async def engage_panic(self, guild: discord.Guild, reason: str = "Bloqueo de emergencia") -> bool:
        if await db.get_lockdown_state(guild.id):
            return False

        state = {"verification_level": guild.verification_level.value, "channels": {}}

        for channel in guild.text_channels:
            overwrite = channel.overwrites_for(guild.default_role)
            state["channels"][str(channel.id)] = {"type": "text", "send_messages": overwrite.send_messages}
            overwrite.send_messages = False
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            except discord.HTTPException:
                pass

        for channel in guild.voice_channels:
            overwrite = channel.overwrites_for(guild.default_role)
            state["channels"][str(channel.id)] = {"type": "voice", "connect": overwrite.connect}
            overwrite.connect = False
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            except discord.HTTPException:
                pass

        try:
            await guild.edit(verification_level=discord.VerificationLevel.highest, reason=reason)
        except discord.HTTPException:
            pass

        await db.save_lockdown_state(guild.id, state)
        return True

    async def disengage_panic(self, guild: discord.Guild) -> bool:
        state = await db.get_lockdown_state(guild.id)
        if not state:
            return False

        for channel_id, info in state.get("channels", {}).items():
            channel = guild.get_channel(int(channel_id))
            if channel is None:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            if info.get("type") == "text":
                overwrite.send_messages = info.get("send_messages")
            else:
                overwrite.connect = info.get("connect")
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Fin del bloqueo de emergencia")
            except discord.HTTPException:
                pass

        try:
            await guild.edit(verification_level=discord.VerificationLevel(state.get("verification_level", 0)), reason="Fin del bloqueo de emergencia")
        except discord.HTTPException:
            pass

        await db.clear_lockdown_state(guild.id)
        return True

    # ------------------------------------------------------------------
    # Comandos /lockdown
    # ------------------------------------------------------------------
    @lockdown_group.command(name="panic", description="🚨 Bloquea TODO el servidor: nadie puede escribir ni entrar a voz")
    @checks.is_admin()
    async def lockdown_panic(self, interaction: discord.Interaction, razon: str = "Bloqueo de emergencia"):
        await interaction.response.defer()
        ok = await self.engage_panic(interaction.guild, reason=razon)
        if ok:
            await db.log_incident(interaction.guild.id, "manual_panic", interaction.user.id, razon, "servidor bloqueado")
            await interaction.followup.send(embed=embeds.alert("🔒 Servidor bloqueado", f"Motivo: {razon}\nUsa `/lockdown unpanic` para revertirlo cuando todo esté controlado."))
        else:
            await interaction.followup.send(embed=embeds.error("Ya estaba en modo pánico", "Usa `/lockdown unpanic` primero si quieres reiniciarlo."))

    @lockdown_group.command(name="unpanic", description="Revierte el bloqueo total del servidor")
    @checks.is_admin()
    async def lockdown_unpanic(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ok = await self.disengage_panic(interaction.guild)
        if ok:
            await db.log_incident(interaction.guild.id, "manual_unpanic", interaction.user.id, "", "servidor desbloqueado")
            await interaction.followup.send(embed=embeds.success("🔓 Bloqueo revertido", "El servidor ha vuelto a su estado anterior."))
        else:
            await interaction.followup.send(embed=embeds.error("El servidor no estaba en modo pánico"))

    @lockdown_group.command(name="lock", description="Bloquea un canal concreto (o el actual)")
    @checks.is_admin()
    async def lockdown_lock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal = canal or interaction.channel
        overwrite = canal.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await canal.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Bloqueado por {interaction.user}")
        await interaction.response.send_message(embed=embeds.warning("Canal bloqueado", canal.mention))

    @lockdown_group.command(name="unlock", description="Desbloquea un canal concreto (o el actual)")
    @checks.is_admin()
    async def lockdown_unlock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal = canal or interaction.channel
        overwrite = canal.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await canal.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Desbloqueado por {interaction.user}")
        await interaction.response.send_message(embed=embeds.success("Canal desbloqueado", canal.mention))


async def setup(bot: commands.Bot):
    await bot.add_cog(Lockdown(bot))
