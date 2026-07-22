"""
AstroCube Anti-Raid - Configuración central del bot.

A diferencia de AstroCube Security (pensado para un único servidor), este bot
está diseñado para funcionar en MUCHOS servidores a la vez. Por eso los
permisos no dependen de una lista fija de roles de staff: cada servidor usa
sus propios administradores (permiso nativo "Administrador" de Discord).

Todas las variables sensibles se leen desde el archivo .env (ver .env.example).
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _parse_id_list(raw: str) -> list[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


TOKEN: str = os.getenv("DISCORD_TOKEN", "")

# ID de un servidor de pruebas (opcional). Si se define, los comandos se
# sincronizan al instante SOLO ahí, útil en desarrollo. Déjalo vacío para
# sincronizar globalmente (necesario una vez el bot esté en varios servidores).
DEV_GUILD_ID: int | None = int(os.getenv("DEV_GUILD_ID")) if os.getenv("DEV_GUILD_ID") else None

# IDs de los desarrolladores/dueños del bot (no de cada servidor). Solo ellos
# pueden usar /owner (reload, sync, guildlist, leaveguild, blacklist, broadcast).
OWNER_IDS: list[int] = _parse_id_list(os.getenv("OWNER_IDS", ""))

BOT_NAME = "AstroCube Anti-Raid"
BRAND_ICON_URL = os.getenv("BRAND_ICON_URL", "")

# Servidor de soporte/comunidad de AstroCube (equivalente al botón "Únete a mi
# Servidor" de otros paneles). Se puede sobreescribir desde el .env.
SUPPORT_SERVER_INVITE = os.getenv("SUPPORT_SERVER_INVITE", "https://discord.gg/jRdnjBqVK")

COLOR_PRIMARY = 0x5865F2
COLOR_SUCCESS = 0x2ECC71
COLOR_WARNING = 0xF1C40F
COLOR_DANGER = 0xE74C3C
COLOR_ALERT = 0xFF4500   # incidentes de anti-nuke / anti-raid

# Antes esto estaba fijo y NO se podía cambiar con una variable de entorno,
# lo cual era un problema real en Railway: el panel sí que leía DB_PATH del
# entorno, pero el bot lo ignoraba y siempre usaba su propia carpeta local,
# así que aunque en el código pareciera "la misma" base de datos, en producción
# eran dos archivos distintos. Ahora se puede fijar con la variable DB_PATH
# (ej: /data/antiraid.db si montas un Volume persistente en Railway).
DB_PATH = os.getenv("DB_PATH") or os.path.join(os.path.dirname(__file__), "data", "antiraid.db")

# --- Valores por defecto de los módulos de seguridad (configurables luego
# por servidor con /antinuke, /antispam, /antiraid) ---
DEFAULT_ANTINUKE_THRESHOLDS = {
    "channel_delete": (3, 10),   # 3 acciones en 10 segundos
    "channel_create": (5, 10),
    "role_delete": (3, 10),
    "role_create": (5, 10),
    "ban": (3, 10),
    "webhook_create": (3, 10),
}
DEFAULT_ANTISPAM_MESSAGE_THRESHOLD = (6, 6)   # 6 mensajes en 6 segundos
DEFAULT_ANTISPAM_MENTION_THRESHOLD = 5        # menciones en un solo mensaje
DEFAULT_ANTIRAID_JOIN_THRESHOLD = (10, 15)    # 10 entradas en 15 segundos
# Desactivado por defecto: la antigüedad de una cuenta por sí sola no es un
# indicio fiable de raid (mucha gente legítima crea su cuenta el mismo día
# que entra a un servidor). La protección real contra raids es la detección
# de oleadas de entrada (DEFAULT_ANTIRAID_JOIN_THRESHOLD) que sigue activa.
# Si algún servidor quiere expulsar cuentas nuevas igualmente, puede activarlo
# con /antiraid minaccountage <dias>.
DEFAULT_MIN_ACCOUNT_AGE_DAYS = 0
