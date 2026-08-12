import discord
from discord.ext import commands
from discord import app_commands
from functions import *


def build_help_embed(user_id, guild, guild_id_str):
    stats = load_stats()
    prefix = stats.get("prefix", ".")
    trusted_pool = stats.get("trusted_users", {}).get(guild_id_str, [])

    uid_str = str(user_id)
    is_user_op = is_op(user_id)
    is_user_admin = is_admin(user_id, guild)
    is_user_trusted = uid_str in trusted_pool
    is_privileged = is_user_trusted or is_user_admin or is_user_op

    # Tier colours
    if is_user_op:
        color = 0x5865F2
    elif is_user_admin:
        color = 0xED4245
    elif is_user_trusted:
        color = 0xFEE75C
    else:
        color = 0x2f3136

    embed = discord.Embed(title="📖 Wordle Help", color=color)

    # ── Normal commands ──
    if is_privileged:
        normal_lines = (
            f"`{prefix}wordle` / `/wordle` — Play a wordle game. Trusted+ can also start custom words with `/wordle <word>` or a category game with `{prefix}wordle mode <cat> <diff>`\n"
            f"`{prefix}difficulty <mode>` / `/difficulty` — Set the server's default word difficulty\n"
            f"`{prefix}leaderboard` / `/leaderboard` — View the server leaderboard\n"
            f"`{prefix}mode 1v1` — Start a 1v1 wordle match *(Admin/Op only)*\n"
            f"`{prefix}ping` / `/ping` — Check bot latency and prefix\n"
            f"`{prefix}help` / `/help` — Show this help menu"
        )
    else:
        normal_lines = (
            f"`{prefix}wordle` / `/wordle` — Play a wordle game\n"
            f"`{prefix}difficulty <mode>` / `/difficulty` — Set the server's default word difficulty\n"
            f"`{prefix}leaderboard` / `/leaderboard` — View the server leaderboard\n"
            f"`{prefix}ping` / `/ping` — Check bot latency and prefix\n"
            f"`{prefix}help` / `/help` — Show this help menu"
        )

    embed.add_field(name="🔓 Normal", value=normal_lines, inline=False)

    # ── Trusted section ──
    if is_privileged:
        trusted_lines = (
            f"`/say` — Send a message as the bot in any channel\n"
            f"`/autoresponder` — Create or manage server autoresponders\n"
            f"`{prefix}wordle mode <category> <difficulty>` — Start a custom-category wordle\n"
            f"`{prefix}whato` — Toggle all bot commands on/off for this server *(Admin/Op)*"
        )
        embed.add_field(name="🟡 Trusted / Admin / Op", value=trusted_lines, inline=False)

    # ── Admin section ──
    if is_user_admin or is_user_op:
        admin_lines = (
            f"`{prefix}wordle end` / `/wordle end` — End the active wordle in this server\n"
            f"`{prefix}eg` / `/endgame` — Force-end game(s) in this server\n"
            f"`{prefix}hint` — Reveal a random hint letter\n"
            f"`{prefix}reveal` / `/reveal` — Reveal the current secret word\n"
            f"`{prefix}mode 1v1 <@u1> <@u2>` — Force 1v1 two specific users\n"
            f"`{prefix}give trusted <@user>` — Grant trusted access in this server\n"
            f"`{prefix}give admin <@user>` — Grant admin access globally\n"
            f"`{prefix}give iw <@user> add` — Give infinite wordle plays\n"
            f"`{prefix}give rwordle <@user>` — Reset a user's daily wordle limit\n"
            f"`{prefix}access` — Reset ALL daily wordle limits globally\n"
            f"`{prefix}bllserver [serverID]` — Blacklist or unblacklist a server\n"
            f"`{prefix}maintenance` / `/maintenance` — Toggle maintenance mode\n"
            f"`{prefix}status <status> \"<text>\" <on|off>` — Set the bot's status and activity\n"
            f"`{prefix}whato` — Toggle bot commands for this server"
        )
        embed.add_field(name="🔴 Admin", value=admin_lines, inline=False)

    # ── Op section ──
    if is_user_op:
        op_lines = (
            f"`{prefix}give op <@user>` — Grant Operator access globally\n"
            f"`{prefix}give trusted <@user> global` — Give trusted access across all servers\n"
            f"`{prefix}eg global` / `/endgame global` — End all games across every server\n"
            f"`{prefix}leave <serverID>` — Make the bot leave a specific server\n"
            f"`{prefix}leave all` — Make the bot leave all servers\n"
            f"`{prefix}leave server list` — List all servers the bot is in\n"
            f"`{prefix}debugtest <label>` — Send a test message to the debug channel\n"
            f"`{prefix}atcmd` — Create a new template command file (auto-loads, no restart)\n"
            f"`{prefix}wordle secrethelp` — Full privileged command reference\n"
            f"`{prefix}whato` — Toggle all commands on/off for a server"
        )
        embed.add_field(name="🔵 Op", value=op_lines, inline=False)

    # ── Secret section for trusted/admin/op ──
    if is_privileged:
        secret_lines = (
            f"🔒 You have access to privileged commands.\n"
            f"Run `{prefix}wordle secrethelp` or `.wordle secrethelp info` for the full deep-dive reference.\n"
            f"This section is only visible to Trusted, Admin, and Op users."
        )
        embed.add_field(name="🔐 Secret Access", value=secret_lines, inline=False)

    if not is_privileged:
        embed.set_footer(text="Use /help or .help to see this menu anytime.")
    else:
        tier = "Op" if is_user_op else "Admin" if is_user_admin else "Trusted"
        embed.set_footer(text=f"Access level: {tier} • Use .wordle secrethelp for full details")

    return embed


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_prefix(self, ctx):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        guild_id_str = str(ctx.guild.id) if ctx.guild else "0"
        embed = build_help_embed(ctx.author.id, ctx.guild, guild_id_str)
        await ctx.send(embed=embed)

    @app_commands.command(name="help", description="Show the bot's command list")
    async def help_slash(self, interaction: discord.Interaction):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        guild_id_str = str(interaction.guild.id) if interaction.guild else "0"
        embed = build_help_embed(interaction.user.id, interaction.guild, guild_id_str)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
