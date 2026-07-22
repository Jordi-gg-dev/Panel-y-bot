"""
AstroCube Anti-Raid - Sorteos (giveaways).

/sorteo crear -> publica un embed con un boton "Participar" (persistente).
Cada minuto se revisa si algun sorteo ha terminado y, si es asi, se sortea
entre los participantes registrados y se anuncian los ganadores.
"""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database as db
from utils import embeds, checks


def _format_ends_at(ends_at: int) -> str:
    return f"<t:{ends_at}:R>"


def _giveaway_embed(row) -> discord.Embed:
    _, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winners, created_at = row
    if ended:
        ganadores = winners.split(",") if winners else []
        desc = (
            f"🎉 **Sorteo terminado**\n\n"
            f"**Premio:** {prize}\n"
            f"**Ganador(es):** {', '.join(f'<@{w}>' for w in ganadores) if ganadores else 'Nadie participo'}"
        )
    else:
        desc = (
            f"**Premio:** {prize}\n"
            f"**Ganadores:** {winners_count}\n"
            f"**Termina:** {_format_ends_at(ends_at)}\n\n"
            f"Pulsa el boton para participar."
        )
    embed = discord.Embed(title="🎉 Sorteo", description=desc, color=config.COLOR_PRIMARY)
    return embed


class GiveawayJoinView(discord.ui.View):
    """Vista persistente del boton de participacion de un sorteo concreto."""

    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.participar.custom_id = f"astrocube:sorteo:{giveaway_id}"

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.success)
    async def participar(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await db.get_giveaway(self.giveaway_id)
        if row is None or row[8]:  # ended
            await interaction.response.send_message("Este sorteo ya ha terminado.", ephemeral=True)
            return
        nuevo = await db.add_giveaway_entry(self.giveaway_id, interaction.user.id)
        if nuevo:
            await interaction.response.send_message("✅ ¡Estas participando en el sorteo! Buena suerte.", ephemeral=True)
        else:
            await interaction.response.send_message("Ya estabas participando en este sorteo.", ephemeral=True)


class Sorteos(commands.Cog):
    """Sorteos (giveaways) de AstroCube Anti-Raid."""

    sorteo_group = app_commands.Group(
        name="sorteo", description="Crear y gestionar sorteos",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @sorteo_group.command(name="crear", description="Crea un nuevo sorteo en este canal")
    @app_commands.describe(premio="Que se sortea", duracion_minutos="Cuanto dura el sorteo", ganadores="Numero de ganadores")
    @checks.is_admin()
    async def sorteo_crear(self, interaction: discord.Interaction, premio: str, duracion_minutos: int, ganadores: int = 1):
        if not await db.is_premium(interaction.guild.id):
            activos = await db.count_active_giveaways(interaction.guild.id)
            if activos >= 1:
                await interaction.response.send_message(
                    embed=embeds.warning(
                        "Límite del plan gratuito",
                        "Los servidores gratuitos solo pueden tener **1 sorteo activo** a la vez. "
                        "Espera a que termine el actual, o hazte Premium desde el panel web para tener sorteos ilimitados.",
                    ),
                    ephemeral=True,
                )
                return
        ends_at = int(time.time()) + duracion_minutos * 60
        giveaway_id = await db.create_giveaway(
            interaction.guild.id, interaction.channel.id, premio, ganadores, interaction.user.id, ends_at
        )
        row = await db.get_giveaway(giveaway_id)
        view = GiveawayJoinView(giveaway_id)
        self.bot.add_view(view)
        msg = await interaction.channel.send(embed=_giveaway_embed(row), view=view)
        await db.set_giveaway_message_id(giveaway_id, msg.id)
        await interaction.response.send_message(f"Sorteo #{giveaway_id} creado.", ephemeral=True)

    @sorteo_group.command(name="terminar", description="Termina un sorteo antes de tiempo y sortea ya")
    @app_commands.describe(id="ID del sorteo")
    @checks.is_admin()
    async def sorteo_terminar(self, interaction: discord.Interaction, id: int):
        row = await db.get_giveaway(id)
        if row is None or row[1] != interaction.guild.id:
            await interaction.response.send_message("No existe ese sorteo en este servidor.", ephemeral=True)
            return
        if row[8]:
            await interaction.response.send_message("Ese sorteo ya habia terminado.", ephemeral=True)
            return
        await self._finalizar_sorteo(row)
        await interaction.response.send_message(f"Sorteo #{id} finalizado.", ephemeral=True)

    async def _finalizar_sorteo(self, row):
        giveaway_id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winners, created_at = row
        entries = await db.list_giveaway_entries(giveaway_id)
        ganadores = random.sample(entries, min(winners_count, len(entries))) if entries else []
        await db.finish_giveaway(giveaway_id, ganadores)

        channel = self.bot.get_channel(channel_id)
        updated_row = await db.get_giveaway(giveaway_id)
        if channel:
            try:
                if message_id:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=_giveaway_embed(updated_row), view=None)
                    except discord.NotFound:
                        pass
                if ganadores:
                    await channel.send(
                        f"🎉 ¡Felicidades {', '.join(f'<@{w}>' for w in ganadores)}! Habeis ganado **{prize}**."
                    )
                else:
                    await channel.send(f"El sorteo de **{prize}** ha terminado sin participantes.")
            except discord.Forbidden:
                pass

    @tasks.loop(seconds=60)
    async def check_giveaways(self):
        due = await db.list_due_giveaways()
        for row in due:
            await self._finalizar_sorteo(row)

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Sorteos(bot))
