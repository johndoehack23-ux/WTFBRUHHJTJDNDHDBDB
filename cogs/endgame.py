import discord
from discord.ext import commands
from discord import app_commands
from functions import *


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
            return await ctx.send(f"✅ **Global Endgame** - Ended {count} game(s) across all servers.")

        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == ctx.guild.id:
                    del active_games[k]
                    ended += 1
            return await ctx.send(
                f"✅ Ended {ended} game(s) in this server." if ended else "No active game found in this server."
            )

        else:
            await ctx.send("❌ Invalid option. Use: `endgame server` or `endgame global`")

    @app_commands.command(name="endgame", description="End active games in this server (admin only)")
    @app_commands.describe(scope="server (default) or global")
    async def endgame_slash(self, interaction: discord.Interaction, scope: str = "server"):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        scope = scope.lower()

        if scope == "global":
            if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
            count = len(active_games)
            active_games.clear()
            return await interaction.response.send_message(f"✅ **Global Endgame** - Ended {count} game(s) across all servers.", ephemeral=True)

        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == interaction.guild.id:
                    del active_games[k]
                    ended += 1
            return await interaction.response.send_message(
                f"✅ Ended {ended} game(s) in this server." if ended else "No active game found in this server.",
                ephemeral=True
            )

        else:
            await interaction.response.send_message("❌ Invalid option. Use: `server` or `global`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(EndgameCog(bot))
