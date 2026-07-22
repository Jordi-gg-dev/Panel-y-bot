"""
AstroCube Anti-Raid - Información general, historial de incidentes y
configuración de verificación del servidor.
"""

from __future__ import annotations

import time
import platform
import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database as db
from utils import embeds, checks

FREE_INCIDENT_RETENTION_DAYS = 7


VERIFICATION_CHOICES = [
    app_commands.Choice(name="Ninguna", value="none"),
    app_commands.Choice(name="Baja", value="low"),
    app_commands.Choice(name="Media", value="medium"),
    app_commands.Choice(name="Alta", value="high"),
    app_commands.Choice(name="Máxima (recomendado en riesgo de raid)", value="highest"),
]
_LEVEL_MAP = {
    "none": discord.VerificationLevel.none,
    "low": discord.VerificationLevel.low,
    "medium": discord.VerificationLevel.medium,
    "high": discord.VerificationLevel.high,
    "highest": discord.VerificationLevel.highest,
}


class Info(commands.Cog):
    """Información, incidentes y verificación de AstroCube Anti-Raid."""

    verification_group = app_commands.Group(
        name="verification", description="Configura el nivel de verificación de entrada del servidor",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.purge_old_incidents.start()

    def cog_unload(self):
        self.purge_old_incidents.cancel()

    @tasks.loop(hours=24)
    async def purge_old_incidents(self):
        """[Plan gratuito] Los servidores sin Premium solo conservan
        FREE_INCIDENT_RETENTION_DAYS días de historial de incidentes."""
        guild_ids = await db.list_all_guild_ids_with_incidents()
        for guild_id in guild_ids:
            if await db.is_premium(guild_id):
                continue
            await db.purge_old_incidents(guild_id, FREE_INCIDENT_RETENTION_DAYS)

    @purge_old_incidents.before_loop
    async def before_purge_old_incidents(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="help", description="Muestra todos los comandos de AstroCube Anti-Raid")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def help_command(self, interaction: discord.Interaction):
        embed = embeds.info(f"🛡️ Comandos de {config.BOT_NAME}", "Todos los comandos requieren permiso de Administrador (o Gestionar Servidor).")
        grouped: dict[str, list[str]] = {}
        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Group):
                continue
            cog_name = cmd.binding.__class__.__name__ if cmd.binding else "General"
            grouped.setdefault(cog_name, []).append(f"`/{cmd.qualified_name}`")
        for cog_name, cmds in sorted(grouped.items()):
            embed.add_field(name=cog_name, value=" ".join(sorted(cmds))[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Muestra la latencia del bot")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=embeds.info("🏓 Pong", f"Latencia: **{round(self.bot.latency * 1000)}ms**"))

    @app_commands.command(name="botinfo", description="Muestra información sobre AstroCube Anti-Raid")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def botinfo(self, interaction: discord.Interaction):
        embed = embeds.info(f"🛰️ {config.BOT_NAME}", "Protección anti-nuke, anti-spam y anti-raid para servidores de Discord.")
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latencia", value=f"{round(self.bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="Comandos", value=str(len(self.bot.tree.get_commands())), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Muestra información del servidor")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = embeds.info(f"🌐 {guild.name}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Dueño", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Miembros", value=str(guild.member_count), inline=True)
        embed.add_field(name="Verificación", value=str(guild.verification_level), inline=True)
        embed.add_field(name="Creado", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Muestra información de un usuario")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def userinfo(self, interaction: discord.Interaction, usuario: discord.Member = None):
        usuario = usuario or interaction.user
        age_days = (discord.utils.utcnow() - usuario.created_at).days
        embed = embeds.info(f"👤 {usuario}")
        embed.set_thumbnail(url=usuario.display_avatar.url)
        embed.add_field(name="ID", value=f"`{usuario.id}`", inline=True)
        embed.add_field(name="Cuenta creada", value=f"<t:{int(usuario.created_at.timestamp())}:R> ({age_days} días)", inline=True)
        embed.add_field(name="Se unió", value=f"<t:{int(usuario.joined_at.timestamp())}:R>" if usuario.joined_at else "—", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Muestra el avatar de un usuario en grande")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def avatar(self, interaction: discord.Interaction, usuario: discord.User = None):
        usuario = usuario or interaction.user
        embed = embeds.info(f"Avatar de {usuario}")
        embed.set_image(url=usuario.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="uptime", description="Muestra cuánto tiempo lleva encendido el bot")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def uptime(self, interaction: discord.Interaction):
        delta = datetime.timedelta(seconds=int(time.time() - self.bot.start_time))
        await interaction.response.send_message(embed=embeds.info("⏱️ Uptime", f"**{str(delta)}**"))

    @app_commands.command(name="invite", description="Genera el enlace para añadir AstroCube Anti-Raid a otro servidor")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def invite(self, interaction: discord.Interaction):
        url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(administrator=True))
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Invitar al bot", style=discord.ButtonStyle.link, url=url, emoji="🤖"))
        view.add_item(discord.ui.Button(label="Únete a nuestro servidor", style=discord.ButtonStyle.link, url=config.SUPPORT_SERVER_INVITE, emoji="💬"))
        await interaction.response.send_message(embed=embeds.info("🔗 Invitar a AstroCube Anti-Raid", f"[Haz clic aquí para invitarlo a otro servidor]({url})"), view=view, ephemeral=True)

    @app_commands.command(name="soporte", description="Muestra el enlace para unirte al servidor de soporte de AstroCube")
    async def soporte(self, interaction: discord.Interaction):
        embed = embeds.info("💬 Servidor de soporte", "¿Necesitas ayuda, quieres proponer una idea o seguir las novedades de AstroCube? Únete a nuestro servidor de Discord.")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Únete a nuestro servidor", style=discord.ButtonStyle.link, url=config.SUPPORT_SERVER_INVITE, emoji="💬"))
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="incidents", description="Muestra el historial reciente de incidentes de seguridad")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def incidents(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 1, 25] = 10):
        rows = await db.get_incidents(interaction.guild.id, cantidad)
        if not rows:
            return await interaction.response.send_message(embed=embeds.info("Sin incidentes registrados", "Buena señal 👍"), ephemeral=True)
        desc = "\n".join(
            f"**{module}** — {(f'<@{ex}>' if ex else 'N/D')} — {detail} → *{action}* — <t:{ts}:R>"
            for module, ex, detail, action, ts in rows
        )
        await interaction.response.send_message(embed=embeds.alert("📋 Historial de incidentes", desc[:4000]), ephemeral=True)

    @app_commands.command(name="incidents-clear", description="Borra el historial de incidentes de este servidor")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def incidents_clear(self, interaction: discord.Interaction):
        await db.clear_incidents(interaction.guild.id)
        await interaction.response.send_message(embed=embeds.success("Historial de incidentes borrado"), ephemeral=True)

    # ------------------------------------------------------------------
    # GRUPO /verification
    # ------------------------------------------------------------------
    @verification_group.command(name="setlevel", description="Cambia el nivel de verificación de entrada del servidor")
    @app_commands.choices(nivel=VERIFICATION_CHOICES)
    @checks.is_admin()
    async def verification_setlevel(self, interaction: discord.Interaction, nivel: app_commands.Choice[str]):
        try:
            await interaction.guild.edit(verification_level=_LEVEL_MAP[nivel.value], reason=f"Cambiado por {interaction.user}")
            await interaction.response.send_message(embed=embeds.success("Nivel de verificación actualizado", nivel.name))
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embeds.error("No se pudo cambiar", str(exc)), ephemeral=True)

    @verification_group.command(name="autorole", description="Define un rol que se asigna automáticamente a cada nuevo miembro")
    @checks.is_admin()
    async def verification_autorole(self, interaction: discord.Interaction, rol: discord.Role = None):
        if rol is None:
            await db.set_config(interaction.guild.id, "autorole", "")
            return await interaction.response.send_message(embed=embeds.success("Autorole desactivado"), ephemeral=True)
        await db.set_config(interaction.guild.id, "autorole", rol.id)
        await interaction.response.send_message(embed=embeds.success("Autorole configurado", rol.mention), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        role_id = await db.get_config(member.guild.id, "autorole")
        if role_id:
            role = member.guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Autorole AstroCube Anti-Raid")
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
