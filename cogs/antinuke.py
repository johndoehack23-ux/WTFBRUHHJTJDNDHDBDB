"""
Anti-Nuke system
- .whitelist / .wl <userID>     — server owner or bot creator only
- .antinuke / .au enable|disable|config
  Access: whitelisted, creator, op, or server owner
Everything starts DISABLED per server.

Defaults when enabled:
  Roles    → Kick
  Channels → Ban
  Messages → Mute 5 min (spam: 6 msgs / 3s)
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from functions import load_stats, save_stats, is_op

CREATOR_ID = 1465295674768883889

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_PUNISHMENTS = {
    "roles": {"type": "kick", "duration": 0},
    "channels": {"type": "ban", "duration": 0},
    "messages": {"type": "mute", "duration": 5},
}
DEFAULT_SPAM = {"count": 6, "window": 3.0}  # 6 msgs within 3s (Sapphire-style sliding window)

TOKEN_RE = re.compile(
    r"(?:[MN][A-Za-z\d]{23,}\.[\w-]{6,}\.[\w-]{27,}|mfa\.[\w-]{80,})",
    re.IGNORECASE,
)
INVITE_RE = re.compile(
    r"(?:discord\.gg/|discord(?:app)?\.com/invite/)[a-zA-Z0-9\-]+",
    re.IGNORECASE,
)
NSFW_DOMAIN_RE = re.compile(
    r"https?://(?:www\.)?(?:pornhub|xvideos|xnxx|xhamster|redtube|youporn|onlyfans|chaturbate|stripchat|nhentai|rule34|e621|gelbooru|hentai|porn|xxx)[^\s]*",
    re.IGNORECASE,
)


def _empty_guild_config() -> dict:
    return {
        "enabled": False,
        "whitelist": [],
        "logs_channel": None,
        "punishments": {
            "roles": dict(DEFAULT_PUNISHMENTS["roles"]),
            "channels": dict(DEFAULT_PUNISHMENTS["channels"]),
            "messages": dict(DEFAULT_PUNISHMENTS["messages"]),
        },
        "spam": dict(DEFAULT_SPAM),
    }


def _normalize_punishment(category: str, data: dict) -> dict:
    """Roles/Channels never use mute — force kick/ban defaults."""
    ptype = str((data or {}).get("type", DEFAULT_PUNISHMENTS[category]["type"])).lower()
    try:
        duration = int((data or {}).get("duration", DEFAULT_PUNISHMENTS[category]["duration"]))
    except (TypeError, ValueError):
        duration = DEFAULT_PUNISHMENTS[category]["duration"]

    if category in ("roles", "channels") and ptype == "mute":
        ptype = "kick" if category == "roles" else "ban"
    if ptype not in ("mute", "kick", "ban"):
        ptype = DEFAULT_PUNISHMENTS[category]["type"]
    return {"type": ptype, "duration": max(0, duration)}


def get_antinuke_config(guild_id: int | str) -> dict:
    stats = load_stats()
    raw = (stats.get("antinuke") or {}).get(str(guild_id))
    if not isinstance(raw, dict):
        return _empty_guild_config()
    cfg = _empty_guild_config()
    cfg["enabled"] = bool(raw.get("enabled", False))
    cfg["whitelist"] = [str(x) for x in (raw.get("whitelist") or [])]
    cfg["logs_channel"] = raw.get("logs_channel")
    pun = raw.get("punishments") or {}
    for key in ("roles", "channels", "messages"):
        if isinstance(pun.get(key), dict):
            cfg["punishments"][key] = _normalize_punishment(key, pun[key])
    spam = raw.get("spam") or {}
    try:
        cfg["spam"]["count"] = int(spam.get("count", DEFAULT_SPAM["count"]))
        cfg["spam"]["window"] = float(spam.get("window", DEFAULT_SPAM["window"]))
    except (TypeError, ValueError):
        pass
    return cfg


def save_antinuke_config(guild_id: int | str, cfg: dict):
    stats = load_stats()
    if "antinuke" not in stats or not isinstance(stats["antinuke"], dict):
        stats["antinuke"] = {}
    pun = cfg.get("punishments") or {}
    stats["antinuke"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "whitelist": [str(x) for x in (cfg.get("whitelist") or [])],
        "logs_channel": cfg.get("logs_channel"),
        "punishments": {
            "roles": _normalize_punishment("roles", pun.get("roles") or DEFAULT_PUNISHMENTS["roles"]),
            "channels": _normalize_punishment("channels", pun.get("channels") or DEFAULT_PUNISHMENTS["channels"]),
            "messages": _normalize_punishment("messages", pun.get("messages") or DEFAULT_PUNISHMENTS["messages"]),
        },
        "spam": cfg.get("spam") or dict(DEFAULT_SPAM),
    }
    save_stats(stats)


def is_antinuke_enabled(guild_id: int | str) -> bool:
    return bool(get_antinuke_config(guild_id).get("enabled"))


def is_antinuke_whitelisted(guild_id: int | str, user_id: int) -> bool:
    cfg = get_antinuke_config(guild_id)
    return str(user_id) in cfg.get("whitelist", [])


def can_manage_whitelist(user: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
    if user.id == CREATOR_ID:
        return True
    if guild and guild.owner_id == user.id:
        return True
    return False


def can_use_antinuke(user: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
    if user.id == CREATOR_ID:
        return True
    if is_op(user.id):
        return True
    if guild and guild.owner_id == user.id:
        return True
    if guild and is_antinuke_whitelisted(guild.id, user.id):
        return True
    return False


def is_protected_actor(user_id: int, guild: discord.Guild) -> bool:
    """Antinuke whitelist / owner / creator / op — NEVER punish these."""
    if user_id == CREATOR_ID:
        return True
    if is_op(user_id):
        return True
    if guild.owner_id == user_id:
        return True
    if is_antinuke_whitelisted(guild.id, user_id):
        return True
    return False


def has_message_immunity(member: discord.Member) -> bool:
    """
    Discord permission immunity for MESSAGE antinuke only.
    Administrator or Manage Messages → skip mute/spam checks.
    Bot trusted/admin lists do NOT grant immunity (they can still be muted).
    """
    try:
        perms = member.guild_permissions
        if perms.administrator or perms.manage_messages:
            return True
    except Exception:
        pass
    return False


def bot_role_is_top(guild: discord.Guild, bot_user: discord.Member) -> bool:
    if not guild.me:
        return False
    roles = [r for r in guild.roles if not r.is_default()]
    if not roles:
        return True
    top = max(roles, key=lambda r: r.position)
    bot_top = guild.me.top_role
    return bot_top.id == top.id or bot_top.position >= top.position


def _duration_label(minutes: int) -> str:
    if minutes <= 0:
        return "0 (infinite)"
    return f"{minutes} min"


def format_punishment_description(cfg: dict) -> str:
    pun = cfg.get("punishments") or DEFAULT_PUNISHMENTS
    lines = []
    for key, title in (("roles", "Roles"), ("channels", "Channels"), ("messages", "Messages")):
        p = pun.get(key) or DEFAULT_PUNISHMENTS[key]
        lines.append(
            f"**{title}**\n"
            f"Punishment: {str(p.get('type', 'kick')).title()}\n"
            f"Duration: {_duration_label(int(p.get('duration', 0)))}"
        )
    return "\n\n".join(lines)


async def antinuke_log(bot, guild: discord.Guild, text: str):
    cfg = get_antinuke_config(guild.id)
    ch_id = cfg.get("logs_channel")
    if not ch_id:
        return
    try:
        ch = bot.get_channel(int(ch_id)) or await bot.fetch_channel(int(ch_id))
        if isinstance(ch, discord.TextChannel):
            await ch.send(text)
    except Exception:
        pass


async def apply_punishment(bot, guild: discord.Guild, member: discord.Member, category: str, reason: str):
    if is_protected_actor(member.id, guild):
        return

    # Message antinuke: skip Discord Administrator / Manage Messages
    if category == "messages" and has_message_immunity(member):
        await antinuke_log(
            bot, guild,
            f"⏭️ Skipped {member} (`{member.id}`) — has Administrator or Manage Messages ({reason})",
        )
        return

    cfg = get_antinuke_config(guild.id)
    pun = _normalize_punishment(
        category,
        (cfg.get("punishments") or {}).get(category) or DEFAULT_PUNISHMENTS.get(category, {}),
    )
    ptype = pun["type"]
    duration = pun["duration"]

    me = guild.me
    if me is None:
        await antinuke_log(bot, guild, f"⚠️ Cannot punish {member}: bot member not cached")
        return

    # Hierarchy: bot must be above the target (except guild owner which is already protected)
    if member.top_role >= me.top_role and member.id != guild.owner_id:
        msg = (
            f"⚠️ Cannot punish {member} (`{member.id}`) — their role is >= bot role. "
            f"Move the bot role higher. Reason: {reason}"
        )
        print(f"[antinuke] {msg}")
        await antinuke_log(bot, guild, msg)
        return

    try:
        if ptype == "ban":
            if not me.guild_permissions.ban_members:
                msg = f"⚠️ Cannot ban {member} (`{member.id}`) — bot missing **Ban Members**"
                print(f"[antinuke] {msg}")
                await antinuke_log(bot, guild, msg)
                return
            await guild.ban(member, reason=f"[AntiNuke/{category}] {reason}", delete_message_days=0)
            await antinuke_log(bot, guild, f"🔨 Banned {member} (`{member.id}`) — {reason}")
        elif ptype == "kick":
            if not me.guild_permissions.kick_members:
                msg = f"⚠️ Cannot kick {member} (`{member.id}`) — bot missing **Kick Members**"
                print(f"[antinuke] {msg}")
                await antinuke_log(bot, guild, msg)
                return
            await member.kick(reason=f"[AntiNuke/{category}] {reason}")
            await antinuke_log(bot, guild, f"👢 Kicked {member} (`{member.id}`) — {reason}")
        else:
            # mute = timeout
            if not me.guild_permissions.moderate_members:
                msg = (
                    f"⚠️ Cannot mute {member} (`{member.id}`) — bot missing **Moderate Members** "
                    f"(Timeout). Enable it on the bot role."
                )
                print(f"[antinuke] {msg}")
                await antinuke_log(bot, guild, msg)
                return
            if duration <= 0:
                until = discord.utils.utcnow() + timedelta(days=28)
            else:
                until = discord.utils.utcnow() + timedelta(minutes=max(1, duration))
            await member.timeout(until, reason=f"[AntiNuke/{category}] {reason}")
            print(f"[antinuke] muted {member.id} for {duration}m — {reason}")
            await antinuke_log(
                bot, guild,
                f"🔇 Muted {member} (`{member.id}`) for {_duration_label(duration)} — {reason}",
            )
    except (discord.Forbidden, discord.HTTPException) as e:
        msg = f"⚠️ Failed to punish {member} (`{member.id}`) [{ptype}]: {e}"
        print(f"[antinuke] {msg}")
        await antinuke_log(bot, guild, msg)


async def find_audit_executor(
    guild: discord.Guild,
    actions,
    target_id: int | None = None,
    within_seconds: float = 15.0,
) -> discord.Member | None:
    """
    Who performed a recent audit action.
    `actions` may be a single AuditLogAction or a list of them.
    """
    if not isinstance(actions, (list, tuple, set)):
        actions = [actions]

    try:
        # Broad recent log scan — permission overwrites often aren't target-matched cleanly
        async for entry in guild.audit_logs(limit=12):
            if entry.action not in actions:
                continue
            if (discord.utils.utcnow() - entry.created_at).total_seconds() > within_seconds:
                continue
            if target_id is not None and entry.target is not None:
                tid = getattr(entry.target, "id", None)
                # For overwrites, target can be the channel OR the role/member overwritten
                if tid is not None and tid != target_id:
                    # still accept if extra matches channel via changes (handled by caller passing channel id)
                    # Allow mismatch only when action is overwrite_* and we already filtered by action
                    if entry.action not in (
                        discord.AuditLogAction.overwrite_create,
                        discord.AuditLogAction.overwrite_update,
                        discord.AuditLogAction.overwrite_delete,
                    ):
                        continue
            user = entry.user
            if user is None or getattr(user, "bot", False):
                continue
            member = guild.get_member(user.id)
            if member is None:
                try:
                    member = await guild.fetch_member(user.id)
                except Exception:
                    continue
            return member
    except (discord.Forbidden, discord.HTTPException):
        return None
    return None


# ── Config UI ────────────────────────────────────────────────────────────────

class PunishmentModal(discord.ui.Modal):
    def __init__(self, category: str):
        # Title is ONLY the category name — never "Mute"
        titles = {"roles": "Roles", "channels": "Channels", "messages": "Messages"}
        super().__init__(title=titles.get(category, category.title()))
        self.category = category

        if category in ("roles", "channels"):
            placeholder = "Kick or Ban"
            hint = "Kick or Ban only (Mute not allowed)"
        else:
            placeholder = "Mute, Kick, or Ban"
            hint = "Mute, Kick, or Ban"

        self.punishment_name = discord.ui.TextInput(
            label="Punishment Name",
            placeholder=placeholder,
            required=True,
            max_length=10,
        )
        self.duration_input = discord.ui.TextInput(
            label="Duration",
            placeholder="Minutes (0 = infinite). Example: 10",
            required=True,
            max_length=6,
        )
        self.add_item(self.punishment_name)
        self.add_item(self.duration_input)
        self._hint = hint

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)

        name = str(self.punishment_name.value).strip().lower()
        if self.category in ("roles", "channels"):
            if name not in ("kick", "ban"):
                return await interaction.response.send_message(
                    f"❌ For **{self.category}**, punishment must be `Kick` or `Ban` (no Mute).",
                    ephemeral=True,
                )
        else:
            if name not in ("mute", "kick", "ban"):
                return await interaction.response.send_message(
                    "❌ Punishment must be `Mute`, `Kick`, or `Ban`.",
                    ephemeral=True,
                )
        try:
            duration = int(str(self.duration_input.value).strip())
            if duration < 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Duration must be a number of minutes (0 = infinite).", ephemeral=True
            )

        cfg = get_antinuke_config(interaction.guild.id)
        cfg["punishments"][self.category] = {"type": name, "duration": duration}
        save_antinuke_config(interaction.guild.id, cfg)

        await interaction.response.send_message(
            f"✅ **{self.category.title()}** → `{name.title()}` · Duration `{_duration_label(duration)}`.",
            ephemeral=True,
        )


class PunishmentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _open(self, interaction: discord.Interaction, category: str):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)
        await interaction.response.send_modal(PunishmentModal(category))

    @discord.ui.button(label="Roles", style=discord.ButtonStyle.danger, custom_id="au_pun_roles")
    async def roles_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open(interaction, "roles")

    @discord.ui.button(label="Channels", style=discord.ButtonStyle.danger, custom_id="au_pun_channels")
    async def channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open(interaction, "channels")

    @discord.ui.button(label="Messages", style=discord.ButtonStyle.danger, custom_id="au_pun_messages")
    async def messages_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open(interaction, "messages")


class LogsChannelModal(discord.ui.Modal, title="Set Anti Nuke Logs"):
    server_id_input = discord.ui.TextInput(
        label="serverID",
        placeholder="This server's ID",
        required=True,
        max_length=30,
    )
    channel_id_input = discord.ui.TextInput(
        label="channelID",
        placeholder="Logs channel ID (1 channel only)",
        required=True,
        max_length=30,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)

        sid = str(self.server_id_input.value).strip()
        cid = str(self.channel_id_input.value).strip().replace("<#", "").replace(">", "")
        if not sid.isdigit() or int(sid) != interaction.guild.id:
            return await interaction.response.send_message(
                "❌ serverID must match this server.", ephemeral=True
            )
        if not cid.isdigit():
            return await interaction.response.send_message(
                "❌ channelID must be numeric.", ephemeral=True
            )

        channel = interaction.guild.get_channel(int(cid))
        if channel is None:
            try:
                channel = await interaction.client.fetch_channel(int(cid))
            except Exception:
                channel = None
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != interaction.guild.id:
            return await interaction.response.send_message(
                "❌ Channel not found in this server.", ephemeral=True
            )

        cfg = get_antinuke_config(interaction.guild.id)
        cfg["logs_channel"] = str(cid)
        save_antinuke_config(interaction.guild.id, cfg)

        await interaction.response.send_message(
            f"✅ Anti Nuke logs channel set to {channel.mention} (`{cid}`).",
            ephemeral=True,
        )


class ChannelsConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Set", style=discord.ButtonStyle.primary, custom_id="au_logs_set")
    async def set_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)
        await interaction.response.send_modal(LogsChannelModal())


class AntiNukeConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Punishment", style=discord.ButtonStyle.secondary, custom_id="au_cfg_punishment")
    async def punishment_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)
        cfg = get_antinuke_config(interaction.guild.id)
        embed = discord.Embed(
            title="Punishment Configuration",
            description=format_punishment_description(cfg),
            color=0xED4245,
        )
        embed.set_footer(text="Roles/Channels: Kick or Ban only · Messages: Mute/Kick/Ban")
        await interaction.response.send_message(embed=embed, view=PunishmentView(), ephemeral=True)

    @discord.ui.button(label="Channels", style=discord.ButtonStyle.secondary, custom_id="au_cfg_channels")
    async def channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)
        cfg = get_antinuke_config(interaction.guild.id)
        logs = cfg.get("logs_channel")
        logs_txt = f"`{logs}`" if logs else "`not set`"
        embed = discord.Embed(
            title="Channels Configuration",
            description=f"**Anti Nuke Logs:** {logs_txt}",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=ChannelsConfigView(), ephemeral=True)


# ── Cog ──────────────────────────────────────────────────────────────────────

class AntiNukeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._spam: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=30))
        # de-dupe rapid double events
        self._recent_hits: dict[tuple[int, int, str], float] = {}

    def _dedupe(self, guild_id: int, user_id: int, tag: str, window: float = 3.0) -> bool:
        """Return True if this hit should be ignored (duplicate)."""
        key = (guild_id, user_id, tag)
        now = time.monotonic()
        last = self._recent_hits.get(key, 0)
        if now - last < window:
            return True
        self._recent_hits[key] = now
        return False

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.command(name="whitelist", aliases=["wl"])
    async def whitelist_cmd(self, ctx: commands.Context, user_id: str = None):
        if not ctx.guild:
            return
        if not can_manage_whitelist(ctx.author, ctx.guild):
            return await ctx.send("❌ Only the **server owner** or **bot creator** can manage the antinuke whitelist.")

        if not user_id:
            cfg = get_antinuke_config(ctx.guild.id)
            wl = cfg.get("whitelist") or []
            if not wl:
                return await ctx.send("📭 Antinuke whitelist is empty.")
            lines = [f"• <@{uid}> (`{uid}`)" for uid in wl]
            return await ctx.send("**Antinuke whitelist:**\n" + "\n".join(lines))

        uid = user_id.strip().replace("<@", "").replace("!", "").replace(">", "")
        if not uid.isdigit():
            return await ctx.send("❌ Provide a numeric user ID.")
        if int(uid) == CREATOR_ID:
            return await ctx.send("❌ Cannot modify the bot creator.")

        cfg = get_antinuke_config(ctx.guild.id)
        wl = list(cfg.get("whitelist") or [])
        if uid in wl:
            wl.remove(uid)
            cfg["whitelist"] = wl
            save_antinuke_config(ctx.guild.id, cfg)
            return await ctx.send(f"✅ Removed <@{uid}> (`{uid}`) from antinuke whitelist.")
        wl.append(uid)
        cfg["whitelist"] = wl
        save_antinuke_config(ctx.guild.id, cfg)
        await ctx.send(f"✅ Added <@{uid}> (`{uid}`) to antinuke whitelist.")

    @commands.command(name="antinuke", aliases=["au"])
    async def antinuke_cmd(self, ctx: commands.Context, action: str = None, *rest):
        if not ctx.guild:
            return
        if not can_use_antinuke(ctx.author, ctx.guild):
            return await ctx.send(
                "❌ Only the **server owner**, **bot creator**, **op**, or **whitelisted** users can use antinuke."
            )

        if not action:
            cfg = get_antinuke_config(ctx.guild.id)
            state = "🟢 ENABLED" if cfg["enabled"] else "🔴 DISABLED"
            return await ctx.send(
                f"**Anti Nuke:** {state}\n"
                f"Use `{ctx.prefix}antinuke enable` / `disable` / `config`"
            )

        action = action.lower().strip()

        if action in ("enable", "on", "true"):
            if not bot_role_is_top(ctx.guild, ctx.guild.me):
                return await ctx.send(
                    "❌ Move the **bot's role to the top** of the role list before enabling Anti Nuke."
                )
            cfg = get_antinuke_config(ctx.guild.id)
            cfg["enabled"] = True
            save_antinuke_config(ctx.guild.id, cfg)
            await ctx.send(
                "✅ **Anti Nuke ENABLED**\n"
                "Defaults: **Roles → Kick** · **Channels → Ban** · **Messages → Mute 5m** (6 msgs / 3s)"
            )
            await antinuke_log(self.bot, ctx.guild, f"✅ Anti Nuke enabled by {ctx.author} (`{ctx.author.id}`)")
            return

        if action in ("disable", "off", "false"):
            cfg = get_antinuke_config(ctx.guild.id)
            cfg["enabled"] = False
            save_antinuke_config(ctx.guild.id, cfg)
            await ctx.send("🔴 **Anti Nuke DISABLED** for this server.")
            await antinuke_log(self.bot, ctx.guild, f"🔴 Anti Nuke disabled by {ctx.author} (`{ctx.author.id}`)")
            return

        if action in ("config", "cfg", "settings"):
            cfg = get_antinuke_config(ctx.guild.id)
            state = "ENABLED" if cfg["enabled"] else "DISABLED"
            embed = discord.Embed(
                title="Anti Nuke Configuration",
                description=(
                    f"Status: **{state}**\n"
                    f"Whitelisted users: **{len(cfg.get('whitelist') or [])}**\n"
                    f"Logs channel: `{cfg.get('logs_channel') or 'not set'}`\n\n"
                    "Use the buttons below to configure punishments and log channel."
                ),
                color=0x2f3136,
            )
            return await ctx.send(embed=embed, view=AntiNukeConfigView())

        await ctx.send("❌ Usage: `antinuke enable` | `disable` | `config`")

    # ── Messages ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not is_antinuke_enabled(message.guild.id):
            return
        if is_protected_actor(message.author.id, message.guild):
            return

        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if member is None:
            try:
                member = await message.guild.fetch_member(message.author.id)
            except Exception:
                return
        if member is None:
            return

        # Discord Administrator / Manage Messages → never mute for messages
        if has_message_immunity(member):
            return

        content = message.content or ""
        reason = None

        if TOKEN_RE.search(content):
            reason = "Posted a Discord token"
        elif NSFW_DOMAIN_RE.search(content):
            reason = "Posted NSFW link"
        elif INVITE_RE.search(content):
            reason = "Posted a Discord invite"

        # ── Sapphire-style anti-spam ──────────────────────────────────────
        # Sliding window: if 6 messages from the same user land within 3.0s,
        # treat it as spam. Messages do NOT need to be "instant" — just 6
        # inside any 3-second window.
        if reason is None:
            limit = 6
            window = 3.0
            key = (message.guild.id, member.id)
            now = time.time()
            q = self._spam[key]
            q.append(now)
            # Drop anything older than the window
            while q and (now - q[0]) > window:
                q.popleft()
            count = len(q)
            if count >= limit:
                span = round(now - q[0], 2) if q else window
                reason = f"Spam ({count} messages in {span}s / window {window}s)"
                q.clear()
                print(
                    f"[antinuke] SPAM TRIGGER guild={message.guild.id} user={member.id} "
                    f"channel={message.channel.id} count={count} span={span}s"
                )

        if not reason:
            return

        # Delete the triggering message (best-effort)
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Prevent double-mute from the same burst
        if self._dedupe(message.guild.id, member.id, "msg:spam" if reason.startswith("Spam") else f"msg:{reason}", window=3.0):
            return

        await apply_punishment(self.bot, message.guild, member, "messages", reason)

    # ── Channels (create / delete / update / permission overwrites) ──────────

    async def _punish_channel_actor(self, guild: discord.Guild, actions, target_id: int, label: str):
        if not is_antinuke_enabled(guild.id):
            return
        # small delay so audit log is available
        await asyncio.sleep(0.6)
        executor = await find_audit_executor(guild, actions, target_id=target_id)
        if executor is None or is_protected_actor(executor.id, guild):
            return
        if self._dedupe(guild.id, executor.id, f"ch:{label[:40]}"):
            return
        await apply_punishment(self.bot, guild, executor, "channels", label)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._punish_channel_actor(
            channel.guild,
            discord.AuditLogAction.channel_create,
            channel.id,
            f"Created channel #{getattr(channel, 'name', channel.id)}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._punish_channel_actor(
            channel.guild,
            discord.AuditLogAction.channel_delete,
            channel.id,
            f"Deleted channel #{getattr(channel, 'name', channel.id)}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        # Name/topic/nsfw/etc OR permission overwrite changes all fire this event.
        # Permission overwrites also create overwrite_* audit entries — check both.
        actions = [
            discord.AuditLogAction.channel_update,
            discord.AuditLogAction.overwrite_create,
            discord.AuditLogAction.overwrite_update,
            discord.AuditLogAction.overwrite_delete,
        ]
        # Detect overwrite-only changes for a clearer reason
        overwrites_changed = before.overwrites != after.overwrites
        label = (
            f"Changed permissions on #{getattr(after, 'name', after.id)}"
            if overwrites_changed
            else f"Updated channel #{getattr(after, 'name', after.id)}"
        )
        await self._punish_channel_actor(after.guild, actions, after.id, label)

    # ── Roles (create / delete / update / give / remove) ─────────────────────

    async def _punish_role_actor(self, guild: discord.Guild, actions, target_id: int | None, label: str):
        if not is_antinuke_enabled(guild.id):
            return
        await asyncio.sleep(0.6)
        executor = await find_audit_executor(guild, actions, target_id=target_id)
        if executor is None or is_protected_actor(executor.id, guild):
            return
        if self._dedupe(guild.id, executor.id, f"role:{label[:40]}"):
            return
        await apply_punishment(self.bot, guild, executor, "roles", label)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._punish_role_actor(
            role.guild,
            discord.AuditLogAction.role_create,
            role.id,
            f"Created role @{role.name}",
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._punish_role_actor(
            role.guild,
            discord.AuditLogAction.role_delete,
            role.id,
            f"Deleted role @{role.name}",
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        # Permission / name / color changes on the role itself
        await self._punish_role_actor(
            after.guild,
            discord.AuditLogAction.role_update,
            after.id,
            f"Updated role @{after.name}",
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Detect giving or removing roles from a member."""
        if before.roles == after.roles:
            return
        if not is_antinuke_enabled(after.guild.id):
            return

        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if not added and not removed:
            return

        await asyncio.sleep(0.6)
        executor = await find_audit_executor(
            after.guild,
            discord.AuditLogAction.member_role_update,
            target_id=after.id,
        )
        if executor is None or is_protected_actor(executor.id, after.guild):
            return

        parts = []
        if added:
            parts.append("gave " + ", ".join(f"@{r.name}" for r in added))
        if removed:
            parts.append("removed " + ", ".join(f"@{r.name}" for r in removed))
        label = f"Role change on {after}: " + "; ".join(parts)

        if self._dedupe(after.guild.id, executor.id, f"mrole:{after.id}"):
            return
        await apply_punishment(self.bot, after.guild, executor, "roles", label)


async def setup(bot):
    await bot.add_cog(AntiNukeCog(bot))
