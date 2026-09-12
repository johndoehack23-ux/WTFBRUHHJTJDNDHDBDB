"""
.opsafe enable | disable | unlock | test
Creator / server owner only.

enable  -> only turns monitoring ON (does NOT lockdown)
disable -> turns monitoring OFF
unlock  -> restores channel perms after a real lockdown
test    -> safe pre-check (Mongo + permissions), no lockdown
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from functions import load_stats, save_stats

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
        return {
            "enabled": False,
            "locked": False,
            "saved_overwrites": {},
            "join_limit": 6,
            "join_window_seconds": 86400,  # default 1 day
            "require_spam": True,
            "spam_message_count": 6,
        }
    try:
        join_limit = int(raw.get("join_limit", 6))
    except (TypeError, ValueError):
        join_limit = 6
    try:
        join_window = int(raw.get("join_window_seconds", 86400))
    except (TypeError, ValueError):
        join_window = 86400
    join_limit = max(1, min(15, join_limit))
    # 1 hour .. 24 hours minimum window support, up to 10 days still ok
    join_window = max(3600, min(10 * 86400, join_window))
    return {
        "enabled": bool(raw.get("enabled", False)),
        "locked": bool(raw.get("locked", False)),
        "saved_overwrites": raw.get("saved_overwrites") or {},
        "join_limit": join_limit,
        "join_window_seconds": join_window,
        "require_spam": bool(raw.get("require_spam", True)) if isinstance(raw, dict) else True,
        "spam_message_count": max(5, min(15, int((raw or {}).get("spam_message_count", 6) if isinstance(raw, dict) else 6))),
    }


def save_cfg(guild_id, cfg: dict):
    stats = load_stats()
    if "opsafe" not in stats or not isinstance(stats["opsafe"], dict):
        stats["opsafe"] = {}
    stats["opsafe"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "locked": bool(cfg.get("locked", False)),
        "saved_overwrites": cfg.get("saved_overwrites") or {},
        "join_limit": int(cfg.get("join_limit", 6)),
        "join_window_seconds": int(cfg.get("join_window_seconds", 86400)),
        "require_spam": bool(cfg.get("require_spam", True)),
        "spam_message_count": max(5, min(15, int(cfg.get("spam_message_count", 6)))),
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
    g = dict(an.get(str(guild_id)) or {})
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


def _is_announcement_channel(channel) -> bool:
    if not isinstance(channel, discord.TextChannel):
        return False
    try:
        if channel.is_news():
            return True
    except Exception:
        pass
    name = (channel.name or "").lower()
    return "announcement" in name or name in ("announcements", "news", "updates")


async def lockdown_guild(bot, guild: discord.Guild):
    """Private all channels except announcement. Saves prior overwrites to Mongo."""
    cfg = get_cfg(guild.id)
    if cfg.get("locked"):
        return

    saved = {}
    locked_count = 0
    skipped = 0

    for channel in list(guild.channels):
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel, discord.StageChannel)):
            continue

        is_ann = _is_announcement_channel(channel)

        try:
            # Save full overwrite state (including whether @everyone had one)
            overwrites = {}
            everyone_ow = channel.overwrites_for(guild.default_role)
            overwrites[str(guild.default_role.id)] = {
                "allow": everyone_ow.pair()[0].value,
                "deny": everyone_ow.pair()[1].value,
                "type": "role",
            }
            for target, ow in channel.overwrites.items():
                if target.id == guild.default_role.id:
                    continue
                overwrites[str(target.id)] = {
                    "allow": ow.pair()[0].value,
                    "deny": ow.pair()[1].value,
                    "type": "role" if isinstance(target, discord.Role) else "member",
                }
            saved[str(channel.id)] = overwrites

            if is_ann:
                skipped += 1
                continue

            await channel.set_permissions(
                guild.default_role,
                view_channel=False,
                reason="[OpSafe] lockdown",
            )
            locked_count += 1
        except Exception as e:
            print(f"[opsafe] lockdown channel {getattr(channel, 'id', '?')}: {e}")

    cfg["locked"] = True
    cfg["saved_overwrites"] = saved
    save_cfg(guild.id, cfg)
    print(f"[opsafe] lockdown guild={guild.id} locked={locked_count} skipped_ann={skipped}")

    ann = None
    for channel in guild.text_channels:
        if _is_announcement_channel(channel):
            ann = channel
            break
    if ann is None:
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

    await opsafe_log(
        bot, guild,
        f"<@{guild.owner_id}>\nUse `.opsafe unlock` to unlockdown!",
    )


async def unlock_guild(bot, guild: discord.Guild):
    """Restore saved overwrites from Mongo (including @everyone)."""
    cfg = get_cfg(guild.id)
    saved = cfg.get("saved_overwrites") or {}

    restored = 0
    for ch_id, overs in saved.items():
        channel = guild.get_channel(int(ch_id))
        if channel is None:
            continue
        try:
            for target_id, data in overs.items():
                tid = int(target_id)
                target = guild.get_role(tid) or guild.get_member(tid)
                if target is None:
                    continue
                allow = discord.Permissions(int(data.get("allow", 0)))
                deny = discord.Permissions(int(data.get("deny", 0)))
                # If both empty, clear the overwrite
                if allow.value == 0 and deny.value == 0:
                    await channel.set_permissions(target, overwrite=None, reason="[OpSafe] unlock")
                else:
                    ow = discord.PermissionOverwrite.from_pair(allow, deny)
                    await channel.set_permissions(target, overwrite=ow, reason="[OpSafe] unlock")
            restored += 1
        except Exception as e:
            print(f"[opsafe] unlock {ch_id}: {e}")

    cfg["locked"] = False
    cfg["saved_overwrites"] = {}
    save_cfg(guild.id, cfg)
    await opsafe_log(bot, guild, f"OpSafe lockdown lifted ({restored} channels restored).")
    print(f"[opsafe] unlock guild={guild.id} restored={restored}")



def parse_join_timer(text: str) -> int | None:
    """
    Parse timer text.
    Hours: 1-24 (e.g. `1 hour`, `12 hours`, `24h`)
    Days: 1-10 (e.g. `1 Day`, `2 days`)
    Plain number 1-24 = hours. Plain number with day unit = days.
    Minutes not allowed.
    """
    t = text.strip().lower().replace(",", "")
    if not t:
        return None
    # plain number → hours (1-24)
    if t.isdigit():
        hours = int(t)
        if 1 <= hours <= 24:
            return hours * 3600
        if 1 <= hours <= 10:
            # treat 1-10 alone as days if >24 not possible; already handled 1-24 as hours
            return hours * 3600
        return None
    # compact forms: 12h, 2d
    if len(t) >= 2 and t[:-1].isdigit():
        num = int(t[:-1])
        u = t[-1]
        if u == "h" and 1 <= num <= 24:
            return num * 3600
        if u == "d" and 1 <= num <= 10:
            return num * 86400
        return None
    parts = t.split()
    if len(parts) != 2:
        return None
    try:
        num = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].rstrip("s")
    if unit in ("minute", "min", "m"):
        return None
    if unit in ("hour", "hr", "h"):
        if num < 1 or num > 24:
            return None
        return int(num * 3600)
    if unit in ("day", "d"):
        if num < 1 or num > 10:
            return None
        return int(num * 86400)
    return None


class OpSafeJoinModal(discord.ui.Modal, title="Edit"):
    max_join = discord.ui.TextInput(
        label="Max joining users (1-15)",
        placeholder="1-15 (default 6)",
        required=True,
        max_length=2,
    )
    timer = discord.ui.TextInput(
        label="Join timer (1-24 hours)",
        placeholder="1-24 hours, e.g. 1 hour, 12 hours, 24h",
        required=True,
        max_length=20,
    )
    spam_field = discord.ui.TextInput(
        label="spam",
        placeholder="Type spam to require spam, or leave empty / no",
        required=False,
        max_length=10,
    )
    spam_count_field = discord.ui.TextInput(
        label="Raid spam message count (5-15)",
        placeholder="5-15 (default 6)",
        required=False,
        max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not can_opsafe(interaction.user, interaction.guild):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        try:
            limit = int(str(self.max_join.value).strip())
        except ValueError:
            return await interaction.response.send_message("Join limit must be a number 1-15.", ephemeral=True)
        if limit < 1 or limit > 15:
            return await interaction.response.send_message("Join limit max is 15.", ephemeral=True)
        secs = parse_join_timer(str(self.timer.value))
        if secs is None:
            return await interaction.response.send_message(
                "Invalid timer. Use 1-24 hours (`1 hour`, `12 hours`, `24h`) or 1-10 days (`1 Day`). Minutes not allowed.",
                ephemeral=True,
            )
        spam_raw = str(self.spam_field.value or "").strip().lower()
        require_spam = spam_raw in ("spam", "yes", "true", "on", "1")
        spam_count = 6
        sc_raw = str(self.spam_count_field.value or "").strip()
        if sc_raw:
            try:
                spam_count = int(sc_raw)
            except ValueError:
                return await interaction.response.send_message(
                    "Spam message count must be a number 5-15.", ephemeral=True
                )
            if spam_count < 5 or spam_count > 15:
                return await interaction.response.send_message(
                    "Spam message count must be between 5 and 15.", ephemeral=True
                )
        cfg = get_cfg(interaction.guild.id)
        cfg["join_limit"] = limit
        cfg["join_window_seconds"] = secs
        cfg["require_spam"] = require_spam
        cfg["spam_message_count"] = spam_count
        save_cfg(interaction.guild.id, cfg)
        if secs >= 86400:
            tlabel = f"{secs / 86400:g} day(s)"
        else:
            tlabel = f"{secs / 3600:g} hour(s)"
        await interaction.response.send_message(
            f"Updated. Join limit **{limit}** in **{tlabel}**. "
            f"Spam required: **{'yes' if require_spam else 'no'}**. "
            f"Spam messages: **{spam_count}**.",
            ephemeral=True,
        )


class OpSafeConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.success)
    async def edit_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Creator always allowed; also server owner
        uid = interaction.user.id
        if uid != CREATOR_ID and not (
            interaction.guild and interaction.guild.owner_id == uid
        ):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message(
                "Use this button in a server.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(OpSafeJoinModal())
        except Exception as e:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"Edit failed: `{e}`", ephemeral=True)
                else:
                    await interaction.response.send_message(f"Edit failed: `{e}`", ephemeral=True)
            except Exception:
                print(f"[opsafe] edit modal fail: {e}")


class OpSafeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._trust_hits: dict[tuple[int, int], dict] = defaultdict(lambda: {"cats": set(), "t0": 0.0})
        self._joins: dict[int, deque] = defaultdict(lambda: deque(maxlen=500))
        self._new_spam: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=20))
        self._raid_spam_flag: dict[int, float] = {}  # guild_id -> time of recent new-user spam ban

    @commands.command(name="opsafe")
    async def opsafe_cmd(self, ctx: commands.Context, action: str = None):
        if not ctx.guild:
            return
        if not can_opsafe(ctx.author, ctx.guild):
            return await ctx.send("No permission.")

        if not action:
            cfg = get_cfg(ctx.guild.id)
            return await ctx.send(
                f"**OpSafe:** {'ON' if cfg['enabled'] else 'OFF'}"
                f"{' · LOCKED' if cfg.get('locked') else ''}\n"
                f"`.opsafe enable` / `disable` / `unlock` / `config`"
            )

        action = action.lower().strip()

        if action in ("enable", "on", "true"):
            # SAFE: only flips the flag. Does NOT touch channels.
            cfg = get_cfg(ctx.guild.id)
            cfg["enabled"] = True
            # keep locked/saved_overwrites as-is
            save_cfg(ctx.guild.id, cfg)
            # verify mongo round-trip
            verify = get_cfg(ctx.guild.id)
            if not verify.get("enabled"):
                return await ctx.send("Failed to save OpSafe to MongoDB. Check MONGO_URI.")
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
            return await ctx.send("Lockdown removed.")

        if action == "test":
            if ctx.author.id != CREATOR_ID:
                return  # silent for non-creator
            # Instant lockdown test — no need for joins/spam
            cfg = get_cfg(ctx.guild.id)
            if not cfg.get("enabled"):
                cfg["enabled"] = True
                save_cfg(ctx.guild.id, cfg)
            await ctx.send("OpSafe **TEST** — locking down now…")
            await lockdown_guild(self.bot, ctx.guild)
            return await ctx.send(
                "Lockdown applied (test). Use `.opsafe unlock` to restore channels."
            )

        if action == "config":
            if not can_opsafe(ctx.author, ctx.guild):
                return await ctx.send("No permission.")
            cfg = get_cfg(ctx.guild.id)
            window = int(cfg.get("join_window_seconds") or 86400)
            if window >= 86400:
                wlabel = f"{window / 86400:g} day(s)"
            else:
                wlabel = f"{window / 3600:g} hour(s)"
            desc = "\n".join([
                "OVERPOWERED Security watches this server for raid patterns and can lock channels when a flood is detected.",
                "",
                "How it works.",
                f"Join limit is currently **{cfg.get('join_limit', 6)}** users inside **{wlabel}**.",
                f"Spam requirement is **{'ON' if cfg.get('require_spam', True) else 'OFF'}**. When ON, a new member must also spam about **{cfg.get('spam_message_count', 6)}** messages in a short window before lockdown can trigger with the join flood.",
                "When spam is OFF, the join flood alone can trigger lockdown once the join limit is hit inside the timer window.",
                "",
                "Press **Edit** to change the join limit (1-15), the timer (1-24 hours or up to 10 days), whether spam is required (type spam), and how many spam messages (5-15).",
                "Use `.opsafe enable` to arm monitoring. Use `.opsafe unlock` only after a lockdown to restore channel permissions.",
                "`.opsafe test` is creator only and force locks the server for practice without needing real joins.",
            ])
            embed = discord.Embed(
                title="🔧 Configure OVERPOWERED Security System 💻",
                description=desc,
                color=0xE0FFFF,
            )
            return await ctx.send(embed=embed, view=OpSafeConfigView())

        await ctx.send("Usage: `.opsafe enable` | `disable` | `unlock` | `config`")

    def _trust_mark(self, guild_id: int, user_id: int, category: str) -> bool:
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
            f"OpSafe banned {member} (`{member.id}`) — {reason}\n"
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

        # Trusted spam (6 in 5s) counts as one abuse category
        if uid in bits["whitelist"] or uid in bits["extraowners"]:
            if author.id not in (guild.owner_id, CREATOR_ID):
                key = ("trust", guild.id, author.id)
                now = time.time()
                q = self._new_spam[key]
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

        member = author if isinstance(author, discord.Member) else guild.get_member(author.id)
        if member is None:
            return

        joined = member.joined_at
        is_new = bool(joined and (discord.utils.utcnow() - joined).total_seconds() < 172800)  # 2 days
        if not is_new:
            return

        key = (guild.id, member.id)
        now = time.time()
        q = self._new_spam[key]
        q.append(now)
        need = int(cfg.get("spam_message_count") or 6)
        need = max(5, min(15, need))
        while q and now - q[0] > 2.0:
            q.popleft()
        if len(q) < need:
            return

        q.clear()
        try:
            await guild.ban(member, reason="[OpSafe] raid spam", delete_message_days=1)
        except Exception as e:
            print(f"[opsafe] raid ban fail: {e}")

        self._raid_spam_flag[guild.id] = now

        joins = self._joins[guild.id]
        window = int(cfg.get("join_window_seconds") or 86400)
        limit = int(cfg.get("join_limit") or 6)
        while joins and now - joins[0] > window:
            joins.popleft()

        # Lockdown only if join flood ALSO active
        if len(joins) >= limit and not cfg.get("locked"):
            await opsafe_log(
                self.bot, guild,
                f"<@{guild.owner_id}>\nUse `.opsafe unlock` to unlockdown!",
            )
            await lockdown_guild(self.bot, guild)
        else:
            await opsafe_log(
                self.bot, guild,
                f"OpSafe banned new spammer {member} (`{member.id}`)\n<@{guild.owner_id}>",
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = get_cfg(member.guild.id)
        if not cfg.get("enabled"):
            return
        joins = self._joins[member.guild.id]
        now = time.time()
        joins.append(now)
        window = int(cfg.get("join_window_seconds") or 86400)
        limit = int(cfg.get("join_limit") or 6)
        while joins and now - joins[0] > window:
            joins.popleft()

        # Join flood: if require_spam, need recent spam signal. Else lockdown on joins alone.
        if len(joins) >= limit and not cfg.get("locked"):
            require_spam = bool(cfg.get("require_spam", True))
            spam_at = self._raid_spam_flag.get(member.guild.id, 0)
            if (not require_spam) or (now - spam_at <= 120):
                await opsafe_log(
                    self.bot, member.guild,
                    f"<@{member.guild.owner_id}>\nUse `.opsafe unlock` to unlockdown!",
                )
                await lockdown_guild(self.bot, member.guild)


async def setup(bot):
    await bot.add_cog(OpSafeCog(bot))
    print("[opsafe] cog loaded")
