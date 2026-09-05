"""
Anti-Nuke system
- .whitelist / .wl <userID>     — server owner or bot creator only
- .antinuke / .au enable|disable|config
  Access: whitelisted, creator, op, or server owner
Everything starts DISABLED per server.
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

# ── Defaults (everything off until enabled) ──────────────────────────────────
DEFAULT_PUNISHMENTS = {
    "roles": {"type": "mute", "duration": 10},
    "channels": {"type": "ban", "duration": 5},
    "messages": {"type": "mute", "duration": 5},
}
DEFAULT_SPAM = {"count": 5, "window": 1.2}  # 5 msgs within 1.2s

# Token-ish patterns (bot/user tokens)
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


# ── Storage helpers ──────────────────────────────────────────────────────────

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
            cfg["punishments"][key]["type"] = str(pun[key].get("type", cfg["punishments"][key]["type"])).lower()
            try:
                cfg["punishments"][key]["duration"] = int(pun[key].get("duration", cfg["punishments"][key]["duration"]))
            except (TypeError, ValueError):
                pass
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
    stats["antinuke"][str(guild_id)] = {
        "enabled": bool(cfg.get("enabled", False)),
        "whitelist": [str(x) for x in (cfg.get("whitelist") or [])],
        "logs_channel": cfg.get("logs_channel"),
        "punishments": cfg.get("punishments") or dict(DEFAULT_PUNISHMENTS),
        "spam": cfg.get("spam") or dict(DEFAULT_SPAM),
    }
    save_stats(stats)


def is_antinuke_enabled(guild_id: int | str) -> bool:
    return bool(get_antinuke_config(guild_id).get("enabled"))


def is_antinuke_whitelisted(guild_id: int | str, user_id: int) -> bool:
    cfg = get_antinuke_config(guild_id)
    return str(user_id) in cfg.get("whitelist", [])


def can_manage_whitelist(user: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
    """Only server owner or bot creator can whitelist."""
    if user.id == CREATOR_ID:
        return True
    if guild and guild.owner_id == user.id:
        return True
    return False


def can_use_antinuke(user: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
    """Whitelisted, creator, op, or server owner."""
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
    """People antinuke should NEVER punish."""
    if user_id == CREATOR_ID:
        return True
    if is_op(user_id):
        return True
    if guild.owner_id == user_id:
        return True
    if is_antinuke_whitelisted(guild.id, user_id):
        return True
    return False


def bot_role_is_top(guild: discord.Guild, bot_user: discord.Member) -> bool:
    """True if the bot's highest role is the top role (or only under @everyone)."""
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
            f"Punishment: {str(p.get('type', 'mute')).title()}\n"
            f"Duration: {_duration_label(int(p.get('duration', 10)))}"
        )
    return "\n\n".join(lines)


# ── Logging ──────────────────────────────────────────────────────────────────

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


# ── Punishment execution ─────────────────────────────────────────────────────

async def apply_punishment(
    bot,
    guild: discord.Guild,
    member: discord.Member,
    category: str,
    reason: str,
):
    """category: roles | channels | messages"""
    if is_protected_actor(member.id, guild):
        return

    cfg = get_antinuke_config(guild.id)
    pun = (cfg.get("punishments") or {}).get(category) or DEFAULT_PUNISHMENTS.get(category, {})
    ptype = str(pun.get("type", "mute")).lower()
    duration = int(pun.get("duration", 10))

    try:
        if ptype == "ban":
            await guild.ban(member, reason=f"[AntiNuke/{category}] {reason}", delete_message_days=0)
            await antinuke_log(bot, guild, f"🔨 Banned {member} (`{member.id}`) — {reason}")
        elif ptype == "kick":
            await member.kick(reason=f"[AntiNuke/{category}] {reason}")
            await antinuke_log(bot, guild, f"👢 Kicked {member} (`{member.id}`) — {reason}")
        else:  # mute / timeout
            if duration <= 0:
                # "infinite" mute via long timeout (28d max Discord allows)
                until = discord.utils.utcnow() + timedelta(days=28)
            else:
                until = discord.utils.utcnow() + timedelta(minutes=duration)
            await member.timeout(until, reason=f"[AntiNuke/{category}] {reason}")
            await antinuke_log(
                bot,
                guild,
                f"🔇 Muted {member} (`{member.id}`) for {_duration_label(duration)} — {reason}",
            )
    except (discord.Forbidden, discord.HTTPException) as e:
        await antinuke_log(bot, guild, f"⚠️ Failed to punish {member} (`{member.id}`): {e}")


async def find_audit_executor(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int | None = None,
    within_seconds: float = 8.0,
) -> discord.Member | None:
    """Best-effort: who did the recent audit action."""
    try:
        async for entry in guild.audit_logs(limit=6, action=action):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() > within_seconds:
                continue
            if target_id is not None and entry.target and getattr(entry.target, "id", None) != target_id:
                continue
            user = entry.user
            if user is None or user.bot:
                return None
            member = guild.get_member(user.id)
            return member
    except (discord.Forbidden, discord.HTTPException):
        return None
    return None


# ── Config UI ────────────────────────────────────────────────────────────────

VALID_PUNISHMENTS = {"mute", "kick", "ban"}


class PunishmentModal(discord.ui.Modal):
    def __init__(self, category: str):
        super().__init__(title=f"{category.title()} Punishment")
        self.category = category  # roles | channels | messages
        self.punishment_name = discord.ui.TextInput(
            label="Punishment Name",
            placeholder="Mute, Kick, or Ban",
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

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not can_use_antinuke(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ No access.", ephemeral=True)

        name = str(self.punishment_name.value).strip().lower()
        if name not in VALID_PUNISHMENTS:
            return await interaction.response.send_message(
                "❌ Punishment must be `Mute`, `Kick`, or `Ban`.", ephemeral=True
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
            f"✅ **{self.category.title()}** → `{name.title()}` for `{_duration_label(duration)}`.",
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
        embed.set_footer(text="Mute / Kick / Ban · Duration in minutes (0 = infinite)")
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
        # spam tracking: (guild_id, user_id) -> deque of timestamps
        self._spam: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=30))
        self._lock = asyncio.Lock()

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
            # Bot role must be top
            if not bot_role_is_top(ctx.guild, ctx.guild.me):
                return await ctx.send(
                    "❌ Move the **bot's role to the top** of the role list before enabling Anti Nuke."
                )
            cfg = get_antinuke_config(ctx.guild.id)
            cfg["enabled"] = True
            save_antinuke_config(ctx.guild.id, cfg)
            await ctx.send("✅ **Anti Nuke ENABLED** for this server.")
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

    # ── Message protection (spam / tokens / NSFW / invites) ──────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not is_antinuke_enabled(message.guild.id):
            return
        if is_protected_actor(message.author.id, message.guild):
            return

        member = message.author
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(message.author.id)
            if member is None:
                return

        content = message.content or ""
        reason = None

        # Tokens
        if TOKEN_RE.search(content):
            reason = "Posted a Discord token"
        # NSFW links
        elif NSFW_DOMAIN_RE.search(content):
            reason = "Posted NSFW link"
        # Invites
        elif INVITE_RE.search(content):
            reason = "Posted a Discord invite"

        # Spam: N messages under window seconds
        if reason is None:
            cfg = get_antinuke_config(message.guild.id)
            spam = cfg.get("spam") or DEFAULT_SPAM
            limit = int(spam.get("count", 5))
            window = float(spam.get("window", 1.2))
            key = (message.guild.id, member.id)
            now = time.monotonic()
            q = self._spam[key]
            q.append(now)
            # drop old
            while q and (now - q[0]) > window:
                q.popleft()
            if len(q) >= limit:
                reason = f"Spam ({limit}+ messages in {window}s)"
                q.clear()

        if not reason:
            return

        # Delete offending message best-effort
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await apply_punishment(self.bot, message.guild, member, "messages", reason)

    # ── Channel anti-nuke ────────────────────────────────────────────────────

    async def _handle_channel_action(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int, label: str):
        if not is_antinuke_enabled(guild.id):
            return
        executor = await find_audit_executor(guild, action, target_id=target_id)
        if executor is None or is_protected_actor(executor.id, guild):
            return
        await apply_punishment(self.bot, guild, executor, "channels", label)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.abc.GuildChannel):
            return
        await self._handle_channel_action(
            channel.guild,
            discord.AuditLogAction.channel_create,
            channel.id,
            f"Created channel #{getattr(channel, 'name', channel.id)}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._handle_channel_action(
            channel.guild,
            discord.AuditLogAction.channel_delete,
            channel.id,
            f"Deleted channel #{getattr(channel, 'name', channel.id)}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        await self._handle_channel_action(
            after.guild,
            discord.AuditLogAction.channel_update,
            after.id,
            f"Updated channel #{getattr(after, 'name', after.id)}",
        )

    # ── Role anti-nuke ───────────────────────────────────────────────────────

    async def _handle_role_action(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int, label: str):
        if not is_antinuke_enabled(guild.id):
            return
        executor = await find_audit_executor(guild, action, target_id=target_id)
        if executor is None or is_protected_actor(executor.id, guild):
            return
        await apply_punishment(self.bot, guild, executor, "roles", label)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._handle_role_action(
            role.guild,
            discord.AuditLogAction.role_create,
            role.id,
            f"Created role @{role.name}",
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._handle_role_action(
            role.guild,
            discord.AuditLogAction.role_delete,
            role.id,
            f"Deleted role @{role.name}",
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        await self._handle_role_action(
            after.guild,
            discord.AuditLogAction.role_update,
            after.id,
            f"Updated role @{after.name}",
        )


async def setup(bot):
    await bot.add_cog(AntiNukeCog(bot))
