"""
.tester <userID> — creator only, tester server only
.tester set <roleID> — change tester role id (creator only)
"""

from __future__ import annotations

import discord
from discord.ext import commands

from functions import (
    get_tester_role_id,
    set_tester_role_id,
    get_tester_server_id,
    user_has_tester_role,
)

CREATOR_ID = 1465295674768883889


class TesterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="tester", invoke_without_command=True)
    async def tester_group(self, ctx: commands.Context, user_id: str = None):
        # Silent outside tester server
        if not ctx.guild or ctx.guild.id != get_tester_server_id():
            return
        # Silent if not creator
        if ctx.author.id != CREATOR_ID:
            return

        if not user_id:
            try:
                await ctx.send(
                    f"Tester role: `{get_tester_role_id()}`\n"
                    f"`.tester <userID>` · `.tester set <roleID>`",
                    delete_after=12,
                )
            except Exception:
                pass
            return

        uid = user_id.strip().replace("<@", "").replace("!", "").replace(">", "")
        if not uid.isdigit():
            return

        role = ctx.guild.get_role(get_tester_role_id())
        if role is None:
            try:
                await ctx.send("Tester role not found. Use `.tester set <roleID>`.", delete_after=10)
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

    @tester_group.command(name="set")
    async def tester_set(self, ctx: commands.Context, role_id: str = None):
        if not ctx.guild or ctx.guild.id != get_tester_server_id():
            return
        if ctx.author.id != CREATOR_ID:
            return
        if not role_id:
            return await ctx.send(f"Current tester role: `{get_tester_role_id()}`", delete_after=10)

        rid = role_id.strip().replace("<@&", "").replace(">", "")
        if not rid.isdigit():
            return await ctx.send("Provide a numeric roleID.", delete_after=8)

        role = ctx.guild.get_role(int(rid))
        set_tester_role_id(int(rid))
        if role:
            await ctx.send(f"Tester role set to {role.mention} (`{rid}`)", delete_after=12)
        else:
            await ctx.send(f"Tester role set to `{rid}` (role not in this server cache)", delete_after=12)


async def setup(bot):
    await bot.add_cog(TesterCog(bot))
