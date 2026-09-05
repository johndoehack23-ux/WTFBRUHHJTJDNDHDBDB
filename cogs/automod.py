"""
Automod — anti-spam (sliding window)

.automod / .am  enable | disable | status

Spam: 6 messages from the same user within 3.0s
  → delete the burst + mute 5 minutes

Debug: every tracked message is logged to the antinuke logs channel as:
  username (userID) | message count: N
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from functions import load_stats, save_stats, is_op

CREATOR_ID = 1465295674768883889

SPAM_LIMIT = 6
SPAM_WINDOW = 3.0
MUTE_MINUTES = 5


# ── Shared helpers (duplicated so automod never fails if antinuke import breaks) ─

def _is_op(uid: int) -> bool:
    try:
        return bool(is_op(uid))
    except Exception:
        return False


def can_use_automod(user: discord.abc.User, guild: discord.Guild | None) -> bool:
    if user.id == CREATOR_ID:
        return True
    if _is_op(user.id):
        return True
    if guild and guild.owner_id == user.id:
        return True
    # antinuke whitelist also counts
    try:
        stats = load_stats()
        wl = ((stats.get("antinuke") or {}).get(str(guild.id)) or {}).get("whitelist") or []
        if str(user.id) in [str(x) for x in wl]:
            return True
    except Exception:
        pass
    return False


def is_protected(user_id: int, guild: discord.Guild) -> bool:
    if user_id == CREATOR_ID:
        return True
    if _is_op(user_id):
        return True
    if guild.owner_id == user_id:
        return True
    try:
        stats = load_stats()
        wl = ((stats.get("antinuke") or {}).get(str(guild.id)) or {}).get("whitelist") or []
        if str(user_id) in [str(x) for x in wl]:
            return True
    except Exception:
        pass
    return False


def has_msg_immunity(member: discord.Member) -> bool:
    try:
        p = member.guild_permissions
        return bool(p.administrator or p.manage_messages)
    except Exception:
        return False


def bot_role_is_top(guild: discord.Guild) -> bool:
    if not guild.me:
        return False
    roles = [r for r in guild.roles if not r.is_default()]
    if not roles:
        return True
    top = max(roles, key=lambda r: r.position)
    return guild.me.top_role.position >= top.position


def get_logs_channel_id(guild_id: int) -> int | None:
    """Use antinuke logs channel for automod debug + actions."""
    try:
        stats = load_stats()
        raw = ((stats.get("antinuke") or {}).get(str(guild_id)) or {}).get("logs_channel")
        if raw and str(raw).isdigit():
            return int(raw)
    except Exception:
        pass
    return None


async def send_log(bot, guild: discord.Guild, text: str):
    ch_id = get_logs_channel_id(guild.id)
    if not ch_id:
        print(f"[automod:nolog] {guild.id} | {text}")
        return
    try:
        ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(text)
    except Exception as e:
        print(f"[automod] log send failed: {e}")


# ── Config (Mongo) ───────────────────────────────────────────────────────────

def get_automod_config(guild_id: int | str) -> dict:
    stats = load_stats()
    raw = (stats.get("automod") or {}).get(str(guild_id))
    cfg = {
        "enabled": False,
        "limit": SPAM_LIMIT,
        "window": SPAM_WINDOW,
        "mute_minutes": MUTE_MINUTES,
    }
    if isinstance(raw, dict):
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


# ── Cog ──────────────────────────────────────────────────────────────────────

class AutoModCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> deque of (timestamp, channel_id, message_id)
        self._buckets: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))
        self._muted_until: dict[tuple[int, int], float] = {}

    @commands.command(name="automod", aliases=["am"])
    async def automod_cmd(self, ctx: commands.Context, action: str = None):
        if not ctx.guild:
            return
        if not can_use_automod(ctx.author, ctx.guild):
            return await ctx.send(
                "❌ Only the **server owner**, **bot creator**, **op**, or **antinuke-whitelisted** users can use automod."
            )

        cfg = get_automod_config(ctx.guild.id)

        if not action:
            state = "🟢 ENABLED" if cfg["enabled"] else "🔴 DISABLED"
            logs = get_logs_channel_id(ctx.guild.id)
            return await ctx.send(
                f"**Automod:** {state}\n"
                f"Spam: **{cfg['limit']}** msgs / **{cfg['window']}s** → mute **{cfg['mute_minutes']}m** + delete\n"
                f"Debug logs: {'<#' + str(logs) + '>' if logs else '`not set — use .au config → Channels → Set`'}\n"
                f"Use `{ctx.prefix}automod enable` / `disable`"
            )

        action = action.lower().strip()

        if action in ("enable", "on", "true"):
            if not bot_role_is_top(ctx.guild):
                return await ctx.send(
                    "❌ Move the **bot's role to the top** of the role list before enabling Automod."
                )
            me = ctx.guild.me
            missing = []
            if me and not me.guild_permissions.moderate_members:
                missing.append("Moderate Members")
            if me and not me.guild_permissions.manage_messages:
                missing.append("Manage Messages")
            if missing:
                return await ctx.send(
                    f"❌ Bot is missing permissions: **{', '.join(missing)}**"
                )

            cfg["enabled"] = True
            cfg["limit"] = SPAM_LIMIT
            cfg["window"] = SPAM_WINDOW
            cfg["mute_minutes"] = MUTE_MINUTES
            save_automod_config(ctx.guild.id, cfg)

            logs = get_logs_channel_id(ctx.guild.id)
            extra = ""
            if not logs:
                extra = "\n⚠️ No logs channel set — set one with `.au config` → **Channels** → **Set** so debug lines appear."

            await ctx.send(
                "✅ **Automod ENABLED**\n"
                f"Rule: **{SPAM_LIMIT} messages within {SPAM_WINDOW}s** "
                f"(0.5s–2s spacing is fine) → **mute {MUTE_MINUTES}m** + **delete burst**."
                f"{extra}"
            )
            await send_log(
                self.bot, ctx.guild,
                f"✅ Automod enabled by {ctx.author} (`{ctx.author.id}`)",
            )
            return

        if action in ("disable", "off", "false"):
            cfg["enabled"] = False
            save_automod_config(ctx.guild.id, cfg)
            await ctx.send("🔴 **Automod DISABLED**")
            await send_log(
                self.bot, ctx.guild,
                f"🔴 Automod disabled by {ctx.author} (`{ctx.author.id}`)",
            )
            return

        if action in ("status", "info"):
            state = "ENABLED" if cfg["enabled"] else "DISABLED"
            logs = get_logs_channel_id(ctx.guild.id)
            return await ctx.send(
                f"**Automod:** {state}\n"
                f"Limit: {cfg['limit']} / {cfg['window']}s · Mute: {cfg['mute_minutes']}m\n"
                f"Logs: {f'<#{logs}>' if logs else 'not set'}"
            )

        await ctx.send("❌ Usage: `automod enable` | `disable` | `status`")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        cfg = get_automod_config(message.guild.id)
        if not cfg.get("enabled"):
            return

        if is_protected(message.author.id, message.guild):
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

        if has_msg_immunity(member):
            return

        key = (message.guild.id, member.id)
        now = time.time()

        if self._muted_until.get(key, 0) > now:
            return

        limit = int(cfg.get("limit") or SPAM_LIMIT)
        window = float(cfg.get("window") or SPAM_WINDOW)
        mute_mins = int(cfg.get("mute_minutes") or MUTE_MINUTES)

        bucket = self._buckets[key]
        bucket.append((now, message.channel.id, message.id))

        # Drop timestamps outside the sliding window
        while bucket and (now - bucket[0][0]) > window:
            bucket.popleft()

        count = len(bucket)
        uname = str(member)
        uid = member.id

        # ── DEBUG LOG every tracked message ──────────────────────────────────
        debug_line = f"{uname} (`{uid}`) | message count: **{count}**"
        print(f"[automod] {message.guild.id} #{getattr(message.channel, 'name', '?')} | {debug_line}")
        try:
            await send_log(self.bot, message.guild, debug_line)
        except Exception as e:
            print(f"[automod] debug log error: {e}")

        if count < limit:
            return

        # ── SPAM TRIGGER ─────────────────────────────────────────────────────
        burst = list(bucket)
        bucket.clear()
        self._muted_until[key] = now + (mute_mins * 60)

        span = round(burst[-1][0] - burst[0][0], 2) if len(burst) > 1 else 0.0
        trigger_msg = (
            f"🚨 **SPAM DETECTED** {uname} (`{uid}`) — "
            f"**{len(burst)}** msgs in **{span}s** (window {window}s) → muting {mute_mins}m"
        )
        print(f"[automod] {trigger_msg}")
        await send_log(self.bot, message.guild, trigger_msg)

        # Delete all messages in the burst
        by_channel: dict[int, list[int]] = {}
        for _ts, ch_id, msg_id in burst:
            by_channel.setdefault(ch_id, []).append(msg_id)

        for ch_id, msg_ids in by_channel.items():
            channel = message.guild.get_channel(ch_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(ch_id)
                except Exception:
                    channel = message.channel
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                continue
            try:
                if len(msg_ids) >= 2:
                    await channel.delete_messages(
                        [discord.Object(id=mid) for mid in msg_ids[:100]]
                    )
                else:
                    m = await channel.fetch_message(msg_ids[0])
                    await m.delete()
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"[automod] bulk delete failed: {e}")
                for mid in msg_ids:
                    try:
                        m = await channel.fetch_message(mid)
                        await m.delete()
                    except Exception:
                        pass

        # Mute
        me = message.guild.me
        if me is None:
            await send_log(self.bot, message.guild, "⚠️ Automod: bot member not cached")
            return
        if not me.guild_permissions.moderate_members:
            await send_log(
                self.bot, message.guild,
                f"⚠️ Cannot mute {uname} — bot missing **Moderate Members**",
            )
            return
        if member.top_role >= me.top_role and member.id != message.guild.owner_id:
            await send_log(
                self.bot, message.guild,
                f"⚠️ Cannot mute {uname} — their highest role is >= the bot role. Move bot role higher.",
            )
            return

        try:
            until = discord.utils.utcnow() + timedelta(minutes=mute_mins)
            await member.timeout(
                until,
                reason=f"[Automod] Spam: {len(burst)} messages in {span}s",
            )
            await send_log(
                self.bot, message.guild,
                f"🔇 Muted {uname} (`{uid}`) for **{mute_mins}m**",
            )
            print(f"[automod] muted {uid}")
        except (discord.Forbidden, discord.HTTPException) as e:
            await send_log(
                self.bot, message.guild,
                f"⚠️ Mute failed for {uname} (`{uid}`): {e}",
            )
            print(f"[automod] mute failed: {e}")


async def setup(bot):
    await bot.add_cog(AutoModCog(bot))
    print("[automod] cog loaded")
