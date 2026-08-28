import re
import discord
from discord.ext import commands
from discord import app_commands
from functions import *

# Matches discord.gg/, discord.com/invite/, discordapp.com/invite/
INVITE_PATTERN = re.compile(
    r"(discord\.gg/|discord(?:app)?\.com/invite/)[a-zA-Z0-9\-]+",
    re.IGNORECASE
)

def get_selfpromo_channels(guild_id: str) -> list:
    stats = load_stats()
    return stats.get("selfpromo_channels", {}).get(str(guild_id), [])

def add_selfpromo_channel(guild_id: str, channel_id: str):
    stats = load_stats()
    if "selfpromo_channels" not in stats or not isinstance(stats["selfpromo_channels"], dict):
        stats["selfpromo_channels"] = {}
    channels = stats["selfpromo_channels"].get(str(guild_id), [])
    if channel_id not in channels:
        channels.append(channel_id)
    stats["selfpromo_channels"][str(guild_id)] = channels
    save_stats(stats)

def remove_selfpromo_channel(guild_id: str, channel_id: str) -> bool:
    stats = load_stats()
    channels = stats.get("selfpromo_channels", {}).get(str(guild_id), [])
    if channel_id not in channels:
        return False
    channels.remove(channel_id)
    stats["selfpromo_channels"][str(guild_id)] = channels
    save_stats(stats)
    return True


class SelfPromoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        # Ignore admins/ops/trusted
        if is_admin(message.author.id, message.guild) or is_op(message.author.id):
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        selfpromo_channels = get_selfpromo_channels(guild_id)

        if channel_id not in selfpromo_channels:
            return

        # Check if message contains a Discord invite link
        if not INVITE_PATTERN.search(message.content):
            try:
                await message.delete()
                warn = await message.channel.send(
                    f"{message.author.mention} ❌ Only Discord invite links are allowed in this channel.",
                    delete_after=5
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    @app_commands.command(name="selfpromo", description="Set a channel as a self-promo channel (invite links only)")
    @app_commands.describe(channel="The channel to restrict to Discord invite links only")
    async def selfpromo(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not (is_admin(interaction.user.id, interaction.guild) or is_op(interaction.user.id) or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        channel_id = str(channel.id)
        channels = get_selfpromo_channels(guild_id)

        if channel_id in channels:
            return await interaction.response.send_message(
                f"❌ {channel.mention} is already a self-promo channel.", ephemeral=True
            )

        add_selfpromo_channel(guild_id, channel_id)
        await interaction.response.send_message(
            f"✅ {channel.mention} is now a **self-promo channel** — only Discord invite links will be allowed.",
            ephemeral=True
        )
        await send_debug_msg(
            self.bot,
            f"📢 `/selfpromo` | {interaction.user} (`{interaction.user.id}`) set {channel.name} as self-promo | {interaction.guild.name}",
            guild_id=guild_id
        )

    @app_commands.command(name="unselfpromo", description="Remove a self-promo channel or list all active ones")
    @app_commands.describe(text="Enter a channel to remove, or type 'list' to see all self-promo channels")
    async def unselfpromo(self, interaction: discord.Interaction, text: str):
        if not (is_admin(interaction.user.id, interaction.guild) or is_op(interaction.user.id) or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        channels = get_selfpromo_channels(guild_id)

        # LIST mode
        if text.strip().lower() == "list":
            if not channels:
                return await interaction.response.send_message(
                    "📭 No self-promo channels set for this server.", ephemeral=True
                )
            lines = []
            for cid in channels:
                ch = interaction.guild.get_channel(int(cid))
                lines.append(f"• {ch.mention if ch else f'`{cid}` (deleted)'}")
            embed = discord.Embed(
                title="📢 Self-Promo Channels",
                description="\n".join(lines),
                color=0x2f3136
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # REMOVE mode — accepts both #mention and raw channel ID
        raw = text.strip().replace("<#", "").replace(">", "")
        if not raw.isdigit():
            return await interaction.response.send_message(
                "❌ Please enter a valid channel mention or channel ID, or type `list` to see all.",
                ephemeral=True
            )

        channel_id = raw
        removed = remove_selfpromo_channel(guild_id, channel_id)

        if not removed:
            return await interaction.response.send_message(
                f"❌ <#{channel_id}> is not a self-promo channel.", ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ <#{channel_id}> removed from self-promo channels.", ephemeral=True
        )
        await send_debug_msg(
            self.bot,
            f"🗑️ `/unselfpromo` | {interaction.user} (`{interaction.user.id}`) removed <#{channel_id}> from self-promo | {interaction.guild.name}",
            guild_id=guild_id
        )


async def setup(bot):
    await bot.add_cog(SelfPromoCog(bot))
