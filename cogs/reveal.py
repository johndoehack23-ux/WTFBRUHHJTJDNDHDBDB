import discord
from discord.ext import commands
from discord import app_commands
from functions import *
from editrespond import get_response

F = "reveal"

class RevealCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reveal")
    async def reveal_prefix(self, ctx):
        if not is_admin(ctx.author.id):
            return
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send(get_response(F, "maintenance"))
        channel_id = ctx.channel.id
        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            secret = match['secret'].upper() if match.get('secret') else 'Not started yet'
            await ctx.send(get_response(F, "secret_1v1", secret=secret))
            await send_debug_msg(self.bot, f"🔍 `.reveal` (1v1) | {ctx.author} (`{ctx.author.id}`) revealed `{secret}` | #{ctx.channel.name} | {ctx.guild.name}")
            return
        g = next((v for v in active_games.values() if v["guild_id"] == ctx.guild.id), None)
        if g and g.get("secret"):
            await ctx.send(get_response(F, "secret_word", secret=g['secret'].upper()))
            await send_debug_msg(self.bot, f"🔍 `.reveal` | {ctx.author} (`{ctx.author.id}`) revealed `{g['secret']}` | #{ctx.channel.name} | {ctx.guild.name}")
            return
        await ctx.send(get_response(F, "no_game"))

    @app_commands.command(name="reveal", description="···")
    async def reveal_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message(get_response(F, "no_permission"), ephemeral=False)
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message(get_response(F, "maintenance"), ephemeral=True)
        channel_id = interaction.channel.id
        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            secret = match['secret'].upper() if match.get('secret') else 'Not started yet'
            await interaction.response.send_message(get_response(F, "secret_1v1", secret=secret), ephemeral=True)
            await send_debug_msg(self.bot, f"🔍 `/reveal` (1v1) | {interaction.user} (`{interaction.user.id}`) revealed `{secret}` | #{interaction.channel.name} | {interaction.guild.name}")
            return
        g = next((v for v in active_games.values() if v["guild_id"] == interaction.guild.id), None)
        if g and g.get("secret"):
            await interaction.response.send_message(get_response(F, "secret_word", secret=g['secret'].upper()), ephemeral=True)
            await send_debug_msg(self.bot, f"🔍 `/reveal` | {interaction.user} (`{interaction.user.id}`) revealed `{g['secret']}` | #{interaction.channel.name} | {interaction.guild.name}")
            return
        await interaction.response.send_message(get_response(F, "no_game"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(RevealCog(bot))
