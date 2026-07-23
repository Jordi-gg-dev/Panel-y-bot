"""
AstroCube Anti-Raid - Capa de base de datos (SQLite / aiosqlite).
"""

import time
import json
import aiosqlite

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS antinuke_whitelist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS antinuke_trusted_bots (
    guild_id INTEGER NOT NULL,
    bot_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, bot_id)
);

CREATE TABLE IF NOT EXISTS antispam_whitelist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS antiraid_whitelist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    executor_id INTEGER,
    detail TEXT,
    action_taken TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    label TEXT,
    data TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS lockdown_state (
    guild_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS guild_blacklist (
    guild_id INTEGER PRIMARY KEY,
    reason TEXT,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_blacklist (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS staff_members (
    user_id INTEGER PRIMARY KEY,
    rank TEXT NOT NULL,
    username TEXT,
    avatar_url TEXT,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS premium_guilds (
    guild_id INTEGER PRIMARY KEY,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'inactive',
    current_period_end INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    trigger_text TEXT NOT NULL,
    response TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_profile (
    guild_id INTEGER PRIMARY KEY,
    nickname TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_levels (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 0,
    last_message_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    prize TEXT NOT NULL,
    winners_count INTEGER NOT NULL DEFAULT 1,
    host_id INTEGER,
    ends_at INTEGER NOT NULL,
    ended INTEGER NOT NULL DEFAULT 0,
    winners TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at INTEGER NOT NULL,
    closed_at INTEGER
);

CREATE TABLE IF NOT EXISTS reaction_role_panels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reaction_role_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    panel_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS level_role_rewards (
    guild_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);

CREATE TABLE IF NOT EXISTS command_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    guild_name TEXT,
    user_id INTEGER NOT NULL,
    username TEXT,
    command_name TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dm_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    avatar_url TEXT,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    responded_by INTEGER,
    responded_by_username TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dm_read_state (
    user_id INTEGER PRIMARY KEY,
    last_read_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    avatar_url TEXT,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_canned_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

_conn: aiosqlite.Connection | None = None


async def _migrate(conn: aiosqlite.Connection):
    """Anade columnas nuevas a tablas que ya existian antes de esta version,
    sin romper bases de datos en produccion (CREATE TABLE IF NOT EXISTS no
    anade columnas a una tabla que ya existe, asi que hace falta ALTER TABLE
    aparte). Se ignora el error si la columna ya existe."""
    migrations = [
        "ALTER TABLE tickets ADD COLUMN language TEXT NOT NULL DEFAULT 'es'",
    ]
    for stmt in migrations:
        try:
            await conn.execute(stmt)
        except Exception:
            pass
    await conn.commit()


async def init():
    global _conn
    _conn = await aiosqlite.connect(config.DB_PATH)
    await _conn.executescript(_SCHEMA)
    await _conn.commit()
    await _migrate(_conn)


def conn() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("La base de datos no ha sido inicializada (database.init()).")
    return _conn


async def close():
    if _conn is not None:
        await _conn.close()


# ---------------------------------------------------------------------------
# Config genérico por servidor
# ---------------------------------------------------------------------------
async def set_config(guild_id: int, key: str, value) -> None:
    await conn().execute(
        "INSERT INTO guild_config (guild_id, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value",
        (guild_id, key, str(value)),
    )
    await conn().commit()


async def get_config(guild_id: int, key: str, default=None):
    cur = await conn().execute(
        "SELECT value FROM guild_config WHERE guild_id=? AND key=?", (guild_id, key)
    )
    row = await cur.fetchone()
    return row[0] if row else default


async def get_bool(guild_id: int, key: str, default: bool = False) -> bool:
    value = await get_config(guild_id, key, "1" if default else "0")
    return value == "1"


async def get_int_pair(guild_id: int, key: str, default: tuple[int, int]) -> tuple[int, int]:
    value = await get_config(guild_id, key)
    if not value:
        return default
    try:
        count, seconds = value.split(":")
        return int(count), int(seconds)
    except (ValueError, AttributeError):
        return default


async def set_int_pair(guild_id: int, key: str, count: int, seconds: int):
    await set_config(guild_id, key, f"{count}:{seconds}")


# ---------------------------------------------------------------------------
# Whitelists
# ---------------------------------------------------------------------------
async def _wl_add(table: str, guild_id: int, entity_id: int, col: str):
    await conn().execute(f"INSERT OR IGNORE INTO {table} (guild_id, {col}) VALUES (?, ?)", (guild_id, entity_id))
    await conn().commit()


async def _wl_remove(table: str, guild_id: int, entity_id: int, col: str):
    await conn().execute(f"DELETE FROM {table} WHERE guild_id=? AND {col}=?", (guild_id, entity_id))
    await conn().commit()


async def _wl_list(table: str, guild_id: int, col: str) -> list[int]:
    cur = await conn().execute(f"SELECT {col} FROM {table} WHERE guild_id=?", (guild_id,))
    rows = await cur.fetchall()
    return [r[0] for r in rows]


async def _wl_has(table: str, guild_id: int, entity_id: int, col: str) -> bool:
    cur = await conn().execute(f"SELECT 1 FROM {table} WHERE guild_id=? AND {col}=?", (guild_id, entity_id))
    return await cur.fetchone() is not None


async def antinuke_whitelist_add(guild_id, user_id): await _wl_add("antinuke_whitelist", guild_id, user_id, "user_id")
async def antinuke_whitelist_remove(guild_id, user_id): await _wl_remove("antinuke_whitelist", guild_id, user_id, "user_id")
async def antinuke_whitelist_list(guild_id): return await _wl_list("antinuke_whitelist", guild_id, "user_id")
async def antinuke_whitelist_has(guild_id, user_id): return await _wl_has("antinuke_whitelist", guild_id, user_id, "user_id")

async def antinuke_trustedbot_add(guild_id, bot_id): await _wl_add("antinuke_trusted_bots", guild_id, bot_id, "bot_id")
async def antinuke_trustedbot_remove(guild_id, bot_id): await _wl_remove("antinuke_trusted_bots", guild_id, bot_id, "bot_id")
async def antinuke_trustedbot_list(guild_id): return await _wl_list("antinuke_trusted_bots", guild_id, "bot_id")
async def antinuke_trustedbot_has(guild_id, bot_id): return await _wl_has("antinuke_trusted_bots", guild_id, bot_id, "bot_id")

async def antispam_whitelist_add(guild_id, user_id): await _wl_add("antispam_whitelist", guild_id, user_id, "user_id")
async def antispam_whitelist_remove(guild_id, user_id): await _wl_remove("antispam_whitelist", guild_id, user_id, "user_id")
async def antispam_whitelist_has(guild_id, user_id): return await _wl_has("antispam_whitelist", guild_id, user_id, "user_id")

async def antiraid_whitelist_add(guild_id, user_id): await _wl_add("antiraid_whitelist", guild_id, user_id, "user_id")
async def antiraid_whitelist_remove(guild_id, user_id): await _wl_remove("antiraid_whitelist", guild_id, user_id, "user_id")
async def antiraid_whitelist_has(guild_id, user_id): return await _wl_has("antiraid_whitelist", guild_id, user_id, "user_id")


# ---------------------------------------------------------------------------
# Incidentes (histórico de detecciones)
# ---------------------------------------------------------------------------
async def log_incident(guild_id: int, module: str, executor_id: int | None, detail: str, action_taken: str):
    await conn().execute(
        "INSERT INTO incidents (guild_id, module, executor_id, detail, action_taken, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, module, executor_id, detail, action_taken, int(time.time())),
    )
    await conn().commit()


async def get_incidents(guild_id: int, limit: int = 15):
    cur = await conn().execute(
        "SELECT module, executor_id, detail, action_taken, created_at FROM incidents "
        "WHERE guild_id=? ORDER BY created_at DESC LIMIT ?",
        (guild_id, limit),
    )
    return await cur.fetchall()


async def clear_incidents(guild_id: int):
    await conn().execute("DELETE FROM incidents WHERE guild_id=?", (guild_id,))


async def purge_old_incidents(guild_id: int, keep_days: int) -> int:
    """Borra incidentes mas antiguos que keep_days para este servidor. Devuelve cuantos borro."""
    cutoff = int(time.time()) - keep_days * 86400
    cur = await conn().execute(
        "DELETE FROM incidents WHERE guild_id=? AND created_at<?", (guild_id, cutoff)
    )
    await conn().commit()
    return cur.rowcount


async def list_all_guild_ids_with_incidents():
    cur = await conn().execute("SELECT DISTINCT guild_id FROM incidents")
    rows = await cur.fetchall()
    return [r[0] for r in rows]
    await conn().commit()


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
async def save_backup(guild_id: int, label: str, data: dict) -> int:
    cur = await conn().execute(
        "INSERT INTO backups (guild_id, label, data, created_at) VALUES (?, ?, ?, ?)",
        (guild_id, label, json.dumps(data), int(time.time())),
    )
    await conn().commit()
    return cur.lastrowid


async def list_backups(guild_id: int):
    cur = await conn().execute(
        "SELECT id, label, created_at FROM backups WHERE guild_id=? ORDER BY created_at DESC", (guild_id,)
    )
    return await cur.fetchall()


async def get_backup(backup_id: int, guild_id: int):
    cur = await conn().execute(
        "SELECT data FROM backups WHERE id=? AND guild_id=?", (backup_id, guild_id)
    )
    row = await cur.fetchone()
    return json.loads(row[0]) if row else None


async def delete_backup(backup_id: int, guild_id: int) -> bool:
    cur = await conn().execute("DELETE FROM backups WHERE id=? AND guild_id=?", (backup_id, guild_id))
    await conn().commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Estado de lockdown (para poder revertir con precisión)
# ---------------------------------------------------------------------------
async def save_lockdown_state(guild_id: int, data: dict):
    await conn().execute(
        "INSERT INTO lockdown_state (guild_id, data, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
        (guild_id, json.dumps(data), int(time.time())),
    )
    await conn().commit()


async def get_lockdown_state(guild_id: int):
    cur = await conn().execute("SELECT data FROM lockdown_state WHERE guild_id=?", (guild_id,))
    row = await cur.fetchone()
    return json.loads(row[0]) if row else None


async def clear_lockdown_state(guild_id: int):
    await conn().execute("DELETE FROM lockdown_state WHERE guild_id=?", (guild_id,))
    await conn().commit()


# ---------------------------------------------------------------------------
# Blacklists globales (a nivel de bot, gestionadas por los owners)
# ---------------------------------------------------------------------------
async def blacklist_guild_add(guild_id: int, reason: str):
    await conn().execute(
        "INSERT OR REPLACE INTO guild_blacklist (guild_id, reason, added_at) VALUES (?, ?, ?)",
        (guild_id, reason, int(time.time())),
    )
    await conn().commit()


async def blacklist_guild_remove(guild_id: int) -> bool:
    cur = await conn().execute("DELETE FROM guild_blacklist WHERE guild_id=?", (guild_id,))
    await conn().commit()
    return cur.rowcount > 0


async def is_guild_blacklisted(guild_id: int) -> bool:
    cur = await conn().execute("SELECT 1 FROM guild_blacklist WHERE guild_id=?", (guild_id,))
    return await cur.fetchone() is not None


async def blacklist_user_add(user_id: int, reason: str):
    await conn().execute(
        "INSERT OR REPLACE INTO user_blacklist (user_id, reason, added_at) VALUES (?, ?, ?)",
        (user_id, reason, int(time.time())),
    )
    await conn().commit()


async def blacklist_user_remove(user_id: int) -> bool:
    cur = await conn().execute("DELETE FROM user_blacklist WHERE user_id=?", (user_id,))
    await conn().commit()
    return cur.rowcount > 0


async def is_user_blacklisted(user_id: int) -> bool:
    cur = await conn().execute("SELECT 1 FROM user_blacklist WHERE user_id=?", (user_id,))
    return await cur.fetchone() is not None


async def get_staff_rank(user_id: int):
    """Rango del Staff (Fundador/Co-Fundador/Administrador/...) para este
    usuario, o None. Tabla gestionada desde el panel (pestaña Staff)."""
    cur = await conn().execute("SELECT rank FROM staff_members WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Premium (Stripe) por servidor
# ---------------------------------------------------------------------------
async def is_premium(guild_id: int) -> bool:
    cur = await conn().execute("SELECT status FROM premium_guilds WHERE guild_id=?", (guild_id,))
    row = await cur.fetchone()
    return bool(row and row[0] == "active")


async def get_premium(guild_id: int):
    cur = await conn().execute(
        "SELECT guild_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, updated_at "
        "FROM premium_guilds WHERE guild_id=?",
        (guild_id,),
    )
    return await cur.fetchone()


async def upsert_premium(
    guild_id: int, status: str, stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None, current_period_end: int | None = None,
) -> None:
    """Espejo del upsert_premium del panel, para que el propio bot pueda
    auto-conceder Premium (p. ej. a los servidores de los que el dueño del
    bot es el propietario real de Discord) sin depender del panel."""
    now = int(time.time())
    cur = await conn().execute("SELECT guild_id FROM premium_guilds WHERE guild_id=?", (guild_id,))
    existing = await cur.fetchone()
    if existing:
        await conn().execute(
            "UPDATE premium_guilds SET status=?, "
            "stripe_customer_id=COALESCE(?, stripe_customer_id), "
            "stripe_subscription_id=COALESCE(?, stripe_subscription_id), "
            "current_period_end=COALESCE(?, current_period_end), "
            "updated_at=? WHERE guild_id=?",
            (status, stripe_customer_id, stripe_subscription_id, current_period_end, now, guild_id),
        )
    else:
        await conn().execute(
            "INSERT INTO premium_guilds (guild_id, stripe_customer_id, stripe_subscription_id, status, "
            "current_period_end, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, now),
        )
    await conn().commit()


# ---------------------------------------------------------------------------
# Comandos personalizados (funcion Premium, gestionados desde el panel web)
# ---------------------------------------------------------------------------
async def list_enabled_custom_commands(guild_id: int):
    cur = await conn().execute(
        "SELECT trigger_text, response FROM custom_commands WHERE guild_id=? AND enabled=1",
        (guild_id,),
    )
    return await cur.fetchall()


# ---------------------------------------------------------------------------
# Niveles (XP) por servidor
# ---------------------------------------------------------------------------
async def get_bool_config(guild_id: int, key: str, default: bool = False) -> bool:
    return await get_bool(guild_id, key, default)


async def add_xp(guild_id: int, user_id: int, username: str, amount: int, now: int):
    cur = await conn().execute(
        "SELECT xp, level FROM user_levels WHERE guild_id=? AND user_id=?", (guild_id, user_id)
    )
    row = await cur.fetchone()
    old_xp = row[0] if row else 0
    old_level = row[1] if row else 0
    new_xp = old_xp + amount
    new_level = int(0.1 * (new_xp ** 0.5))

    if row:
        await conn().execute(
            "UPDATE user_levels SET username=?, xp=?, level=?, last_message_at=? WHERE guild_id=? AND user_id=?",
            (username, new_xp, new_level, now, guild_id, user_id),
        )
    else:
        await conn().execute(
            "INSERT INTO user_levels (guild_id, user_id, username, xp, level, last_message_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, username, new_xp, new_level, now),
        )
    await conn().commit()
    return old_level, new_level, new_xp


async def get_last_message_at(guild_id: int, user_id: int) -> int:
    cur = await conn().execute(
        "SELECT last_message_at FROM user_levels WHERE guild_id=? AND user_id=?", (guild_id, user_id)
    )
    row = await cur.fetchone()
    return row[0] if row else 0


async def get_user_level(guild_id: int, user_id: int):
    cur = await conn().execute(
        "SELECT xp, level FROM user_levels WHERE guild_id=? AND user_id=?", (guild_id, user_id)
    )
    return await cur.fetchone()


async def leaderboard(guild_id: int, limit: int = 10):
    cur = await conn().execute(
        "SELECT user_id, username, xp, level FROM user_levels WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
        (guild_id, limit),
    )
    return await cur.fetchall()


# ---------------------------------------------------------------------------
# Roles de recompensa por nivel (funcion Premium)
# ---------------------------------------------------------------------------
async def set_level_role_reward(guild_id: int, level: int, role_id: int) -> None:
    await conn().execute(
        "INSERT INTO level_role_rewards (guild_id, level, role_id) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id",
        (guild_id, level, role_id),
    )
    await conn().commit()


async def remove_level_role_reward(guild_id: int, level: int) -> None:
    await conn().execute(
        "DELETE FROM level_role_rewards WHERE guild_id=? AND level=?", (guild_id, level)
    )
    await conn().commit()


async def get_level_role_reward(guild_id: int, level: int):
    cur = await conn().execute(
        "SELECT role_id FROM level_role_rewards WHERE guild_id=? AND level=?", (guild_id, level)
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def list_level_role_rewards(guild_id: int):
    cur = await conn().execute(
        "SELECT level, role_id FROM level_role_rewards WHERE guild_id=? ORDER BY level ASC", (guild_id,)
    )
    return await cur.fetchall()


# ---------------------------------------------------------------------------
# Sorteos (giveaways)
# ---------------------------------------------------------------------------
async def create_giveaway(guild_id: int, channel_id: int, prize: str, winners_count: int, host_id: int, ends_at: int) -> int:
    cur = await conn().execute(
        "INSERT INTO giveaways (guild_id, channel_id, prize, winners_count, host_id, ends_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, prize, winners_count, host_id, ends_at, int(__import__("time").time())),
    )
    await conn().commit()
    return cur.lastrowid


async def set_giveaway_message_id(giveaway_id: int, message_id: int):
    await conn().execute("UPDATE giveaways SET message_id=? WHERE id=?", (message_id, giveaway_id))
    await conn().commit()


async def get_giveaway(giveaway_id: int):
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winners, created_at "
        "FROM giveaways WHERE id=?",
        (giveaway_id,),
    )
    return await cur.fetchone()


async def list_active_giveaways():
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winners, created_at "
        "FROM giveaways WHERE ended=0"
    )
    return await cur.fetchall()


async def count_active_giveaways(guild_id: int) -> int:
    cur = await conn().execute(
        "SELECT COUNT(*) FROM giveaways WHERE guild_id=? AND ended=0", (guild_id,)
    )
    row = await cur.fetchone()
    return row[0] if row else 0


async def list_due_giveaways():
    now = int(__import__("time").time())
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winners, created_at "
        "FROM giveaways WHERE ended=0 AND ends_at<=?",
        (now,),
    )
    return await cur.fetchall()


async def finish_giveaway(giveaway_id: int, winners_ids: list):
    await conn().execute(
        "UPDATE giveaways SET ended=1, winners=? WHERE id=?",
        (",".join(str(w) for w in winners_ids), giveaway_id),
    )
    await conn().commit()


async def add_giveaway_entry(giveaway_id: int, user_id: int) -> bool:
    """Devuelve True si era una entrada nueva, False si ya estaba apuntado."""
    if await has_giveaway_entry(giveaway_id, user_id):
        return False
    await conn().execute(
        "INSERT OR IGNORE INTO giveaway_entries (giveaway_id, user_id, created_at) VALUES (?, ?, ?)",
        (giveaway_id, user_id, int(__import__("time").time())),
    )
    await conn().commit()
    return True


async def has_giveaway_entry(giveaway_id: int, user_id: int) -> bool:
    cur = await conn().execute(
        "SELECT 1 FROM giveaway_entries WHERE giveaway_id=? AND user_id=?", (giveaway_id, user_id)
    )
    return await cur.fetchone() is not None


async def list_giveaway_entries(giveaway_id: int):
    cur = await conn().execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))
    rows = await cur.fetchall()
    return [r[0] for r in rows]


async def count_giveaway_entries(giveaway_id: int) -> int:
    cur = await conn().execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))
    row = await cur.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
async def create_ticket(guild_id: int, user_id: int, language: str = "es") -> int:
    cur = await conn().execute(
        "INSERT INTO tickets (guild_id, user_id, status, created_at, language) VALUES (?, ?, 'open', ?, ?)",
        (guild_id, user_id, int(time.time()), language),
    )
    await conn().commit()
    return cur.lastrowid


async def set_ticket_channel(ticket_id: int, channel_id: int):
    await conn().execute("UPDATE tickets SET channel_id=? WHERE id=?", (channel_id, ticket_id))
    await conn().commit()


async def get_ticket(ticket_id: int):
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, user_id, status, created_at, closed_at, language FROM tickets WHERE id=?",
        (ticket_id,),
    )
    return await cur.fetchone()


async def get_ticket_by_channel(channel_id: int):
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, user_id, status, created_at, closed_at, language FROM tickets WHERE channel_id=?",
        (channel_id,),
    )
    return await cur.fetchone()


async def get_open_ticket_for_user(guild_id: int, user_id: int):
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, user_id, status, created_at, closed_at, language FROM tickets "
        "WHERE guild_id=? AND user_id=? AND status='open'",
        (guild_id, user_id),
    )
    return await cur.fetchone()


async def close_ticket(ticket_id: int):
    await conn().execute("UPDATE tickets SET status='closed', closed_at=? WHERE id=?", (int(time.time()), ticket_id))
    await conn().commit()


async def log_ticket_message(ticket_id: int, guild_id: int, user_id: int, username: str | None,
                              avatar_url: str | None, direction: str, content: str):
    """Guarda un mensaje de un canal de ticket para que el panel pueda
    mostrar el hilo completo de la conversacion. direction: 'in' (quien abrio
    el ticket) o 'out' (staff/bot, incluidas las respuestas enviadas desde
    el panel)."""
    await conn().execute(
        "INSERT INTO ticket_messages (ticket_id, guild_id, user_id, username, avatar_url, direction, content, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, guild_id, user_id, username, avatar_url, direction, content, int(time.time())),
    )
    await conn().commit()


# ---------------------------------------------------------------------------
# Roles de reaccion / boton
# ---------------------------------------------------------------------------
async def get_reaction_panel(panel_id: int):
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, message_id, title, description, created_at FROM reaction_role_panels WHERE id=?",
        (panel_id,),
    )
    return await cur.fetchone()


async def list_reaction_options(panel_id: int):
    cur = await conn().execute(
        "SELECT id, panel_id, role_id, label, emoji FROM reaction_role_options WHERE panel_id=?",
        (panel_id,),
    )
    return await cur.fetchall()


async def list_all_reaction_panels():
    cur = await conn().execute(
        "SELECT id, guild_id, channel_id, message_id, title, description, created_at FROM reaction_role_panels"
    )
    return await cur.fetchall()


# ---------------------------------------------------------------------------
# Registro global de comandos usados (solo panel, propietario)
# ---------------------------------------------------------------------------
async def log_command_use(guild_id, guild_name, user_id: int, username: str, command_name: str) -> None:
    await conn().execute(
        "INSERT INTO command_log (guild_id, guild_name, user_id, username, command_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, guild_name, user_id, username, command_name, int(time.time())),
    )
    await conn().commit()


# ---------------------------------------------------------------------------
# Mensajes privados (modmail) — recibidos por DM y respondidos desde el panel
# ---------------------------------------------------------------------------
async def log_dm_message(user_id: int, username: str, avatar_url: str | None, direction: str, content: str) -> None:
    await conn().execute(
        "INSERT INTO dm_messages (user_id, username, avatar_url, direction, content, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, avatar_url, direction, content, int(time.time())),
    )
    await conn().commit()
