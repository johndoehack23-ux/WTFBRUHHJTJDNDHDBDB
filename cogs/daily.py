"""
.daily — everyone (once per day)
Requires 3 wordle games completed today first.
Grants random +1, +2, or +3 bonus plays.
"""

from __future__ import annotations

import random

from discord.ext import commands

from functions import add_daily_wordle_bonus, get_user_game_count

REQUIRED_WORDLES = 3


class DailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="daily")
    async def daily_cmd(self, ctx: commands.Context):
        # Must finish 3 wordles today before claiming
        played = int(get_user_game_count(ctx.author.id) or 0)
        if played < REQUIRED_WORDLES:
            need = REQUIRED_WORDLES - played
            return await ctx.send(
                f"Play **{REQUIRED_WORDLES}** wordles today first "
                f"(you have **{played}/{REQUIRED_WORDLES}**). "
                f"**{need}** more to unlock `.daily`."
            )

        # True uniform random among 1, 2, 3
        amount = random.choice([1, 2, 3])
        result = add_daily_wordle_bonus(ctx.author.id, amount)

        if result.get("already_claimed"):
            return await ctx.send(
                f"You already claimed `.daily` today. "
                f"Effective plays used: **{result.get('effective_count', 0)}**"
            )

        await ctx.send(
            "\n".join([
                f"Daily bonus: **+{result['bonus_added']}** wordle play(s)",
                f"Effective games used today: **{result['effective_count']}**",
            ])
        )


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
    print("[daily] cog loaded")
