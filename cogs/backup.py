"""
AstroCube Anti-Raid - Módulo de Backups.

Guarda una foto de los roles y canales del servidor y permite restaurar lo
que falte tras un ataque. La restauración es siempre ADITIVA: nunca borra
nada, solo recrea lo que ya no existe.

Además de las copias manuales (/backup create), este módulo mantiene UNA
copia automática por servidor que se refresca sola cada hora (nunca se
acumulan varias: la nueva sustituye a la anterior). Cuando Anti-Nuke detecta
un borrado masivo de canales o roles, usa esa copia automática para
autorestaurar el servidor justo después de castigar al responsable — sin que
nadie tenga que mover un dedo.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database as db
from utils import embeds, checks


def _build_snapshot(guild: discord.Guild) -> dict:
    """Genera la foto de roles/categorías/canales de un servidor (sin tocar nada)."""
    return {
        "roles": [
            {
                "name": r.name,
                "color": r.color.value,
                "permissions": r.permissions.value,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
            }
            for r in guild.roles if r.name != "@everyone" and not r.managed
        ],
        "categories": [{"name": c.name} for c in guild.categories],
        "channels": [
            {
                "name": ch.name,
                "type": str(ch.type),
                "category": ch.category.name if ch.category else None,
                "topic": getattr(ch, "topic", None),
                "nsfw": getattr(ch, "nsfw", False),
            }
            for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)
        ],
    }


async def _restore_snapshot(guild: discord.Guild, data: dict, reason: str) -> tuple[int, int, int]:
    """Recrea lo que falte según `data`. Nunca borra ni modifica nada existente.
    Devuelve (roles_creados, categorias_creadas, canales_creados)."""
    created_roles = created_categories = created_channels = 0

    existing_role_names = {r.name for r in guild.roles}
    for role_data in data.get("roles", []):
        if role_data["name"] in existing_role_names:
            continue
        try:
            await guild.create_role(
                name=role_data["name"],
                color=discord.Color(role_data["color"]),
                permissions=discord.Permissions(role_data["permissions"]),
                hoist=role_data["hoist"],
                mentionable=role_data["mentionable"],
                reason=reason,
            )
            created_roles += 1
        except discord.HTTPException:
            pass

    category_map = {c.name: c for c in guild.categories}
    for cat_data in data.get("categories", []):
        if cat_data["name"] in category_map:
            continue
        try:
            new_cat = await guild.create_category(cat_data["name"], reason=reason)
            category_map[cat_data["name"]] = new_cat
            created_categories += 1
        except discord.HTTPException:
            pass

    existing_channel_names = {ch.name for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)}
    for ch_data in data.get("channels", []):
        if ch_data["name"] in existing_channel_names:
            continue
        category = category_map.get(ch_data["category"]) if ch_data.get("category") else None
        try:
            if "voice" in ch_data["type"]:
                await guild.create_voice_channel(ch_data["name"], category=category, reason=reason)
            else:
                await guild.create_text_channel(
                    ch_data["name"], category=category, topic=ch_data.get("topic"),
                    nsfw=ch_data.get("nsfw", False), reason=reason,
                )
            created_channels += 1
        except discord.HTTPException:
            pass

    return created_roles, created_categories, created_channels


class Backup(commands.Cog):
    """Copias de seguridad de AstroCube Anti-Raid."""

    backup_group = app_commands.Group(
        name="backup", description="Copias de seguridad de canales y roles",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    # ------------------------------------------------------------------
    # Auto-backup en segundo plano (usado por el autoheal de Anti-Nuke)
    # ------------------------------------------------------------------
    @tasks.loop(hours=config.DEFAULT_AUTOBACKUP_INTERVAL_HOURS)
    async def auto_backup_loop(self):
        for guild in list(self.bot.guilds):
            try:
                await db.save_auto_backup(guild.id, _build_snapshot(guild))
            except discord.HTTPException:
                pass

    @auto_backup_loop.before_loop
    async def before_auto_backup_loop(self):
        await self.bot.wait_until_ready()

    async def restore_from_auto(self, guild: discord.Guild, reason: str) -> tuple[bool, tuple[int, int, int] | None]:
        """Usado por Anti-Nuke para autorestaurar. Devuelve (encontrada, conteos)."""
        result = await db.get_auto_backup(guild.id)
        if not result:
            return False, None
        data, _created_at = result
        counts = await _restore_snapshot(guild, data, reason)
        return True, counts

    # ------------------------------------------------------------------
    # Comandos /backup
    # ------------------------------------------------------------------
    @backup_group.command(name="create", description="Crea una copia de seguridad de canales y roles del servidor")
    @checks.is_admin()
    async def backup_create(self, interaction: discord.Interaction, etiqueta: str = "Backup manual"):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        data = _build_snapshot(guild)
        backup_id = await db.save_backup(guild.id, etiqueta, data)
        await interaction.followup.send(embed=embeds.success(
            "Backup creado", f"ID: `{backup_id}` — {len(data['roles'])} roles, {len(data['channels'])} canales, {len(data['categories'])} categorías."
        ))

    @backup_group.command(name="list", description="Lista las copias de seguridad guardadas de este servidor")
    @checks.is_admin()
    async def backup_list(self, interaction: discord.Interaction):
        backups = await db.list_backups(interaction.guild.id)
        if not backups:
            return await interaction.response.send_message(embed=embeds.info("Sin backups guardados", "Usa /backup create para crear el primero."), ephemeral=True)
        desc = "\n".join(f"`#{bid}` — {label} — <t:{ts}:R>" for bid, label, ts in backups)
        await interaction.response.send_message(embed=embeds.info("📦 Copias de seguridad", desc), ephemeral=True)

    @backup_group.command(name="restore", description="Recrea los canales/roles que falten según una copia de seguridad")
    @checks.is_admin()
    async def backup_restore(self, interaction: discord.Interaction, backup_id: int):
        await interaction.response.defer()
        data = await db.get_backup(backup_id, interaction.guild.id)
        if not data:
            return await interaction.followup.send(embed=embeds.error("Backup no encontrado", f"No existe el backup `#{backup_id}` en este servidor."))

        guild = interaction.guild
        created_roles, created_categories, created_channels = await _restore_snapshot(
            guild, data, reason=f"Restauración de backup #{backup_id} por {interaction.user}"
        )

        await db.log_incident(guild.id, "backup_restore", interaction.user.id, f"Backup #{backup_id}", f"{created_roles} roles, {created_categories} categorías, {created_channels} canales recreados")
        await interaction.followup.send(embed=embeds.success(
            "Restauración completada",
            f"{created_roles} rol(es), {created_categories} categoría(s) y {created_channels} canal(es) recreados.\n"
            f"Solo se crea lo que faltaba — no se ha borrado ni modificado nada existente.",
        ))

    @backup_group.command(name="delete", description="Elimina una copia de seguridad guardada")
    @checks.is_admin()
    async def backup_delete(self, interaction: discord.Interaction, backup_id: int):
        ok = await db.delete_backup(backup_id, interaction.guild.id)
        if ok:
            await interaction.response.send_message(embed=embeds.success("Backup eliminado", f"`#{backup_id}`"), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds.error("Backup no encontrado"), ephemeral=True)

    @backup_group.command(name="auto-status", description="Muestra el estado de la copia de seguridad automática (autoheal de Anti-Nuke)")
    @checks.is_admin()
    async def backup_auto_status(self, interaction: discord.Interaction):
        result = await db.get_auto_backup(interaction.guild.id)
        autoheal_on = await db.get_bool(interaction.guild.id, "antinuke_autoheal", True)
        embed = embeds.info("🤖 Copia de seguridad automática")
        embed.add_field(name="Auto-restauración tras Anti-Nuke", value="Activada ✅" if autoheal_on else "Desactivada ❌ (`/antinuke autoheal`)", inline=False)
        if result:
            data, created_at = result
            embed.add_field(name="Última copia automática", value=f"<t:{created_at}:R> — {len(data['roles'])} roles, {len(data['channels'])} canales", inline=False)
        else:
            embed.add_field(name="Última copia automática", value="Todavía no se ha generado ninguna (se crea sola en la próxima hora).", inline=False)
        embed.add_field(name="Frecuencia", value=f"Cada {config.DEFAULT_AUTOBACKUP_INTERVAL_HOURS}h, se sobreescribe sola (solo se guarda 1)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @backup_group.command(name="auto-now", description="Fuerza ya una copia de seguridad automática de este servidor")
    @checks.is_admin()
    async def backup_auto_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = _build_snapshot(interaction.guild)
        await db.save_auto_backup(interaction.guild.id, data)
        await interaction.followup.send(embed=embeds.success(
            "Copia automática actualizada", f"{len(data['roles'])} roles, {len(data['channels'])} canales, {len(data['categories'])} categorías."
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
