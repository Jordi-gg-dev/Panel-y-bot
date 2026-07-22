"""
AstroCube Anti-Raid - Módulo Anti-Spam.

Detecta ráfagas de mensajes y spam de menciones (mass-mention) por usuario,
borra los mensajes y aplica un castigo configurable.
"""

from __future__ import annotations

import time
import datetime
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks


PUNISHMENT_CHOICES = [
    app_commands.Choice(name="Silenciar 10 minutos (timeout)", value="timeout"),
    app_commands.Choice(name="Expulsar", value="kick"),
    app_commands.Choice(name="Banear", value="ban"),
]


class AntiSpam(commands.Cog):
    """Protección anti-spam de AstroCube Anti-Raid."""

    antispam_group = app_commands.Group(
        name="antispam", description="Protección contra flood de mensajes y spam de menciones",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._message_log: dict[tuple[int, int], list[tuple[float, discord.Message]]] = defaultdict(list)

    async def _punish(self, member: discord.Member, reason: str, punishment: str) -> str:
        try:
            if punishment == "ban":
                await member.guild.ban(member, reason=reason, delete_message_seconds=60)
                return "usuario baneado"
            if punishment == "kick":
                await member.guild.kick(member, reason=reason)
                return "usuario expulsado"
            await member.timeout(datetime.timedelta(minutes=10), reason=reason)
            return "usuario silenciado 10 minutos"
        except discord.HTTPException as exc:
            return f"error al castigar ({exc})"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        if await checks.is_server_admin(message.author):
            return
        if not await db.get_bool(message.guild.id, "antispam_enabled", True):
            return
        if await db.antispam_whitelist_has(message.guild.id, message.author.id):
            return

        guild_id = message.guild.id

        # --- Spam de menciones (un solo mensaje con muchas menciones) ---
        mention_threshold = int(await db.get_config(guild_id, "antispam_mention_threshold", config.DEFAULT_ANTISPAM_MENTION_THRESHOLD))
        total_mentions = len(message.mentions) + len(message.role_mentions) + (5 if message.mention_everyone else 0)
        if total_mentions >= mention_threshold:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            punishment = await db.get_config(guild_id, "antispam_punishment", "timeout")
            action = await self._punish(message.author, "AstroCube Anti-Raid: spam de menciones", punishment)
            await db.log_incident(guild_id, "mention_spam", message.author.id, f"{total_mentions} menciones en un mensaje", action)
            return

        # --- Flood de mensajes (muchos mensajes seguidos) ---
        count_threshold, window = await db.get_int_pair(
            guild_id, "antispam_message_threshold", config.DEFAULT_ANTISPAM_MESSAGE_THRESHOLD
        )
        now = time.time()
        key = (guild_id, message.author.id)
        recent = [(t, m) for t, m in self._message_log[key] if now - t < window]
        recent.append((now, message))
        self._message_log[key] = recent

        if len(recent) >= count_threshold:
            self._message_log[key] = []
            punishment = await db.get_config(guild_id, "antispam_punishment", "timeout")
            action = await self._punish(message.author, "AstroCube Anti-Raid: flood de mensajes", punishment)
            for _, msg in recent:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass
            await db.log_incident(guild_id, "message_spam", message.author.id, f"{len(recent)} mensajes en {window}s", action)

    # ------------------------------------------------------------------
    # Comandos /antispam
    # ------------------------------------------------------------------
    @antispam_group.command(name="toggle", description="Activa o desactiva el anti-spam en este servidor")
    @checks.is_admin()
    async def antispam_toggle(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antispam_enabled", True)
        await db.set_config(interaction.guild.id, "antispam_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-spam {estado}"))

    @antispam_group.command(name="message-threshold", description="Define cuántos mensajes seguidos se consideran flood")
    @checks.is_admin()
    async def antispam_message_threshold(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 3, 30], segundos: app_commands.Range[int, 2, 60]):
        await db.set_int_pair(interaction.guild.id, "antispam_message_threshold", cantidad, segundos)
        await interaction.response.send_message(embed=embeds.success("Umbral actualizado", f"{cantidad} mensajes en {segundos}s"), ephemeral=True)

    @antispam_group.command(name="mention-threshold", description="Define cuántas menciones en un mensaje se consideran spam")
    @checks.is_admin()
    async def antispam_mention_threshold(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 3, 30]):
        await db.set_config(interaction.guild.id, "antispam_mention_threshold", cantidad)
        await interaction.response.send_message(embed=embeds.success("Umbral actualizado", f"{cantidad} menciones por mensaje"), ephemeral=True)

    @antispam_group.command(name="punishment", description="Define el castigo automático del anti-spam")
    @app_commands.choices(castigo=PUNISHMENT_CHOICES)
    @checks.is_admin()
    async def antispam_punishment(self, interaction: discord.Interaction, castigo: app_commands.Choice[str]):
        await db.set_config(interaction.guild.id, "antispam_punishment", castigo.value)
        await interaction.response.send_message(embed=embeds.success("Castigo actualizado", castigo.name), ephemeral=True)

    @antispam_group.command(name="whitelist-add", description="Excluye a un usuario del anti-spam")
    @checks.is_admin()
    async def antispam_whitelist_add(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.antispam_whitelist_add(interaction.guild.id, usuario.id)
        await interaction.response.send_message(embed=embeds.success("Excluido del anti-spam", usuario.mention), ephemeral=True)

    @antispam_group.command(name="whitelist-remove", description="Quita a un usuario de la lista de exclusión del anti-spam")
    @checks.is_admin()
    async def antispam_whitelist_remove(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.antispam_whitelist_remove(interaction.guild.id, usuario.id)
        await interaction.response.send_message(embed=embeds.success("Quitado de la exclusión", usuario.mention), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))
