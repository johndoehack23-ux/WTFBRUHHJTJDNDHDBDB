import discord
from discord.ext import commands
from discord import app_commands
from functions import load_stats, is_maintenance_mode, is_admin


def build_help_embed(guild):
    stats = load_stats()
    prefix = stats.get("prefix", ".")
    if guild:
        sp = (stats.get("server_prefixes") or {}).get(str(guild.id))
        if sp:
            prefix = sp

    return discord.Embed(
        title="Commands",
        description=(
            f"`{prefix}wordle` — Play Wordle\n"
            f"`{prefix}ping` — Check bot latency\n"
            f"`{prefix}leaderboard` / `{prefix}lb` — Server leaderboard\n"
            f"`{prefix}lb global` — Global leaderboard"
        ),
        color=0x2f3136,
    )


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_prefix(self, ctx):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("Maintenance mode is on.")
        await ctx.send(embed=build_help_embed(ctx.guild))

    @app_commands.command(name="help", description="Show the bot's command list")
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_help_embed(interaction.guild))


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
