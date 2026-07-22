"""
AstroCube Anti-Raid - Comandos personalizados (funcion Premium).

Los servidores con suscripcion Premium activa pueden crear "comandos"
tipo trigger -> respuesta desde el panel web. Este cog escucha los mensajes
y responde cuando alguien escribe exactamente el prefijo configurado
seguido del trigger (por ejemplo: "!bienvenida").

No usa slash commands para no gastar el limite de comandos de aplicacion
del bot ni pedir otra sincronizacion; es prefijo simple sobre el propio
mensaje de texto.
"""

import discord
from discord.ext import commands

import database as db

PREFIX = "!"


class CustomCommands(commands.Cog):
    """Responde a los comandos personalizados definidos por servidores Premium."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.content.startswith(PREFIX):
            return

        if not await db.is_premium(message.guild.id):
            return

        trigger = message.content[len(PREFIX):].strip().lower()
        if not trigger:
            return

        comandos = await db.list_enabled_custom_commands(message.guild.id)
        for trigger_text, response in comandos:
            if trigger_text == trigger:
                try:
                    await message.channel.send(response)
                except discord.Forbidden:
                    pass
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommands(bot))
