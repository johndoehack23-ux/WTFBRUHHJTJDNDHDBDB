import discord
from discord.ext import commands
from functions import *


class EndgameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="endgame", aliases=["eg"])
    async def endgame(self, ctx, scope: str = "server"):
        if not is_admin(ctx.author.id):
            return

        scope = scope.lower()

        if scope == "global":
            count = len(active_games)
            active_games.clear()
            await ctx.send(f"✅ **Global Endgame** - Ended {count} game(s) across all servers.")
            await send_debug_msg(self.bot, f"⚡ `.eg global` | {ctx.author} (`{ctx.author.id}`) ended **{count}** game(s) globally")
            return

        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == ctx.guild.id:
                    del active_games[k]
                    ended += 1
            await ctx.send(f"✅ Ended {ended} game(s) in this server." if ended else "No active game found in this server.")
            if ended:
                await send_debug_msg(self.bot, f"⚡ `.eg server` | {ctx.author} (`{ctx.author.id}`) ended **{ended}** game(s) in {ctx.guild.name} (`{ctx.guild.id}`)")
            return

        else:
            await ctx.send("❌ Invalid option. Use: `endgame server` or `endgame global`")



async def setup(bot):
    await bot.add_cog(EndgameCog(bot))
