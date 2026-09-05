"""
Automod — anti-spam

.automod / .am  enable | disable | status | config | debug
"""

from __future__ import annotations

import asyncio
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


def _is_op(uid: int) -> bool:
    try:
        return bool(is_op(uid))
    except Exception:
        return False


def can_use_automod(user, guild) -> bool:
    if user.id == CREATOR_ID:
        return True
    if _is_op(user.id):
        return True
    if guild and guild.owner_id == user.id:
        return True
    try:
        stats = load_stats()
        wl = ((stats.get("antinuke") or {}).get(str(guild.id)) or {}).get("whitelist") or []
        if str(user.id) in [str(x) for x in wl]:
            return True
    except Exception:
        pass
    return False


def is_protected(user_id: int, guild: discord.Guild) -> bool:
    if user_id == CREATOR_ID or _is_op(user_id) or guild.owner_id == user_id:
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
        print(f"[automod:nolog] {text}")
        return
    try:
        ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(text)
    except Exception as e:
        print(f"[automod] log failed: {e}")


def get_automod_config(guild_id) -> dict:
    stats = load_stats()
    raw = (stats.get("automod") or {}).get(str(guild_id))
    cfg = {
        "enabled": False,
        "debug": False,
        "limit": SPAM_LIMIT,
        "window": SPAM_WINDOW,
        "mute_minutes": MUTE_MINUTES,
    }
    if isinstance(raw, dict):
        cfg["enabled"] = bool(raw.get("enabled", False))
        cfg["debug"] = bool(raw.get("debug", False))
        try:
            cfg["limit"] = int(raw.get("limit", SPAM_LIMIT))
            cfg["window"] = float(raw.get("window", SPAM_WINDOW))
            cfg["mute_minutes"] = int(raw.get("mute_minutes", MUTE_MINUTES))
        except (TypeError, ValueError):
            pass
    # clamp
    cfg["limit"] = max(2, min(50, int(cfg["limit"])))
    cfg["window"] = max(1.0, min(30.0, float(cfg["window"])))
    cfg["mute_minutes"] = max(1, min(60 * 24, int(cfg["mute_minutes"])))
    return cfg


def save_automod_config(guild_id, cfg: dict):
    stats = load_stats()
    if "automod" not in stats or not isinstance(stats["automod"], dict):
        stats["automod"] = {}
    stats["automod"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "debug": bool(cfg.get("debug", False)),
        "limit": int(cfg.get("limit", SPAM_LIMIT)),
        "window": float(cfg.get("window", SPAM_WINDOW)),
        "mute_minutes": int(cfg.get("mute_minutes", MUTE_MINUTES)),
    }
    save_stats(stats)


def format_config_description(cfg: dict) -> str:
    mute = int(cfg.get("mute_minutes", MUTE_MINUTES))
    limit = int(cfg.get("limit", SPAM_LIMIT))
    seconds = cfg.get("window", SPAM_WINDOW)
    # show whole number if .0
    if float(seconds) == int(float(seconds)):
        sec_txt = str(int(seconds))
    else:
        sec_txt = str(seconds)
    return (
        f"**Spamming**\n"
        f"Mute: {mute} min\n"
        f"Limit: {limit}\n"
        f"Seconds: {sec_txt}\n\n"
        f"**SOON**"
    )


# ── Config UI ────────────────────────────────────────────────────────────────

class AutomodValueModal(discord.ui.Modal, title="Mute, Limit, Seconds"):
    mute_input = discord.ui.TextInput(
        label="Mute",
        placeholder="Minutes (e.g. 5)",
        required=True,
        max_length=5,
    )
    limit_input = discord.ui.TextInput(
        label="Limit",
        placeholder="How many messages (e.g. 6)",
        required=True,
        max_length=3,
    )
    seconds_input = discord.ui.TextInput(
        label="Seconds",
        placeholder="Window 1–30 (e.g. 3)",
        required=True,
        max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not can_use_automod(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)

        try:
            mute = int(str(self.mute_input.value).strip())
            limit = int(str(self.limit_input.value).strip())
            seconds = int(str(self.seconds_input.value).strip())
        except ValueError:
            return await interaction.response.send_message(
                "❌ Mute, Limit, and Seconds must all be whole numbers.",
                ephemeral=True,
            )

        if mute < 1 or mute > 60 * 24:
            return await interaction.response.send_message(
                "❌ Mute must be 1–1440 minutes.", ephemeral=True
            )
        if limit < 2 or limit > 50:
            return await interaction.response.send_message(
                "❌ Limit must be 2–50 messages.", ephemeral=True
            )
        if seconds < 1 or seconds > 30:
            return await interaction.response.send_message(
                "❌ Seconds must be 1–30.", ephemeral=True
            )

        cfg = get_automod_config(interaction.guild.id)
        cfg["mute_minutes"] = mute
        cfg["limit"] = limit
        cfg["window"] = float(seconds)
        save_automod_config(interaction.guild.id, cfg)

        await interaction.response.send_message(
            f"✅ Automod values updated:\n"
            f"Mute: **{mute}** min · Limit: **{limit}** · Seconds: **{seconds}**",
            ephemeral=True,
        )


class AutomodConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Value", style=discord.ButtonStyle.primary, custom_id="automod_cfg_value")
    async def value_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not can_use_automod(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)
        await interaction.response.send_modal(AutomodValueModal())


# ── Cog ──────────────────────────────────────────────────────────────────────

class AutoModCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._buckets: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))
        self._muted_until: dict[tuple[int, int], float] = {}
        self._handling: set[tuple[int, int]] = set()
        self._locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)

    @commands.command(name="automod", aliases=["am"])
    async def automod_cmd(self, ctx: commands.Context, action: str = None, *rest):
        if not ctx.guild:
            return
        if not can_use_automod(ctx.author, ctx.guild):
            return await ctx.send(
                "❌ Only the **server owner**, **bot creator**, **op**, or **antinuke-whitelisted** users can use automod."
            )

        cfg = get_automod_config(ctx.guild.id)

        if not action:
            state = "🟢 ENABLED" if cfg["enabled"] else "🔴 DISABLED"
            dbg = "ON" if cfg.get("debug") else "OFF"
            logs = get_logs_channel_id(ctx.guild.id)
            return await ctx.send(
                f"**Automod:** {state} · Debug: **{dbg}**\n"
                f"Spam: **{cfg['limit']}** msgs / **{cfg['window']}s** → mute **{cfg['mute_minutes']}m** + delete\n"
                f"Logs: {f'<#{logs}>' if logs else '`not set`'}\n"
                f"Use `{ctx.prefix}automod enable` / `disable` / `config` / `debug`"
            )

        action = action.lower().strip()

        if action in ("enable", "on", "true"):
            if not bot_role_is_top(ctx.guild):
                return await ctx.send(
                    "❌ Move the **bot's role to the top** before enabling Automod."
                )
            me = ctx.guild.me
            missing = []
            if me and not me.guild_permissions.moderate_members:
                missing.append("Moderate Members")
            if me and not me.guild_permissions.manage_messages:
                missing.append("Manage Messages")
            if missing:
                return await ctx.send(f"❌ Bot missing: **{', '.join(missing)}**")

            cfg["enabled"] = True
            save_automod_config(ctx.guild.id, cfg)
            logs = get_logs_channel_id(ctx.guild.id)
            extra = "" if logs else "\n⚠️ Set logs: `.au config` → **Channels** → **Set**"
            await ctx.send(
                f"✅ **Automod ENABLED** — {cfg['limit']} msgs / {cfg['window']}s → mute {cfg['mute_minutes']}m + delete"
                f"{extra}"
            )
            await send_log(self.bot, ctx.guild, f"✅ Automod enabled by {ctx.author} (`{ctx.author.id}`)")
            return

        if action in ("disable", "off", "false"):
            cfg["enabled"] = False
            save_automod_config(ctx.guild.id, cfg)
            await ctx.send("🔴 **Automod DISABLED**")
            await send_log(self.bot, ctx.guild, f"🔴 Automod disabled by {ctx.author} (`{ctx.author.id}`)")
            return

        if action in ("status", "info"):
            logs = get_logs_channel_id(ctx.guild.id)
            return await ctx.send(
                f"**Automod:** {'ENABLED' if cfg['enabled'] else 'DISABLED'} · "
                f"Debug: {'ON' if cfg.get('debug') else 'OFF'}\n"
                f"Limit: {cfg['limit']} / {cfg['window']}s · Mute: {cfg['mute_minutes']}m\n"
                f"Logs: {f'<#{logs}>' if logs else 'not set'}"
            )

        if action in ("debug", "dbg"):
            cfg["debug"] = not bool(cfg.get("debug"))
            save_automod_config(ctx.guild.id, cfg)
            state = "ON" if cfg["debug"] else "OFF"
            await ctx.send(f"🐛 Automod debug is now **{state}**.")
            if cfg["debug"]:
                await send_log(
                    self.bot, ctx.guild,
                    f"🐛 Automod debug ON by {ctx.author} (`{ctx.author.id}`)",
                )
            return

        if action in ("config", "cfg", "settings"):
            embed = discord.Embed(
                title="Automod Configuration",
                description=format_config_description(cfg),
                color=0x5865F2,
            )
            embed.set_footer(
                text=f"Status: {'ENABLED' if cfg['enabled'] else 'DISABLED'} · Debug: {'ON' if cfg.get('debug') else 'OFF'}"
            )
            return await ctx.send(embed=embed, view=AutomodConfigView())

        await ctx.send(
            "❌ Usage: `automod enable` | `disable` | `status` | `config` | `debug`"
        )

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
        if member is None or has_msg_immunity(member):
            return

        key = (message.guild.id, member.id)
        now = time.time()

        if self._muted_until.get(key, 0) > now:
            return
        if key in self._handling:
            return

        limit = int(cfg.get("limit") or SPAM_LIMIT)
        window = float(cfg.get("window") or SPAM_WINDOW)
        mute_mins = int(cfg.get("mute_minutes") or MUTE_MINUTES)
        debug_on = bool(cfg.get("debug"))

        async with self._locks[key]:
            if self._muted_until.get(key, 0) > time.time() or key in self._handling:
                return

            bucket = self._buckets[key]
            bucket.append((time.time(), message.channel.id, message.id))

            while bucket and (time.time() - bucket[0][0]) > window:
                bucket.popleft()

            count = len(bucket)
            uname = str(member)
            uid = member.id

            if debug_on:
                debug_line = f"{uname} ({uid}) | message count: {count}"
                print(f"[automod] {debug_line}")
                await send_log(self.bot, message.guild, debug_line)

            if count < limit:
                return

            self._handling.add(key)
            burst = list(bucket)
            bucket.clear()
            self._muted_until[key] = time.time() + (mute_mins * 60)

        try:
            span = round(burst[-1][0] - burst[0][0], 2) if len(burst) > 1 else 0.0
            await send_log(
                self.bot, message.guild,
                f"SPAM DETECTED {uname} ({uid}) — {len(burst)} msgs in {span}s "
                f"(window {window}s) → muting {mute_mins}m",
            )

            # Mute first
            try:
                try:
                    member = await message.guild.fetch_member(uid)
                except Exception:
                    pass

                me = message.guild.me
                if me is None:
                    await send_log(self.bot, message.guild, f"MUTE FAIL {uname} ({uid}): bot not in cache")
                elif not me.guild_permissions.moderate_members:
                    await send_log(
                        self.bot, message.guild,
                        f"MUTE FAIL {uname} ({uid}): bot missing Moderate Members (Timeout)",
                    )
                elif member.top_role >= me.top_role and member.id != message.guild.owner_id:
                    await send_log(
                        self.bot, message.guild,
                        f"MUTE FAIL {uname} ({uid}): their role is higher/equal to the bot — move bot role UP",
                    )
                else:
                    until = discord.utils.utcnow() + timedelta(minutes=mute_mins)
                    await member.timeout(
                        until,
                        reason=f"[Automod] Spam: {len(burst)} messages in {span}s",
                    )
                    await send_log(
                        self.bot, message.guild,
                        f"MUTED {uname} ({uid}) for {mute_mins}m",
                    )
                    print(f"[automod] MUTED {uid}")
            except Exception as e:
                await send_log(
                    self.bot, message.guild,
                    f"MUTE FAIL {uname} ({uid}): {type(e).__name__}: {e}",
                )
                print(f"[automod] mute exception: {e}")

            # Delete burst
            by_channel: dict[int, list[int]] = {}
            for _ts, ch_id, msg_id in burst:
                by_channel.setdefault(ch_id, []).append(msg_id)

            for ch_id, msg_ids in by_channel.items():
                channel = message.guild.get_channel(ch_id) or message.channel
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
                except Exception as e:
                    print(f"[automod] delete fail: {e}")
                    for mid in msg_ids:
                        try:
                            m = await channel.fetch_message(mid)
                            await m.delete()
                        except Exception:
                            pass
        finally:
            self._handling.discard(key)


async def setup(bot):
    if bot.get_cog("AutoModCog") is not None:
        await bot.remove_cog("AutoModCog")
    await bot.add_cog(AutoModCog(bot))
    print("[automod] cog loaded")
