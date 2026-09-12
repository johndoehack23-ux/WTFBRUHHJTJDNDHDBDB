"""
.quest — randomized daily quests (messages / wordle / both)
Everyone can use it. Progress bar emojis from emoji.json
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
    format_quest_reset_footer,
    _complete_quest_item,
    _load_quests,
    _save_quests,
)

EMOJI_FILE = Path(__file__).resolve().parent.parent / "emoji.json"
BAR_LEN = 10


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


def _build_bar(ratio: float) -> str:
    """
    <50%  : white fill + white back
    >=50% and <100%: red fill + green back
    100%  : all green
    """
    em = _load_progress_emojis()
    white = em["1"]
    red = em["2"]
    green = em["3"]

    filled = int(round(min(1.0, max(0.0, ratio)) * BAR_LEN))
    filled = max(0, min(BAR_LEN, filled))
    empty_n = BAR_LEN - filled

    if ratio >= 1.0:
        return green * BAR_LEN
    if ratio >= 0.5:
        return (red * filled) + (green * empty_n)
    return (white * filled) + (white * empty_n)


def _item_line(item: dict) -> str:
    n = int(item.get("id", 1))
    goal = max(1, int(item.get("goal", 0) or 0))
    prog = int(item.get("progress", 0) or 0)
    if prog >= goal:
        prog = goal
        item["completed"] = True
    reward = int(item.get("reward", 1))
    remaining = max(0, goal - prog)
    ratio = prog / goal
    bar = _build_bar(min(1.0, ratio))
    done = bool(item.get("completed")) or prog >= goal

    if item.get("type") == "messages":
        if done:
            body = f"**Send {goal} messages to get {reward}× wordle tries** ✅ DONE ({prog}/{goal})"
        else:
            body = f"**Send {remaining} messages to get {reward}× wordle tries** ({prog}/{goal})"
    else:
        if done:
            body = f"**Play {goal} wordle game(s) to get {reward}× wordle use** ✅ DONE ({prog}/{goal})"
        else:
            body = f"**Play {remaining} wordle game(s) to get {reward}× wordle use** ({prog}/{goal})"

    return f"{n}. {body}\n{bar}"


def _quest_description(pack: dict) -> str:
    lines = [_item_line(item) for item in (pack.get("quests") or [])]
    return "\n\n".join(lines) if lines else "No quests today."


class QuestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quest")
    async def quest_cmd(self, ctx: commands.Context):
        # Everyone can use .quest
        pack = get_user_quest(ctx.author.id)
        if pack is None:
            pack = start_user_quest(ctx.author.id)

        # Finalize quests that already hit the goal
        try:
            changed = False
            for item in pack.get("quests") or []:
                goal = int(item.get("goal", 0) or 0)
                prog = int(item.get("progress", 0) or 0)
                if goal and prog >= goal and not item.get("completed"):
                    _complete_quest_item(ctx.author.id, item)
                    changed = True
            if changed:
                data = _load_quests()
                data.setdefault("users", {})[str(ctx.author.id)] = pack
                _save_quests(data)
        except Exception as e:
            print(f"[quest] finalize fail: {e}")

        embed = discord.Embed(
            title="📜 Quest",
            description=_quest_description(pack),
            color=0x2B2D31,
        )
        embed.set_footer(text=format_quest_reset_footer())
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        pack = get_user_quest(message.author.id)
        if not pack:
            return
        increment_quest_progress(message.author.id, 1, qtype="messages")


async def setup(bot):
    await bot.add_cog(QuestCog(bot))
    print("[quest] cog loaded")
