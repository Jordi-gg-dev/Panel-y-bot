"""
AstroCube Anti-Raid - Comandos reservados a los desarrolladores del bot
(config.OWNER_IDS), no a cada servidor. Gestión multi-servidor del propio bot.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks


class Owner(commands.Cog):
    """Comandos de owner de AstroCube Anti-Raid."""

    owner_group = app_commands.Group(
        name="owner", description="Comandos exclusivos de los desarrolladores del bot",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @owner_group.command(name="reload", description="Recarga un módulo (cog) del bot en caliente")
    @checks.is_bot_owner()
    async def owner_reload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(embed=embeds.success("Cog recargado", f"`cogs.{cog}`"), ephemeral=True)
        except commands.ExtensionError as exc:
            await interaction.response.send_message(embed=embeds.error("Error al recargar", str(exc)), ephemeral=True)

    @owner_group.command(name="sync", description="Sincroniza los slash commands (globalmente o en el servidor de pruebas)")
    @checks.is_bot_owner()
    async def owner_sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if config.DEV_GUILD_ID:
            guild_obj = discord.Object(id=config.DEV_GUILD_ID)
            self.bot.tree.copy_global_to(guild=guild_obj)
            synced = await self.bot.tree.sync(guild=guild_obj)
        else:
            synced = await self.bot.tree.sync()
        await interaction.followup.send(embed=embeds.success("Comandos sincronizados", f"{len(synced)} comandos actualizados."))

    @owner_group.command(name="guildlist", description="Lista los servidores en los que está el bot")
    @checks.is_bot_owner()
    async def owner_guildlist(self, interaction: discord.Interaction):
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        desc = "\n".join(f"`{g.id}` — {g.name} ({g.member_count} miembros)" for g in guilds[:30])
        embed = embeds.info(f"Servidores ({len(guilds)})", desc or "Ninguno")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @owner_group.command(name="leaveguild", description="Hace que el bot abandone un servidor por su ID")
    @checks.is_bot_owner()
    async def owner_leaveguild(self, interaction: discord.Interaction, guild_id: str):
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return await interaction.response.send_message(embed=embeds.error("El bot no está en ese servidor"), ephemeral=True)
        name = guild.name
        await guild.leave()
        await interaction.response.send_message(embed=embeds.success("Servidor abandonado", name), ephemeral=True)

    @owner_group.command(name="blacklistguild-add", description="Bloquea un servidor: el bot lo abandona y no puede volver a entrar")
    @checks.is_bot_owner()
    async def owner_blacklistguild_add(self, interaction: discord.Interaction, guild_id: str, razon: str = "Sin especificar"):
        gid = int(guild_id)
        await db.blacklist_guild_add(gid, razon)
        guild = self.bot.get_guild(gid)
        if guild:
            await guild.leave()
        await interaction.response.send_message(embed=embeds.success("Servidor bloqueado", f"`{guild_id}` — {razon}"), ephemeral=True)

    @owner_group.command(name="blacklistguild-remove", description="Desbloquea un servidor previamente bloqueado")
    @checks.is_bot_owner()
    async def owner_blacklistguild_remove(self, interaction: discord.Interaction, guild_id: str):
        ok = await db.blacklist_guild_remove(int(guild_id))
        if ok:
            await interaction.response.send_message(embed=embeds.success("Servidor desbloqueado", guild_id), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.error("Ese servidor no estaba bloqueado"), ephemeral=True)

    @owner_group.command(name="blacklistuser-add", description="Impide que un usuario use el bot en cualquier servidor")
    @checks.is_bot_owner()
    async def owner_blacklistuser_add(self, interaction: discord.Interaction, usuario: discord.User, razon: str = "Sin especificar"):
        await db.blacklist_user_add(usuario.id, razon)
        await interaction.response.send_message(embed=embeds.success("Usuario bloqueado del bot", usuario.mention), ephemeral=True)

    @owner_group.command(name="blacklistuser-remove", description="Quita a un usuario de la blacklist global del bot")
    @checks.is_bot_owner()
    async def owner_blacklistuser_remove(self, interaction: discord.Interaction, usuario: discord.User):
        ok = await db.blacklist_user_remove(usuario.id)
        if ok:
            await interaction.response.send_message(embed=embeds.success("Usuario desbloqueado", usuario.mention), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.error("Ese usuario no estaba bloqueado"), ephemeral=True)

    @owner_group.command(name="broadcast", description="Envía un DM a los dueños de todos los servidores donde está el bot")
    @checks.is_bot_owner()
    async def owner_broadcast(self, interaction: discord.Interaction, mensaje: str):
        await interaction.response.defer(ephemeral=True)
        sent, failed = 0, 0
        embed = embeds.info(f"📢 Aviso de {config.BOT_NAME}", mensaje)
        for guild in self.bot.guilds:
            owner = guild.owner or await self.bot.fetch_user(guild.owner_id)
            try:
                await owner.send(embed=embed)
                sent += 1
            except discord.HTTPException:
                failed += 1
        await interaction.followup.send(embed=embeds.success("Broadcast enviado", f"Entregados: {sent} · Fallidos: {failed}"))

    @owner_group.command(name="maintenance", description="Activa/desactiva el modo mantenimiento global del bot")
    @checks.is_bot_owner()
    async def owner_maintenance(self, interaction: discord.Interaction):
        self.bot.maintenance = not getattr(self.bot, "maintenance", False)
        estado = "activado 🔧" if self.bot.maintenance else "desactivado ✅"
        await interaction.response.send_message(embed=embeds.warning("Modo mantenimiento", f"Ahora está {estado}."), ephemeral=True)

    @owner_group.command(name="shutdown", description="Apaga el bot de forma segura")
    @checks.is_bot_owner()
    async def owner_shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=embeds.warning("Apagando AstroCube Anti-Raid...", "🛰️"), ephemeral=True)
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
