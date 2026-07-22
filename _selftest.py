"""
Script de autoverificación (no se conecta a Discord). Carga todos los cogs,
cuenta comandos slash y comprueba que no haya nombres duplicados.
No forma parte del bot: puedes borrarlo.
"""

import os
import asyncio

os.environ.setdefault("DISCORD_TOKEN", "fake-token-for-selftest")

import discord
from discord.ext import commands
from discord import app_commands


async def main():
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.moderation = True

    bot = commands.Bot(command_prefix="antiraid!", intents=intents, help_command=None)
    bot.maintenance = False
    bot.start_time = 0

    import database as db
    await db.init()

    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    loaded = []
    for filename in sorted(os.listdir(cogs_dir)):
        if filename.endswith(".py") and not filename.startswith("_"):
            ext = f"cogs.{filename[:-3]}"
            await bot.load_extension(ext)
            loaded.append(ext)

    print(f"Cogs cargados: {loaded}")

    subcommands = 0
    names = set()
    for cmd in bot.tree.walk_commands():
        if isinstance(cmd, app_commands.Group):
            continue
        subcommands += 1
        names.add(cmd.qualified_name)

    print(f"Comandos/grupos de nivel superior: {len(bot.tree.get_commands())}")
    print(f"Total de comandos ejecutables: {subcommands}")
    print("✅ Sin nombres duplicados" if len(names) == subcommands else "⚠️ HAY NOMBRES DUPLICADOS")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
