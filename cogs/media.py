import re
from urllib.parse import urlparse

import discord
from discord.ext import commands
from discord import app_commands
from functions import *

CREATOR_ID = 1465295674768883889

VALID_ATTACHMENT_PREFIXES = ("image/", "video/")
ALLOWED_MEDIA_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "twitch.tv",
}
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


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


def get_media_settings(guild_id: str) -> dict:
    """Return {channel_id: allow_platform_links} for this guild."""
    stats = load_stats()
    settings = stats.get("media_settings", {})
    if not isinstance(settings, dict):
        return {}
    guild_settings = settings.get(str(guild_id), {})
    if not isinstance(guild_settings, dict):
        return {}
    return {str(channel_id): bool(value) for channel_id, value in guild_settings.items()}


def set_media_channel(guild_id: str, channel_id: str, allow_links: bool):
    stats = load_stats()
    if "media_settings" not in stats or not isinstance(stats["media_settings"], dict):
        stats["media_settings"] = {}
    if str(guild_id) not in stats["media_settings"] or not isinstance(stats["media_settings"][str(guild_id)], dict):
        stats["media_settings"][str(guild_id)] = {}

    stats["media_settings"][str(guild_id)][str(channel_id)] = bool(allow_links)
    save_stats(stats)


def remove_media_channel(guild_id: str, channel_id: str) -> bool:
    stats = load_stats()
    guild_settings = stats.get("media_settings", {}).get(str(guild_id), {})
    if not isinstance(guild_settings, dict) or str(channel_id) not in guild_settings:
        return False

    del guild_settings[str(channel_id)]
    stats["media_settings"][str(guild_id)] = guild_settings
    save_stats(stats)
    return True


def _is_allowed_platform_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False

    return any(hostname == domain or hostname.endswith("." + domain) for domain in ALLOWED_MEDIA_DOMAINS)


def _get_urls(content: str) -> list[str]:
    return URL_RE.findall(content or "")


def _has_valid_media(message: discord.Message, allow_links: bool) -> bool:
    has_valid_attachment = any(
        (attachment.content_type or "").lower().startswith(VALID_ATTACHMENT_PREFIXES)
        for attachment in message.attachments
    )

    if has_valid_attachment:
        return True

    if not allow_links:
        return False

    urls = _get_urls(message.content)
    if not urls:
        return False

    # If a message contains URLs, every URL must be one of the three allowed
    # platforms. This prevents other websites from being used in media channels.
    return all(_is_allowed_platform_url(url.rstrip(".,!?;:")) for url in urls)


class MediaCog(commands.Cog):
    """
    Slash-only:
      /media channelid1 media1 [channelid2 media2 ... channelid5 media5]
        Each channel has its own true/false:
          true  -> images, recordings, and YouTube/TikTok/Twitch links
          false -> images and recordings only
      /unmedia channelid1 [channelid2..5] -> remove the restriction(s)
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # The creator is controlled exclusively by /bypass.
        # When OFF, the creator is subject to the same media restriction as regular users.
        if message.author.id == CREATOR_ID:
            if is_creator_bypass_enabled():
                return
        elif is_admin(message.author.id, message.guild) or is_op(message.author.id):
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        settings = get_media_settings(guild_id)

        if channel_id not in settings:
            return

        allow_links = settings[channel_id]

        if _has_valid_media(message, allow_links):
            return

        try:
            await message.delete()
            if allow_links:
                text = (
                    f"{message.author.mention} ❌ Only images, recordings, or "
                    "YouTube/TikTok/Twitch links are allowed in this channel."
                )
            else:
                text = f"{message.author.mention} ❌ Only images or recordings are allowed in this channel."
            await message.channel.send(text, delete_after=6)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="media", description="Set channel(s) to media-only mode (up to 5; each has its own true/false)")
    @app_commands.describe(
        channelid1="Channel ID 1 (required)",
        media1="true/false for channel ID 1 (required)",
        channelid2="Channel ID 2 (optional)",
        media2="true/false for channel ID 2",
        channelid3="Channel ID 3 (optional)",
        media3="true/false for channel ID 3",
        channelid4="Channel ID 4 (optional)",
        media4="true/false for channel ID 4",
        channelid5="Channel ID 5 (optional)",
        media5="true/false for channel ID 5",
    )
    @app_commands.choices(
        media1=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
        media2=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
        media3=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
        media4=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
        media5=[
            app_commands.Choice(name="true", value="true"),
            app_commands.Choice(name="false", value="false"),
        ],
    )
    async def media(
        self,
        interaction: discord.Interaction,
        channelid1: str,
        media1: app_commands.Choice[str],
        channelid2: str = None,
        media2: app_commands.Choice[str] = None,
        channelid3: str = None,
        media3: app_commands.Choice[str] = None,
        channelid4: str = None,
        media4: app_commands.Choice[str] = None,
        channelid5: str = None,
        media5: app_commands.Choice[str] = None,
    ):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You do not have permission to use this command.", ephemeral=True
            )

        pairs = [
            (channelid1, media1),
            (channelid2, media2),
            (channelid3, media3),
            (channelid4, media4),
            (channelid5, media5),
        ]

        entries = []  # (channel_id, allow_links)
        seen = set()
        for idx, (raw, media_choice) in enumerate(pairs, start=1):
            if raw is None or str(raw).strip() == "":
                continue
            cid = str(raw).strip().replace("<#", "").replace(">", "")
            if not cid.isdigit():
                return await interaction.response.send_message(
                    f"❌ Invalid channel ID for channelid{idx}: `{raw}` — use numeric channel IDs only.",
                    ephemeral=True,
                )
            if media_choice is None:
                return await interaction.response.send_message(
                    f"❌ channelid{idx} was given but media{idx} is missing. Set media{idx} to true or false.",
                    ephemeral=True,
                )
            if cid in seen:
                continue
            seen.add(cid)
            entries.append((cid, media_choice.value == "true"))

        if not entries:
            return await interaction.response.send_message(
                "❌ Provide at least channelid1 and media1.", ephemeral=True
            )

        guild_id = str(interaction.guild.id)

        for cid, allow_links in entries:
            set_media_channel(guild_id, cid, allow_links)

        lines = []
        for cid, allow_links in entries:
            mode_text = (
                "images, recordings, and YouTube/TikTok/Twitch links"
                if allow_links
                else "images and recordings only"
            )
            lines.append(f"• <#{cid}> → **{'true' if allow_links else 'false'}** ({mode_text})")

        await interaction.response.send_message(
            "✅ Media-only settings updated:\n" + "\n".join(lines),
            ephemeral=True,
        )
        await send_debug_msg(
            self.bot,
            f"🖼️ `/media` | {interaction.user} (`{interaction.user.id}`) set {len(entries)} channel(s) | {interaction.guild.name}",
            guild_id=guild_id,
        )

    @app_commands.command(name="unmedia", description="Remove media-only restriction from channel(s) (up to 5 channel IDs)")
    @app_commands.describe(
        channelid1="Channel ID 1 (required)",
        channelid2="Channel ID 2 (optional)",
        channelid3="Channel ID 3 (optional)",
        channelid4="Channel ID 4 (optional)",
        channelid5="Channel ID 5 (optional)",
    )
    async def unmedia(
        self,
        interaction: discord.Interaction,
        channelid1: str,
        channelid2: str = None,
        channelid3: str = None,
        channelid4: str = None,
        channelid5: str = None,
    ):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You do not have permission to use this command.", ephemeral=True
            )

        raw_ids = [channelid1, channelid2, channelid3, channelid4, channelid5]
        channel_ids = []
        for raw in raw_ids:
            if raw is None or str(raw).strip() == "":
                continue
            cid = str(raw).strip().replace("<#", "").replace(">", "")
            if not cid.isdigit():
                return await interaction.response.send_message(
                    f"❌ Invalid channel ID: `{raw}` — use numeric channel IDs only.",
                    ephemeral=True,
                )
            if cid not in channel_ids:
                channel_ids.append(cid)

        if not channel_ids:
            return await interaction.response.send_message(
                "❌ Provide at least one valid channel ID.", ephemeral=True
            )

        guild_id = str(interaction.guild.id)
        removed = []
        not_found = []
        for cid in channel_ids:
            if remove_media_channel(guild_id, cid):
                removed.append(cid)
            else:
                not_found.append(cid)

        parts = []
        if removed:
            parts.append(f"✅ Removed: {' '.join(f'<#{c}>' for c in removed)}")
        if not_found:
            parts.append(f"❌ Not media channels: {' '.join(f'<#{c}>' for c in not_found)}")

        await interaction.response.send_message("\n".join(parts), ephemeral=True)
        if removed:
            await send_debug_msg(
                self.bot,
                f"🗑️ `/unmedia` | {interaction.user} (`{interaction.user.id}`) removed {len(removed)} channel(s) | {interaction.guild.name}",
                guild_id=guild_id,
            )


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
