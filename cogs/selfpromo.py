import re
import discord
from discord.ext import commands
from discord import app_commands
from functions import *

# Discord invite links
INVITE_PATTERN = re.compile(
    r"(discord\.gg/|discord(?:app)?\.com/invite/)[a-zA-Z0-9\-]+",
    re.IGNORECASE
)

# Platform/social media links
LINKS_PATTERN = re.compile(
    r"https?://(www\.)?"
    r"(youtube\.com|youtu\.be|tiktok\.com|twitch\.tv|twitter\.com|x\.com"
    r"|instagram\.com|facebook\.com|soundcloud\.com|spotify\.com"
    r"|kick\.com|rumble\.com|threads\.net|linktr\.ee)[^\s]*",
    re.IGNORECASE
)

CREATOR_ID = 1465295674768883889

def _has_permission(user: discord.Member) -> bool:
    """Returns True if user is creator, op, admin, or server administrator."""
    if user.id == CREATOR_ID:
        return True
    if is_op(user.id):
        return True
    if is_admin(user.id, user.guild):
        return True
    if user.guild_permissions.administrator:
        return True
    return False


MODE_INVITE = "invite"
MODE_LINKS  = "links"
MODE_BOTH   = "both"


def get_selfpromo_channels(guild_id: str) -> dict:
    """Returns {channel_id: mode} for the guild. Handles legacy list format."""
    stats = load_stats()
    raw = stats.get("selfpromo_channels", {}).get(str(guild_id), {})
    # Legacy: was stored as a list of channel IDs before the mode system
    if isinstance(raw, list):
        return {str(cid): MODE_INVITE for cid in raw}
    return raw if isinstance(raw, dict) else {}


def add_selfpromo_channel(guild_id: str, channel_id: str, mode: str):
    stats = load_stats()
    if "selfpromo_channels" not in stats or not isinstance(stats["selfpromo_channels"], dict):
        stats["selfpromo_channels"] = {}
    existing = stats["selfpromo_channels"].get(str(guild_id), {})
    # Migrate legacy list to dict
    if isinstance(existing, list):
        existing = {str(cid): MODE_INVITE for cid in existing}
    existing[str(channel_id)] = mode
    stats["selfpromo_channels"][str(guild_id)] = existing
    save_stats(stats)


def remove_selfpromo_channel(guild_id: str, channel_id: str) -> bool:
    stats = load_stats()
    guild_data = stats.get("selfpromo_channels", {}).get(str(guild_id), {})
    # Migrate legacy list to dict
    if isinstance(guild_data, list):
        guild_data = {str(cid): MODE_INVITE for cid in guild_data}
    if str(channel_id) not in guild_data:
        return False
    del guild_data[str(channel_id)]
    stats["selfpromo_channels"][str(guild_id)] = guild_data
    save_stats(stats)
    return True


def fix_selfpromo_guild(guild_id: str) -> int:
    """Wipes all selfpromo data for a guild from MongoDB. Returns number of channels removed."""
    stats = load_stats()
    guild_data = stats.get("selfpromo_channels", {}).get(str(guild_id), {})
    count = len(guild_data) if isinstance(guild_data, (dict, list)) else 0
    if "selfpromo_channels" in stats:
        stats["selfpromo_channels"][str(guild_id)] = {}
        save_stats(stats)
    return count


class SelfPromoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # The creator is controlled exclusively by /bypass.
        # When OFF, the creator is subject to the same channel restriction as regular users.
        if message.author.id == CREATOR_ID:
            if is_creator_bypass_enabled():
                return
        elif is_admin(message.author.id, message.guild) or is_op(message.author.id):
            return

        guild_id  = str(message.guild.id)
        channel_id = str(message.channel.id)
        channels  = get_selfpromo_channels(guild_id)

        if channel_id not in channels:
            return

        mode = channels[channel_id]

        if mode == MODE_INVITE:
            valid = bool(INVITE_PATTERN.search(message.content))
            warn_text = "Only Discord server invite links are allowed in this channel."
        elif mode == MODE_LINKS:
            valid = bool(LINKS_PATTERN.search(message.content))
            warn_text = "Only platform links (YouTube, TikTok, Twitch, etc.) are allowed in this channel."
        else:  # both — either link type is accepted on its own
            valid = bool(INVITE_PATTERN.search(message.content)) or bool(LINKS_PATTERN.search(message.content))
            warn_text = "A Discord invite link or a platform link (YouTube, TikTok, Twitch, etc.) is required in this channel."

        if not valid:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} ❌ {warn_text}",
                    delete_after=6
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ── /selfpromo ──────────────────────────────────────────────────────────
    @app_commands.command(name="selfpromo", description="Set channel(s) as self-promo (up to 5; each has its own mode)")
    @app_commands.describe(
        channelid1="Channel ID 1 (required)",
        mode1="invite / links / both for channel ID 1 (required)",
        channelid2="Channel ID 2 (optional)",
        mode2="invite / links / both for channel ID 2",
        channelid3="Channel ID 3 (optional)",
        mode3="invite / links / both for channel ID 3",
        channelid4="Channel ID 4 (optional)",
        mode4="invite / links / both for channel ID 4",
        channelid5="Channel ID 5 (optional)",
        mode5="invite / links / both for channel ID 5",
    )
    @app_commands.choices(
        mode1=[
            app_commands.Choice(name="invite", value="invite"),
            app_commands.Choice(name="links", value="links"),
            app_commands.Choice(name="both", value="both"),
        ],
        mode2=[
            app_commands.Choice(name="invite", value="invite"),
            app_commands.Choice(name="links", value="links"),
            app_commands.Choice(name="both", value="both"),
        ],
        mode3=[
            app_commands.Choice(name="invite", value="invite"),
            app_commands.Choice(name="links", value="links"),
            app_commands.Choice(name="both", value="both"),
        ],
        mode4=[
            app_commands.Choice(name="invite", value="invite"),
            app_commands.Choice(name="links", value="links"),
            app_commands.Choice(name="both", value="both"),
        ],
        mode5=[
            app_commands.Choice(name="invite", value="invite"),
            app_commands.Choice(name="links", value="links"),
            app_commands.Choice(name="both", value="both"),
        ],
    )
    async def selfpromo(
        self,
        interaction: discord.Interaction,
        channelid1: str,
        mode1: app_commands.Choice[str],
        channelid2: str = None,
        mode2: app_commands.Choice[str] = None,
        channelid3: str = None,
        mode3: app_commands.Choice[str] = None,
        channelid4: str = None,
        mode4: app_commands.Choice[str] = None,
        channelid5: str = None,
        mode5: app_commands.Choice[str] = None,
    ):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        pairs = [
            (channelid1, mode1),
            (channelid2, mode2),
            (channelid3, mode3),
            (channelid4, mode4),
            (channelid5, mode5),
        ]

        entries = []  # (channel_id, mode_value)
        seen = set()
        for idx, (raw, mode_choice) in enumerate(pairs, start=1):
            if raw is None or str(raw).strip() == "":
                continue
            cid = str(raw).strip().replace("<#", "").replace(">", "")
            if not cid.isdigit():
                return await interaction.response.send_message(
                    f"❌ Invalid channel ID for channelid{idx}: `{raw}` — use numeric channel IDs only.",
                    ephemeral=True,
                )
            if mode_choice is None:
                return await interaction.response.send_message(
                    f"❌ channelid{idx} was given but mode{idx} is missing. Set mode{idx} to invite, links, or both.",
                    ephemeral=True,
                )
            if cid in seen:
                continue
            seen.add(cid)
            entries.append((cid, mode_choice.value))

        if not entries:
            return await interaction.response.send_message(
                "❌ Provide at least channelid1 and mode1.", ephemeral=True
            )

        guild_id = str(interaction.guild.id)

        for cid, mode_value in entries:
            add_selfpromo_channel(guild_id, cid, mode_value)

        desc_map = {
            MODE_INVITE: "only Discord server invite links",
            MODE_LINKS: "only platform links (YouTube, TikTok, Twitch, etc.)",
            MODE_BOTH: "invite or platform link",
        }
        lines = [
            f"• <#{cid}> → **{mode_value}** ({desc_map.get(mode_value, mode_value)})"
            for cid, mode_value in entries
        ]

        await interaction.response.send_message(
            "✅ Self-promo settings updated:\n" + "\n".join(lines),
            ephemeral=True
        )
        await send_debug_msg(
            self.bot,
            f"📢 `/selfpromo` | {interaction.user} (`{interaction.user.id}`) set {len(entries)} channel(s) | {interaction.guild.name}",
            guild_id=guild_id
        )

    # ── /unselfpromo ─────────────────────────────────────────────────────────
    @app_commands.command(name="unselfpromo", description="Remove self-promo channel(s) or list all (up to 5 channel IDs)")
    @app_commands.describe(
        channelid1="Channel ID 1, or type 'list' to see all",
        channelid2="Channel ID 2 (optional)",
        channelid3="Channel ID 3 (optional)",
        channelid4="Channel ID 4 (optional)",
        channelid5="Channel ID 5 (optional)",
    )
    async def unselfpromo(
        self,
        interaction: discord.Interaction,
        channelid1: str,
        channelid2: str = None,
        channelid3: str = None,
        channelid4: str = None,
        channelid5: str = None,
    ):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        channels = get_selfpromo_channels(guild_id)

        if channelid1.strip().lower() == "list":
            if not channels:
                return await interaction.response.send_message("📭 No self-promo channels set for this server.", ephemeral=True)
            lines = []
            for cid, m in channels.items():
                ch = interaction.guild.get_channel(int(cid))
                label = {"links": "Links", "invite": "Invites", "both": "Both"}.get(m, "Invites")
                lines.append(f"• {ch.mention if ch else f'<#{cid}>'} — {label}")
            embed = discord.Embed(title="📢 Self-Promo Channels", description="\n".join(lines), color=0x2f3136)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        raw_ids = [channelid1, channelid2, channelid3, channelid4, channelid5]
        channel_ids = []
        for raw in raw_ids:
            if raw is None or str(raw).strip() == "":
                continue
            cid = str(raw).strip().replace("<#", "").replace(">", "")
            if not cid.isdigit():
                return await interaction.response.send_message(
                    f"❌ Invalid channel ID: `{raw}` — use numeric channel IDs only, or type `list`.",
                    ephemeral=True,
                )
            if cid not in channel_ids:
                channel_ids.append(cid)

        if not channel_ids:
            return await interaction.response.send_message(
                "❌ Provide at least one valid channel ID, or type `list`.", ephemeral=True
            )

        removed = []
        not_found = []
        for cid in channel_ids:
            if remove_selfpromo_channel(guild_id, cid):
                removed.append(cid)
            else:
                not_found.append(cid)

        parts = []
        if removed:
            parts.append(f"✅ Removed: {' '.join(f'<#{c}>' for c in removed)}")
        if not_found:
            parts.append(f"❌ Not self-promo channels: {' '.join(f'<#{c}>' for c in not_found)}")

        await interaction.response.send_message("\n".join(parts), ephemeral=True)
        if removed:
            await send_debug_msg(
                self.bot,
                f"🗑️ `/unselfpromo` | {interaction.user} (`{interaction.user.id}`) removed {len(removed)} channel(s) | {interaction.guild.name}",
                guild_id=guild_id
            )


    @app_commands.command(name="fixpromo", description="Wipe all self-promo data for this server from MongoDB")
    @app_commands.describe(channel="Optional: remove only this specific channel instead of all")
    async def fixpromo(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)

        if channel:
            removed = remove_selfpromo_channel(guild_id, str(channel.id))
            if removed:
                await interaction.followup.send(f"✅ Removed {channel.mention} from self-promo data in MongoDB.", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ {channel.mention} was not in self-promo data — nothing to remove.", ephemeral=True)
        else:
            count = fix_selfpromo_guild(guild_id)
            await interaction.followup.send(f"✅ Wiped all self-promo data for this server from MongoDB ({count} channel(s) removed).", ephemeral=True)

        await send_debug_msg(
            self.bot,
            f"🔧 `/fixpromo` | {interaction.user} (`{interaction.user.id}`) wiped selfpromo data"
            + (f" for {channel.name}" if channel else " (all)") + f" | {interaction.guild.name}",
            guild_id=guild_id
        )


async def setup(bot):
    await bot.add_cog(SelfPromoCog(bot))
