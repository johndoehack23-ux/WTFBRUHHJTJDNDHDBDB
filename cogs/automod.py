"""
Automod — anti-spam (Sapphire-style sliding window)

Commands:
  .automod enable | disable | status
  Alias: .am

Access: same as antinuke (server owner / creator / op / antinuke-whitelisted)
Enable requirement: bot role must be at the top (same as antinuke)

Spam rule:
  6 messages from the same user inside any 3.0s window
  → mute 5 minutes + delete all messages in that burst

Message spacing of ~0.5s–2s is fine; they do not need to be instant.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from functions import load_stats, save_stats, is_op

# Reuse antinuke helpers where possible
try:
    from cogs.antinuke import (
        CREATOR_ID,
        can_use_antinuke,
        is_protected_actor,
        has_message_immunity,
        bot_role_is_top,
        antinuke_log,
        is_antinuke_whitelisted,
    )
except Exception:
    CREATOR_ID = 1465295674768883889

    def can_use_antinuke(user, guild):
        if user.id == CREATOR_ID:
            return True
        if is_op(user.id):
            return True
        if guild and guild.owner_id == user.id:
            return True
        return False

    def is_protected_actor(user_id, guild):
        if user_id == CREATOR_ID:
            return True
        if is_op(user_id):
            return True
        if guild and guild.owner_id == user_id:
            return True
        return False

    def has_message_immunity(member):
        try:
            p = member.guild_permissions
            return bool(p.administrator or p.manage_messages)
        except Exception:
            return False

    def bot_role_is_top(guild, bot_user):
        if not guild.me:
            return False
        roles = [r for r in guild.roles if not r.is_default()]
        if not roles:
            return True
        top = max(roles, key=lambda r: r.position)
        return guild.me.top_role.position >= top.position

    async def antinuke_log(bot, guild, text):
        pass


# ── Config ───────────────────────────────────────────────────────────────────

SPAM_LIMIT = 6          # messages
SPAM_WINDOW = 3.0       # seconds (sliding window)
MUTE_MINUTES = 5


def _empty_automod() -> dict:
    return {
        "enabled": False,
        "limit": SPAM_LIMIT,
        "window": SPAM_WINDOW,
        "mute_minutes": MUTE_MINUTES,
    }


def get_automod_config(guild_id: int | str) -> dict:
    stats = load_stats()
    raw = (stats.get("automod") or {}).get(str(guild_id))
    cfg = _empty_automod()
    if not isinstance(raw, dict):
        return cfg
    cfg["enabled"] = bool(raw.get("enabled", False))
    try:
        cfg["limit"] = int(raw.get("limit", SPAM_LIMIT))
        cfg["window"] = float(raw.get("window", SPAM_WINDOW))
        cfg["mute_minutes"] = int(raw.get("mute_minutes", MUTE_MINUTES))
    except (TypeError, ValueError):
        pass
    return cfg


def save_automod_config(guild_id: int | str, cfg: dict):
    stats = load_stats()
    if "automod" not in stats or not isinstance(stats["automod"], dict):
        stats["automod"] = {}
    stats["automod"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "limit": int(cfg.get("limit", SPAM_LIMIT)),
        "window": float(cfg.get("window", SPAM_WINDOW)),
        "mute_minutes": int(cfg.get("mute_minutes", MUTE_MINUTES)),
    }
    save_stats(stats)


def is_automod_enabled(guild_id: int | str) -> bool:
    return bool(get_automod_config(guild_id).get("enabled"))


# ── Cog ──────────────────────────────────────────────────────────────────────

class AutoModCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> deque[(timestamp, channel_id, message_id)]
        self._buckets: dict[tuple[int, int], deque] = defaultdict(
            lambda: deque(maxlen=40)
        )
        # mute cooldown so we don't re-trigger while already timing out
        self._muted_until: dict[tuple[int, int], float] = {}

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.command(name="automod", aliases=["am"])
    async def automod_cmd(self, ctx: commands.Context, action: str = None):
        if not ctx.guild:
            return
        if not can_use_antinuke(ctx.author, ctx.guild):
            return await ctx.send(
                "❌ Only the **server owner**, **bot creator**, **op**, or **antinuke-whitelisted** users can use automod."
            )

        if not action:
            cfg = get_automod_config(ctx.guild.id)
            state = "🟢 ENABLED" if cfg["enabled"] else "🔴 DISABLED"
            return await ctx.send(
                f"**Automod:** {state}\n"
                f"Spam: **{cfg.get('limit', SPAM_LIMIT)}** messages within **{cfg.get('window', SPAM_WINDOW)}s** → "
                f"mute **{cfg.get('mute_minutes', MUTE_MINUTES)}m** + delete burst\n"
                f"Use `{ctx.prefix}automod enable` / `disable`"
            )

        action = action.lower().strip()

        if action in ("enable", "on", "true"):
            if not bot_role_is_top(ctx.guild, ctx.guild.me):
                return await ctx.send(
                    "❌ Move the **bot's role to the top** of the role list before enabling Automod."
                )
            me = ctx.guild.me
            if me and not me.guild_permissions.moderate_members:
                return await ctx.send(
                    "❌ Bot needs **Moderate Members** (Timeout) permission before enabling Automod."
                )
            if me and not me.guild_permissions.manage_messages:
                return await ctx.send(
                    "❌ Bot needs **Manage Messages** permission to delete spam."
                )

            cfg = get_automod_config(ctx.guild.id)
            cfg["enabled"] = True
            cfg["limit"] = SPAM_LIMIT
            cfg["window"] = SPAM_WINDOW
            cfg["mute_minutes"] = MUTE_MINUTES
            save_automod_config(ctx.guild.id, cfg)
            await ctx.send(
                "✅ **Automod ENABLED**\n"
                f"Spam rule: **{SPAM_LIMIT} messages within {SPAM_WINDOW}s** "
                f"(spacing ~0.5s–2s is fine) → **mute {MUTE_MINUTES}m** + **delete** those messages."
            )
            await antinuke_log(
                self.bot, ctx.guild,
                f"✅ Automod enabled by {ctx.author} (`{ctx.author.id}`)",
            )
            return

        if action in ("disable", "off", "false"):
            cfg = get_automod_config(ctx.guild.id)
            cfg["enabled"] = False
            save_automod_config(ctx.guild.id, cfg)
            await ctx.send("🔴 **Automod DISABLED** for this server.")
            await antinuke_log(
                self.bot, ctx.guild,
                f"🔴 Automod disabled by {ctx.author} (`{ctx.author.id}`)",
            )
            return

        if action in ("status", "info"):
            cfg = get_automod_config(ctx.guild.id)
            state = "ENABLED" if cfg["enabled"] else "DISABLED"
            return await ctx.send(
                f"**Automod:** {state}\n"
                f"Limit: {cfg.get('limit', SPAM_LIMIT)} msgs / {cfg.get('window', SPAM_WINDOW)}s\n"
                f"Mute: {cfg.get('mute_minutes', MUTE_MINUTES)} minutes"
            )

        await ctx.send("❌ Usage: `automod enable` | `disable` | `status`")

    # ── Spam listener ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not is_automod_enabled(message.guild.id):
            return
        if is_protected_actor(message.author.id, message.guild):
            return

        member = (
            message.author
            if isinstance(message.author, discord.Member)
            else message.guild.get_member(message.author.id)
        )
        if member is None:
            try:
                member = await message.guild.fetch_member(message.author.id)
            except Exception:
                return
        if member is None:
            return

        # Discord Administrator / Manage Messages → never mute
        if has_message_immunity(member):
            return

        key = (message.guild.id, member.id)
        now = time.time()

        # Already muted recently — don't spam-process
        if self._muted_until.get(key, 0) > now:
            return

        cfg = get_automod_config(message.guild.id)
        limit = int(cfg.get("limit", SPAM_LIMIT)) or SPAM_LIMIT
        window = float(cfg.get("window", SPAM_WINDOW)) or SPAM_WINDOW
        mute_mins = int(cfg.get("mute_minutes", MUTE_MINUTES)) or MUTE_MINUTES

        bucket = self._buckets[key]
        # Store timestamp + where the message is so we can delete the whole burst
        bucket.append((now, message.channel.id, message.id))

        # Drop entries outside the sliding window
        while bucket and (now - bucket[0][0]) > window:
            bucket.popleft()

        if len(bucket) < limit:
            return

        # ── SPAM TRIGGER ─────────────────────────────────────────────────────
        burst = list(bucket)
        bucket.clear()
        self._muted_until[key] = now + (mute_mins * 60)

        span = round(burst[-1][0] - burst[0][0], 2) if len(burst) > 1 else 0.0
        print(
            f"[automod] SPAM guild={message.guild.id} user={member.id} "
            f"count={len(burst)} span={span}s window={window}s"
        )

        # Delete every message in the burst (group by channel)
        by_channel: dict[int, list[int]] = {}
        for _ts, ch_id, msg_id in burst:
            by_channel.setdefault(ch_id, []).append(msg_id)

        for ch_id, msg_ids in by_channel.items():
            channel = message.guild.get_channel(ch_id) or message.channel
            if not isinstance(channel, discord.TextChannel):
                continue
            # bulk delete if possible (messages < 14 days), else one-by-one
            try:
                if len(msg_ids) == 1:
                    m = await channel.fetch_message(msg_ids[0])
                    await m.delete()
                else:
                    await channel.delete_messages(
                        [discord.Object(id=mid) for mid in msg_ids]
                    )
            except (discord.Forbidden, discord.HTTPException):
                for mid in msg_ids:
                    try:
                        m = await channel.fetch_message(mid)
                        await m.delete()
                    except Exception:
                        pass

        # Mute (timeout)
        me = message.guild.me
        if me is None:
            return
        if not me.guild_permissions.moderate_members:
            await antinuke_log(
                self.bot, message.guild,
                f"⚠️ Automod: cannot mute {member} — missing **Moderate Members**",
            )
            return
        if member.top_role >= me.top_role and member.id != message.guild.owner_id:
            await antinuke_log(
                self.bot, message.guild,
                f"⚠️ Automod: cannot mute {member} — their role is >= bot role",
            )
            return

        try:
            until = discord.utils.utcnow() + timedelta(minutes=mute_mins)
            await member.timeout(
                until,
                reason=f"[Automod] Spam: {len(burst)} messages in {span}s (window {window}s)",
            )
            await antinuke_log(
                self.bot, message.guild,
                f"🔇 Automod muted {member} (`{member.id}`) for {mute_mins}m — "
                f"{len(burst)} msgs in {span}s",
            )
            print(f"[automod] muted {member.id} for {mute_mins}m")
        except (discord.Forbidden, discord.HTTPException) as e:
            await antinuke_log(
                self.bot, message.guild,
                f"⚠️ Automod failed to mute {member} (`{member.id}`): {e}",
            )
            print(f"[automod] mute failed: {e}")


async def setup(bot):
    await bot.add_cog(AutoModCog(bot))
