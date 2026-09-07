"""
.extrahelp — DM only
Trusted / Admin / Op / Server owner (owner needs a mutual guild context via optional mention - in DMs we check ownership of any mutual guild or stored role).
"""

from __future__ import annotations

import discord
from discord.ext import commands

from functions import load_stats, is_admin, is_op

CREATOR_ID = 1465295674768883889


def _is_server_owner_anywhere(user: discord.User, bot) -> bool:
    for g in bot.guilds:
        if g.owner_id == user.id:
            return True
    return False


def _tier(user: discord.User, bot) -> str | None:
    """Return op | admin | owner | trusted | None"""
    if user.id == CREATOR_ID or is_op(user.id):
        return "op"
    if is_admin(user.id):
        return "admin"
    if _is_server_owner_anywhere(user, bot):
        return "owner"
    # trusted in any mutual guild
    try:
        stats = load_stats()
        trusted = stats.get("trusted_users") or {}
        for gid, pool in trusted.items():
            if str(user.id) in [str(x) for x in (pool or [])]:
                return "trusted"
    except Exception:
        pass
    return None


def _build_embed(tier: str, prefix: str = ".") -> discord.Embed:
    embed = discord.Embed(title="Extra Help", color=0x2f3136)

    trusted_cmds = (
        f"`{prefix}wordle` — play / custom tools you have access to\n"
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
        f"`{prefix}media` / `{prefix}selfpromo` (slash)"
    )
    op_cmds = (
        f"`{prefix}give op`\n"
        f"`{prefix}leave`\n"
        f"`/panel`\n"
        f"All admin + trusted + owner tools"
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
    return embed


class ExtraHelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="extrahelp")
    async def extrahelp(self, ctx: commands.Context):
        # DM only
        if ctx.guild is not None:
            return await ctx.send("Use this command in DMs only.")

        tier = _tier(ctx.author, self.bot)
        if not tier:
            return await ctx.send("No access.")

        stats = load_stats()
        prefix = stats.get("prefix", ".")
        embed = _build_embed(tier, prefix)
        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(ExtraHelpCog(bot))
