import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_prefix(self, ctx):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.** Only admins can use commands.")

        embed = discord.Embed(title="Wordle Help", color=0x2f3136)
        embed.description = (
            "wordle — Enter to play the wordle.\n"
            "difficulty — Sets a difficulty (easy, medium, hard, impossible)\n"
            "leaderboard/lb — Shows a leaderboard (1-10 only)\n"
            "mode 1v1 <length> — Starts a wordle 1v1 mode\n"
            "mode end — Ends the current 1v1 mode"
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="help", description="Wordle Help")
    async def help_slash(self, interaction: discord.Interaction):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        embed = discord.Embed(title="COMING SOON", color=0x2f3136)
        embed.description = "This command is being wip. Please comeback when it's done"
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
