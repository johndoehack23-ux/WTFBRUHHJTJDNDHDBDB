
from discord.ext import commands


class WorkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="work")
    async def work(self, ctx: commands.Context):
        return


async def setup(bot):
    await bot.add_cog(WorkCog(bot))
    print("[economy.work] loaded (disabled)")
