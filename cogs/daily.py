"""
.daily — tester role / creator only (silent for everyone else)
Grants +1 to +3 bonus wordle plays for the day.
"""

from __future__ import annotations

import random

from discord.ext import commands

from functions import add_daily_wordle_bonus, user_has_tester_role, get_user_game_count


class DailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="daily")
    async def daily_cmd(self, ctx: commands.Context):
        # Silent for non-tester (creator counts as tester in helper)
        if not user_has_tester_role(ctx.author.id, bot=self.bot, guild=ctx.guild):
            return

        amount = random.randint(1, 3)
        result = add_daily_wordle_bonus(ctx.author.id, amount)

        if result.get("already_claimed"):
            return await ctx.send(
                f"You already claimed `.daily` today. Effective plays used: **{result.get('effective_count', 0)}**"
            )

        await ctx.send(
            f"Daily bonus: **+{result['bonus_added']}** wordle play(s)\n"
            f"Effective games used today: **{result['effective_count']}**"
        )


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
    print("[daily] cog loaded")
