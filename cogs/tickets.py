"""
AstroCube Anti-Raid - Sistema de Tickets.

/ticket-panel (staff) publica un mensaje con boton "Abrir ticket". Al pulsarlo
se crea un canal privado (visible solo para quien lo abre y el staff) donde
se puede pedir ayuda; /ticket-cerrar o el boton de cerrar lo archivan.

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


class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.cerrar.custom_id = f"astrocube:ticket:cerrar:{ticket_id}"

    @discord.ui.button(label="Cerrar ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _cerrar_ticket(interaction, self.ticket_id)


class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir ticket", style=discord.ButtonStyle.success, emoji="🎫",
        custom_id="astrocube:ticket:abrir",
    )
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        existente = await db.get_open_ticket_for_user(guild.id, user.id)
        if existente:
            canal = guild.get_channel(existente[2]) if existente[2] else None
            if canal:
                await interaction.response.send_message(f"Ya tienes un ticket abierto: {canal.mention}", ephemeral=True)
                return

        await interaction.response.send_message("Creando tu ticket...", ephemeral=True)

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

        ticket_id = await db.create_ticket(guild.id, user.id)

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{user.name}"[:90],
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                reason=f"Ticket abierto por {user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permisos para crear canales. Avisa a un administrador.", ephemeral=True
            )
            return

        await db.set_ticket_channel(ticket_id, channel.id)

        embed = embeds.info(
            f"🎫 Ticket #{ticket_id}",
            f"Hola {user.mention}, cuentanos en que podemos ayudarte. El staff respondera pronto.",
        )
        await channel.send(embed=embed, view=CloseTicketView(ticket_id))
        await interaction.followup.send(f"Tu ticket ha sido creado: {channel.mention}", ephemeral=True)


async def _generar_transcripcion(channel: discord.TextChannel) -> discord.File:
    """[Premium] Genera un .txt con el historial de mensajes del canal del ticket."""
    lineas = []
    async for msg in channel.history(limit=500, oldest_first=True):
        hora = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        contenido = msg.content or "[sin texto / adjunto]"
        lineas.append(f"[{hora}] {msg.author}: {contenido}")
    texto = "\n".join(lineas) if lineas else "(el ticket no tuvo mensajes)"
    buffer = io.BytesIO(texto.encode("utf-8"))
    return discord.File(buffer, filename=f"transcripcion-{channel.name}.txt")


async def _enviar_transcripcion(guild: discord.Guild, channel: discord.TextChannel, ticket_id: int, user_id: int, closer: discord.abc.User):
    """[Premium] Envia la transcripcion al canal configurado, o por MD al creador del ticket si no hay canal."""
    try:
        archivo = await _generar_transcripcion(channel)
    except discord.Forbidden:
        return
    embed = embeds.info(
        f"📄 Transcripción del ticket #{ticket_id}",
        f"Ticket de <@{user_id}>, cerrado por {closer.mention}.",
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
        await interaction.response.send_message("Ese ticket ya no existe.", ephemeral=True)
        return

    _, guild_id, channel_id, user_id, status, created_at, closed_at = ticket
    if status == "closed":
        await interaction.response.send_message("Este ticket ya estaba cerrado.", ephemeral=True)
        return

    is_owner = interaction.user.id == user_id
    is_staff = await checks.is_server_admin(interaction.user) if isinstance(interaction.user, discord.Member) else False
    if not (is_owner or is_staff):
        await interaction.response.send_message("No puedes cerrar este ticket.", ephemeral=True)
        return

    await db.close_ticket(ticket_id)
    await interaction.response.send_message("Ticket cerrado. Este canal se borrara en unos segundos.")

    guild = interaction.guild
    if guild is not None and await db.is_premium(guild.id):
        await _enviar_transcripcion(guild, interaction.channel, ticket_id, user_id, interaction.user)

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

    @app_commands.command(name="ticket-panel", description="Publica el panel para abrir tickets en este canal")
    @checks.is_admin()
    async def ticket_panel(self, interaction: discord.Interaction):
        embed = embeds.info(
            "🎫 Soporte",
            "¿Necesitas ayuda? Pulsa el boton de abajo para abrir un ticket privado con el staff.",
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
