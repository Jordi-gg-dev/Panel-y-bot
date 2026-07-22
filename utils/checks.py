"""
AstroCube Anti-Raid - Control de permisos.

Este bot vive en muchos servidores distintos, así que (a diferencia de
AstroCube Security) NO usa una lista fija de roles de staff: cada servidor
usa su propio permiso nativo de Discord ("Administrador" o "Gestionar
servidor"). Los comandos /owner están reservados a los desarrolladores del
bot (config.OWNER_IDS), no a cada servidor.
"""

import discord
from discord import app_commands

import config


def is_server_admin(member: discord.Member) -> bool:
    if member.id in config.OWNER_IDS:
        return True
    perms = member.guild_permissions
    return perms.administrator or perms.manage_guild


def is_owner(user_id: int) -> bool:
    return user_id in config.OWNER_IDS


class NotAdmin(app_commands.CheckFailure):
    pass


class NotOwner(app_commands.CheckFailure):
    pass


def is_admin():
    """Solo administradores del servidor (o 'Gestionar servidor') pueden usar el comando."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            raise NotAdmin("Este comando solo puede usarse dentro de un servidor.")
        if is_server_admin(interaction.user):
            return True
        raise NotAdmin("Necesitas el permiso de Administrador (o Gestionar Servidor) para usar este comando.")

    return app_commands.check(predicate)


def is_bot_owner():
    """Reservado a los desarrolladores del bot."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if is_owner(interaction.user.id):
            return True
        raise NotOwner("Este comando solo puede usarlo el equipo desarrollador de AstroCube Anti-Raid.")

    return app_commands.check(predicate)
