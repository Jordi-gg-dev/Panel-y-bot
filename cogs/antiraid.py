"""
AstroCube Anti-Raid - Módulo Anti-Raid (oleadas de entrada).

Dos protecciones independientes:
1. Filtro de cuentas nuevas: expulsa automáticamente cuentas más jóvenes que
   el mínimo configurado (típico en raids con cuentas creadas al momento).
2. Detección de oleada de entradas: si entran muchos miembros en poco
   tiempo, sube el nivel de verificación del servidor (y opcionalmente activa
   el bloqueo total vía el módulo de Lockdown).
"""

from __future__ import annotations

import time
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks, alerts


ACTION_CHOICES = [
    app_commands.Choice(name="Solo subir verificación al máximo", value="lockdown-verification"),
    app_commands.Choice(name="Bloqueo total del servidor (lockdown completo)", value="full-lockdown"),
]


class AntiRaid(commands.Cog):
    """Protección anti-raid (oleadas de entrada) de AstroCube Anti-Raid."""

    antiraid_group = app_commands.Group(
        name="antiraid", description="Protección contra oleadas de entrada y cuentas nuevas",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._joins: dict[int, list[float]] = defaultdict(list)

    async def _notify(self, guild: discord.Guild, title: str, description: str):
        embed = embeds.alert(title, description)
        channel_id = await db.get_config(guild.id, "antiraid_log_channel") or await db.get_config(guild.id, "antinuke_log_channel")
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        # Alertas (Premium): oleada de entradas es exactamente el tipo de
        # "emergencia" que justifica el aviso central + MD al dueño.
        await alerts.notify_realtime(guild, embed)
        await alerts.notify_owner_dm(guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if member.bot:
            await self._check_antibots(member)
            return
        if not await db.get_bool(guild.id, "antiraid_enabled", True):
            return
        if await db.antiraid_whitelist_has(guild.id, member.id):
            return

        account_age_days = (discord.utils.utcnow() - member.created_at).days
        min_age = int(await db.get_config(guild.id, "antiraid_min_account_age", config.DEFAULT_MIN_ACCOUNT_AGE_DAYS))

        if min_age > 0 and account_age_days < min_age:
            try:
                await member.kick(reason=f"AstroCube Anti-Raid: cuenta de {account_age_days} días (mínimo {min_age})")
                await db.log_incident(guild.id, "new_account", member.id, f"Cuenta de {account_age_days} días (mínimo {min_age})", "expulsado automáticamente")
                await self._notify(guild, "Cuenta nueva expulsada", f"{member} (`{member.id}`) — cuenta de {account_age_days} días.")
            except discord.HTTPException:
                pass
            return

        count_threshold, window = await db.get_int_pair(
            guild.id, "antiraid_join_threshold", config.DEFAULT_ANTIRAID_JOIN_THRESHOLD
        )
        now = time.time()
        history = [t for t in self._joins[guild.id] if now - t < window]
        history.append(now)
        self._joins[guild.id] = history

        if len(history) >= count_threshold:
            self._joins[guild.id] = []
            await self._trigger_raid_mode(guild, len(history), window)

    async def _check_antibots(self, member: discord.Member):
        """Anti-Bots: si un bot se une y no está en la lista de bots de
        confianza (la misma whitelist que usa Anti-Nuke con /antinuke
        trustedbot-add), se expulsa al instante. Así cualquier bot añadido
        por sorpresa (por ejemplo con un token robado con permiso de
        invitar bots) no llega a hacer nada."""
        guild = member.guild
        if member.id == self.bot.user.id:
            return
        if not await db.get_bool(guild.id, "antibots_enabled", True):
            return
        if await db.antinuke_trustedbot_has(guild.id, member.id):
            return
        try:
            await member.kick(reason="AstroCube Anti-Raid (Anti-Bots): bot no autorizado")
            await db.log_incident(guild.id, "unauthorized_bot", member.id, f"Bot no autorizado: {member}", "bot expulsado automáticamente")
            await self._notify(guild, "🤖 Bot no autorizado expulsado", f"{member} (`{member.id}`) no estaba en la lista de bots de confianza.\nSi era legítimo, autorízalo con `/antinuke trustedbot-add` antes de volver a invitarlo.")
        except discord.HTTPException:
            pass

    @app_commands.command(name="antibots", description="Activa/desactiva la expulsión automática de bots no autorizados al entrar")
    @checks.is_admin()
    async def antibots_toggle(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antibots_enabled", True)
        await db.set_config(interaction.guild.id, "antibots_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(
            f"Anti-Bots {estado}",
            "Los bots que autorices con `/antinuke trustedbot-add` seguirán pudiendo entrar sin problema."
            if not current else None,
        ))

    async def _trigger_raid_mode(self, guild: discord.Guild, count: int, window: int):
        action = await db.get_config(guild.id, "antiraid_action", "lockdown-verification")
        detail = f"{count} miembros se unieron en {window} segundos"
        action_taken = "ninguna"

        try:
            await guild.edit(verification_level=discord.VerificationLevel.highest, reason="AstroCube Anti-Raid: oleada de entradas detectada")
            action_taken = "nivel de verificación subido al máximo"
        except discord.HTTPException as exc:
            action_taken = f"error al subir verificación ({exc})"

        if action == "full-lockdown":
            lockdown_cog = self.bot.get_cog("Lockdown")
            if lockdown_cog:
                await lockdown_cog.engage_panic(guild, reason="Oleada de entradas detectada")
                action_taken += " + bloqueo total del servidor"

        await db.log_incident(guild.id, "join_raid", None, detail, action_taken)
        await self._notify(guild, "🚨 Oleada de entradas detectada", f"{detail}\nAcción tomada: {action_taken}")

    # ------------------------------------------------------------------
    # Comandos /antiraid
    # ------------------------------------------------------------------
    @antiraid_group.command(name="toggle", description="Activa o desactiva la protección anti-raid en este servidor")
    @checks.is_admin()
    async def antiraid_toggle(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antiraid_enabled", True)
        await db.set_config(interaction.guild.id, "antiraid_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-raid {estado}"))

    @antiraid_group.command(name="joinrate", description="Define cuántas entradas en cuántos segundos se consideran una oleada")
    @checks.is_admin()
    async def antiraid_joinrate(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 3, 100], segundos: app_commands.Range[int, 3, 120]):
        await db.set_int_pair(interaction.guild.id, "antiraid_join_threshold", cantidad, segundos)
        await interaction.response.send_message(embed=embeds.success("Umbral actualizado", f"{cantidad} entradas en {segundos}s"), ephemeral=True)

    @antiraid_group.command(name="minaccountage", description="Expulsa automáticamente cuentas más nuevas que X días (0 para desactivar)")
    @checks.is_admin()
    async def antiraid_minaccountage(self, interaction: discord.Interaction, dias: app_commands.Range[int, 0, 90]):
        await db.set_config(interaction.guild.id, "antiraid_min_account_age", dias)
        if dias == 0:
            await interaction.response.send_message(embed=embeds.success("Filtro de cuentas nuevas desactivado"), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.success("Filtro actualizado", f"Se expulsará a cuentas con menos de {dias} días de antigüedad"), ephemeral=True)

    @antiraid_group.command(name="action", description="Define qué hace el bot al detectar una oleada de entradas")
    @app_commands.choices(accion=ACTION_CHOICES)
    @checks.is_admin()
    async def antiraid_action(self, interaction: discord.Interaction, accion: app_commands.Choice[str]):
        await db.set_config(interaction.guild.id, "antiraid_action", accion.value)
        await interaction.response.send_message(embed=embeds.success("Acción actualizada", accion.name), ephemeral=True)

    @antiraid_group.command(name="logchannel", description="Define el canal donde se avisa de incidentes anti-raid")
    @checks.is_admin()
    async def antiraid_logchannel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await db.set_config(interaction.guild.id, "antiraid_log_channel", canal.id)
        await interaction.response.send_message(embed=embeds.success("Canal de logs configurado", canal.mention), ephemeral=True)

    @antiraid_group.command(name="status", description="Muestra la configuración actual del anti-raid")
    @checks.is_admin()
    async def antiraid_status(self, interaction: discord.Interaction):
        enabled = await db.get_bool(interaction.guild.id, "antiraid_enabled", True)
        min_age = await db.get_config(interaction.guild.id, "antiraid_min_account_age", config.DEFAULT_MIN_ACCOUNT_AGE_DAYS)
        count, window = await db.get_int_pair(interaction.guild.id, "antiraid_join_threshold", config.DEFAULT_ANTIRAID_JOIN_THRESHOLD)
        action = await db.get_config(interaction.guild.id, "antiraid_action", "lockdown-verification")
        embed = embeds.info("🛡️ Estado del Anti-Raid")
        embed.add_field(name="Activo", value="Sí ✅" if enabled else "No ❌", inline=True)
        embed.add_field(name="Edad mínima de cuenta", value=f"{min_age} días", inline=True)
        embed.add_field(name="Umbral de oleada", value=f"{count} en {window}s", inline=True)
        embed.add_field(name="Acción", value=action, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antiraid_group.command(name="whitelist-add", description="Excluye a un usuario del filtro de cuentas nuevas")
    @checks.is_admin()
    async def antiraid_whitelist_add(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.antiraid_whitelist_add(interaction.guild.id, usuario.id)
        await interaction.response.send_message(embed=embeds.success("Excluido del anti-raid", usuario.mention), ephemeral=True)

    @antiraid_group.command(name="whitelist-remove", description="Quita a un usuario de la lista de exclusión del anti-raid")
    @checks.is_admin()
    async def antiraid_whitelist_remove(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.antiraid_whitelist_remove(interaction.guild.id, usuario.id)
        await interaction.response.send_message(embed=embeds.success("Quitado de la exclusión", usuario.mention), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
