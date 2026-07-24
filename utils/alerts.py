"""
AstroCube Anti-Raid - Alertas centralizadas (Premium).

Tres funciones independientes que cualquier módulo (Anti-Nuke, Anti-Raid,
Anti-Spam, AutoMod...) puede llamar tras detectar y castigar algo:

- notify_realtime: manda un aviso inmediato a UN canal central de alertas
  (distinto del canal de logs propio de cada módulo, que sigue funcionando
  igual que siempre). Solo si el servidor tiene Premium y lo activó.
- notify_owner_dm: manda un MD directo al dueño del servidor para
  "emergencias" (Anti-Nuke, oleada de entradas). Solo Premium.
- maybe_send_weekly_report: usado por cogs/reports.py, no se llama a mano.

Todo esto es aditivo: si el servidor no es Premium o no ha activado estas
opciones, no pasa nada (ni se manda nada ni se rompe nada existente).
"""

from __future__ import annotations

import discord

import database as db


async def notify_realtime(guild: discord.Guild, embed: discord.Embed):
    if guild is None:
        return
    if not await db.is_premium(guild.id):
        return
    if not await db.get_bool(guild.id, "alerts_realtime_enabled", False):
        return
    channel_id = await db.get_config(guild.id, "alerts_channel")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def notify_owner_dm(guild: discord.Guild, embed: discord.Embed):
    if guild is None:
        return
    if not await db.is_premium(guild.id):
        return
    if not await db.get_bool(guild.id, "alerts_dm_enabled", False):
        return
    owner = guild.owner
    if owner is None and guild.owner_id:
        try:
            owner = await guild.fetch_member(guild.owner_id)
        except discord.HTTPException:
            return
    if owner is None:
        return
    try:
        await owner.send(embed=embed)
    except discord.HTTPException:
        pass
