"""
AstroCube - Sistema de idiomas (ES/EN).

Modulo compartido por el bot (cogs/*.py, main.py) Y el panel web (panel.py,
plantillas), sin depender de discord.py ni de Flask, para poder importarlo
desde cualquiera de los dos sin problema.

Uso:
    from i18n import t
    t("es", "ticket.welcome.title", id=3)   -> "Ticket #3"
    t("en", "ticket.welcome.title", id=3)   -> "Ticket #3"

Por ahora el diccionario cubre por completo el sistema de Tickets (Discord +
panel), que es lo primero que se tradujo. El resto de comandos/embeds del bot
y del panel siguen en espanol; se pueden ir anadiendo claves aqui e ir
sustituyendo los textos sueltos por t(...) progresivamente sin romper nada
(si una clave no existe en un idioma, se usa la version en espanol, y si
tampoco existe ahi, se devuelve la propia clave para que sea facil detectar
textos pendientes de traducir).
"""

DEFAULT_LANG = "es"
SUPPORTED_LANGS = ("es", "en")

LANG_LABELS = {"es": "Español", "en": "English"}
LANG_FLAGS = {"es": "🇪🇸", "en": "🇬🇧"}

STRINGS: dict[str, dict[str, str]] = {
    "es": {
        # --- Panel de abrir ticket (mensaje con los botones) ---
        "ticket.panel.title": "🎫 Soporte",
        "ticket.panel.description": (
            "¿Necesitas ayuda? Elige tu idioma y pulsa el botón para abrir "
            "un ticket privado con el staff."
        ),
        "ticket.panel.button": "Abrir ticket",
        "ticket.panel.published": "Panel de tickets publicado.",
        "ticket.panel.no_perms": (
            "No tengo permiso para escribir en {channel}. Revisa los permisos de "
            "este canal (a veces tiene overrides propios): mi rol necesita "
            "'Ver canal' y 'Enviar mensajes' aquí."
        ),
        # --- Al abrir un ticket ---
        "ticket.creating": "Creando tu ticket...",
        "ticket.already_open": "Ya tienes un ticket abierto: {channel}",
        "ticket.created": "Tu ticket ha sido creado: {channel}",
        "ticket.no_channel_perms": (
            "No tengo permisos para crear canales. Avisa a un administrador."
        ),
        "ticket.welcome.title": "🎫 Ticket #{id}",
        "ticket.welcome.description": (
            "Hola {mention}, cuéntanos en qué podemos ayudarte. El staff "
            "responderá pronto."
        ),
        # --- Cerrar ticket ---
        "ticket.button.close": "Cerrar ticket",
        "ticket.not_found": "Ese ticket ya no existe.",
        "ticket.already_closed": "Este ticket ya estaba cerrado.",
        "ticket.cannot_close": "No puedes cerrar este ticket.",
        "ticket.closed": "Ticket cerrado. Este canal se borrará en unos segundos.",
        "ticket.not_a_ticket": "Este canal no es un ticket.",
        # --- Transcripción (Premium) ---
        "ticket.transcript.title": "📄 Transcripción del ticket #{id}",
        "ticket.transcript.description": "Ticket de {opener}, cerrado por {closer}.",
        "ticket.transcript.empty": "(el ticket no tuvo mensajes)",
        "ticket.transcript.attachment": "[sin texto / adjunto]",
    },
    "en": {
        "ticket.panel.title": "🎫 Support",
        "ticket.panel.description": (
            "Need help? Choose your language and click the button to open "
            "a private ticket with staff."
        ),
        "ticket.panel.button": "Open ticket",
        "ticket.panel.published": "Ticket panel published.",
        "ticket.panel.no_perms": (
            "I don't have permission to post in {channel}. Check this channel's "
            "permissions (it may have its own overrides): my role needs "
            "'View Channel' and 'Send Messages' here."
        ),
        "ticket.creating": "Creating your ticket...",
        "ticket.already_open": "You already have an open ticket: {channel}",
        "ticket.created": "Your ticket has been created: {channel}",
        "ticket.no_channel_perms": (
            "I don't have permission to create channels. Please tell an admin."
        ),
        "ticket.welcome.title": "🎫 Ticket #{id}",
        "ticket.welcome.description": (
            "Hi {mention}, tell us how we can help. Staff will reply soon."
        ),
        "ticket.button.close": "Close ticket",
        "ticket.not_found": "That ticket no longer exists.",
        "ticket.already_closed": "This ticket was already closed.",
        "ticket.cannot_close": "You can't close this ticket.",
        "ticket.closed": "Ticket closed. This channel will be deleted in a few seconds.",
        "ticket.not_a_ticket": "This channel is not a ticket.",
        "ticket.transcript.title": "📄 Transcript for ticket #{id}",
        "ticket.transcript.description": "Ticket from {opener}, closed by {closer}.",
        "ticket.transcript.empty": "(this ticket had no messages)",
        "ticket.transcript.attachment": "[no text / attachment]",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """Traduce 'key' al idioma 'lang' (o a espanol si no existe ahi, o a la
    propia clave como ultimo recurso). Si se pasan kwargs, se usan para
    rellenar placeholders tipo {channel}/{id} con .format()."""
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    template = STRINGS.get(lang, {}).get(key)
    if template is None:
        template = STRINGS[DEFAULT_LANG].get(key, key)
    return template.format(**kwargs) if kwargs else template
