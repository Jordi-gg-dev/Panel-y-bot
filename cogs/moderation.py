"""
AstroCube Anti-Raid - Comandos de moderación básica para responder a un
ataque en curso (banear/expulsar raiders, purgar spam, poner en cuarentena).
"""

from __future__ import annotations

import re
import datetime

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils import embeds, checks


DURATION_RE = re.compile(r"^(\d+)([smhd])$")


def parse_duration(text: str) -> datetime.timedelta | None:
    match = DURATION_RE.match(text.strip().lower())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return datetime.timedelta(seconds=amount * seconds)


class Moderation(commands.Cog):
    """Moderación básica de AstroCube Anti-Raid."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ban", description="Banea a un usuario del servidor")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def ban(self, interaction: discord.Interaction, usuario: discord.User, razon: str = "Sin especificar"):
        await interaction.guild.ban(usuario, reason=f"{interaction.user}: {razon}")
        await db.log_incident(interaction.guild.id, "manual_ban", interaction.user.id, f"{usuario} — {razon}", "baneado")
        await interaction.response.send_message(embed=embeds.success("Usuario baneado", f"{usuario.mention} — {razon}"))

    @app_commands.command(name="unban", description="Desbanea a un usuario por su ID")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def unban(self, interaction: discord.Interaction, user_id: str, razon: str = "Sin especificar"):
        try:
            user = discord.Object(id=int(user_id))
        except ValueError:
            return await interaction.response.send_message(embed=embeds.error("ID inválido"), ephemeral=True)
        await interaction.guild.unban(user, reason=f"{interaction.user}: {razon}")
        await interaction.response.send_message(embed=embeds.success("Usuario desbaneado", f"ID `{user_id}`"))

    @app_commands.command(name="massban", description="Banea varios IDs de golpe (útil tras un raid)")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def massban(self, interaction: discord.Interaction, ids: str, razon: str = "Massban anti-raid"):
        raw_ids = [i.strip() for i in re.split(r"[,\s]+", ids) if i.strip().isdigit()]
        await interaction.response.defer()
        banned, failed = 0, 0
        for raw_id in raw_ids:
            try:
                await interaction.guild.ban(discord.Object(id=int(raw_id)), reason=f"{interaction.user}: {razon}")
                banned += 1
            except discord.HTTPException:
                failed += 1
        await db.log_incident(interaction.guild.id, "manual_massban", interaction.user.id, razon, f"{banned} baneados, {failed} fallidos")
        await interaction.followup.send(embed=embeds.success("Massban completado", f"Baneados: {banned} · Fallidos: {failed}"))

    @app_commands.command(name="kick", description="Expulsa a un usuario del servidor")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def kick(self, interaction: discord.Interaction, usuario: discord.Member, razon: str = "Sin especificar"):
        await usuario.kick(reason=f"{interaction.user}: {razon}")
        await interaction.response.send_message(embed=embeds.success("Usuario expulsado", f"{usuario.mention} — {razon}"))

    @app_commands.command(name="timeout", description="Silencia temporalmente a un usuario")
    @app_commands.describe(duracion="Ej: 10m, 1h, 1d")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def timeout(self, interaction: discord.Interaction, usuario: discord.Member, duracion: str, razon: str = "Sin especificar"):
        delta = parse_duration(duracion)
        if delta is None:
            return await interaction.response.send_message(embed=embeds.error("Duración inválida", "Usa formato como 10m, 2h, 1d."), ephemeral=True)
        await usuario.timeout(delta, reason=f"{interaction.user}: {razon}")
        await interaction.response.send_message(embed=embeds.success(f"Timeout aplicado ({duracion})", f"{usuario.mention} — {razon}"))

    @app_commands.command(name="untimeout", description="Quita el timeout a un usuario")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def untimeout(self, interaction: discord.Interaction, usuario: discord.Member):
        await usuario.timeout(None, reason=f"Removido por {interaction.user}")
        await interaction.response.send_message(embed=embeds.success("Timeout removido", usuario.mention))

    @app_commands.command(name="purge", description="Elimina mensajes recientes del canal")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def purge(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 1, 200]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=cantidad)
        await interaction.followup.send(embed=embeds.success("Mensajes eliminados", f"{len(deleted)} mensajes borrados."))

    @app_commands.command(name="quarantine", description="Aísla a un usuario sospechoso: le quita todos los roles")
    @app_commands.default_permissions(administrator=True)
    @checks.is_admin()
    async def quarantine(self, interaction: discord.Interaction, usuario: discord.Member, razon: str = "Cuenta sospechosa"):
        removable = [r for r in usuario.roles if r.name != "@everyone" and r < interaction.guild.me.top_role]
        if removable:
            await usuario.remove_roles(*removable, reason=f"Cuarentena por {interaction.user}: {razon}")
        await db.log_incident(interaction.guild.id, "manual_quarantine", interaction.user.id, f"{usuario} — {razon}", f"{len(removable)} roles retirados")
        await interaction.response.send_message(embed=embeds.warning("Usuario en cuarentena", f"{usuario.mention} — se retiraron {len(removable)} rol(es). Motivo: {razon}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
