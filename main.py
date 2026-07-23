"""
AstroCube Anti-Raid 🛡️
Bot defensivo multi-servidor: anti-nuke, anti-spam, anti-raid, lockdown y
backups. Pensado para poder añadirse a cualquier servidor de Discord.

Punto de entrada del bot. Carga la configuración, la base de datos y todos
los cogs (módulos de comandos) automáticamente desde la carpeta /cogs.
"""

import os
import time
import asyncio
import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("antiraid")


class AntiRaidTree(app_commands.CommandTree):
    """CommandTree personalizado: bloquea servidores/usuarios en la blacklist
    global y el modo mantenimiento, y centraliza el manejo de errores."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            await db.log_command_use(
                interaction.guild.id if interaction.guild else None,
                interaction.guild.name if interaction.guild else "DM",
                interaction.user.id,
                str(interaction.user),
                getattr(interaction.command, "qualified_name", "?"),
            )
        except Exception:
            log.exception("No se pudo registrar el uso del comando en command_log")

        if await checks.is_owner(interaction.user.id):
            return True

        if await db.is_user_blacklisted(interaction.user.id):
            await interaction.response.send_message(
                embed=embeds.error("Acceso bloqueado", "No tienes permiso para usar este bot."),
                ephemeral=True,
            )
            return False

        if interaction.guild and await db.is_guild_blacklisted(interaction.guild.id):
            await interaction.response.send_message(
                embed=embeds.error("Servidor bloqueado", "Este servidor no puede usar el bot."),
                ephemeral=True,
            )
            return False

        if getattr(self.client, "maintenance", False):
            await interaction.response.send_message(
                embed=embeds.warning("Mantenimiento", f"{config.BOT_NAME} está en mantenimiento. Inténtalo más tarde."),
                ephemeral=True,
            )
            return False

        return True

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # discord.py envuelve la excepción real de un comando dentro de
        # CommandInvokeError (error.original). Sin desenvolverla aquí, un
        # discord.Forbidden (bot sin permisos en ese canal/servidor) nunca
        # coincidía con el "isinstance(error, discord.Forbidden)" de abajo
        # y siempre caía en el mensaje genérico "Ha ocurrido un error", sin
        # decir la causa real. Desenvolvemos antes de comprobar el tipo.
        original = getattr(error, "original", error)

        if isinstance(error, (checks.NotAdmin, checks.NotOwner)):
            embed = embeds.error("Permiso denegado", str(error) or "No tienes permisos para usar este comando.")
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed = embeds.warning("Espera un momento", f"Cooldown activo. Inténtalo en {error.retry_after:.1f}s.")
        elif isinstance(original, discord.Forbidden):
            embed = embeds.error(
                "Permisos insuficientes",
                "El bot no tiene permisos suficientes para hacer esto AQUÍ. Revisa: 1) que el rol del bot tenga "
                "'Ver canal' y 'Enviar mensajes' en este canal/categoría (a veces un canal tiene permisos "
                "personalizados que se lo bloquean), y 2) que el rol del bot esté correctamente colocado en la "
                "lista de roles del servidor.",
            )
        else:
            log.error("Error en comando %s: %s", getattr(interaction.command, "qualified_name", "?"), original)
            traceback.print_exception(type(original), original, original.__traceback__)
            embed = embeds.error("Ha ocurrido un error", "El error fue registrado. Inténtalo de nuevo más tarde.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.moderation = True

bot = commands.Bot(command_prefix="antiraid!", intents=intents, tree_cls=AntiRaidTree, help_command=None)
bot.maintenance = False


async def _auto_grant_owner_premium(guild: discord.Guild):
    """Si el propietario real de este servidor de Discord es uno de los
    dueños del bot (OWNER_IDS), le concede Premium automáticamente y de
    forma permanente la PRIMERA vez que se ve ese servidor (igual que si se
    lo regalara desde el panel), sin ningún paso manual.

    Importante: solo actúa si el servidor no tiene NINGÚN registro de Premium
    todavía (ni activo ni cancelado). Así, si el propio dueño decide quitarse
    el Premium manualmente para probar cómo se ve el bot sin él, esa decisión
    se respeta y no se le vuelve a conceder solo porque el bot se reinicie."""
    if not (guild.owner_id and guild.owner_id in config.OWNER_IDS):
        return
    existing = await db.get_premium(guild.id)
    if existing is None:
        await db.upsert_premium(guild.id, "active")
        log.info("Premium automático concedido a %s (%s): su propietario es el dueño del bot", guild.name, guild.id)


@bot.event
async def on_ready():
    log.info("Conectado como %s (ID: %s)", bot.user, bot.user.id)
    log.info("Sirviendo en %d servidor(es)", len(bot.guilds))

    try:
        if config.DEV_GUILD_ID:
            guild_obj = discord.Object(id=config.DEV_GUILD_ID)
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
            log.info("Sincronizados %d comandos en el servidor de pruebas %s", len(synced), config.DEV_GUILD_ID)
        else:
            synced = await bot.tree.sync()
            log.info("Sincronizados %d comandos globalmente (puede tardar hasta 1h en propagarse)", len(synced))
    except discord.HTTPException as exc:
        log.error("Error al sincronizar comandos: %s", exc)

    for guild in bot.guilds:
        try:
            await _auto_grant_owner_premium(guild)
        except Exception:
            log.exception("Error comprobando Premium automático en %s", guild.id)

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servidor(es) | /help")
    )


@bot.event
async def on_guild_join(guild: discord.Guild):
    if await db.is_guild_blacklisted(guild.id):
        log.warning("Servidor %s (%s) está en la blacklist, abandonando.", guild.name, guild.id)
        await guild.leave()
        return

    try:
        await _auto_grant_owner_premium(guild)
    except Exception:
        log.exception("Error comprobando Premium automático en %s", guild.id)

    log.info("Añadido a nuevo servidor: %s (%s) — %d miembros", guild.name, guild.id, guild.member_count)

    embed = embeds.info(
        f"🛡️ ¡Gracias por añadir {config.BOT_NAME}!",
        "Soy un bot de protección: anti-nuke, anti-spam, anti-raid, bloqueo de emergencia y backups.\n\n"
        "**Primeros pasos recomendados:**\n"
        "1. `/antinuke logchannel` — canal donde avisaré de intentos de nuke.\n"
        "2. `/antinuke whitelist-add` — añade a tus admins/bots de confianza para que nunca sean castigados por error.\n"
        "3. `/antiraid logchannel` — canal donde avisaré de oleadas de entrada.\n"
        "4. `/backup create` — guarda una copia de tus canales y roles ahora, antes de que la necesites.\n"
        "5. `/help` — lista completa de comandos.",
    )

    target = guild.system_channel
    if target is None or not target.permissions_for(guild.me).send_messages:
        target = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)

    if target:
        try:
            await target.send(embed=embed)
        except discord.HTTPException:
            pass

    try:
        owner = guild.owner or await bot.fetch_user(guild.owner_id)
        await owner.send(embed=embed)
    except discord.HTTPException:
        pass


async def load_cogs():
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    for filename in sorted(os.listdir(cogs_dir)):
        if filename.endswith(".py") and not filename.startswith("_"):
            extension = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(extension)
                log.info("Cog cargado: %s", extension)
            except commands.ExtensionError:
                log.exception("Error al cargar el cog: %s", extension)


async def main():
    if not config.TOKEN:
        raise SystemExit(
            "❌ No se encontró DISCORD_TOKEN. Copia .env.example a .env y añade el token de tu bot."
        )

    bot.start_time = time.time()
    await db.init()
    await load_cogs()

    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
