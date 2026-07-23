"""
AstroCube Anti-Raid - Sistema de Tickets.

/ticket-panel (staff) publica un mensaje con DOS botones, uno por idioma
(Español / English). Quien pulsa uno crea su ticket en ese idioma: todos los
textos de ESE ticket (bienvenida, botón de cerrar, avisos) salen en el
idioma elegido, sin afectar al resto del servidor. /ticket-cerrar o el boton
de cerrar lo archivan.

Los mensajes que se escriben dentro de un canal de ticket se registran en la
base de datos (ticket_messages) para que el panel web pueda mostrar el hilo
completo de la conversación y permitir responder desde ahí.

Configuracion por servidor (guild_config generico):
- tickets_category_id: categoria donde se crean los canales de ticket
- tickets_staff_role_id: rol que puede ver y cerrar todos los tickets
"""

import io

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils import embeds, checks
from i18n import t


class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.cerrar.custom_id = f"astrocube:ticket:cerrar:{ticket_id}"

    @discord.ui.button(label="Cerrar ticket / Close ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _cerrar_ticket(interaction, self.ticket_id)


async def _abrir_ticket(interaction: discord.Interaction, language: str):
    guild = interaction.guild
    user = interaction.user

    existente = await db.get_open_ticket_for_user(guild.id, user.id)
    if existente:
        canal = guild.get_channel(existente[2]) if existente[2] else None
        if canal:
            await interaction.response.send_message(
                t(language, "ticket.already_open", channel=canal.mention), ephemeral=True
            )
            return

    await interaction.response.send_message(t(language, "ticket.creating"), ephemeral=True)

    category_id = await db.get_config(guild.id, "tickets_category_id")
    staff_role_id = await db.get_config(guild.id, "tickets_staff_role_id")
    category = guild.get_channel(int(category_id)) if category_id else None
    staff_role = guild.get_role(int(staff_role_id)) if staff_role_id else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    ticket_id = await db.create_ticket(guild.id, user.id, language=language)

    try:
        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}"[:90],
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            reason=f"Ticket abierto por {user}",
        )
    except discord.Forbidden:
        await interaction.followup.send(t(language, "ticket.no_channel_perms"), ephemeral=True)
        return

    await db.set_ticket_channel(ticket_id, channel.id)

    embed = embeds.info(
        t(language, "ticket.welcome.title", id=ticket_id),
        t(language, "ticket.welcome.description", mention=user.mention),
    )
    await channel.send(embed=embed, view=CloseTicketView(ticket_id))
    await interaction.followup.send(t(language, "ticket.created", channel=channel.mention), ephemeral=True)


class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir ticket", style=discord.ButtonStyle.success, emoji="🇪🇸",
        custom_id="astrocube:ticket:abrir:es",
    )
    async def abrir_es(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _abrir_ticket(interaction, "es")

    @discord.ui.button(
        label="Open ticket", style=discord.ButtonStyle.success, emoji="🇬🇧",
        custom_id="astrocube:ticket:abrir:en",
    )
    async def abrir_en(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _abrir_ticket(interaction, "en")


async def _generar_transcripcion(channel: discord.TextChannel, language: str) -> discord.File:
    """[Premium] Genera un .txt con el historial de mensajes del canal del ticket."""
    lineas = []
    async for msg in channel.history(limit=500, oldest_first=True):
        hora = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        contenido = msg.content or t(language, "ticket.transcript.attachment")
        lineas.append(f"[{hora}] {msg.author}: {contenido}")
    texto = "\n".join(lineas) if lineas else t(language, "ticket.transcript.empty")
    buffer = io.BytesIO(texto.encode("utf-8"))
    return discord.File(buffer, filename=f"transcripcion-{channel.name}.txt")


async def _enviar_transcripcion(guild: discord.Guild, channel: discord.TextChannel, ticket_id: int,
                                 user_id: int, closer: discord.abc.User, language: str):
    """[Premium] Envia la transcripcion al canal configurado, o por MD al creador del ticket si no hay canal."""
    try:
        archivo = await _generar_transcripcion(channel, language)
    except discord.Forbidden:
        return
    embed = embeds.info(
        t(language, "ticket.transcript.title", id=ticket_id),
        t(language, "ticket.transcript.description", opener=f"<@{user_id}>", closer=closer.mention),
    )
    transcript_channel_id = await db.get_config(guild.id, "tickets_transcript_channel")
    destino = guild.get_channel(int(transcript_channel_id)) if transcript_channel_id else None
    try:
        if destino:
            await destino.send(embed=embed, file=archivo)
        else:
            opener = guild.get_member(user_id)
            if opener:
                await opener.send(embed=embed, file=archivo)
    except discord.Forbidden:
        pass


async def _cerrar_ticket(interaction: discord.Interaction, ticket_id: int):
    ticket = await db.get_ticket(ticket_id)
    if ticket is None:
        await interaction.response.send_message(t("es", "ticket.not_found"), ephemeral=True)
        return

    _, guild_id, channel_id, user_id, status, created_at, closed_at, language = ticket
    if status == "closed":
        await interaction.response.send_message(t(language, "ticket.already_closed"), ephemeral=True)
        return

    is_owner = interaction.user.id == user_id
    is_staff = await checks.is_server_admin(interaction.user) if isinstance(interaction.user, discord.Member) else False
    if not (is_owner or is_staff):
        await interaction.response.send_message(t(language, "ticket.cannot_close"), ephemeral=True)
        return

    await db.close_ticket(ticket_id)
    await interaction.response.send_message(t(language, "ticket.closed"))

    guild = interaction.guild
    if guild is not None and await db.is_premium(guild.id):
        await _enviar_transcripcion(guild, interaction.channel, ticket_id, user_id, interaction.user, language)

    import asyncio
    await asyncio.sleep(5)
    try:
        await interaction.channel.delete(reason=f"Ticket #{ticket_id} cerrado")
    except discord.Forbidden:
        pass


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(OpenTicketView())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Registra cada mensaje humano escrito dentro de un canal de ticket,
        # para que el panel web pueda mostrar el hilo completo y permitir
        # responder desde ahi (como la bandeja de mensajes privados).
        if message.author.bot or message.guild is None:
            return
        ticket = await db.get_ticket_by_channel(message.channel.id)
        if ticket is None or ticket[4] != "open":
            return
        ticket_id, guild_id, channel_id, opener_id, status, created_at, closed_at, language = ticket
        content = message.content or "*(mensaje sin texto: puede que sea un adjunto o una imagen)*"
        avatar_url = None
        try:
            avatar_url = str(message.author.display_avatar.url)
        except Exception:
            pass
        direction = "in" if message.author.id == opener_id else "out"
        await db.log_ticket_message(
            ticket_id, guild_id, message.author.id, str(message.author), avatar_url, direction, content
        )

    @app_commands.command(name="ticket-panel", description="Publica el panel para abrir tickets en este canal (ES/EN)")
    @checks.is_admin()
    async def ticket_panel(self, interaction: discord.Interaction):
        embed = embeds.info(
            "🎫 Soporte / Support",
            "¿Necesitas ayuda? Elige tu idioma y pulsa el botón para abrir un ticket privado con el staff.\n"
            "Need help? Choose your language and click the button to open a private ticket with staff.",
        )
        try:
            await interaction.channel.send(embed=embed, view=OpenTicketView())
        except discord.Forbidden:
            await interaction.response.send_message(
                f"No tengo permiso para escribir en {interaction.channel.mention}. Revisa los permisos de este "
                "canal (a veces tiene overrides propios): mi rol necesita 'Ver canal' y 'Enviar mensajes' aquí.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Panel de tickets publicado.", ephemeral=True)

    @app_commands.command(name="ticket-cerrar", description="Cierra el ticket actual (usalo dentro del canal del ticket)")
    @checks.is_admin()
    async def ticket_cerrar(self, interaction: discord.Interaction):
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message("Este canal no es un ticket.", ephemeral=True)
            return
        await _cerrar_ticket(interaction, ticket[0])


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
