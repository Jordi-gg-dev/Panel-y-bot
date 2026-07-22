"""
AstroCube Anti-Raid - Mensajes privados (modmail).

Cuando alguien le escribe un mensaje directo (DM) al bot, se guarda en la
base de datos compartida con el panel web para que el propietario (o
cualquier moderador del panel al que se le haya dado acceso) pueda verlo y
responder directamente desde ahí. La respuesta se envía por DM usando el
propio token del bot desde el panel, así que no hace falta que este cog
haga nada para las respuestas salientes: solo escucha los mensajes que
llegan.
"""

import discord
from discord.ext import commands

import database as db
from utils import embeds


class DMRelay(commands.Cog):
    """Reenvía los DMs recibidos por el bot al panel web (bandeja de mensajes)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Solo nos interesan los mensajes directos (sin servidor) de humanos.
        if message.guild is not None:
            return
        if message.author.bot:
            return

        content = message.content or "*(mensaje sin texto: puede que sea un adjunto o una imagen)*"
        avatar_url = None
        try:
            avatar_url = str(message.author.display_avatar.url)
        except Exception:
            pass

        await db.log_dm_message(message.author.id, str(message.author), avatar_url, "in", content)

        try:
            await message.channel.send(
                embed=embeds.info(
                    "📬 Mensaje recibido",
                    "Gracias por escribirnos. El equipo verá tu mensaje y te responderá por aquí mismo en cuanto pueda.",
                )
            )
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(DMRelay(bot))
