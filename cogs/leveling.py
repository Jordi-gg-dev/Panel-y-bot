"""
AstroCube Anti-Raid - Sistema de Niveles (XP).

Cada mensaje (con un tiempo de espera entre mensajes, configurable) da una
cantidad aleatoria de XP al autor. Al subir de nivel se avisa en el canal
configurado (o el mismo canal del mensaje si no se configura ninguno).
"""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks

DEFAULT_XP_MIN = 15
DEFAULT_XP_MAX = 25
DEFAULT_COOLDOWN = 60


class Leveling(commands.Cog):
    """Sistema de XP y niveles de AstroCube Anti-Raid."""

    niveles_group = app_commands.Group(
        name="niveles", description="Configuracion del sistema de niveles (XP)",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        if not await db.get_bool(message.guild.id, "xp_enabled", True):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = int(time.time())

        cooldown = int(await db.get_config(guild_id, "xp_cooldown", DEFAULT_COOLDOWN))
        last = await db.get_last_message_at(guild_id, user_id)
        if now - last < cooldown:
            return

        xp_min = int(await db.get_config(guild_id, "xp_min", DEFAULT_XP_MIN))
        xp_max = int(await db.get_config(guild_id, "xp_max", DEFAULT_XP_MAX))
        amount = random.randint(min(xp_min, xp_max), max(xp_min, xp_max))

        # Multiplicador de XP: funcion Premium. Si el servidor no es premium,
        # se ignora cualquier valor guardado y se usa siempre x1.
        if await db.is_premium(guild_id):
            try:
                multiplier = float(await db.get_config(guild_id, "xp_multiplier", 1.0))
            except (TypeError, ValueError):
                multiplier = 1.0
            amount = max(1, int(amount * multiplier))

        old_level, new_level, new_xp = await db.add_xp(guild_id, user_id, str(message.author), amount, now)

        if new_level > old_level:
            channel_id = await db.get_config(guild_id, "xp_levelup_channel")
            channel = self.bot.get_channel(int(channel_id)) if channel_id else message.channel
            if channel is None:
                channel = message.channel
            embed = embeds.success(
                "¡Subida de nivel! 🎉",
                f"{message.author.mention} ha alcanzado el **nivel {new_level}** (con {new_xp} XP).",
            )
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

            # Rol de recompensa por nivel: funcion Premium.
            if await db.is_premium(guild_id):
                role_id = await db.get_level_role_reward(guild_id, new_level)
                if role_id:
                    role = message.guild.get_role(int(role_id))
                    if role and role not in message.author.roles:
                        try:
                            await message.author.add_roles(role, reason=f"Recompensa de nivel {new_level}")
                        except discord.Forbidden:
                            pass

    @niveles_group.command(name="activar", description="Activa o desactiva el sistema de niveles")
    @checks.is_admin()
    async def niveles_activar(self, interaction: discord.Interaction, activo: bool):
        await db.set_config(interaction.guild.id, "xp_enabled", "1" if activo else "0")
        await interaction.response.send_message(
            embed=embeds.success("Niveles actualizados", f"Sistema de niveles {'activado' if activo else 'desactivado'}."),
            ephemeral=True,
        )

    @niveles_group.command(name="canal-anuncio", description="Canal donde se anuncian las subidas de nivel")
    @checks.is_admin()
    async def niveles_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await db.set_config(interaction.guild.id, "xp_levelup_channel", canal.id)
        await interaction.response.send_message(
            embed=embeds.success("Canal actualizado", f"Las subidas de nivel se anunciaran en {canal.mention}."),
            ephemeral=True,
        )

    @niveles_group.command(name="multiplicador", description="[Premium] Configura un multiplicador de XP para este servidor")
    @checks.is_admin()
    async def niveles_multiplicador(self, interaction: discord.Interaction, valor: app_commands.Range[float, 0.1, 10.0]):
        if not await db.is_premium(interaction.guild.id):
            await interaction.response.send_message(
                embed=embeds.warning("Funcion Premium", "El multiplicador de XP es una ventaja Premium. Actívalo desde el panel web (pestaña Premium)."),
                ephemeral=True,
            )
            return
        await db.set_config(interaction.guild.id, "xp_multiplier", valor)
        await interaction.response.send_message(
            embed=embeds.success("Multiplicador actualizado", f"Ahora se gana XP x**{valor}**."), ephemeral=True,
        )

    @niveles_group.command(name="color", description="[Premium] Personaliza el color de la tarjeta de /nivel")
    @app_commands.describe(color_hex="Color en formato hexadecimal, ej: FF5733")
    @checks.is_admin()
    async def niveles_color(self, interaction: discord.Interaction, color_hex: str):
        if not await db.is_premium(interaction.guild.id):
            await interaction.response.send_message(
                embed=embeds.warning("Funcion Premium", "El color personalizado es una ventaja Premium. Actívalo desde el panel web (pestaña Premium)."),
                ephemeral=True,
            )
            return
        color_hex = color_hex.strip().lstrip("#")
        try:
            int(color_hex, 16)
        except ValueError:
            await interaction.response.send_message(
                embed=embeds.error("Color invalido", "Usa un color hexadecimal valido, por ejemplo `FF5733`."), ephemeral=True,
            )
            return
        await db.set_config(interaction.guild.id, "rank_color", color_hex)
        await interaction.response.send_message(
            embed=discord.Embed(title="Color actualizado", description="Este sera el color de tu tarjeta de nivel a partir de ahora.", color=int(color_hex, 16)),
            ephemeral=True,
        )

    @niveles_group.command(name="rol-nivel", description="[Premium] Asigna un rol automatico al alcanzar un nivel")
    @checks.is_admin()
    async def niveles_rol_nivel(self, interaction: discord.Interaction, nivel: int, rol: discord.Role):
        if not await db.is_premium(interaction.guild.id):
            await interaction.response.send_message(
                embed=embeds.warning("Funcion Premium", "Los roles de recompensa por nivel son una ventaja Premium. Actívalo desde el panel web (pestaña Premium)."),
                ephemeral=True,
            )
            return
        await db.set_level_role_reward(interaction.guild.id, nivel, rol.id)
        await interaction.response.send_message(
            embed=embeds.success("Recompensa configurada", f"Quien alcance el **nivel {nivel}** recibira el rol {rol.mention} automaticamente."),
            ephemeral=True,
        )

    @niveles_group.command(name="quitar-rol-nivel", description="Elimina la recompensa de rol configurada para un nivel")
    @checks.is_admin()
    async def niveles_quitar_rol_nivel(self, interaction: discord.Interaction, nivel: int):
        await db.remove_level_role_reward(interaction.guild.id, nivel)
        await interaction.response.send_message(
            embed=embeds.success("Recompensa eliminada", f"Ya no hay ningun rol asociado al nivel {nivel}."), ephemeral=True,
        )

    @niveles_group.command(name="lista-roles-nivel", description="Muestra los roles de recompensa configurados")
    async def niveles_lista_roles(self, interaction: discord.Interaction):
        rewards = await db.list_level_role_rewards(interaction.guild.id)
        if not rewards:
            await interaction.response.send_message(embed=embeds.info("Roles por nivel", "No hay ninguno configurado."), ephemeral=True)
            return
        lineas = [f"**Nivel {level}** → <@&{role_id}>" for level, role_id in rewards]
        await interaction.response.send_message(embed=embeds.info("Roles por nivel", "\n".join(lineas)), ephemeral=True)

    @app_commands.command(name="nivel", description="Muestra tu nivel y XP (o el de otro miembro)")
    @app_commands.describe(miembro="Miembro a consultar (por defecto, tu)")
    async def nivel(self, interaction: discord.Interaction, miembro: discord.Member = None):
        miembro = miembro or interaction.user
        row = await db.get_user_level(interaction.guild.id, miembro.id)
        xp, level = (row[0], row[1]) if row else (0, 0)
        embed = embeds.info(f"Nivel de {miembro.display_name}", f"**Nivel:** {level}\n**XP:** {xp}")
        if await db.is_premium(interaction.guild.id):
            rank_color = await db.get_config(interaction.guild.id, "rank_color")
            if rank_color:
                try:
                    embed.color = discord.Color(int(rank_color, 16))
                except ValueError:
                    pass
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clasificacion", description="Muestra el top de niveles del servidor")
    async def clasificacion(self, interaction: discord.Interaction):
        top = await db.leaderboard(interaction.guild.id, 10)
        if not top:
            await interaction.response.send_message(
                embed=embeds.info("Clasificación", "Todavía no hay nadie con XP en este servidor."),
                ephemeral=True,
            )
            return
        lineas = []
        medallas = ["🥇", "🥈", "🥉"]
        for i, (user_id, username, xp, level) in enumerate(top):
            medalla = medallas[i] if i < 3 else f"{i + 1}."
            lineas.append(f"{medalla} **{username}** — nivel {level} ({xp} XP)")
        embed = embeds.info("🏆 Clasificación del servidor", "\n".join(lineas))
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
