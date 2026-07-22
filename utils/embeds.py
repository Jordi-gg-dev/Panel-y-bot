"""AstroCube Anti-Raid - Constructores de embeds con la identidad visual del bot."""

import datetime
import discord
import config


def _base(color: int) -> discord.Embed:
    embed = discord.Embed(color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.set_footer(text=config.BOT_NAME, icon_url=config.BRAND_ICON_URL or None)
    return embed


def success(title: str, description: str = "") -> discord.Embed:
    e = _base(config.COLOR_SUCCESS)
    e.title = f"✅ {title}"
    if description:
        e.description = description
    return e


def error(title: str, description: str = "") -> discord.Embed:
    e = _base(config.COLOR_DANGER)
    e.title = f"❌ {title}"
    if description:
        e.description = description
    return e


def warning(title: str, description: str = "") -> discord.Embed:
    e = _base(config.COLOR_WARNING)
    e.title = f"⚠️ {title}"
    if description:
        e.description = description
    return e


def info(title: str, description: str = "") -> discord.Embed:
    e = _base(config.COLOR_PRIMARY)
    e.title = title
    if description:
        e.description = description
    return e


def alert(title: str, description: str = "") -> discord.Embed:
    e = _base(config.COLOR_ALERT)
    e.title = f"🚨 {title}"
    if description:
        e.description = description
    return e
