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
      /media <channel> <true|false>
        true  -> images, recordings, and YouTube/TikTok/Twitch links
        false -> images and recordings only
      /unmedia <channel> -> remove the restriction
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

    @app_commands.command(name="media", description="Set a channel to media-only mode")
    @app_commands.describe(
        channel="The channel to restrict",
        media="true = allow YouTube/TikTok/Twitch links; false = images/recordings only",
    )
    @app_commands.choices(media=[
        app_commands.Choice(name="true", value="true"),
        app_commands.Choice(name="false", value="false"),
    ])
    async def media(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        media: app_commands.Choice[str],
    ):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You do not have permission to use this command.", ephemeral=True
            )

        guild_id = str(interaction.guild.id)
        channel_id = str(channel.id)
        allow_links = media.value == "true"
        existing = get_media_settings(guild_id)

        set_media_channel(guild_id, channel_id, allow_links)

        if allow_links:
            mode_text = "images, recordings, and YouTube/TikTok/Twitch links"
        else:
            mode_text = "images and recordings only"

        status_text = "updated" if channel_id in existing else "set"
        await interaction.response.send_message(
            f"✅ {channel.mention} {status_text} as a media-only channel — allowed: {mode_text}.",
            ephemeral=True,
        )
        await send_debug_msg(
            self.bot,
            f"🖼️ `/media` | {interaction.user} (`{interaction.user.id}`) set {channel.name} media mode to `{media.value}` | {interaction.guild.name}",
            guild_id=guild_id,
        )

    @app_commands.command(name="unmedia", description="Remove a channel's media-only restriction")
    @app_commands.describe(channel="The channel to unrestrict")
    async def unmedia(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You do not have permission to use this command.", ephemeral=True
            )

        guild_id = str(interaction.guild.id)
        removed = remove_media_channel(guild_id, str(channel.id))

        if not removed:
            return await interaction.response.send_message(
                f"❌ {channel.mention} is not a media-only channel.", ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ {channel.mention} removed from media-only channels.", ephemeral=True
        )
        await send_debug_msg(
            self.bot,
            f"🗑️ `/unmedia` | {interaction.user} (`{interaction.user.id}`) removed {channel.name} | {interaction.guild.name}",
            guild_id=guild_id,
        )


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
