"""
AstroCube Anti-Raid - Control de permisos.

Este bot vive en muchos servidores distintos, así que (a diferencia de
AstroCube Security) NO usa una lista fija de roles de staff: cada servidor
usa su propio permiso nativo de Discord ("Administrador" o "Gestionar
servidor"). Los comandos /owner están reservados a los desarrolladores del
bot (config.OWNER_IDS), no a cada servidor.

Además, cualquier miembro del Staff (gestionado desde el panel, pestaña
Staff) con rango Fundador, Co-Fundador o Administrador tiene ese mismo nivel
de acceso total en TODOS los servidores y en /owner, exactamente igual que
si estuviera en OWNER_IDS. Ver FULL_ACCESS_STAFF_RANKS más abajo. El resto de
rangos (Moderador/Soporte/Colaborador) son solo decorativos y no dan ningún
permiso extra por sí solos.
"""

import discord
from discord import app_commands

import config
import database as db

FULL_ACCESS_STAFF_RANKS = {"Fundador", "Co-Fundador", "Administrador"}


async def _is_full_access_staff(user_id: int) -> bool:
    rank = await db.get_staff_rank(user_id)
    return rank in FULL_ACCESS_STAFF_RANKS


async def is_server_admin(member: discord.Member) -> bool:
    if member.id in config.OWNER_IDS:
        return True
    if await _is_full_access_staff(member.id):
        return True
    perms = member.guild_permissions
    return perms.administrator or perms.manage_guild


async def is_owner(user_id: int) -> bool:
    if user_id in config.OWNER_IDS:
        return True
    return await _is_full_access_staff(user_id)


class NotAdmin(app_commands.CheckFailure):
    pass


class NotOwner(app_commands.CheckFailure):
    pass


def is_admin():
    """Solo administradores del servidor (o 'Gestionar servidor'), el dueño
    del bot, o Staff Fundador/Co-Fundador/Administrador pueden usar el comando."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            raise NotAdmin("Este comando solo puede usarse dentro de un servidor.")
        if await is_server_admin(interaction.user):
            return True
        raise NotAdmin("Necesitas el permiso de Administrador (o Gestionar Servidor) para usar este comando.")

    return app_commands.check(predicate)


def is_bot_owner():
    """Reservado a los desarrolladores del bot y al Staff Fundador/Co-Fundador/Administrador."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if await is_owner(interaction.user.id):
            return True
        raise NotOwner("Este comando solo puede usarlo el equipo desarrollador de AstroCube Anti-Raid.")

    return app_commands.check(predicate)
