"""
.quest — daily global message quest (activates only when user runs .quest)
Progress bar uses progress1/2/3 emojis from emoji.json
"""

from __future__ import annotations

import json
from pathlib import Path

import discord
from discord.ext import commands

from functions import (
    get_user_quest,
    start_user_quest,
    increment_quest_progress,
    quest_remaining,
)

EMOJI_FILE = Path(__file__).resolve().parent.parent / "emoji.json"
BAR_LEN = 10  # |||||||||| style — 10 segments


def _load_progress_emojis() -> dict:
    defaults = {
        "1": "<:progress1:1547168443659452446>",
        "2": "<:progress2:1547168483135979552>",
        "3": "<:progress3:1547168511753723955>",
    }
    try:
        data = json.loads(EMOJI_FILE.read_text(encoding="utf-8"))
        prog = data.get("progress") or {}
        return {
            "1": prog.get("1") or defaults["1"],
            "2": prog.get("2") or defaults["2"],
            "3": prog.get("3") or defaults["3"],
        }
    except Exception:
        return defaults


def _progress_ratio(q: dict) -> float:
    goal = max(1, int(q.get("goal", 500)))
    prog = max(0, int(q.get("progress", 0)))
    return min(1.0, prog / goal)


def _build_bar(ratio: float) -> str:
    """
    Classic |||||||||| bar (10 segments).
    <50%  : white fill (progress1)
    ==50% : green fill (progress3)
    >50% and <100%: red fill (progress2)
    100%  : all green (progress3)
    Empty remainder always white (progress1).
    """
    em = _load_progress_emojis()
    white = em["1"]
    red = em["2"]
    green = em["3"]

    filled = int(round(ratio * BAR_LEN))
    filled = max(0, min(BAR_LEN, filled))
    empty_n = BAR_LEN - filled

    if ratio >= 1.0:
        return green * BAR_LEN
    if ratio > 0.5:
        fill_emoji = red
    elif abs(ratio - 0.5) < 1e-9 or (filled == BAR_LEN // 2 and ratio >= 0.5):
        fill_emoji = green
    elif ratio >= 0.5:
        fill_emoji = green
    else:
        fill_emoji = white

    return (fill_emoji * filled) + (white * empty_n)


def _quest_text(q: dict) -> str:
    remaining = quest_remaining(q)
    reward = int(q.get("reward", 1))
    goal = int(q.get("goal", 500))
    prog = int(q.get("progress", 0))
    ratio = _progress_ratio(q)
    bar = _build_bar(ratio)

    if q.get("completed"):
        line = f"1. **Send {goal} messages to get {reward}× wordle tries** ✅ DONE ({prog}/{goal})"
    else:
        line = f"1. **Send {remaining} messages to get {reward}× wordle tries** ({prog}/{goal})"

    return f"{line}\n{bar}"


class QuestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quest")
    async def quest_cmd(self, ctx: commands.Context):
        q = get_user_quest(ctx.author.id)
        if q is None:
            q = start_user_quest(ctx.author.id, goal=500)

        embed = discord.Embed(
            title="📜 Quest",
            description=_quest_text(q),
            color=0x2B2D31,
        )
        if q.get("completed"):
            embed.set_footer(text="Quest complete — bonus wordle tries granted!")
        else:
            embed.set_footer(text="Quest is active today · messages in any shared server count")

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        q = get_user_quest(message.author.id)
        if not q:
            return
        if q.get("completed") or q.get("claimed"):
            return
        increment_quest_progress(message.author.id, 1)


async def setup(bot):
    await bot.add_cog(QuestCog(bot))
    print("[quest] cog loaded")
