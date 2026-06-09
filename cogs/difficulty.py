import discord
from discord.ext import commands
from discord import app_commands
import random
from functions import *


class DifficultyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="difficulty")
    async def difficulty_prefix(self, ctx, mode: str = "default"):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.** Only admins can use commands.")

        mode = mode.lower().strip()
        valid = ["easy", "medium", "hard", "impossible", "default"]
        if mode not in valid:
            return await ctx.send("❌ Invalid mode!")

        if mode == "default":
            mode = random.choice(["medium", "hard"])

        gid = str(ctx.guild.id)
        if "default_modes" not in server_config:
            server_config["default_modes"] = {}
        server_config["default_modes"][gid] = mode
        save_json(CONFIG_FILE, server_config)

        await ctx.send(f"✅ Default mode set to **{mode.upper()}**")

    @app_commands.command(name="difficulty", description="Set the default wordle difficulty for this server")
    @app_commands.describe(mode="easy | medium | hard | impossible | default")
    async def difficulty_slash(self, interaction: discord.Interaction, mode: str):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance. Only admins allowed.", ephemeral=True)

        mode = mode.lower().strip()
        valid = ["easy", "medium", "hard", "impossible", "default"]
        if mode not in valid:
            return await interaction.response.send_message("❌ Invalid mode!", ephemeral=True)

        if mode == "default":
            mode = random.choice(["medium", "hard"])

        gid = str(interaction.guild.id)
        if "default_modes" not in server_config:
            server_config["default_modes"] = {}
        server_config["default_modes"][gid] = mode
        save_json(CONFIG_FILE, server_config)

        await interaction.response.send_message(f"✅ Default mode set to **{mode.upper()}**", ephemeral=True)


async def setup(bot):
    await bot.add_cog(DifficultyCog(bot))
