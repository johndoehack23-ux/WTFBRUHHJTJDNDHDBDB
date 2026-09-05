"""
.autorole <role> <true/false> [botRole]
.autorole on/off | true/false
"""

from __future__ import annotations

import discord
from discord.ext import commands

from functions import load_stats, save_stats, is_admin, is_op

CREATOR_ID = 1465295674768883889


def can_manage(user, guild) -> bool:
    if user.id == CREATOR_ID or is_op(user.id):
        return True
    if guild and guild.owner_id == user.id:
        return True
    if guild and is_admin(user.id, guild):
        return True
    return False


def get_cfg(guild_id) -> dict:
    stats = load_stats()
    raw = (stats.get("autorole") or {}).get(str(guild_id))
    if not isinstance(raw, dict):
        return {"enabled": False, "member_role": None, "bot_role": None, "bots_enabled": False}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "member_role": raw.get("member_role"),
        "bot_role": raw.get("bot_role"),
        "bots_enabled": bool(raw.get("bots_enabled", False)),
    }


def save_cfg(guild_id, cfg: dict):
    stats = load_stats()
    if "autorole" not in stats or not isinstance(stats["autorole"], dict):
        stats["autorole"] = {}
    stats["autorole"][str(guild_id)] = cfg
    save_stats(stats)


class AutoRoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="autorole")
    async def autorole_cmd(self, ctx: commands.Context, *args):
        if not ctx.guild:
            return
        if not can_manage(ctx.author, ctx.guild):
            return await ctx.send("❌ No permission.")

        if not args:
            cfg = get_cfg(ctx.guild.id)
            state = "ON" if cfg["enabled"] else "OFF"
            mr = f"<@&{cfg['member_role']}>" if cfg.get("member_role") else "not set"
            br = f"<@&{cfg['bot_role']}>" if cfg.get("bot_role") else "not set"
            return await ctx.send(
                f"**Autorole:** {state}\n"
                f"Member role: {mr}\n"
                f"Bot role: {br} (bots: {'yes' if cfg.get('bots_enabled') else 'no'})\n"
                f"Usage: `.autorole <@role> <true/false> [@botRole]` · `.autorole on/off`"
            )

        first = args[0].lower().strip()

        if first in ("on", "off", "true", "false", "enable", "disable"):
            cfg = get_cfg(ctx.guild.id)
            cfg["enabled"] = first in ("on", "true", "enable")
            save_cfg(ctx.guild.id, cfg)
            return await ctx.send(f"✅ Autorole **{'ON' if cfg['enabled'] else 'OFF'}**")

        if len(args) < 2:
            return await ctx.send("Usage: `.autorole <@role> <true/false> [@botRole]`")

        role_raw = args[0].replace("<@&", "").replace(">", "").strip()
        flag = args[1].lower().strip()
        if flag not in ("true", "false"):
            return await ctx.send("Second arg must be `true` or `false` (enable bot autorole).")
        bots_on = flag == "true"

        bot_role_id = None
        if bots_on:
            if len(args) < 3:
                return await ctx.send("Bot role is required when true: `.autorole <@role> true <@botRole>`")
            bot_role_id = args[2].replace("<@&", "").replace(">", "").strip()
            if not bot_role_id.isdigit():
                return await ctx.send("Invalid bot role.")
        elif len(args) >= 3:
            bot_role_id = args[2].replace("<@&", "").replace(">", "").strip()
            if bot_role_id and not bot_role_id.isdigit():
                bot_role_id = None

        if not role_raw.isdigit():
            return await ctx.send("Invalid member role.")

        member_role = ctx.guild.get_role(int(role_raw))
        if member_role is None:
            return await ctx.send("Member role not found.")

        bot_role = None
        if bot_role_id:
            bot_role = ctx.guild.get_role(int(bot_role_id))
            if bot_role is None:
                return await ctx.send("Bot role not found.")

        cfg = get_cfg(ctx.guild.id)
        cfg["member_role"] = str(member_role.id)
        cfg["bots_enabled"] = bots_on
        cfg["bot_role"] = str(bot_role.id) if bot_role else None
        cfg["enabled"] = True
        save_cfg(ctx.guild.id, cfg)

        msg = f"✅ Autorole set · members → {member_role.mention}"
        if bots_on and bot_role:
            msg += f" · bots → {bot_role.mention}"
        await ctx.send(msg)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = get_cfg(member.guild.id)
        if not cfg.get("enabled"):
            return
        try:
            if member.bot:
                if cfg.get("bots_enabled") and cfg.get("bot_role"):
                    role = member.guild.get_role(int(cfg["bot_role"]))
                    if role:
                        await member.add_roles(role, reason="Autorole (bot)")
            else:
                if cfg.get("member_role"):
                    role = member.guild.get_role(int(cfg["member_role"]))
                    if role:
                        await member.add_roles(role, reason="Autorole (member)")
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"[autorole] failed: {e}")


async def setup(bot):
    await bot.add_cog(AutoRoleCog(bot))
