
import discord
from discord.ext import commands
from cogs.economy.eco_data import CREATOR_ID, get_cash, format_money


class BalanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="balance", aliases=["bal", "money"])
    async def balance(self, ctx: commands.Context, user: discord.User = None):
        if ctx.author.id != CREATOR_ID:
            return
        target = user or ctx.author
        cash = get_cash(target.id)
        embed = discord.Embed(
            title=f"{target.name} Balance",
            description=f"💵 Cash: {format_money(cash)}\n🏦 Bank: SOON",
            color=0x2f3136,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(BalanceCog(bot))
    print("[economy.balance] loaded")
