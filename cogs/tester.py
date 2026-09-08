"""
.tester <userID> — creator only, one server only, silent otherwise
Gives role 1545319674814791701 in guild 1545272798451343360
"""

from __future__ import annotations

import discord
from discord.ext import commands

CREATOR_ID = 1465295674768883889
TESTER_SERVER_ID = 1545272798451343360
TESTER_ROLE_ID = 1545319674814791701


def member_has_tester_role(member: discord.Member | None) -> bool:
    if member is None:
        return False
    return any(r.id == TESTER_ROLE_ID for r in getattr(member, "roles", []))


def user_has_tester_access(user: discord.abc.User, guild: discord.Guild | None, bot=None) -> bool:
    """True if user has tester role in the allowed server (or is that member)."""
    if user.id == CREATOR_ID:
        return True
    if guild and guild.id == TESTER_SERVER_ID:
        m = guild.get_member(user.id)
        if member_has_tester_role(m):
            return True
    # Check the home server even when command runs elsewhere
    if bot is not None:
        home = bot.get_guild(TESTER_SERVER_ID)
        if home:
            m = home.get_member(user.id)
            if member_has_tester_role(m):
                return True
    return False


class TesterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="tester")
    async def tester_cmd(self, ctx: commands.Context, user_id: str = None):
        # Silent if wrong server
        if not ctx.guild or ctx.guild.id != TESTER_SERVER_ID:
            return
        # Silent if not creator
        if ctx.author.id != CREATOR_ID:
            return
        if not user_id:
            return
        uid = user_id.strip().replace("<@", "").replace("!", "").replace(">", "")
        if not uid.isdigit():
            return

        role = ctx.guild.get_role(TESTER_ROLE_ID)
        if role is None:
            try:
                await ctx.send("Tester role not found.", delete_after=8)
            except Exception:
                pass
            return

        member = ctx.guild.get_member(int(uid))
        if member is None:
            try:
                member = await ctx.guild.fetch_member(int(uid))
            except Exception:
                try:
                    await ctx.send("User not in this server.", delete_after=8)
                except Exception:
                    pass
                return

        try:
            await member.add_roles(role, reason="tester grant")
            await ctx.send(f"Gave tester role to {member.mention}", delete_after=10)
        except Exception as e:
            try:
                await ctx.send(f"Failed: {e}", delete_after=10)
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(TesterCog(bot))
