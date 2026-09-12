"""
Slash: /arole  (fresh command id — avoids stuck /autorole not showing)
Prefix: .autorole / .arole
Toggle: /autorole_toggle
"""

from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord import app_commands
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


async def backfill_roles(guild, member_role, bot_role, bots_enabled):
    members_ok = bots_ok = fail = 0
    me = guild.me
    for member in list(guild.members):
        try:
            if member.bot:
                if bots_enabled and bot_role and bot_role not in member.roles:
                    if me and me.top_role <= bot_role:
                        fail += 1
                        continue
                    await member.add_roles(bot_role, reason="Autorole backfill (bot)")
                    bots_ok += 1
                    await asyncio.sleep(0.35)
            else:
                if member_role and member_role not in member.roles:
                    if me and me.top_role <= member_role:
                        fail += 1
                        continue
                    await member.add_roles(member_role, reason="Autorole backfill (member)")
                    members_ok += 1
                    await asyncio.sleep(0.35)
        except (discord.Forbidden, discord.HTTPException):
            fail += 1
    return members_ok, bots_ok, fail


class AutoRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _do_set(
        self,
        ctx: commands.Context,
        member_role: Optional[discord.Role],
        bots: bool,
        bot_role: Optional[discord.Role],
        enabled: bool,
    ):
        if not ctx.guild:
            return await ctx.send("Server only.", ephemeral=bool(ctx.interaction))
        if not can_manage(ctx.author, ctx.guild):
            return await ctx.send("No permission.", ephemeral=bool(ctx.interaction))

        # No role given → status
        if member_role is None:
            cfg = get_cfg(ctx.guild.id)
            mr = f"<@&{cfg['member_role']}>" if cfg.get("member_role") else "not set"
            br = f"<@&{cfg['bot_role']}>" if cfg.get("bot_role") else "not set"
            return await ctx.send(
                "\n".join([
                    f"**Autorole:** {'ON' if cfg.get('enabled') else 'OFF'}",
                    f"Member: {mr} · Bot: {br} (bots: {'yes' if cfg.get('bots_enabled') else 'no'})",
                    "Set: `/arole` or `.autorole @MemberRole true/false [@BotRole]`",
                ]),
                ephemeral=bool(ctx.interaction),
            )

        if bots and bot_role is None:
            return await ctx.send(
                "`bot_role` is required when bots is True.",
                ephemeral=bool(ctx.interaction),
            )

        cfg = get_cfg(ctx.guild.id)
        cfg["member_role"] = str(member_role.id)
        cfg["bots_enabled"] = bool(bots)
        cfg["bot_role"] = str(bot_role.id) if bot_role else None
        cfg["enabled"] = bool(enabled)
        save_cfg(ctx.guild.id, cfg)

        await ctx.send(
            f"Autorole saved · members → {member_role.mention}"
            + (f" · bots → {bot_role.mention}" if bots and bot_role else "")
            + f" · **{'ON' if enabled else 'OFF'}** — applying…",
            ephemeral=bool(ctx.interaction),
        )

        if enabled:
            m_ok, b_ok, fail = await backfill_roles(
                ctx.guild, member_role, bot_role if bots else None, bots
            )
            await ctx.send(
                f"Backfill · members **{m_ok}** · bots **{b_ok}** · failed **{fail}**",
                ephemeral=bool(ctx.interaction),
            )

    # NEW slash name so Discord creates a fresh command (old /autorole was stuck hidden)
    @commands.hybrid_command(
        name="arole",
        aliases=["autorole", "setautorole"],
        description="Autorole: set member/bot roles and apply to everyone in the server",
        with_app_command=True,
    )
    @app_commands.describe(
        member_role="Role for members (leave empty for status)",
        bots="Also assign bot_role to bots",
        bot_role="Role for bots (required if bots=True)",
        enabled="Enable autorole after save",
    )
    @app_commands.guild_only()
    async def arole(
        self,
        ctx: commands.Context,
        member_role: Optional[discord.Role] = None,
        bots: bool = False,
        bot_role: Optional[discord.Role] = None,
        enabled: bool = True,
    ):
        await self._do_set(ctx, member_role, bots, bot_role, enabled)

    @commands.hybrid_command(
        name="autorole_toggle",
        description="Turn autorole on or off",
        with_app_command=True,
    )
    @app_commands.describe(enabled="Enable or disable autorole")
    @app_commands.guild_only()
    async def autorole_toggle(self, ctx: commands.Context, enabled: bool):
        if not ctx.guild:
            return await ctx.send("Server only.", ephemeral=bool(ctx.interaction))
        if not can_manage(ctx.author, ctx.guild):
            return await ctx.send("No permission.", ephemeral=bool(ctx.interaction))
        cfg = get_cfg(ctx.guild.id)
        cfg["enabled"] = bool(enabled)
        save_cfg(ctx.guild.id, cfg)
        await ctx.send(
            f"Autorole **{'ON' if enabled else 'OFF'}**",
            ephemeral=bool(ctx.interaction),
        )

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
            print(f"[autorole] join fail: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleCog(bot))
    print("[autorole] loaded — slash: /arole  prefix: .autorole .arole")
