"""
.extrahelp — works in DMs (and can be used in servers; prefers DMs)
Trusted / Admin / Op / Server owner
Reply auto-deletes after 10 minutes.
"""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from functions import get_tester_role_id, load_stats, is_admin, is_op

CREATOR_ID = 1465295674768883889
TESTER_ROLE_ID = 1545319674814791701
TESTER_SERVER_ID = 1545272798451343360
DELETE_AFTER_SECS = 10 * 60  # 10 minutes


def _is_server_owner_anywhere(user: discord.User, bot) -> bool:
    for g in bot.guilds:
        if g.owner_id == user.id:
            return True
    return False


def _has_tester_role(user, bot) -> bool:
    home = bot.get_guild(TESTER_SERVER_ID) if bot else None
    if not home:
        return False
    m = home.get_member(user.id)
    return bool(m and any(r.id == get_tester_role_id() for r in m.roles))


def _tier(user: discord.User, bot) -> str | None:
    if user.id == CREATOR_ID or is_op(user.id):
        return "op"
    try:
        if is_admin(user.id):
            return "admin"
    except TypeError:
        try:
            if is_admin(user.id, None):
                return "admin"
        except Exception:
            pass
    if _has_tester_role(user, bot):
        return "admin"
    if _is_server_owner_anywhere(user, bot):
        return "owner"
    try:
        stats = load_stats()
        trusted = stats.get("trusted_users") or {}
        for _gid, pool in trusted.items():
            if str(user.id) in [str(x) for x in (pool or [])]:
                return "trusted"
    except Exception:
        pass
    return None


def _build_embed(tier: str, prefix: str = ".") -> discord.Embed:
    embed = discord.Embed(title="Extra Help", color=0x2f3136)

    trusted_cmds = (
        f"`{prefix}wordle` — play / tools you can use\n"
        f"`/say` — send as bot\n"
        f"`/autoresponder` — manage autoresponders"
    )
    admin_cmds = (
        f"`{prefix}hint` / `{prefix}reveal` / `{prefix}eg`\n"
        f"`{prefix}give trusted/admin`\n"
        f"`{prefix}difficulty`\n"
        f"`{prefix}streak set/reset`\n"
        f"`{prefix}rlb`"
    )
    owner_cmds = (
        f"`{prefix}antinuke` / `{prefix}au` enable|disable|config\n"
        f"`{prefix}whitelist` / `{prefix}wl` <userID/roleID>\n"
        f"`{prefix}extraowner` add|remove|list\n"
        f"`{prefix}automod` / `{prefix}am` enable|disable|config|debug\n"
        f"`{prefix}opsafe` enable|disable|unlock|config\n"
        f"`{prefix}autorole`\n"
        f"`/media` / `/selfpromo`"
    )
    op_cmds = (
        f"`{prefix}give op`\n"
        f"`{prefix}leave`\n"
        f"`/panel`\n"
        f"All trusted + admin + owner tools"
    )

    if tier == "trusted":
        embed.description = "**Trusted commands**"
        embed.add_field(name="Trusted", value=trusted_cmds, inline=False)
    elif tier == "admin":
        embed.description = "**Admin commands**"
        embed.add_field(name="Admin", value=admin_cmds, inline=False)
    elif tier == "owner":
        embed.description = "**Server owner commands**"
        embed.add_field(name="Server owner", value=owner_cmds, inline=False)
    elif tier == "op":
        embed.description = "**Operator — full list**"
        embed.add_field(name="Trusted", value=trusted_cmds, inline=False)
        embed.add_field(name="Admin", value=admin_cmds, inline=False)
        embed.add_field(name="Server owner", value=owner_cmds, inline=False)
        embed.add_field(name="Op", value=op_cmds, inline=False)
    else:
        embed.description = "No access."
    embed.set_footer(text="This message deletes in 10 minutes")
    return embed


async def _delete_later(*messages: discord.Message | None, delay: float = DELETE_AFTER_SECS):
    await asyncio.sleep(delay)
    for m in messages:
        if m is None:
            continue
        try:
            await m.delete()
        except Exception:
            pass


class ExtraHelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="extrahelp")
    async def extrahelp(self, ctx: commands.Context):
        # Prefer DMs: if used in a server, still respond but note DMs
        tier = _tier(ctx.author, self.bot)
        if not tier:
            msg = await ctx.reply("No access.")
            self.bot.loop.create_task(_delete_later(msg, ctx.message))
            return

        stats = load_stats()
        prefix = stats.get("prefix", ".")
        embed = _build_embed(tier, prefix)

        try:
            reply = await ctx.reply(embed=embed)
        except discord.HTTPException:
            reply = await ctx.send(embed=embed)

        # Delete bot reply + user command after 10 minutes
        self.bot.loop.create_task(_delete_later(reply, ctx.message))


async def setup(bot):
    await bot.add_cog(ExtraHelpCog(bot))
    print("[extrahelp] cog loaded")
