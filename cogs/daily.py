"""
.daily — everyone (once per day)
Must finish 3 wordle games today first, then RNG picks +1 or +2 or +3 bonus plays.
"""

from __future__ import annotations

import random

from discord.ext import commands

from functions import add_daily_wordle_bonus, get_user_raw_game_count

REQUIRED_WORDLES = 3


class DailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="daily")
    async def daily_cmd(self, ctx: commands.Context):
        # Actual finished wordles today (not reduced by bonuses)
        played = int(get_user_raw_game_count(ctx.author.id) or 0)
        if played < REQUIRED_WORDLES:
            need = REQUIRED_WORDLES - played
            return await ctx.send(
                f"Finish **{REQUIRED_WORDLES}** wordle games today first "
                f"(you have **{played}/{REQUIRED_WORDLES}**). "
                f"**{need}** more before `.daily`."
            )

        # RNG only for the reward size — always exactly one of 1, 2, 3
        amount = random.choice([1, 2, 3])
        result = add_daily_wordle_bonus(ctx.author.id, amount)

        if result.get("already_claimed"):
            return await ctx.send(
                f"You already claimed `.daily` today. "
                f"Effective plays used: **{result.get('effective_count', 0)}**"
            )

        await ctx.send(
            "\n".join([
                f"Daily RNG rolled **{amount}** → **+{result['bonus_added']}** wordle play(s)",
                f"Effective games used today: **{result['effective_count']}**",
            ])
        )


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
    print("[daily] cog loaded")
