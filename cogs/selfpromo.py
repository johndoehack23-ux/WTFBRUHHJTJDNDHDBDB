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

        # Admins/ops bypass
        if is_admin(message.author.id, message.guild) or is_op(message.author.id):
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
        else:  # links
            valid = bool(LINKS_PATTERN.search(message.content))
            warn_text = "Only platform links (YouTube, TikTok, Twitch, etc.) are allowed in this channel."

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
    @app_commands.command(name="selfpromo", description="Set a channel as a self-promo channel")
    @app_commands.describe(
        channel="The channel to restrict",
        mode="invite = Discord invites only | links = YouTube/TikTok/etc only"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="invite — Discord invite links only", value="invite"),
        app_commands.Choice(name="links  — Platform links only (YouTube, TikTok, Twitch…)", value="links"),
    ])
    async def selfpromo(self, interaction: discord.Interaction, channel: discord.TextChannel, mode: str):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id   = str(interaction.guild.id)
        channel_id = str(channel.id)
        existing   = get_selfpromo_channels(guild_id)

        if channel_id in existing and existing[channel_id] == mode:
            return await interaction.response.send_message(
                f"❌ {channel.mention} is already a **{mode}** self-promo channel.", ephemeral=True
            )

        add_selfpromo_channel(guild_id, channel_id, mode)

        if mode == MODE_INVITE:
            desc = "only Discord server invite links allowed"
        else:
            desc = "only platform links (YouTube, TikTok, Twitch, etc.) allowed"

        await interaction.response.send_message(
            f"✅ {channel.mention} set as **{mode}** self-promo channel — {desc}.",
            ephemeral=True
        )
        await send_debug_msg(
            self.bot,
            f"📢 `/selfpromo` | {interaction.user} (`{interaction.user.id}`) set {channel.name} as [{mode}] self-promo | {interaction.guild.name}",
            guild_id=guild_id
        )

    # ── /unselfpromo ─────────────────────────────────────────────────────────
    @app_commands.command(name="unselfpromo", description="Remove a self-promo channel or list all")
    @app_commands.describe(text="Channel mention/ID to remove, or 'list' to see all")
    async def unselfpromo(self, interaction: discord.Interaction, text: str):
        if not _has_permission(interaction.user):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        channels = get_selfpromo_channels(guild_id)

        if text.strip().lower() == "list":
            if not channels:
                return await interaction.response.send_message("📭 No self-promo channels set for this server.", ephemeral=True)
            lines = []
            for cid, m in channels.items():
                ch = interaction.guild.get_channel(int(cid))
                label = "Links" if m == MODE_LINKS else "Invites"
                lines.append(f"• {ch.mention if ch else f'<#{cid}>'} — {label}")
            embed = discord.Embed(title="📢 Self-Promo Channels", description="\n".join(lines), color=0x2f3136)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        raw = text.strip().replace("<#", "").replace(">", "")
        if not raw.isdigit():
            return await interaction.response.send_message(
                "❌ Enter a valid channel mention or ID, or type `list`.", ephemeral=True
            )

        removed = remove_selfpromo_channel(guild_id, raw)
        if not removed:
            return await interaction.response.send_message(f"❌ <#{raw}> is not a self-promo channel.", ephemeral=True)

        await interaction.response.send_message(f"✅ <#{raw}> removed from self-promo channels.", ephemeral=True)
        await send_debug_msg(
            self.bot,
            f"🗑️ `/unselfpromo` | {interaction.user} (`{interaction.user.id}`) removed <#{raw}> | {interaction.guild.name}",
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
