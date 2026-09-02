import discord
from discord.ext import commands
from discord import app_commands
from functions import *
from editrespond import get_response

F = "endgame"

class EndgameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="eg")
    async def endgame(self, ctx, scope: str = "server"):
        if not is_admin(ctx.author.id):
            return
        scope = scope.lower()
        if scope == "global":
            count = len(active_games)
            active_games.clear()
            await ctx.send(get_response(F, "global_done", count=count))
            await send_debug_msg(self.bot, f"⚡ `.eg global` | {ctx.author} (`{ctx.author.id}`) ended **{count}** game(s) globally")
            return
        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == ctx.guild.id:
                    del active_games[k]
                    ended += 1
            await ctx.send(get_response(F, "server_done", count=ended) if ended else get_response(F, "no_active"))
            if ended:
                await send_debug_msg(self.bot, f"⚡ `.eg server` | {ctx.author} (`{ctx.author.id}`) ended **{ended}** game(s) in {ctx.guild.name} (`{ctx.guild.id}`)")
            return
        else:
            await ctx.send(get_response(F, "invalid_option"))

    @app_commands.command(name="endgame", description="End active games in this server (admin only)")
    @app_commands.describe(scope="server (default) or global")
    async def endgame_slash(self, interaction: discord.Interaction, scope: str = "server"):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message(get_response(F, "no_permission"), ephemeral=False)
        scope = scope.lower()
        if scope == "global":
            if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                return await interaction.response.send_message(get_response(F, "no_permission"), ephemeral=False)
            count = len(active_games)
            active_games.clear()
            await interaction.response.send_message(get_response(F, "global_done", count=count), ephemeral=True)
            await send_debug_msg(self.bot, f"⚡ `/endgame global` | {interaction.user} (`{interaction.user.id}`) ended **{count}** game(s) globally")
            return
        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == interaction.guild.id:
                    del active_games[k]
                    ended += 1
            await interaction.response.send_message(
                get_response(F, "server_done", count=ended) if ended else get_response(F, "no_active"),
                ephemeral=True
            )
            if ended:
                await send_debug_msg(self.bot, f"⚡ `/endgame server` | {interaction.user} (`{interaction.user.id}`) ended **{ended}** game(s) in {interaction.guild.name} (`{interaction.guild.id}`)")
            return
        else:
            await interaction.response.send_message(get_response(F, "invalid_option"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(EndgameCog(bot))
