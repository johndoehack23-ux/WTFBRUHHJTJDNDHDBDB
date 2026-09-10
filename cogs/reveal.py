import discord
from discord.ext import commands
from functions import *
from editrespond import r

CREATOR_ID = 1465295674768883889


def _can_reveal_global(user) -> bool:
    from functions import is_op
    return user.id == CREATOR_ID or is_op(user.id)


def _format_reveal_line(channel_id, server_name, wordle_word, mode_word) -> str:
    has_w = bool(wordle_word)
    has_m = bool(mode_word)
    if has_w and has_m:
        tag = "(wordle & mode)"
        words = f"**{wordle_word}** **{mode_word}**"
    elif has_w:
        tag = "(wordle)"
        words = f"**{wordle_word}**"
    elif has_m:
        tag = "(mode)"
        words = f"**{mode_word}**"
    else:
        tag = "(none)"
        words = "**?**"
    return f"<#{channel_id}> ({server_name}): {words} {tag}"


class RevealCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reveal")
    async def reveal_prefix(self, ctx, scope: str = None):
        if not is_admin(ctx.author.id) and not _can_reveal_global(ctx.author):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id) and not _can_reveal_global(ctx.author):
            return await ctx.send(r("maintenance", "on"))

        scope_l = (scope or "").lower().strip()

        if scope_l == "global":
            if not _can_reveal_global(ctx.author):
                return
            lines = self._collect_all_reveals()
            if not lines:
                return await ctx.send("No active wordle or mode games globally.")
            chunks, buf, size = [], [], 0
            for line in lines:
                if size + len(line) + 1 > 1900:
                    chunks.append("\n".join(buf))
                    buf, size = [line], len(line)
                else:
                    buf.append(line)
                    size += len(line) + 1
            if buf:
                chunks.append("\n".join(buf))
            for chunk in chunks:
                await ctx.send(chunk)
            await send_debug_msg(
                self.bot,
                f"🔍 `.reveal global` | {ctx.author} (`{ctx.author.id}`) revealed {len(lines)} channel(s)",
            )
            return

        channel_id = ctx.channel.id
        wordle_word = None
        mode_word = None

        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            mode_word = match["secret"].upper() if match.get("secret") else "Not started yet"

        for key, g in list(active_games.items()):
            if not isinstance(g, dict) or g.get("practice"):
                continue
            try:
                cid = int(key)
            except (TypeError, ValueError):
                continue
            if cid == channel_id and g.get("secret"):
                wordle_word = g["secret"].upper()
                break

        if wordle_word or mode_word is not None:
            gname = ctx.guild.name if ctx.guild else "?"
            await ctx.send(_format_reveal_line(channel_id, gname, wordle_word, mode_word))
            await send_debug_msg(
                self.bot,
                f"🔍 `.reveal` | {ctx.author} (`{ctx.author.id}`)",
                guild_id=ctx.guild.id if ctx.guild else None,
            )
            return

        if not ctx.guild:
            return
        lines = self._collect_server_reveals(ctx.guild)
        if not lines:
            return await ctx.send("No active game or 1v1 match in this server.")
        await ctx.send("\n".join(lines))
        await send_debug_msg(
            self.bot,
            f"🔍 `.reveal` | {ctx.author} (`{ctx.author.id}`) revealed {len(lines)} | {ctx.guild.name}",
            guild_id=ctx.guild.id,
        )

    def _collect_server_reveals(self, guild) -> list:
        by_ch = {}
        for key, g in list(active_games.items()):
            if not isinstance(g, dict) or g.get("practice"):
                continue
            if g.get("guild_id") != guild.id:
                continue
            try:
                cid = int(key)
            except (TypeError, ValueError):
                continue
            if g.get("secret"):
                by_ch.setdefault(cid, {})["wordle"] = g["secret"].upper()
        for cid, match in list(active_1v1_matches.items()):
            if not isinstance(match, dict):
                continue
            if match.get("guild_id") != guild.id:
                continue
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            by_ch.setdefault(cid, {})["mode"] = (
                match["secret"].upper() if match.get("secret") else "Not started yet"
            )
        return [
            _format_reveal_line(cid, guild.name, data.get("wordle"), data.get("mode"))
            for cid, data in sorted(by_ch.items())
        ]

    def _collect_all_reveals(self) -> list:
        by_ch = {}
        for key, g in list(active_games.items()):
            if not isinstance(g, dict) or g.get("practice"):
                continue
            try:
                cid = int(key)
            except (TypeError, ValueError):
                continue
            if not g.get("secret"):
                continue
            gid = g.get("guild_id")
            guild = self.bot.get_guild(int(gid)) if gid else None
            name = guild.name if guild else f"server {gid}"
            by_ch.setdefault(cid, {"guild_name": name, "wordle": None, "mode": None})
            by_ch[cid]["wordle"] = g["secret"].upper()
            by_ch[cid]["guild_name"] = name
        for cid, match in list(active_1v1_matches.items()):
            if not isinstance(match, dict):
                continue
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            gid = match.get("guild_id")
            guild = self.bot.get_guild(int(gid)) if gid else None
            name = guild.name if guild else f"server {gid}"
            by_ch.setdefault(cid, {"guild_name": name, "wordle": None, "mode": None})
            by_ch[cid]["mode"] = match["secret"].upper() if match.get("secret") else "Not started yet"
            by_ch[cid]["guild_name"] = name
        return [
            _format_reveal_line(cid, data.get("guild_name") or "?", data.get("wordle"), data.get("mode"))
            for cid, data in sorted(by_ch.items())
        ]


async def setup(bot):
    await bot.add_cog(RevealCog(bot))
