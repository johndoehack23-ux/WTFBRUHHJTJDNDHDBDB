import discord
from discord.ext import commands
import random
from functions import *


class HintCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="hint")
    async def hint(self, ctx):
        if not is_admin(ctx.author.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        g = next((v for v in active_games.values() if v["guild_id"] == ctx.guild.id), None)
        if not g:
            return await ctx.send("🔐 No game running.")

        avail = [i for i in range(g["length"]) if i not in g.get("revealed_indices", [])]
        if not avail:
            return await ctx.send("💎 No more hints.")

        idx = random.choice(avail)
        g.setdefault("revealed_indices", []).append(idx)
        letter = g['secret'][idx].upper()
        await ctx.send(f"💡 Letter {idx+1} is **{letter}**")
        await send_debug_msg(
            self.bot,
            f"💡 `.hint` | {ctx.author} (`{ctx.author.id}`) revealed letter {idx+1} = `{letter}` "
            f"| #{ctx.channel.name} | {ctx.guild.name}"
        )


async def setup(bot):
    await bot.add_cog(HintCog(bot))
