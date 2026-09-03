import discord
from discord.ext import commands
from discord import app_commands
from functions import *

CREATOR_ID = 1465295674768883889

VALID_ATTACHMENT_PREFIXES = ("image/", "video/")  # "image" and "recording" (video)


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


def get_media_channels(guild_id: str) -> list:
    stats = load_stats()
    return [str(c) for c in stats.get("media_channels", {}).get(str(guild_id), [])]


def add_media_channel(guild_id: str, channel_id: str):
    stats = load_stats()
    if "media_channels" not in stats or not isinstance(stats["media_channels"], dict):
        stats["media_channels"] = {}
    existing = list(stats["media_channels"].get(str(guild_id), []))
    if str(channel_id) not in existing:
        existing.append(str(channel_id))
    stats["media_channels"][str(guild_id)] = existing
    save_stats(stats)


def remove_media_channel(guild_id: str, channel_id: str) -> bool:
    stats = load_stats()
    existing = list(stats.get("media_channels", {}).get(str(guild_id), []))
    if str(channel_id) not in existing:
        return False
    existing.remove(str(channel_id))
    stats["media_channels"][str(guild_id)] = existing
    save_stats(stats)
    return True


class MediaCog(commands.Cog):
    """
    Slash-only:
      /media <channel>    -> restrict a channel to images/recordings only
      /unmedia <channel>  -> remove that restriction
    Access: creator, op, admin, or server Administrator (same tier as selfpromo).
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Admins/ops always bypass
        if is_admin(message.author.id, message.guild) or is_op(message.author.id):
            return

        # Creator bypass — only while the /bypass toggle is ON
        if message.author.id == CREATOR_ID and is_creator_bypass_enabled():
            return

        guild_id   = str(message.guild.id)
        channel_id = str(message.channel.id)
        channels   = get_media_channels(guild_id)

        if channel_id not in channels:
            return

        has_valid_attachment = any(
            (att.content_type or "").startswith(VALID_ATTACHMENT_PREFIXES)
            for att in message.attachments
        )

        if not has_valid_attachment:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} ❌ Only images or recordings are allowed in this channel.",
                    delete_after=6
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ── /media ──────────────────────────────────────────────────────────────
    @app_commands.command(name="media", description="Restrict a channel to images/recordings only")
    @app_commands.describe(channel="The channel to restrict")
    async def media(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id   = str(interaction.guild.id)
        channel_id = str(channel.id)
        existing   = get_media_channels(guild_id)

        if channel_id in existing:
            return await interaction.response.send_message(
                f"❌ {channel.mention} is already a media-only channel.", ephemeral=True
            )

        add_media_channel(guild_id, channel_id)

        await interaction.response.send_message(
            f"✅ {channel.mention} set as a media-only channel — only images or recordings allowed.",
            ephemeral=True
        )
        await send_debug_msg(
            self.bot,
            f"🖼️ `/media` | {interaction.user} (`{interaction.user.id}`) set {channel.name} as media-only | {interaction.guild.name}",
            guild_id=guild_id
        )

    # ── /unmedia ────────────────────────────────────────────────────────────
    @app_commands.command(name="unmedia", description="Remove a channel's images/recordings-only restriction")
    @app_commands.describe(channel="The channel to unrestrict")
    async def unmedia(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        removed  = remove_media_channel(guild_id, str(channel.id))

        if not removed:
            return await interaction.response.send_message(f"❌ {channel.mention} is not a media-only channel.", ephemeral=True)

        await interaction.response.send_message(f"✅ {channel.mention} removed from media-only channels.", ephemeral=True)
        await send_debug_msg(
            self.bot,
            f"🗑️ `/unmedia` | {interaction.user} (`{interaction.user.id}`) removed {channel.name} | {interaction.guild.name}",
            guild_id=guild_id
        )


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
