"""Combined wordle daily bonus + economy cash (creator sees both)."""
import random
from discord.ext import commands
from functions import add_daily_wordle_bonus, get_user_raw_game_count
from cogs.economy.eco_data import CREATOR_ID, add_cash, format_money

DAILY_WORDLE_NEED = 3
DAILY_CASH_MIN = 50
DAILY_CASH_MAX = 150


class DailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="daily")
    async def daily_cmd(self, ctx: commands.Context):
        is_creator = ctx.author.id == CREATOR_ID

        played = get_user_raw_game_count(ctx.author.id)
        if not is_creator and played < DAILY_WORDLE_NEED:
            need = DAILY_WORDLE_NEED - played
            return await ctx.send(
                f"Finish **{DAILY_WORDLE_NEED}** wordle games first. "
                f"**{need}** more before `.daily`."
            )

        amount = random.choice([1, 2, 3])
        result = add_daily_wordle_bonus(ctx.author.id, amount)
        if result.get("already_claimed"):
            return await ctx.send(
                f"You already claimed `.daily` today. "
                f"Effective plays left context: **{result.get('effective_count', '?')}**."
            )

        wordle_line = (
            f"Daily RNG rolled **{amount}** → **+{result['bonus_added']}** wordle play(s)"
        )

        if is_creator:
            cash_gain = random.randint(DAILY_CASH_MIN, DAILY_CASH_MAX)
            new_cash = add_cash(ctx.author.id, cash_gain)
            await ctx.send(
                wordle_line
                + chr(10)
                + f"💵 Economy **+{cash_gain}$** → Cash: **{format_money(new_cash)}**"
            )
        else:
            await ctx.send(wordle_line)


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
    print("[economy.daily] loaded")
