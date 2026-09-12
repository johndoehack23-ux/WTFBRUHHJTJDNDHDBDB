"""
.antibetray — Anti-Betray Freemium V1.5
Requires antinuke enabled. Access: creator, server owner, extraowner, op.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from functions import load_stats, save_stats, is_op

CREATOR_ID = 1465295674768883889

# Official Discord bots — auto bypass (public application IDs)
OFFICIAL_BOT_IDS = {
    159985870782969856,  # MEE6
    155149108183695360,  # Dyno
    235148962103833601,  # Carl-bot
    330916283065565181,  # Welcomer
    437808476106784770,  # Arcane
    172002275412279296,  # Tatsu
    204255221017214977,  # YAGPDB
    270904126974590976,  # Dank Memer
    557628352558202894,  # Ticket Tool
    282859044593598464,  # ProBot
    432610292342587392,  # Mudae
    536184844267716608,  # ServerStats / similar
    472909310210113557,  # UnbelievaBoat
    292953664492929025,  # NQN
    234395307759108106,  # Groovy successor / Auditus etc keep list focused
    705268070880051280,  # Discohook helper variants may change
}

EIGHT_MONTHS_SEC = 8 * 30 * 24 * 3600  # ~8 months


def _ab_cfg(guild_id) -> dict:
    stats = load_stats()
    raw = ((stats.get("antibetray") or {}).get(str(guild_id))) or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "bypass_users": [str(x) for x in (raw.get("bypass_users") or [])],
        "bypass_roles": [str(x) for x in (raw.get("bypass_roles") or [])],
    }


def _save_ab(guild_id, cfg: dict):
    stats = load_stats()
    if "antibetray" not in stats or not isinstance(stats["antibetray"], dict):
        stats["antibetray"] = {}
    stats["antibetray"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "bypass_users": list(cfg.get("bypass_users") or []),
        "bypass_roles": list(cfg.get("bypass_roles") or []),
    }
    save_stats(stats)


def is_antinuke_on(guild_id) -> bool:
    stats = load_stats()
    raw = ((stats.get("antinuke") or {}).get(str(guild_id))) or {}
    return bool(isinstance(raw, dict) and raw.get("enabled"))


def is_extraowner(guild_id, user_id) -> bool:
    stats = load_stats()
    raw = ((stats.get("antinuke") or {}).get(str(guild_id))) or {}
    return str(user_id) in (raw.get("extraowners") or [])


def can_antibetray(user, guild) -> bool:
    if user.id == CREATOR_ID or is_op(user.id):
        return True
    if guild and guild.owner_id == user.id:
        return True
    if guild and is_extraowner(guild.id, user.id):
        return True
    return False


def is_bypassed(guild_id, user_id, member: discord.Member | None = None) -> bool:
    if user_id == CREATOR_ID:
        return True
    if int(user_id) in OFFICIAL_BOT_IDS:
        return True
    cfg = _ab_cfg(guild_id)
    if str(user_id) in cfg["bypass_users"]:
        return True
    if member:
        role_ids = {str(r.id) for r in member.roles}
        if role_ids & set(cfg["bypass_roles"]):
            return True
    return False


def bot_above_admin_roles(guild: discord.Guild) -> bool:
    """Bot top role must sit above any role that has Administrator."""
    me = guild.me
    if not me:
        return False
    if me.guild_permissions.administrator:
        # still require height over other admin roles when possible
        pass
    my_pos = me.top_role.position
    for role in guild.roles:
        if role.is_default() or role.is_bot_managed():
            continue
        if role.permissions.administrator and role.position >= my_pos:
            return False
    return True


def _desc_main() -> str:
    return "\n".join([
        "Anti-Betray watches trusted people and new bots so a whitelist cannot quietly hand out Administrator and wreck the server.",
        "",
        "If only a whitelisted user or role is supposed to be safe, and that user gives someone a role with Administrator, the bot strips the Administrator role from the target and also strips dangerous roles from the person who handed it out.",
        "",
        "New bots with no profile picture, or bot accounts younger than about 8 months, are kicked on join unless you bypass them with `.antibetray bypass <botID>`.",
        "Official bots such as MEE6, Dyno, Carl-bot, Welcomer, Arcane, and similar are auto-bypassed.",
        "",
        "If a bypassed bot starts deleting channels, roles, or emojis, or mass bans or kicks members, it is banned immediately.",
        "",
        "Antinuke must be enabled before Anti-Betray can turn on. The bot role should sit above Administrator roles, except the bot creator can enable without that check.",
        "Use `.antibetray bypass <userID/roleID>` before enabling if you need staff or bots exempt.",
    ])


class AntiBetrayVerifyView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id

    @discord.ui.button(label="⚠️ Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_antibetray(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        if not is_antinuke_on(self.guild_id):
            return await interaction.response.send_message(
                "Enable **antinuke** first (`.antinuke enable`).", ephemeral=True
            )
        if interaction.user.id != CREATOR_ID and interaction.guild and not bot_above_admin_roles(interaction.guild):
            return await interaction.response.send_message(
                "Move the bot role **above** roles with Administrator, then try again.",
                ephemeral=True,
            )
        cfg = _ab_cfg(self.guild_id)
        cfg["enabled"] = True
        _save_ab(self.guild_id, cfg)
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title="Anti-Betray Freemium V1.5",
                description="**ENABLED.** Watching role grants and suspicious bots.",
                color=0x57F287,
            ),
            view=None,
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Cancelled.",
            embed=None,
            view=None,
        )


class AntiBetrayMainView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @discord.ui.button(label="Enable", style=discord.ButtonStyle.success)
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_antibetray(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        if not is_antinuke_on(self.guild_id):
            return await interaction.response.send_message(
                "Enable **antinuke** first.", ephemeral=True
            )
        # Creator skips hierarchy + goes through verify still
        embed = discord.Embed(
            title="Verify",
            description="⚠️ Are you sure you want to enable? Use `.antibetray bypass` first!",
            color=0xFEE75C,
        )
        await interaction.response.send_message(
            embed=embed, view=AntiBetrayVerifyView(self.guild_id), ephemeral=True
        )

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_antibetray(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        cfg = _ab_cfg(self.guild_id)
        cfg["enabled"] = False
        _save_ab(self.guild_id, cfg)
        await interaction.response.send_message("Anti-Betray **DISABLED**.", ephemeral=True)

    @discord.ui.button(label="Config", style=discord.ButtonStyle.primary)
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_antibetray(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        cfg = _ab_cfg(self.guild_id)
        users = ", ".join(f"`{u}`" for u in cfg["bypass_users"]) or "none"
        roles = ", ".join(f"`{r}`" for r in cfg["bypass_roles"]) or "none"
        embed = discord.Embed(
            title="Anti-Betray Config",
            description="\n".join([
                f"Enabled: **{cfg['enabled']}**",
                f"Bypass users: {users}",
                f"Bypass roles: {roles}",
                "",
                "`.antibetray bypass <userID/roleID>` to add or toggle bypass.",
            ]),
            color=0xED4245,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AntiBetrayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="antibetray", invoke_without_command=True)
    async def antibetray(self, ctx: commands.Context):
        if not ctx.guild:
            return
        if not can_antibetray(ctx.author, ctx.guild):
            return await ctx.send("No permission.")
        embed = discord.Embed(
            title="Anti-Betray Freemium V1.5",
            description=_desc_main(),
            color=0xED4245,
        )
        cfg = _ab_cfg(ctx.guild.id)
        embed.set_footer(text=f"Status: {'ON' if cfg['enabled'] else 'OFF'} · Antinuke must be enabled")
        await ctx.send(embed=embed, view=AntiBetrayMainView(ctx.guild.id))

    @antibetray.command(name="bypass")
    async def bypass_cmd(self, ctx: commands.Context, target: str = None):
        if not ctx.guild:
            return
        if not can_antibetray(ctx.author, ctx.guild):
            return await ctx.send("No permission.")
        if not target:
            return await ctx.send("Usage: `.antibetray bypass <userID/roleID>`")
        raw = target.strip().replace("<@&", "").replace("<@", "").replace("!", "").replace(">", "")
        if not raw.isdigit():
            return await ctx.send("Provide a userID or roleID.")
        cfg = _ab_cfg(ctx.guild.id)
        role = ctx.guild.get_role(int(raw))
        if role is not None:
            roles = list(cfg["bypass_roles"])
            if raw in roles:
                roles.remove(raw)
                cfg["bypass_roles"] = roles
                _save_ab(ctx.guild.id, cfg)
                return await ctx.send(f"Removed bypass for role {role.mention}.")
            roles.append(raw)
            cfg["bypass_roles"] = roles
            _save_ab(ctx.guild.id, cfg)
            return await ctx.send(f"Bypass added for role {role.mention}.")
        users = list(cfg["bypass_users"])
        if raw in users:
            users.remove(raw)
            cfg["bypass_users"] = users
            _save_ab(ctx.guild.id, cfg)
            return await ctx.send(f"Removed bypass for <@{raw}>.")
        users.append(raw)
        cfg["bypass_users"] = users
        _save_ab(ctx.guild.id, cfg)
        await ctx.send(f"Bypass added for <@{raw}>.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return
        cfg = _ab_cfg(member.guild.id)
        if not cfg.get("enabled"):
            return
        if is_bypassed(member.guild.id, member.id, member):
            return
        # Official already in is_bypassed
        suspicious = False
        # no avatar
        if member.display_avatar == member.default_avatar or member.avatar is None:
            suspicious = True
        # account age < ~8 months
        try:
            created = member.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - created).total_seconds()
            if age < EIGHT_MONTHS_SEC:
                suspicious = True
        except Exception:
            suspicious = True
        if not suspicious:
            return
        try:
            await member.kick(reason="[Anti-Betray] Suspicious bot (no pfp / young account)")
        except Exception as e:
            print(f"[antibetray] kick fail: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cfg = _ab_cfg(after.guild.id)
        if not cfg.get("enabled"):
            return
        if before.roles == after.roles:
            return
        added = [r for r in after.roles if r not in before.roles]
        admin_added = [r for r in added if r.permissions.administrator]
        if not admin_added:
            return
        # Find who gave the role via audit log
        await asyncio.sleep(0.4)
        executor = None
        try:
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                if entry.target and entry.target.id == after.id:
                    executor = entry.user
                    break
        except Exception:
            return
        if executor is None or getattr(executor, "bot", False) and executor.id == self.bot.user.id:
            return
        # Only act if the giver is antinuke-whitelisted / extraowner path (betray from trusted)
        from cogs.server_protection.antinuke import is_antinuke_whitelisted, is_protected_actor
        if not is_antinuke_whitelisted(after.guild.id, executor.id, after.guild.get_member(executor.id)):
            # still strip if non-creator randomly gives admin while antibetray on? User said whitelist only
            return
        if executor.id == CREATOR_ID or executor.id == after.guild.owner_id:
            return
        # Remove admin roles from target
        try:
            await after.remove_roles(*admin_added, reason="[Anti-Betray] Admin role grant blocked")
        except Exception as e:
            print(f"[antibetray] strip target: {e}")
        # Strip elevated roles from giver
        giver = after.guild.get_member(executor.id)
        if giver and not is_bypassed(after.guild.id, giver.id, giver):
            to_remove = [r for r in giver.roles if not r.is_default() and (r.permissions.administrator or r.permissions.manage_roles)]
            if to_remove:
                try:
                    await giver.remove_roles(*to_remove, reason="[Anti-Betray] Betrayed trust (gave Administrator)")
                except Exception as e:
                    print(f"[antibetray] strip giver: {e}")

    async def _nuke_speed_ban(self, guild: discord.Guild, user: discord.Member | discord.User, reason: str):
        if is_bypassed(guild.id, user.id, guild.get_member(user.id) if hasattr(guild, "get_member") else None):
            # Bypassed bots that do damage still get banned (user request)
            if not getattr(user, "bot", False) and user.id != CREATOR_ID:
                return
            if user.id == CREATOR_ID:
                return
            if int(user.id) in OFFICIAL_BOT_IDS:
                return
        try:
            await guild.ban(user, reason=f"[Anti-Betray] {reason}", delete_message_days=0)
        except Exception as e:
            print(f"[antibetray] ban fail: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild
        cfg = _ab_cfg(guild.id)
        if not cfg.get("enabled"):
            return
        await asyncio.sleep(0.25)
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_delete):
                if entry.user and entry.user.bot:
                    await self._nuke_speed_ban(guild, entry.user, "Channel delete")
                break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild
        cfg = _ab_cfg(guild.id)
        if not cfg.get("enabled"):
            return
        await asyncio.sleep(0.25)
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.role_delete):
                if entry.user and entry.user.bot:
                    await self._nuke_speed_ban(guild, entry.user, "Role delete")
                break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        cfg = _ab_cfg(guild.id)
        if not cfg.get("enabled"):
            return
        if len(after) >= len(before):
            return
        await asyncio.sleep(0.25)
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.emoji_delete):
                if entry.user and entry.user.bot:
                    await self._nuke_speed_ban(guild, entry.user, "Emoji delete")
                break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        cfg = _ab_cfg(guild.id)
        if not cfg.get("enabled"):
            return
        await asyncio.sleep(0.2)
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.ban):
                if entry.user and entry.user.bot and entry.user.id != self.bot.user.id:
                    await self._nuke_speed_ban(guild, entry.user, "Mass ban behaviour")
                break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # kicks
        guild = member.guild
        cfg = _ab_cfg(guild.id)
        if not cfg.get("enabled"):
            return
        await asyncio.sleep(0.2)
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id and entry.user and entry.user.bot:
                    if entry.user.id != self.bot.user.id:
                        await self._nuke_speed_ban(guild, entry.user, "Kick by bot")
                break
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(AntiBetrayCog(bot))
    print("[antibetray] cog loaded")
