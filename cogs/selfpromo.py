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

MODE_INVITE = "invite"
MODE_LINKS  = "links"


def get_selfpromo_channels(guild_id: str) -> dict:
    """Returns {channel_id: mode} for the guild."""
    stats = load_stats()
    return stats.get("selfpromo_channels", {}).get(str(guild_id), {})


def add_selfpromo_channel(guild_id: str, channel_id: str, mode: str):
    stats = load_stats()
    if "selfpromo_channels" not in stats or not isinstance(stats["selfpromo_channels"], dict):
        stats["selfpromo_channels"] = {}
    if str(guild_id) not in stats["selfpromo_channels"] or not isinstance(stats["selfpromo_channels"][str(guild_id)], dict):
        stats["selfpromo_channels"][str(guild_id)] = {}
    stats["selfpromo_channels"][str(guild_id)][str(channel_id)] = mode
    save_stats(stats)


def remove_selfpromo_channel(guild_id: str, channel_id: str) -> bool:
    stats = load_stats()
    guild_data = stats.get("selfpromo_channels", {}).get(str(guild_id), {})
    if str(channel_id) not in guild_data:
        return False
    del guild_data[str(channel_id)]
    stats["selfpromo_channels"][str(guild_id)] = guild_data
    save_stats(stats)
    return True


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
        if not (is_admin(interaction.user.id, interaction.guild) or is_op(interaction.user.id) or interaction.user.guild_permissions.administrator):
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
        if not (is_admin(interaction.user.id, interaction.guild) or is_op(interaction.user.id) or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        channels = get_selfpromo_channels(guild_id)

        if text.strip().lower() == "list":
            if not channels:
                return await interaction.response.send_message("📭 No self-promo channels set for this server.", ephemeral=True)
            lines = []
            for cid, m in channels.items():
                ch = interaction.guild.get_channel(int(cid))
                label = "🔗 links" if m == MODE_LINKS else "📨 invite"
                lines.append(f"• {ch.mention if ch else f'`{cid}` (deleted)'} — {label}")
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


async def setup(bot):
    await bot.add_cog(SelfPromoCog(bot))
