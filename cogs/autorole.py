"""
/autorole — slash only
Assign member role (+ optional bot role) and backfill existing members/bots.
"""

from __future__ import annotations

import asyncio

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


async def backfill_roles(guild: discord.Guild, member_role: discord.Role | None, bot_role: discord.Role | None, bots_enabled: bool):
    """Give roles to members/bots already in the server (no rejoin needed)."""
    members_ok = 0
    bots_ok = 0
    fail = 0
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
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="autorole", description="Set autorole for members (+ optional bots) and apply to everyone already in the server")
    @app_commands.describe(
        member_role="Role given to human members",
        bots="true = also give bots a role / false = members only",
        bot_role="Role for Discord bots (required if bots=true)",
        enabled="Turn autorole on/off (default true when setting roles)",
    )
    @app_commands.choices(
        bots=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
        enabled=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
    )
    async def autorole_slash(
        self,
        interaction: discord.Interaction,
        member_role: discord.Role,
        bots: app_commands.Choice[str],
        bot_role: discord.Role = None,
        enabled: app_commands.Choice[str] = None,
    ):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not can_manage(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)

        bots_on = bots.value == "true"
        if bots_on and bot_role is None:
            return await interaction.response.send_message(
                "bot_role is required when bots is true.", ephemeral=True
            )

        on = True if enabled is None else enabled.value == "true"

        cfg = get_cfg(interaction.guild.id)
        cfg["member_role"] = str(member_role.id)
        cfg["bots_enabled"] = bots_on
        cfg["bot_role"] = str(bot_role.id) if bot_role else None
        cfg["enabled"] = on
        save_cfg(interaction.guild.id, cfg)

        await interaction.response.send_message(
            f"Autorole saved · members → {member_role.mention}"
            + (f" · bots → {bot_role.mention}" if bots_on and bot_role else "")
            + f" · **{'ON' if on else 'OFF'}**\nApplying to existing members/bots…",
            ephemeral=True,
        )

        if on:
            m_ok, b_ok, fail = await backfill_roles(
                interaction.guild, member_role, bot_role if bots_on else None, bots_on
            )
            try:
                await interaction.followup.send(
                    f"Backfill done · members updated: **{m_ok}** · bots updated: **{b_ok}** · failed: **{fail}**",
                    ephemeral=True,
                )
            except Exception:
                pass

    @app_commands.command(name="autorole_toggle", description="Turn autorole on or off for this server")
    @app_commands.describe(state="on or off")
    @app_commands.choices(
        state=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def autorole_toggle(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not can_manage(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        cfg = get_cfg(interaction.guild.id)
        cfg["enabled"] = state.value == "on"
        save_cfg(interaction.guild.id, cfg)
        await interaction.response.send_message(
            f"Autorole **{'ON' if cfg['enabled'] else 'OFF'}**", ephemeral=True
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


async def setup(bot):
    await bot.add_cog(AutoRoleCog(bot))
