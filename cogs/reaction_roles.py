"""
AstroCube Anti-Raid - Roles de reaccion/boton.

Los paneles (mensaje + botones) se crean desde el panel web (que los publica
via API REST). Este cog solo se encarga de RESPONDER a los clics: da o quita
el rol correspondiente. Al arrancar, reconstruye las vistas persistentes de
todos los paneles ya publicados para que sigan funcionando tras un reinicio.
"""

import discord
from discord.ext import commands

import database as db


class RoleButton(discord.ui.Button):
    def __init__(self, panel_id: int, option_id: int, role_id: int, label: str, emoji: str):
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            emoji=emoji or None,
            custom_id=f"astrocube:rrole:{panel_id}:{option_id}:{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        role = interaction.guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("Ese rol ya no existe en el servidor.", ephemeral=True)
            return
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Roles de reaccion (panel)")
                await interaction.response.send_message(f"Se te ha quitado el rol {role.mention}.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Roles de reaccion (panel)")
                await interaction.response.send_message(f"Se te ha dado el rol {role.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos para gestionar ese rol (revisa que mi rol este por encima).", ephemeral=True
            )


class ReactionRolePanelView(discord.ui.View):
    def __init__(self, panel_id: int, options):
        super().__init__(timeout=None)
        for option_id, _panel_id, role_id, label, emoji in options:
            self.add_item(RoleButton(panel_id, option_id, role_id, label, emoji))


class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        panels = await db.list_all_reaction_panels()
        count = 0
        for panel_id, guild_id, channel_id, message_id, title, description, created_at in panels:
            options = await db.list_reaction_options(panel_id)
            if not options:
                continue
            self.bot.add_view(ReactionRolePanelView(panel_id, options), message_id=message_id)
            count += 1


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
