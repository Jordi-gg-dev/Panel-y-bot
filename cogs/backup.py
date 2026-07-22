"""
AstroCube Anti-Raid - Módulo de Backups.

Guarda una foto de los roles y canales del servidor y permite restaurar lo
que falte tras un ataque. La restauración es siempre ADITIVA: nunca borra
nada, solo recrea lo que ya no existe.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils import embeds, checks


class Backup(commands.Cog):
    """Copias de seguridad de AstroCube Anti-Raid."""

    backup_group = app_commands.Group(
        name="backup", description="Copias de seguridad de canales y roles",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @backup_group.command(name="create", description="Crea una copia de seguridad de canales y roles del servidor")
    @checks.is_admin()
    async def backup_create(self, interaction: discord.Interaction, etiqueta: str = "Backup manual"):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        data = {
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
        created_roles = created_channels = created_categories = 0

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
                    reason=f"Restauración de backup #{backup_id} por {interaction.user}",
                )
                created_roles += 1
            except discord.HTTPException:
                pass

        category_map = {c.name: c for c in guild.categories}
        for cat_data in data.get("categories", []):
            if cat_data["name"] in category_map:
                continue
            try:
                new_cat = await guild.create_category(cat_data["name"], reason=f"Restauración de backup #{backup_id}")
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
                    await guild.create_voice_channel(ch_data["name"], category=category, reason=f"Restauración de backup #{backup_id}")
                else:
                    await guild.create_text_channel(
                        ch_data["name"], category=category, topic=ch_data.get("topic"),
                        nsfw=ch_data.get("nsfw", False), reason=f"Restauración de backup #{backup_id}",
                    )
                created_channels += 1
            except discord.HTTPException:
                pass

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
