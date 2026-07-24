"""
AstroCube Anti-Raid - Moderación de Chat y AutoMod Avanzado.

Dos grupos de protecciones independientes de Anti-Nuke/Anti-Raid/Anti-Spam:

Moderación de Chat (siempre disponibles, gratis):
- Filtro de Palabras: borra mensajes que contengan alguna palabra prohibida
  configurada por el servidor.
- Anti-Ghostping: avisa cuando alguien menciona a otra persona y borra el
  mensaje enseguida (para que la mención "fantasma" no quede impune).

AutoMod Avanzado (gratis, con un interruptor general "AutoMod Base" que
activa/desactiva TODO este bloque de golpe, además de sus interruptores
individuales):
- Anti-Links: borra enlaces que no estén en la lista de dominios permitidos.
- Anti-Tokens: borra mensajes que contengan lo que parece un token de Discord
  filtrado (protege la cuenta de quien lo escribió, sea quien sea).
- Anti-Malware: borra mensajes con adjuntos de extensiones peligrosas
  (ejecutables, scripts).
- Anti-Webhook: corta ráfagas de mensajes enviados a través de un webhook.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, checks

TOKEN_RE = re.compile(config.ANTITOKEN_REGEX)
URL_RE = re.compile(r"https?://\S+")


class AutoMod(commands.Cog):
    """Moderación de Chat + AutoMod Avanzado de AstroCube Anti-Raid."""

    automod_group = app_commands.Group(
        name="automod", description="Interruptor general y submódulos avanzados (enlaces, tokens, malware, webhooks)",
        default_permissions=discord.Permissions(administrator=True),
    )
    filtro_group = app_commands.Group(
        name="filtro-palabras", description="Borra automáticamente mensajes con palabras prohibidas",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._webhook_hits: dict[tuple, list[float]] = {}

    # ------------------------------------------------------------------
    # Mensajes
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        guild_id = message.guild.id

        if message.webhook_id is not None:
            if await db.get_bool(guild_id, "automod_base_enabled", True) and await db.get_bool(guild_id, "antiwebhook_enabled", True):
                await self._check_antiwebhook(message)
            return

        if message.author.bot:
            return

        is_admin = isinstance(message.author, discord.Member) and await checks.is_server_admin(message.author)

        if not is_admin and await db.get_bool(guild_id, "filtro_palabras_enabled", True):
            if await self._check_banned_words(message):
                return

        if await db.get_bool(guild_id, "automod_base_enabled", True):
            if await db.get_bool(guild_id, "antitokens_enabled", True):
                if await self._check_antitokens(message):
                    return
            if not is_admin and await db.get_bool(guild_id, "antilinks_enabled", False):
                if await self._check_antilinks(message):
                    return
            if not is_admin and await db.get_bool(guild_id, "antimalware_enabled", True):
                if await self._check_antimalware(message):
                    return

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author is None or message.author.bot:
            return
        if not message.mentions and not message.role_mentions:
            return
        guild_id = message.guild.id
        if not await db.get_bool(guild_id, "antighostping_enabled", True):
            return
        if message.created_at is None:
            return
        age = (discord.utils.utcnow() - message.created_at).total_seconds()
        if age > 30:
            return  # llevaba tiempo publicado: no es un "ghost ping"

        mentioned = ", ".join(m.mention for m in message.mentions) or ", ".join(r.mention for r in message.role_mentions)
        embed = embeds.warning("👻 Ghost ping detectado", f"{message.author.mention} mencionó a {mentioned} y borró el mensaje {int(age)}s después.")
        if message.content:
            embed.add_field(name="Contenido borrado", value=message.content[:1000], inline=False)
        try:
            await message.channel.send(embed=embed)
        except discord.HTTPException:
            pass
        await db.log_incident(guild_id, "ghost_ping", message.author.id, f"Ghost ping a {mentioned}", "aviso publicado en el canal")

    # ------------------------------------------------------------------
    # Detectores (cada uno devuelve True si actuó/borró el mensaje)
    # ------------------------------------------------------------------
    async def _check_banned_words(self, message: discord.Message) -> bool:
        words = await db.banned_word_list(message.guild.id)
        if not words:
            return False
        content_lower = (message.content or "").lower()
        for word in words:
            if word in content_lower:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                await db.log_incident(message.guild.id, "banned_word", message.author.id, f"Mensaje con palabra prohibida ('{word}')", "mensaje borrado")
                try:
                    await message.channel.send(f"{message.author.mention} tu mensaje se ha borrado por contener una palabra no permitida.", delete_after=6)
                except discord.HTTPException:
                    pass
                return True
        return False

    async def _check_antitokens(self, message: discord.Message) -> bool:
        if not TOKEN_RE.search(message.content or ""):
            return False
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await db.log_incident(message.guild.id, "leaked_token", message.author.id, "Posible token de Discord filtrado en un mensaje", "mensaje borrado")
        try:
            await message.channel.send(
                f"⚠️ {message.author.mention} tu mensaje contenía lo que parece un **token de Discord** — lo he borrado "
                "por tu seguridad. Si es real, revócalo YA en tus ajustes de desarrollador.",
                delete_after=15,
            )
        except discord.HTTPException:
            pass
        return True

    async def _check_antilinks(self, message: discord.Message) -> bool:
        urls = URL_RE.findall(message.content or "")
        if not urls:
            return False
        whitelist = await self._get_link_whitelist(message.guild.id)
        for url in urls:
            domain = urlparse(url).netloc.lower()
            if any(domain == d or domain.endswith("." + d) for d in whitelist):
                continue
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await db.log_incident(message.guild.id, "unauthorized_link", message.author.id, f"Enlace no permitido: {domain}", "mensaje borrado")
            try:
                await message.channel.send(f"{message.author.mention} no está permitido publicar enlaces aquí.", delete_after=6)
            except discord.HTTPException:
                pass
            return True
        return False

    async def _check_antimalware(self, message: discord.Message) -> bool:
        if not message.attachments:
            return False
        extensions = await self._get_dangerous_extensions(message.guild.id)
        for att in message.attachments:
            name = att.filename.lower()
            if any(name.endswith(ext) for ext in extensions):
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                await db.log_incident(message.guild.id, "malware_attachment", message.author.id, f"Adjunto peligroso: {att.filename}", "mensaje borrado")
                try:
                    await message.channel.send(f"🛡️ {message.author.mention} tu adjunto `{att.filename}` se ha bloqueado por ser un tipo de archivo potencialmente peligroso.", delete_after=8)
                except discord.HTTPException:
                    pass
                return True
        return False

    async def _check_antiwebhook(self, message: discord.Message):
        guild_id = message.guild.id
        key = (guild_id, message.channel.id, message.webhook_id)
        count_threshold, window = await db.get_int_pair(guild_id, "antiwebhook_threshold", config.DEFAULT_ANTIWEBHOOK_MESSAGE_THRESHOLD)
        now = time.time()
        hits = [t for t in self._webhook_hits.get(key, []) if now - t < window]
        hits.append(now)
        self._webhook_hits[key] = hits
        if len(hits) < count_threshold:
            return
        self._webhook_hits[key] = []
        try:
            await message.channel.purge(limit=20, check=lambda m: m.webhook_id == message.webhook_id)
        except discord.HTTPException:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        await db.log_incident(guild_id, "webhook_spam", None, f"Flood de mensajes vía webhook en #{message.channel.name}", f"{len(hits)}+ mensajes borrados")

    # ------------------------------------------------------------------
    # Helpers de configuración (listas guardadas como JSON en guild_config)
    # ------------------------------------------------------------------
    async def _get_link_whitelist(self, guild_id: int) -> list[str]:
        raw = await db.get_config(guild_id, "antilinks_whitelist_domains", "[]")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    async def _set_link_whitelist(self, guild_id: int, domains: list[str]):
        await db.set_config(guild_id, "antilinks_whitelist_domains", json.dumps(domains))

    async def _get_dangerous_extensions(self, guild_id: int) -> set[str]:
        raw = await db.get_config(guild_id, "antimalware_extensions")
        if not raw:
            return config.DEFAULT_DANGEROUS_EXTENSIONS
        try:
            return set(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            return config.DEFAULT_DANGEROUS_EXTENSIONS

    # ------------------------------------------------------------------
    # /filtro-palabras
    # ------------------------------------------------------------------
    @filtro_group.command(name="toggle", description="Activa/desactiva el filtro de palabras")
    @checks.is_admin()
    async def filtro_toggle(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "filtro_palabras_enabled", True)
        await db.set_config(interaction.guild.id, "filtro_palabras_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Filtro de palabras {estado}"))

    @filtro_group.command(name="add", description="Añade una palabra prohibida")
    @checks.is_admin()
    async def filtro_add(self, interaction: discord.Interaction, palabra: str):
        await db.banned_word_add(interaction.guild.id, palabra)
        await interaction.response.send_message(embed=embeds.success("Palabra añadida", f"`{palabra.lower().strip()}`"), ephemeral=True)

    @filtro_group.command(name="remove", description="Quita una palabra prohibida")
    @checks.is_admin()
    async def filtro_remove(self, interaction: discord.Interaction, palabra: str):
        await db.banned_word_remove(interaction.guild.id, palabra)
        await interaction.response.send_message(embed=embeds.success("Palabra quitada", f"`{palabra.lower().strip()}`"), ephemeral=True)

    @filtro_group.command(name="list", description="Lista las palabras prohibidas configuradas")
    @checks.is_admin()
    async def filtro_list(self, interaction: discord.Interaction):
        words = await db.banned_word_list(interaction.guild.id)
        if not words:
            return await interaction.response.send_message(embed=embeds.info("Sin palabras prohibidas configuradas"), ephemeral=True)
        await interaction.response.send_message(embed=embeds.info("🚫 Palabras prohibidas", ", ".join(f"`{w}`" for w in words)), ephemeral=True)

    # ------------------------------------------------------------------
    # /antighostping (independiente, en "Moderación de Chat")
    # ------------------------------------------------------------------
    @app_commands.command(name="antighostping", description="Activa/desactiva el aviso de menciones borradas (ghost ping)")
    @checks.is_admin()
    async def antighostping_toggle(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antighostping_enabled", True)
        await db.set_config(interaction.guild.id, "antighostping_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-Ghostping {estado}"))

    # ------------------------------------------------------------------
    # /automod (AutoMod Avanzado)
    # ------------------------------------------------------------------
    @automod_group.command(name="base", description="Interruptor general: activa/desactiva TODO el AutoMod Avanzado de golpe")
    @checks.is_admin()
    async def automod_base(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "automod_base_enabled", True)
        await db.set_config(interaction.guild.id, "automod_base_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(
            f"AutoMod Avanzado {estado}",
            "Esto apaga Anti-Links, Anti-Tokens, Anti-Malware y Anti-Webhook a la vez, aunque estén activados individualmente."
            if current else "Ahora se aplican Anti-Links, Anti-Tokens, Anti-Malware y Anti-Webhook según sus interruptores individuales.",
        ))

    @automod_group.command(name="antilinks", description="Activa/desactiva el bloqueo de enlaces no autorizados")
    @checks.is_admin()
    async def automod_antilinks(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antilinks_enabled", False)
        await db.set_config(interaction.guild.id, "antilinks_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-Links {estado}"))

    @automod_group.command(name="antilinks-whitelist-add", description="Permite un dominio (ej: youtube.com) aunque Anti-Links esté activo")
    @checks.is_admin()
    async def automod_antilinks_whitelist_add(self, interaction: discord.Interaction, dominio: str):
        dominio = dominio.lower().strip()
        if dominio.startswith("www."):
            dominio = dominio[4:]
        whitelist = await self._get_link_whitelist(interaction.guild.id)
        if dominio not in whitelist:
            whitelist.append(dominio)
            await self._set_link_whitelist(interaction.guild.id, whitelist)
        await interaction.response.send_message(embed=embeds.success("Dominio permitido", f"`{dominio}`"), ephemeral=True)

    @automod_group.command(name="antilinks-whitelist-remove", description="Quita un dominio de la lista de permitidos de Anti-Links")
    @checks.is_admin()
    async def automod_antilinks_whitelist_remove(self, interaction: discord.Interaction, dominio: str):
        dominio = dominio.lower().strip()
        if dominio.startswith("www."):
            dominio = dominio[4:]
        whitelist = await self._get_link_whitelist(interaction.guild.id)
        whitelist = [d for d in whitelist if d != dominio]
        await self._set_link_whitelist(interaction.guild.id, whitelist)
        await interaction.response.send_message(embed=embeds.success("Dominio quitado", f"`{dominio}`"), ephemeral=True)

    @automod_group.command(name="antitokens", description="Activa/desactiva el borrado de tokens de Discord filtrados")
    @checks.is_admin()
    async def automod_antitokens(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antitokens_enabled", True)
        await db.set_config(interaction.guild.id, "antitokens_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-Tokens {estado}"))

    @automod_group.command(name="antimalware", description="Activa/desactiva el bloqueo de adjuntos peligrosos")
    @checks.is_admin()
    async def automod_antimalware(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antimalware_enabled", True)
        await db.set_config(interaction.guild.id, "antimalware_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-Malware {estado}"))

    @automod_group.command(name="antiwebhook", description="Activa/desactiva la protección contra flood de webhooks")
    @checks.is_admin()
    async def automod_antiwebhook(self, interaction: discord.Interaction):
        current = await db.get_bool(interaction.guild.id, "antiwebhook_enabled", True)
        await db.set_config(interaction.guild.id, "antiwebhook_enabled", "0" if current else "1")
        estado = "desactivado ❌" if current else "activado ✅"
        await interaction.response.send_message(embed=embeds.success(f"Anti-Webhook {estado}"))

    @automod_group.command(name="status", description="Muestra el estado de todos los submódulos de AutoMod")
    @checks.is_admin()
    async def automod_status(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        embed = embeds.info("🤖 Estado de AutoMod Avanzado")
        embed.add_field(name="AutoMod Base", value="✅" if await db.get_bool(guild_id, "automod_base_enabled", True) else "❌", inline=True)
        embed.add_field(name="Anti-Links", value="✅" if await db.get_bool(guild_id, "antilinks_enabled", False) else "❌", inline=True)
        embed.add_field(name="Anti-Tokens", value="✅" if await db.get_bool(guild_id, "antitokens_enabled", True) else "❌", inline=True)
        embed.add_field(name="Anti-Malware", value="✅" if await db.get_bool(guild_id, "antimalware_enabled", True) else "❌", inline=True)
        embed.add_field(name="Anti-Webhook", value="✅" if await db.get_bool(guild_id, "antiwebhook_enabled", True) else "❌", inline=True)
        whitelist = await self._get_link_whitelist(guild_id)
        embed.add_field(name="Dominios permitidos", value=(", ".join(whitelist) if whitelist else "Ninguno"), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
