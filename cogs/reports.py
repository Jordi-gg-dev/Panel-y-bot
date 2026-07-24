"""
AstroCube Anti-Raid - Alertas (Premium).

Comandos /alertas para configurar el canal central de alertas, el aviso por
MD al dueño en emergencias, y el reporte semanal automático. La lógica real
de envío vive en utils/alerts.py (llamada desde antinuke.py/antiraid.py); lo
único que este cog añade por su cuenta es la tarea programada del reporte
semanal.

Las tres opciones son exclusivas de servidores Premium: si un servidor
gratuito intenta activarlas, se le explica y se le dirige al panel.
"""

from __future__ import annotations

import datetime
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database as db
from utils import embeds, checks

SEVEN_DAYS = 7 * 24 * 60 * 60


def _premium_required_embed() -> discord.Embed:
    return embeds.warning(
        "Función Premium",
        "Las Alertas (tiempo real, MD al dueño y reporte semanal) son exclusivas de servidores con Premium. "
        "Actívalo desde el panel web para desbloquearlas.",
    )


class Reports(commands.Cog):
    """Alertas centralizadas + reporte semanal de AstroCube Anti-Raid."""

    alertas_group = app_commands.Group(
        name="alertas", description="Alertas centralizadas Premium: tiempo real, MD al dueño y reporte semanal",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_report_loop.start()

    def cog_unload(self):
        self.weekly_report_loop.cancel()

    # ------------------------------------------------------------------
    # Reporte semanal en segundo plano
    # ------------------------------------------------------------------
    @tasks.loop(hours=24)
    async def weekly_report_loop(self):
        today = datetime.datetime.now(datetime.timezone.utc)
        if today.weekday() != config.WEEKLY_REPORT_WEEKDAY:
            return
        for guild in list(self.bot.guilds):
            try:
                await self._maybe_send_weekly_report(guild)
            except discord.HTTPException:
                pass

    @weekly_report_loop.before_loop
    async def before_weekly_report_loop(self):
        await self.bot.wait_until_ready()

    async def _maybe_send_weekly_report(self, guild: discord.Guild):
        if not await db.is_premium(guild.id):
            return
        if not await db.get_bool(guild.id, "alerts_weekly_enabled", False):
            return

        last_sent = await db.get_last_weekly_report(guild.id)
        now = int(time.time())
        if last_sent and now - last_sent < SEVEN_DAYS - 3600:
            return  # ya se envió esta semana (con un pequeño margen)

        channel_id = await db.get_config(guild.id, "alerts_channel") or await db.get_config(guild.id, "antinuke_log_channel")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            return

        total, by_module = await db.incidents_summary_since(guild.id, now - SEVEN_DAYS)
        embed = embeds.info("📊 Reporte semanal de seguridad", f"Resumen de los últimos 7 días de **{guild.name}**.")
        embed.add_field(name="Incidentes totales", value=str(total), inline=False)
        if by_module:
            desc = "\n".join(f"• **{module}**: {count}" for module, count in by_module)
            embed.add_field(name="Desglose por módulo", value=desc, inline=False)
        else:
            embed.add_field(name="Desglose por módulo", value="Sin incidentes esta semana. 🎉", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            return
        await db.set_last_weekly_report(guild.id, now)

    # ------------------------------------------------------------------
    # /alertas
    # ------------------------------------------------------------------
    @alertas_group.command(name="canal", description="Define el canal central donde llegan las Alertas (Premium)")
    @checks.is_admin()
    async def alertas_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await db.set_config(interaction.guild.id, "alerts_channel", canal.id)
        await interaction.response.send_message(embed=embeds.success("Canal de alertas configurado", canal.mention), ephemeral=True)

    @alertas_group.command(name="tiempo-real", description="Activa/desactiva las alertas en tiempo real en el canal central (Premium)")
    @checks.is_admin()
    async def alertas_tiempo_real(self, interaction: discord.Interaction):
        if not await db.is_premium(interaction.guild.id):
            return await interaction.response.send_message(embed=_premium_required_embed(), ephemeral=True)
        current = await db.get_bool(interaction.guild.id, "alerts_realtime_enabled", False)
        await db.set_config(interaction.guild.id, "alerts_realtime_enabled", "0" if current else "1")
        estado = "desactivadas ❌" if current else "activadas ✅"
        await interaction.response.send_message(embed=embeds.success(f"Alertas en tiempo real {estado}"))

    @alertas_group.command(name="md", description="Activa/desactiva el aviso por MD al dueño en emergencias (Premium)")
    @checks.is_admin()
    async def alertas_md(self, interaction: discord.Interaction):
        if not await db.is_premium(interaction.guild.id):
            return await interaction.response.send_message(embed=_premium_required_embed(), ephemeral=True)
        current = await db.get_bool(interaction.guild.id, "alerts_dm_enabled", False)
        await db.set_config(interaction.guild.id, "alerts_dm_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Aviso por MD al dueño {estado}"))

    @alertas_group.command(name="semanal", description="Activa/desactiva el reporte semanal automático (Premium)")
    @checks.is_admin()
    async def alertas_semanal(self, interaction: discord.Interaction):
        if not await db.is_premium(interaction.guild.id):
            return await interaction.response.send_message(embed=_premium_required_embed(), ephemeral=True)
        current = await db.get_bool(interaction.guild.id, "alerts_weekly_enabled", False)
        await db.set_config(interaction.guild.id, "alerts_weekly_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Reporte semanal {estado}"))

    @alertas_group.command(name="status", description="Muestra el estado de las Alertas")
    @checks.is_admin()
    async def alertas_status(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        premium = await db.is_premium(guild_id)
        channel_id = await db.get_config(guild_id, "alerts_channel")
        embed = embeds.info("🔔 Estado de Alertas")
        embed.add_field(name="Premium", value="Sí ✅" if premium else "No ❌", inline=True)
        embed.add_field(name="Canal central", value=f"<#{channel_id}>" if channel_id else "No configurado", inline=True)
        embed.add_field(name="Tiempo real", value="✅" if await db.get_bool(guild_id, "alerts_realtime_enabled", False) else "❌", inline=True)
        embed.add_field(name="MD al dueño", value="✅" if await db.get_bool(guild_id, "alerts_dm_enabled", False) else "❌", inline=True)
        embed.add_field(name="Reporte semanal", value="✅" if await db.get_bool(guild_id, "alerts_weekly_enabled", False) else "❌", inline=True)
        if not premium:
            embed.add_field(name="Nota", value="Estas 3 opciones solo funcionan con Premium, aunque las actives aquí no se enviará nada hasta que lo tengas.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot))
