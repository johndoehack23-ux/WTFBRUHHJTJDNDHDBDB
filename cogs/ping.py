import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        await ctx.send(f"Pong! {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.bot.latency * 1000)}ms")


async def setup(bot):
    await bot.add_cog(PingCog(bot))
