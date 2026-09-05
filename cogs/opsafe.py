"""
.opsafe enable | disable | unlock
Creator / server owner only.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from functions import load_stats, save_stats, is_op

CREATOR_ID = 1465295674768883889


def can_opsafe(user, guild) -> bool:
    if user.id == CREATOR_ID:
        return True
    if guild and guild.owner_id == user.id:
        return True
    return False


def get_cfg(guild_id) -> dict:
    stats = load_stats()
    raw = (stats.get("opsafe") or {}).get(str(guild_id))
    if not isinstance(raw, dict):
        return {"enabled": False, "locked": False, "saved_overwrites": {}}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "locked": bool(raw.get("locked", False)),
        "saved_overwrites": raw.get("saved_overwrites") or {},
    }


def save_cfg(guild_id, cfg: dict):
    stats = load_stats()
    if "opsafe" not in stats or not isinstance(stats["opsafe"], dict):
        stats["opsafe"] = {}
    stats["opsafe"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "locked": bool(cfg.get("locked", False)),
        "saved_overwrites": cfg.get("saved_overwrites") or {},
    }
    save_stats(stats)


def get_antinuke_bits(guild_id):
    stats = load_stats()
    raw = (stats.get("antinuke") or {}).get(str(guild_id)) or {}
    return {
        "whitelist": [str(x) for x in (raw.get("whitelist") or [])],
        "extraowners": [str(x) for x in (raw.get("extraowners") or [])],
        "logs_channel": raw.get("logs_channel"),
    }


def strip_trust(guild_id, user_id):
    stats = load_stats()
    an = stats.get("antinuke") or {}
    g = an.get(str(guild_id)) or {}
    wl = [str(x) for x in (g.get("whitelist") or [])]
    eo = [str(x) for x in (g.get("extraowners") or [])]
    uid = str(user_id)
    if uid in wl:
        wl.remove(uid)
    if uid in eo:
        eo.remove(uid)
    g["whitelist"] = wl
    g["extraowners"] = eo
    an[str(guild_id)] = g
    stats["antinuke"] = an
    save_stats(stats)


async def opsafe_log(bot, guild, text: str):
    bits = get_antinuke_bits(guild.id)
    ch_id = bits.get("logs_channel")
    if not ch_id:
        print(f"[opsafe] {text}")
        return
    try:
        ch = bot.get_channel(int(ch_id)) or await bot.fetch_channel(int(ch_id))
        if isinstance(ch, discord.TextChannel):
            await ch.send(text)
    except Exception as e:
        print(f"[opsafe] log fail: {e}")


async def lockdown_guild(bot, guild: discord.Guild):
    cfg = get_cfg(guild.id)
    saved = {}
    me = guild.me
    for channel in guild.channels:
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)):
            continue
        # skip announcement-type channels by name/type
        is_ann = False
        if isinstance(channel, discord.TextChannel):
            if channel.is_news() or "announcement" in (channel.name or "").lower():
                is_ann = True
        try:
            overwrites = {}
            for target, ow in channel.overwrites.items():
                overwrites[str(target.id)] = {
                    "allow": ow.pair()[0].value,
                    "deny": ow.pair()[1].value,
                    "type": "role" if isinstance(target, discord.Role) else "member",
                }
            saved[str(channel.id)] = overwrites

            if is_ann:
                continue

            # private: deny view for @everyone
            await channel.set_permissions(
                guild.default_role,
                view_channel=False,
                reason="[OpSafe] lockdown",
            )
        except Exception as e:
            print(f"[opsafe] lockdown channel {channel.id}: {e}")

    cfg["locked"] = True
    cfg["saved_overwrites"] = saved
    save_cfg(guild.id, cfg)

    # announcement message
    ann = None
    for channel in guild.text_channels:
        if channel.is_news() or "announcement" in (channel.name or "").lower():
            ann = channel
            break
    if ann is None:
        # try system channel
        ann = guild.system_channel

    if ann:
        owner = guild.owner
        owner_mention = owner.mention if owner else f"<@{guild.owner_id}>"
        try:
            await ann.send(
                f"@everyone\n\n"
                f"The server is being raided! This bot will automatically lockdown every channels ^-^\n"
                f"Dm {owner_mention} to use .opsafe unlock to remove the lockdown!\n\n\n"
                f"-# Thank you for having this bot!"
            )
        except Exception as e:
            print(f"[opsafe] ann send fail: {e}")

    owner_id = guild.owner_id
    await opsafe_log(
        bot, guild,
        f"<@{owner_id}>\nUse `.opsafe unlock` to unlockdown!",
    )


async def unlock_guild(bot, guild: discord.Guild):
    cfg = get_cfg(guild.id)
    saved = cfg.get("saved_overwrites") or {}
    for ch_id, overs in saved.items():
        channel = guild.get_channel(int(ch_id))
        if channel is None:
            continue
        try:
            # clear and restore
            for target_id, data in overs.items():
                target = guild.get_role(int(target_id)) or guild.get_member(int(target_id))
                if target is None:
                    continue
                allow = discord.Permissions(data.get("allow", 0))
                deny = discord.Permissions(data.get("deny", 0))
                ow = discord.PermissionOverwrite.from_pair(allow, deny)
                await channel.set_permissions(target, overwrite=ow, reason="[OpSafe] unlock")
        except Exception as e:
            print(f"[opsafe] unlock {ch_id}: {e}")

    cfg["locked"] = False
    cfg["saved_overwrites"] = {}
    save_cfg(guild.id, cfg)
    await opsafe_log(bot, guild, "🔓 OpSafe lockdown lifted.")


class OpSafeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # track suspicious actions by trusted users: (guild, user) -> set of categories in window
        self._trust_hits: dict[tuple[int, int], dict] = defaultdict(lambda: {"cats": set(), "t0": 0.0})
        self._joins: dict[int, deque] = defaultdict(lambda: deque(maxlen=50))
        self._new_spam: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=20))

    @commands.command(name="opsafe")
    async def opsafe_cmd(self, ctx: commands.Context, action: str = None):
        if not ctx.guild:
            return
        if not can_opsafe(ctx.author, ctx.guild):
            return await ctx.send("❌ No permission.")

        if not action:
            cfg = get_cfg(ctx.guild.id)
            return await ctx.send(
                f"**OpSafe:** {'ON' if cfg['enabled'] else 'OFF'}"
                f"{' · LOCKED' if cfg.get('locked') else ''}\n"
                f"`.opsafe enable` / `disable` / `unlock`"
            )

        action = action.lower().strip()

        if action in ("enable", "on", "true"):
            cfg = get_cfg(ctx.guild.id)
            cfg["enabled"] = True
            save_cfg(ctx.guild.id, cfg)
            return await ctx.send("OVERPOWERED Security System Activated ✅")

        if action in ("disable", "off", "false"):
            cfg = get_cfg(ctx.guild.id)
            cfg["enabled"] = False
            save_cfg(ctx.guild.id, cfg)
            return await ctx.send("Command Disabled.")

        if action == "unlock":
            cfg = get_cfg(ctx.guild.id)
            if not cfg.get("locked"):
                return await ctx.send("Server is not locked.")
            await unlock_guild(self.bot, ctx.guild)
            return await ctx.send("✅ Lockdown removed.")

        await ctx.send("Usage: `.opsafe enable` | `disable` | `unlock`")

    def _trust_mark(self, guild_id: int, user_id: int, category: str) -> bool:
        """Return True if 2+ different categories hit within 5s."""
        key = (guild_id, user_id)
        now = time.time()
        data = self._trust_hits[key]
        if now - data["t0"] > 5.0:
            data["cats"] = set()
            data["t0"] = now
        data["cats"].add(category)
        return len(data["cats"]) >= 2

    async def _punish_trusted(self, guild: discord.Guild, member: discord.Member, reason: str):
        strip_trust(guild.id, member.id)
        try:
            await guild.ban(member, reason=f"[OpSafe] {reason}", delete_message_days=0)
        except Exception as e:
            print(f"[opsafe] ban fail: {e}")
        await opsafe_log(
            self.bot, guild,
            f"🔨 OpSafe banned {member} (`{member.id}`) — {reason}\n"
            f"<@{guild.owner_id}> trust stripped.",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self._on_struct(channel.guild, "channels", discord.AuditLogAction.channel_create)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self._on_struct(channel.guild, "channels", discord.AuditLogAction.channel_delete)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self._on_struct(role.guild, "roles", discord.AuditLogAction.role_create)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self._on_struct(role.guild, "roles", discord.AuditLogAction.role_delete)

    async def _on_struct(self, guild, category, action):
        cfg = get_cfg(guild.id)
        if not cfg.get("enabled"):
            return
        try:
            async for entry in guild.audit_logs(limit=3, action=action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 10:
                    continue
                user = entry.user
                if user is None or user.bot:
                    return
                bits = get_antinuke_bits(guild.id)
                uid = str(user.id)
                if uid not in bits["whitelist"] and uid not in bits["extraowners"]:
                    return
                if user.id == guild.owner_id or user.id == CREATOR_ID:
                    return
                if self._trust_mark(guild.id, user.id, category):
                    member = guild.get_member(user.id)
                    if member:
                        await self._punish_trusted(
                            guild, member,
                            f"trusted abuse ({category} + other within 5s)",
                        )
                return
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        cfg = get_cfg(message.guild.id)
        if not cfg.get("enabled"):
            return

        guild = message.guild
        author = message.author
        bits = get_antinuke_bits(guild.id)
        uid = str(author.id)

        # Trusted spam under 5s (6 msgs) as one category
        if uid in bits["whitelist"] or uid in bits["extraowners"]:
            if author.id != guild.owner_id and author.id != CREATOR_ID:
                key = (guild.id, author.id)
                now = time.time()
                q = self._new_spam[("trust",) + key]
                q.append(now)
                while q and now - q[0] > 5.0:
                    q.popleft()
                if len(q) >= 6:
                    q.clear()
                    if self._trust_mark(guild.id, author.id, "spam"):
                        member = author if isinstance(author, discord.Member) else guild.get_member(author.id)
                        if member:
                            await self._punish_trusted(guild, member, "trusted spam + other abuse")
                    return

        # New-user raid spam: account or join recently + 6 msgs / 2s
        member = author if isinstance(author, discord.Member) else guild.get_member(author.id)
        if member is None:
            return
        joined = member.joined_at
        is_new = False
        if joined:
            is_new = (discord.utils.utcnow() - joined).total_seconds() < 600
        if is_new:
            key = (guild.id, member.id)
            now = time.time()
            q = self._new_spam[key]
            q.append(now)
            while q and now - q[0] > 2.0:
                q.popleft()
            if len(q) >= 6:
                q.clear()
                try:
                    await guild.ban(member, reason="[OpSafe] raid spam", delete_message_days=1)
                except Exception:
                    pass
                joins = self._joins[guild.id]
                # if also join flood → lockdown
                now2 = time.time()
                while joins and now2 - joins[0] > 600:
                    joins.popleft()
                if len(joins) >= 6:
                    await opsafe_log(
                        self.bot, guild,
                        f"<@{guild.owner_id}>\nUse `.opsafe unlock` to unlockdown!",
                    )
                    if not cfg.get("locked"):
                        await lockdown_guild(self.bot, guild)
                else:
                    await opsafe_log(
                        self.bot, guild,
                        f"🔨 OpSafe banned new spammer {member} (`{member.id}`)\n<@{guild.owner_id}>",
                    )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = get_cfg(member.guild.id)
        if not cfg.get("enabled"):
            return
        joins = self._joins[member.guild.id]
        now = time.time()
        joins.append(now)
        while joins and now - joins[0] > 600:
            joins.popleft()
        if len(joins) >= 6 and not cfg.get("locked"):
            await opsafe_log(
                self.bot, member.guild,
                f"<@{member.guild.owner_id}>\nUse `.opsafe unlock` to unlockdown!",
            )
            await lockdown_guild(self.bot, member.guild)


async def setup(bot):
    await bot.add_cog(OpSafeCog(bot))
