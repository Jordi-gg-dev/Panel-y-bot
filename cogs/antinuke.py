"""
AstroCube Anti-Raid - Módulo Anti-Nuke.

Vigila acciones destructivas masivas (borrado/creación de canales y roles,
baneos, webhooks) usando el registro de auditoría del servidor para
identificar al responsable, y castiga automáticamente cuando se supera el
umbral configurado — salvo que esté en la whitelist.

IMPORTANTE: el bot necesita el permiso "Ver registro de auditoría" para que
esto funcione, y su rol debe estar por encima de los roles que quiere poder
quitar/gestionar.
"""

from __future__ import annotations

import time
import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks, alerts


MODULE_CHOICES = [
    app_commands.Choice(name="Borrado de canales", value="channel_delete"),
    app_commands.Choice(name="Creación de canales", value="channel_create"),
    app_commands.Choice(name="Borrado de roles", value="role_delete"),
    app_commands.Choice(name="Creación de roles", value="role_create"),
    app_commands.Choice(name="Baneos", value="ban"),
    app_commands.Choice(name="Webhooks", value="webhook_create"),
]

PUNISHMENT_CHOICES = [
    app_commands.Choice(name="Quitar todos los roles", value="strip-roles"),
    app_commands.Choice(name="Silenciar 1 hora (timeout)", value="timeout"),
    app_commands.Choice(name="Expulsar", value="kick"),
    app_commands.Choice(name="Banear", value="ban"),
]


class ActionTracker:
    """Cuenta acciones por (servidor, usuario, tipo) en una ventana deslizante."""

    def __init__(self):
        self._events: dict[tuple[int, int, str], list[float]] = {}

    def hit(self, guild_id: int, user_id: int, action: str, window_seconds: int) -> int:
        now = time.time()
        key = (guild_id, user_id, action)
        recent = [t for t in self._events.get(key, []) if now - t < window_seconds]
        recent.append(now)
        self._events[key] = recent
        return len(recent)

    def reset(self, guild_id: int, user_id: int, action: str):
        self._events.pop((guild_id, user_id, action), None)


class AntiNuke(commands.Cog):
    """Protección anti-nuke de AstroCube Anti-Raid."""

    antinuke_group = app_commands.Group(
        name="antinuke", description="Protección contra borrado/creación masiva y baneos (nuke)",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tracker = ActionTracker()

    # ------------------------------------------------------------------
    # Motor de detección
    # ------------------------------------------------------------------
    async def _get_executor(self, guild: discord.Guild, audit_action: discord.AuditLogAction):
        try:
            async for entry in guild.audit_logs(limit=5, action=audit_action):
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age < 8:
                    return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _check(self, guild: discord.Guild, audit_action: discord.AuditLogAction, module_key: str, detail: str):
        if guild is None:
            return
        if not await db.get_bool(guild.id, "antinuke_enabled", True):
            return
        executor = await self._get_executor(guild, audit_action)
        if executor is None:
            return
        await self._handle_trigger(guild, executor, module_key, detail)

    async def _handle_trigger(self, guild: discord.Guild, executor: discord.abc.User, module_key: str, detail: str):
        if executor.id == self.bot.user.id:
            return
        if executor.id == guild.owner_id:
            return
        if await checks.is_owner(executor.id):
            return
        if executor.bot:
            if await db.antinuke_trustedbot_has(guild.id, executor.id):
                return
        else:
            if await db.antinuke_whitelist_has(guild.id, executor.id):
                return

        default_count, default_seconds = config.DEFAULT_ANTINUKE_THRESHOLDS.get(module_key, (3, 10))
        threshold_count, threshold_seconds = await db.get_int_pair(
            guild.id, f"antinuke_threshold_{module_key}", (default_count, default_seconds)
        )
        count = self.tracker.hit(guild.id, executor.id, module_key, threshold_seconds)
        if count < threshold_count:
            return

        self.tracker.reset(guild.id, executor.id, module_key)
        punishment = await db.get_config(guild.id, "antinuke_punishment", "strip-roles")
        member = guild.get_member(executor.id)
        action_taken = "sin acción (el bot no tiene permisos o el usuario ya no está)"

        try:
            if member:
                if punishment == "ban":
                    await guild.ban(member, reason=f"AstroCube Anti-Raid: {detail}", delete_message_seconds=0)
                    action_taken = "usuario baneado"
                elif punishment == "kick":
                    await guild.kick(member, reason=f"AstroCube Anti-Raid: {detail}")
                    action_taken = "usuario expulsado"
                elif punishment == "timeout":
                    await member.timeout(datetime.timedelta(hours=1), reason=f"AstroCube Anti-Raid: {detail}")
                    action_taken = "usuario silenciado 1 hora"
                else:
                    removable = [r for r in member.roles if r.name != "@everyone" and r < guild.me.top_role]
                    if removable:
                        await member.remove_roles(*removable, reason=f"AstroCube Anti-Raid: {detail}")
                    action_taken = "roles retirados"
        except discord.HTTPException as exc:
            action_taken = f"error al castigar ({exc})"

        await db.log_incident(guild.id, module_key, executor.id, detail, action_taken)

        autoheal_summary = None
        if module_key in config.ANTINUKE_AUTOHEAL_MODULES and await db.get_bool(guild.id, "antinuke_autoheal", True):
            autoheal_summary = await self._try_autoheal(guild, module_key)

        alert_embed = embeds.alert(f"Anti-Nuke activado: {module_key}", detail)
        alert_embed.add_field(name="Usuario", value=f"{executor.mention} (`{executor.id}`)", inline=False)
        alert_embed.add_field(name="Veces detectadas", value=str(count), inline=True)
        alert_embed.add_field(name="Acción tomada", value=action_taken, inline=True)
        if autoheal_summary:
            alert_embed.add_field(name="🤖 Auto-restauración", value=autoheal_summary, inline=False)

        log_channel_id = await db.get_config(guild.id, "antinuke_log_channel")
        if log_channel_id:
            channel = guild.get_channel(int(log_channel_id))
            if channel:
                try:
                    await channel.send(embed=alert_embed)
                except discord.HTTPException:
                    pass

        # Alertas (Premium): además del canal de logs propio de arriba, avisa
        # en el canal central de alertas y por MD al dueño si están activados.
        await alerts.notify_realtime(guild, alert_embed)
        await alerts.notify_owner_dm(guild, alert_embed)

    async def _try_autoheal(self, guild: discord.Guild, module_key: str) -> str | None:
        """Tras un borrado masivo de canales/roles, recrea lo que falte usando la
        copia de seguridad automática (si existe). Nunca borra ni modifica nada,
        solo rellena los huecos — es seguro llamarlo aunque el ataque siga."""
        backup_cog = self.bot.get_cog("Backup")
        if backup_cog is None:
            return None
        found, counts = await backup_cog.restore_from_auto(
            guild, reason=f"Auto-restauración de AstroCube Anti-Raid tras {module_key}"
        )
        if not found:
            return "No había ninguna copia automática todavía (se genera sola cada hora). Considera usar `/backup create` ahora."

        created_roles, created_categories, created_channels = counts
        summary = f"{created_roles} rol(es), {created_categories} categoría(s) y {created_channels} canal(es) recreados automáticamente."
        await db.log_incident(guild.id, f"{module_key}_autoheal", None, "Auto-restauración tras Anti-Nuke", summary)
        return summary

    # ------------------------------------------------------------------
    # Eventos vigilados
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._check(channel.guild, discord.AuditLogAction.channel_delete, "channel_delete", f"Canal eliminado: #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._check(channel.guild, discord.AuditLogAction.channel_create, "channel_create", f"Canal creado: #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._check(role.guild, discord.AuditLogAction.role_delete, "role_delete", f"Rol eliminado: {role.name}")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._check(role.guild, discord.AuditLogAction.role_create, "role_create", f"Rol creado: {role.name}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User):
        await self._check(guild, discord.AuditLogAction.ban, "ban", f"Usuario baneado: {user}")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await self._check(channel.guild, discord.AuditLogAction.webhook_create, "webhook_create", f"Webhook modificado en #{channel.name}")

    # ------------------------------------------------------------------
    # Comandos /antinuke
    # ------------------------------------------------------------------
    @antinuke_group.command(name="toggle", description="Activa o desactiva la protección anti-nuke en este servidor")
    @checks.is_admin()
    async def antinuke_toggle(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antinuke_enabled", True)
        await db.set_config(interaction.guild.id, "antinuke_enabled", "0" if current else "1")
        estado = "desactivada ❌" if current else "activada ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-Nuke {estado}"))

    @antinuke_group.command(name="status", description="Muestra la configuración actual del anti-nuke")
    @checks.is_admin()
    async def antinuke_status(self, interaction: discord.Interaction):
        enabled = await db.get_bool(interaction.guild.id, "antinuke_enabled", True)
        autoheal = await db.get_bool(interaction.guild.id, "antinuke_autoheal", True)
        punishment = await db.get_config(interaction.guild.id, "antinuke_punishment", "strip-roles")
        log_channel_id = await db.get_config(interaction.guild.id, "antinuke_log_channel")
        whitelist = await db.antinuke_whitelist_list(interaction.guild.id)
        embed = embeds.info("🛡️ Estado del Anti-Nuke")
        embed.add_field(name="Activo", value="Sí ✅" if enabled else "No ❌", inline=True)
        embed.add_field(name="Auto-restauración", value="Sí ✅" if autoheal else "No ❌", inline=True)
        embed.add_field(name="Castigo", value=punishment, inline=True)
        embed.add_field(name="Canal de logs", value=f"<#{log_channel_id}>" if log_channel_id else "No configurado", inline=True)
        embed.add_field(name="Whitelist", value=str(len(whitelist)) + " usuario(s)", inline=True)
        for key, (default_c, default_s) in config.DEFAULT_ANTINUKE_THRESHOLDS.items():
            count, seconds = await db.get_int_pair(interaction.guild.id, f"antinuke_threshold_{key}", (default_c, default_s))
            embed.add_field(name=key, value=f"{count} en {seconds}s", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antinuke_group.command(name="autoheal", description="Activa o desactiva la auto-restauración de canales/roles tras un ataque")
    @checks.is_admin()
    async def antinuke_autoheal(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antinuke_autoheal", True)
        await db.set_config(interaction.guild.id, "antinuke_autoheal", "0" if current else "1")
        estado = "desactivada ❌" if current else "activada ✅"
        await interaction.response.send_message(embed=embeds.success(
            f"Auto-restauración {estado}",
            "Cuando alguien borre canales/roles en masa, Anti-Nuke ya no recreará automáticamente lo borrado usando la copia de seguridad automática."
            if current else
            "Cuando alguien borre canales/roles en masa, además de castigarlo Anti-Nuke recreará automáticamente lo borrado usando la copia de seguridad automática (`/backup auto-status` para verla).",
        ))

    @antinuke_group.command(name="punishment", description="Define el castigo automático del anti-nuke")
    @app_commands.choices(castigo=PUNISHMENT_CHOICES)
    @checks.is_admin()
    async def antinuke_punishment(self, interaction: discord.Interaction, castigo: app_commands.Choice[str]):
        await db.set_config(interaction.guild.id, "antinuke_punishment", castigo.value)
        await interaction.response.send_message(embed=embeds.success("Castigo actualizado", castigo.name), ephemeral=True)

    @antinuke_group.command(name="threshold", description="Define cuántas acciones en cuántos segundos disparan el anti-nuke")
    @app_commands.choices(modulo=MODULE_CHOICES)
    @checks.is_admin()
    async def antinuke_threshold(self, interaction: discord.Interaction, modulo: app_commands.Choice[str], cantidad: app_commands.Range[int, 1, 50], segundos: app_commands.Range[int, 2, 120]):
        await db.set_int_pair(interaction.guild.id, f"antinuke_threshold_{modulo.value}", cantidad, segundos)
        await interaction.response.send_message(embed=embeds.success("Umbral actualizado", f"{modulo.name}: {cantidad} en {segundos}s"), ephemeral=True)

    @antinuke_group.command(name="logchannel", description="Define el canal donde se avisa de incidentes anti-nuke")
    @checks.is_admin()
    async def antinuke_logchannel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await db.set_config(interaction.guild.id, "antinuke_log_channel", canal.id)
        await interaction.response.send_message(embed=embeds.success("Canal de logs configurado", canal.mention), ephemeral=True)

    @antinuke_group.command(name="whitelist-add", description="Añade a un usuario de confianza (nunca será castigado)")
    @checks.is_admin()
    async def antinuke_whitelist_add(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.antinuke_whitelist_add(interaction.guild.id, usuario.id)
        await interaction.response.send_message(embed=embeds.success("Añadido a la whitelist", usuario.mention), ephemeral=True)

    @antinuke_group.command(name="whitelist-remove", description="Quita a un usuario de la whitelist del anti-nuke")
    @checks.is_admin()
    async def antinuke_whitelist_remove(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.antinuke_whitelist_remove(interaction.guild.id, usuario.id)
        await interaction.response.send_message(embed=embeds.success("Quitado de la whitelist", usuario.mention), ephemeral=True)

    @antinuke_group.command(name="whitelist-list", description="Lista los usuarios de confianza del anti-nuke")
    @checks.is_admin()
    async def antinuke_whitelist_list(self, interaction: discord.Interaction):
        ids = await db.antinuke_whitelist_list(interaction.guild.id)
        if not ids:
            return await interaction.response.send_message(embed=embeds.info("Whitelist vacía"), ephemeral=True)
        await interaction.response.send_message(embed=embeds.info("Whitelist del anti-nuke", "\n".join(f"<@{i}>" for i in ids)), ephemeral=True)

    @antinuke_group.command(name="trustedbot-add", description="Marca un bot como de confianza (no será castigado)")
    @checks.is_admin()
    async def antinuke_trustedbot_add(self, interaction: discord.Interaction, bot_usuario: discord.Member):
        await db.antinuke_trustedbot_add(interaction.guild.id, bot_usuario.id)
        await interaction.response.send_message(embed=embeds.success("Bot marcado como confiable", bot_usuario.mention), ephemeral=True)

    @antinuke_group.command(name="trustedbot-remove", description="Quita a un bot de la lista de confianza")
    @checks.is_admin()
    async def antinuke_trustedbot_remove(self, interaction: discord.Interaction, bot_usuario: discord.Member):
        await db.antinuke_trustedbot_remove(interaction.guild.id, bot_usuario.id)
        await interaction.response.send_message(embed=embeds.success("Bot quitado de la lista de confianza", bot_usuario.mention), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
