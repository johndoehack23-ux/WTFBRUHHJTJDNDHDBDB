import discord
import re
import json
import os
from discord.ext import commands
from discord import app_commands
from datetime import timezone, timedelta
from functions import *

MOD_CASES_FILE = "moderation_cases.json"

# ── Max Discord timeout (28 days in seconds) ──
MAX_TIMEOUT_SECONDS = 28 * 86400  # 2419200

# ── Action colours (Wick-style) ──
COLORS = {
    "warned":  0xFFA500,
    "muted":   0xFF6B00,
    "kicked":  0xFF4500,
    "banned":  0x8B0000,
}

ACTION_EMOJIS = {
    "warned":  "⚠️",
    "muted":   "🔇",
    "kicked":  "👢",
    "banned":  "🔨",
}


# ── Case storage ──

def _load_cases() -> dict:
    if not os.path.exists(MOD_CASES_FILE):
        return {"next_id": 1, "cases": {}}
    try:
        with open(MOD_CASES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"next_id": 1, "cases": {}}


def _save_cases(data: dict):
    with open(MOD_CASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _new_case(guild_id: int, action: str, target: discord.Member, moderator, reason: str, extra: str = None) -> int:
    data = _load_cases()
    case_id = data.get("next_id", 1)
    data["next_id"] = case_id + 1
    gid = str(guild_id)
    data.setdefault("cases", {}).setdefault(gid, []).append({
        "id": case_id,
        "action": action,
        "target_id": target.id,
        "target_name": str(target),
        "moderator_id": moderator.id if hasattr(moderator, 'id') else moderator,
        "moderator_name": str(moderator),
        "reason": reason or "No reason provided.",
        "extra": extra,
    })
    _save_cases(data)
    return case_id


# ── Duration parser ──

def parse_duration(text: str):
    """
    Parses a duration string like '10m', '2h30m', '1d', '3600s'.
    Returns total seconds (int) or None if unparseable.
    Max: 28 days (2419200 s).
    """
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    matches = re.findall(r"(\d+)([smhd])", text.lower())
    if not matches:
        return None
    total = sum(int(n) * units[u] for n, u in matches)
    return min(total, MAX_TIMEOUT_SECONDS)


def fmt_duration(seconds: int) -> str:
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) if parts else "0s"


# ── Embed builder ──

def wick_embed(action: str, target: discord.Member, moderator, reason: str, duration_str: str = None, case_id: int = None) -> discord.Embed:
    emoji = ACTION_EMOJIS.get(action, "🌟")
    color = COLORS.get(action, 0x2B2D31)

    embed = discord.Embed(color=color)
    embed.set_author(
        name=f"{emoji} User {action.capitalize()}",
        icon_url=target.display_avatar.url
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    embed.add_field(name="👤 Target", value=f"{target.mention}\n`{target}` · `{target.id}`", inline=True)
    embed.add_field(
        name="🛡️ Moderator",
        value=f"{moderator.mention if hasattr(moderator, 'mention') else moderator}\n`{moderator}`",
        inline=True
    )

    if duration_str:
        embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)

    embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    case_text = f"Case #{case_id}" if case_id else "🌟"
    embed.set_footer(text=f"{case_text}  •  {now.strftime('%d %b %Y, %H:%M UTC')}")
    return embed


def _has_mod_perm(member: discord.Member, *perms) -> bool:
    """Returns True if member has ANY of the listed permission flags."""
    mp = member.guild_permissions
    return any(getattr(mp, p, False) for p in perms)


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ══════════════════════════════════════════
    #  WARN
    # ══════════════════════════════════════════

    @commands.command(name="warn")
    async def warn_prefix(self, ctx, target: discord.Member = None, *, reason: str = None):
        if is_whato_disabled(str(ctx.guild.id)):
            return

        if not _has_mod_perm(ctx.author, "moderate_members", "kick_members", "ban_members", "administrator"):
            return await ctx.send("❌ You need Timeout, Kick, Ban, or Administrator permission to warn members.")

        if target is None:
            return await ctx.send("❌ Usage: `.warn @user [reason]`")
        if target.bot:
            return await ctx.send("❌ Cannot warn a bot.")
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot warn yourself.")

        case_id = _new_case(ctx.guild.id, "warned", target, ctx.author, reason)
        embed = wick_embed("warned", target, ctx.author, reason, case_id=case_id)
        await ctx.send(embed=embed)

        try:
            dm_embed = discord.Embed(
                color=COLORS["warned"],
                description=f"You have been **warned** in **{ctx.guild.name}**."
            )
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            dm_embed.set_footer(text=f"Case #{case_id}")
            await target.send(embed=dm_embed)
        except Exception:
            pass

        await send_debug_msg(self.bot, f"⚠️ `.warn` | {ctx.author} warned {target} (`{target.id}`) | Reason: {reason or 'none'} | Case #{case_id} | {ctx.guild.name}")

    @app_commands.command(name="warn", description="Warn a member (requires Timeout/Kick/Ban/Admin)")
    @app_commands.describe(target="Member to warn", reason="Reason for the warning")
    async def warn_slash(self, interaction: discord.Interaction, target: discord.Member, reason: str = None):
        if is_whato_disabled(str(interaction.guild.id)):
            return await interaction.response.send_message("🔇 Commands are currently disabled in this server.", ephemeral=True)

        if not _has_mod_perm(interaction.user, "moderate_members", "kick_members", "ban_members", "administrator"):
            return await interaction.response.send_message("❌ You need Timeout, Kick, Ban, or Administrator permission.", ephemeral=True)

        if target.bot:
            return await interaction.response.send_message("❌ Cannot warn a bot.", ephemeral=True)
        if target.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot warn yourself.", ephemeral=True)

        case_id = _new_case(interaction.guild.id, "warned", target, interaction.user, reason)
        embed = wick_embed("warned", target, interaction.user, reason, case_id=case_id)
        await interaction.response.send_message(embed=embed)

        try:
            dm_embed = discord.Embed(color=COLORS["warned"], description=f"You have been **warned** in **{interaction.guild.name}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            dm_embed.set_footer(text=f"Case #{case_id}")
            await target.send(embed=dm_embed)
        except Exception:
            pass

        await send_debug_msg(self.bot, f"⚠️ `/warn` | {interaction.user} warned {target} (`{target.id}`) | Reason: {reason or 'none'} | Case #{case_id} | {interaction.guild.name}")

    # ══════════════════════════════════════════
    #  MUTE (Discord timeout)
    # ══════════════════════════════════════════

    @commands.command(name="mute")
    async def mute_prefix(self, ctx, target: discord.Member = None, duration: str = None, *, reason: str = None):
        if is_whato_disabled(str(ctx.guild.id)):
            return

        if not _has_mod_perm(ctx.author, "moderate_members", "administrator"):
            return await ctx.send("❌ You need Timeout or Administrator permission to mute members.")

        if target is None or duration is None:
            return await ctx.send("❌ Usage: `.mute @user <duration> [reason]`\nDuration examples: `30s` `10m` `2h` `1d` (max 28d)")
        if target.bot:
            return await ctx.send("❌ Cannot mute a bot.")
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot mute yourself.")

        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("❌ Invalid duration. Use: `30s`, `10m`, `2h`, `1d` (max 28d)")

        until = discord.utils.utcnow() + timedelta(seconds=secs)
        try:
            await target.timeout(until, reason=reason)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to timeout that member.")
        except Exception as e:
            return await ctx.send(f"❌ Error: {e}")

        dur_str = fmt_duration(secs)
        case_id = _new_case(ctx.guild.id, "muted", target, ctx.author, reason, extra=dur_str)
        embed = wick_embed("muted", target, ctx.author, reason, duration_str=dur_str, case_id=case_id)
        await ctx.send(embed=embed)

        try:
            dm_embed = discord.Embed(color=COLORS["muted"], description=f"You have been **muted** in **{ctx.guild.name}** for **{dur_str}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            dm_embed.set_footer(text=f"Case #{case_id}")
            await target.send(embed=dm_embed)
        except Exception:
            pass

        await send_debug_msg(self.bot, f"🔇 `.mute` | {ctx.author} muted {target} (`{target.id}`) for {dur_str} | Reason: {reason or 'none'} | Case #{case_id} | {ctx.guild.name}")

    @app_commands.command(name="mute", description="Timeout a member (requires Timeout/Admin, max 28d)")
    @app_commands.describe(target="Member to mute", duration="Duration (e.g. 10m, 2h, 1d — max 28d)", reason="Reason for the mute")
    async def mute_slash(self, interaction: discord.Interaction, target: discord.Member, duration: str, reason: str = None):
        if is_whato_disabled(str(interaction.guild.id)):
            return await interaction.response.send_message("🔇 Commands are currently disabled in this server.", ephemeral=True)

        if not _has_mod_perm(interaction.user, "moderate_members", "administrator"):
            return await interaction.response.send_message("❌ You need Timeout or Administrator permission.", ephemeral=True)

        if target.bot:
            return await interaction.response.send_message("❌ Cannot mute a bot.", ephemeral=True)
        if target.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot mute yourself.", ephemeral=True)

        secs = parse_duration(duration)
        if not secs:
            return await interaction.response.send_message("❌ Invalid duration. Use: `30s`, `10m`, `2h`, `1d` (max 28d)", ephemeral=True)

        until = discord.utils.utcnow() + timedelta(seconds=secs)
        try:
            await target.timeout(until, reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I don't have permission to timeout that member.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

        dur_str = fmt_duration(secs)
        case_id = _new_case(interaction.guild.id, "muted", target, interaction.user, reason, extra=dur_str)
        embed = wick_embed("muted", target, interaction.user, reason, duration_str=dur_str, case_id=case_id)
        await interaction.response.send_message(embed=embed)

        try:
            dm_embed = discord.Embed(color=COLORS["muted"], description=f"You have been **muted** in **{interaction.guild.name}** for **{dur_str}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            dm_embed.set_footer(text=f"Case #{case_id}")
            await target.send(embed=dm_embed)
        except Exception:
            pass

        await send_debug_msg(self.bot, f"🔇 `/mute` | {interaction.user} muted {target} (`{target.id}`) for {dur_str} | Reason: {reason or 'none'} | Case #{case_id} | {interaction.guild.name}")

    # ══════════════════════════════════════════
    #  KICK
    # ══════════════════════════════════════════

    @commands.command(name="kick")
    async def kick_prefix(self, ctx, target: discord.Member = None, *, reason: str = None):
        if is_whato_disabled(str(ctx.guild.id)):
            return

        if not _has_mod_perm(ctx.author, "kick_members", "administrator"):
            return await ctx.send("❌ You need Kick or Administrator permission to kick members.")

        if target is None:
            return await ctx.send("❌ Usage: `.kick @user [reason]`")
        if target.bot:
            return await ctx.send("❌ Cannot kick a bot.")
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot kick yourself.")

        try:
            dm_embed = discord.Embed(color=COLORS["kicked"], description=f"You have been **kicked** from **{ctx.guild.name}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            await target.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await target.kick(reason=reason)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to kick that member.")
        except Exception as e:
            return await ctx.send(f"❌ Error: {e}")

        case_id = _new_case(ctx.guild.id, "kicked", target, ctx.author, reason)
        embed = wick_embed("kicked", target, ctx.author, reason, case_id=case_id)
        await ctx.send(embed=embed)
        await send_debug_msg(self.bot, f"👢 `.kick` | {ctx.author} kicked {target} (`{target.id}`) | Reason: {reason or 'none'} | Case #{case_id} | {ctx.guild.name}")

    @app_commands.command(name="kick", description="Kick a member (requires Kick/Admin)")
    @app_commands.describe(target="Member to kick", reason="Reason for the kick")
    async def kick_slash(self, interaction: discord.Interaction, target: discord.Member, reason: str = None):
        if is_whato_disabled(str(interaction.guild.id)):
            return await interaction.response.send_message("🔇 Commands are currently disabled in this server.", ephemeral=True)

        if not _has_mod_perm(interaction.user, "kick_members", "administrator"):
            return await interaction.response.send_message("❌ You need Kick or Administrator permission.", ephemeral=True)

        if target.bot:
            return await interaction.response.send_message("❌ Cannot kick a bot.", ephemeral=True)
        if target.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot kick yourself.", ephemeral=True)

        try:
            dm_embed = discord.Embed(color=COLORS["kicked"], description=f"You have been **kicked** from **{interaction.guild.name}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            await target.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await target.kick(reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I don't have permission to kick that member.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

        case_id = _new_case(interaction.guild.id, "kicked", target, interaction.user, reason)
        embed = wick_embed("kicked", target, interaction.user, reason, case_id=case_id)
        await interaction.response.send_message(embed=embed)
        await send_debug_msg(self.bot, f"👢 `/kick` | {interaction.user} kicked {target} (`{target.id}`) | Reason: {reason or 'none'} | Case #{case_id} | {interaction.guild.name}")

    # ══════════════════════════════════════════
    #  BAN
    # ══════════════════════════════════════════

    @commands.command(name="ban")
    async def ban_prefix(self, ctx, target: discord.Member = None, *, reason: str = None):
        if is_whato_disabled(str(ctx.guild.id)):
            return

        if not _has_mod_perm(ctx.author, "ban_members", "administrator"):
            return await ctx.send("❌ You need Ban or Administrator permission to ban members.")

        if target is None:
            return await ctx.send("❌ Usage: `.ban @user [reason]`")
        if target.bot:
            return await ctx.send("❌ Cannot ban a bot.")
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot ban yourself.")

        try:
            dm_embed = discord.Embed(color=COLORS["banned"], description=f"You have been **banned** from **{ctx.guild.name}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            await target.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await target.ban(reason=reason, delete_message_days=0)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to ban that member.")
        except Exception as e:
            return await ctx.send(f"❌ Error: {e}")

        case_id = _new_case(ctx.guild.id, "banned", target, ctx.author, reason)
        embed = wick_embed("banned", target, ctx.author, reason, case_id=case_id)
        await ctx.send(embed=embed)
        await send_debug_msg(self.bot, f"🔨 `.ban` | {ctx.author} banned {target} (`{target.id}`) | Reason: {reason or 'none'} | Case #{case_id} | {ctx.guild.name}")

    @app_commands.command(name="ban", description="Ban a member (requires Ban/Admin)")
    @app_commands.describe(target="Member to ban", reason="Reason for the ban")
    async def ban_slash(self, interaction: discord.Interaction, target: discord.Member, reason: str = None):
        if is_whato_disabled(str(interaction.guild.id)):
            return await interaction.response.send_message("🔇 Commands are currently disabled in this server.", ephemeral=True)

        if not _has_mod_perm(interaction.user, "ban_members", "administrator"):
            return await interaction.response.send_message("❌ You need Ban or Administrator permission.", ephemeral=True)

        if target.bot:
            return await interaction.response.send_message("❌ Cannot ban a bot.", ephemeral=True)
        if target.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot ban yourself.", ephemeral=True)

        try:
            dm_embed = discord.Embed(color=COLORS["banned"], description=f"You have been **banned** from **{interaction.guild.name}**.")
            dm_embed.add_field(name="📝 Reason", value=reason or "No reason provided.", inline=False)
            await target.send(embed=dm_embed)
        except Exception:
            pass

        try:
            await target.ban(reason=reason, delete_message_days=0)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I don't have permission to ban that member.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

        case_id = _new_case(interaction.guild.id, "banned", target, interaction.user, reason)
        embed = wick_embed("banned", target, interaction.user, reason, case_id=case_id)
        await interaction.response.send_message(embed=embed)
        await send_debug_msg(self.bot, f"🔨 `/ban` | {interaction.user} banned {target} (`{target.id}`) | Reason: {reason or 'none'} | Case #{case_id} | {interaction.guild.name}")

    # ══════════════════════════════════════════
    #  CASES (view warnings)
    # ══════════════════════════════════════════

    @commands.command(name="cases")
    async def cases_prefix(self, ctx, target: discord.Member = None):
        if not _has_mod_perm(ctx.author, "moderate_members", "kick_members", "ban_members", "administrator"):
            return await ctx.send("❌ No permission.")

        if target is None:
            return await ctx.send("❌ Usage: `.cases @user`")

        data = _load_cases()
        guild_cases = [c for c in data.get("cases", {}).get(str(ctx.guild.id), []) if c["target_id"] == target.id]

        if not guild_cases:
            return await ctx.send(f"✅ No cases found for {target.mention}.")

        embed = discord.Embed(title=f"📋 Cases for {target}", color=0x2B2D31)
        embed.set_thumbnail(url=target.display_avatar.url)
        for c in guild_cases[-10:]:
            emoji = ACTION_EMOJIS.get(c["action"], "🌟")
            extra = f" ({c['extra']})" if c.get("extra") else ""
            embed.add_field(
                name=f"{emoji} Case #{c['id']} — {c['action'].capitalize()}{extra}",
                value=f"**Mod:** {c['moderator_name']}\n**Reason:** {c['reason']}",
                inline=False
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
