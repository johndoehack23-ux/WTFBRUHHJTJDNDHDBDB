import discord
from discord.ext import commands
from functions import *

CREATOR_ID = 1465295674768883889
MAX_WORDLE_CHANNELS = 5


def _parse_channel_ids(raw: str):
    """
    Parses a comma-separated string of channel IDs or #mentions.
    Returns (ids: list[str], bad_pieces: list[str]).
    """
    ids = []
    bad = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        cleaned = piece.strip("<#>")
        if cleaned.isdigit():
            ids.append(cleaned)
        else:
            bad.append(piece)
    return ids, bad


class SetWordleCog(commands.Cog):
    """
    Creator-only, prefix-only command:
      .setwordle <channelID / #mention>
      .setwordle <id1,id2,id3>      -> up to 5, comma-separated
      .setwordle clear              -> remove the restriction
    Restricts .wordle / /wordle to only work in the listed channel(s)
    for the server the command is run in. Each run REPLACES the list —
    it's not additive, so include every channel you want each time.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setwordle")
    async def setwordle(self, ctx, *, channels: str = None):
        if ctx.author.id != CREATOR_ID:
            return  # silent for everyone else

        if not ctx.guild:
            return

        if not channels:
            return await ctx.send(
                "❌ Usage: `.setwordle <channelID/#mention>` or "
                "`.setwordle <id1,id2,id3>` (max 5, comma-separated).\n"
                "Use `.setwordle clear` to remove the restriction."
            )

        if channels.strip().lower() == "clear":
            stats = load_stats()
            if "wordle_channels" in stats and str(ctx.guild.id) in stats["wordle_channels"]:
                del stats["wordle_channels"][str(ctx.guild.id)]
                save_stats(stats)
            await ctx.send("✅ Wordle channel restriction cleared — `.wordle`/`/wordle` can be played anywhere in this server again.")
            await send_debug_msg(
                self.bot,
                f"🎯 `.setwordle clear` | {ctx.author} (`{ctx.author.id}`) cleared wordle channel restriction | {ctx.guild.name}"
            )
            return

        ids, bad = _parse_channel_ids(channels)

        if bad:
            return await ctx.send(f"❌ Couldn't parse: {', '.join(bad)} — use channel IDs or #mentions.")

        if not ids:
            return await ctx.send("❌ No valid channel IDs found.")

        # de-dupe, keep order
        seen, deduped = set(), []
        for cid in ids:
            if cid not in seen:
                seen.add(cid)
                deduped.append(cid)
        ids = deduped

        if len(ids) > MAX_WORDLE_CHANNELS:
            return await ctx.send(f"❌ Max {MAX_WORDLE_CHANNELS} channels — you gave {len(ids)}.")

        stats = load_stats()
        if "wordle_channels" not in stats or not isinstance(stats["wordle_channels"], dict):
            stats["wordle_channels"] = {}
        stats["wordle_channels"][str(ctx.guild.id)] = ids
        save_stats(stats)

        mentions = ", ".join(f"<#{c}>" for c in ids)
        await ctx.send(f"✅ Wordle can now only be played in: {mentions}")
        await send_debug_msg(
            self.bot,
            f"🎯 `.setwordle` | {ctx.author} (`{ctx.author.id}`) restricted wordle to {mentions} | {ctx.guild.name}"
        )


async def setup(bot):
    await bot.add_cog(SetWordleCog(bot))
