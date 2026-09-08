import discord
from discord.ext import commands
import random
from functions import *
from editrespond import r


def _has_tester_or_admin(user, guild, bot=None):
    from functions import is_admin, is_op
    CREATOR_ID = 1465295674768883889
    TESTER_ROLE_ID = 1545319674814791701
    TESTER_SERVER_ID = 1545272798451343360
    if user.id == CREATOR_ID or is_op(user.id) or is_admin(user.id, guild):
        return True
    if isinstance(user, discord.Member) and any(r.id == TESTER_ROLE_ID for r in user.roles):
        return True
    if bot is not None:
        home = bot.get_guild(TESTER_SERVER_ID)
        if home:
            m = home.get_member(user.id)
            if m and any(r.id == TESTER_ROLE_ID for r in m.roles):
                return True
    return False



class HintCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="hint")
    async def hint(self, ctx):
        if not is_admin(ctx.author.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send(r("maintenance", "on"))

        # All non-practice games in this server (supports multiple channels)
        games = []
        for key, g in list(active_games.items()):
            if not isinstance(g, dict):
                continue
            if g.get("guild_id") != ctx.guild.id:
                continue
            if g.get("practice"):
                continue
            try:
                channel_id = int(key)
            except (TypeError, ValueError):
                continue
            games.append((channel_id, g))

        if not games:
            return await ctx.send(r("hint", "no_game"))

        lines = []
        revealed_any = False
        for channel_id, g in games:
            length = int(g.get("length") or len(g.get("secret") or ""))
            secret = g.get("secret") or ""
            if not secret or length <= 0:
                lines.append(f"<#{channel_id}>: —")
                continue

            avail = [i for i in range(length) if i not in g.get("revealed_indices", [])]
            if not avail:
                lines.append(f"<#{channel_id}>: (no more hints)")
                continue

            idx = random.choice(avail)
            g.setdefault("revealed_indices", []).append(idx)
            letter = secret[idx].upper()
            lines.append(f"<#{channel_id}>: **{letter}**")
            revealed_any = True

        if not revealed_any and all("(no more" in ln for ln in lines):
            return await ctx.send(r("hint", "no_more"))

        await ctx.send("\n".join(lines))
        await send_debug_msg(
            self.bot,
            f"💡 `.hint` | {ctx.author} (`{ctx.author.id}`) hinted {len(games)} channel(s) "
            f"| #{ctx.channel.name} | {ctx.guild.name}",
            guild_id=ctx.guild.id,
        )


async def setup(bot):
    await bot.add_cog(HintCog(bot))
