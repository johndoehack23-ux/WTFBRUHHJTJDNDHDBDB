import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="leaderboard", aliases=["lb"])
    async def lb(self, ctx):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        srv = leaderboard["servers"].get(str(ctx.guild.id), {})
        if not srv:
            return await ctx.send("🏆 No stats yet!")

        sorted_lb = sorted(srv.items(), key=lambda x: x[1].get("best_streak", 0), reverse=True)[:10]

        embed = discord.Embed(title=f"🏆 Best Streaks - {ctx.guild.name}", color=0x2f3136)
        for i, (uid, d) in enumerate(sorted_lb, 1):
            embed.add_field(
                name=f"{i}. {d.get('username', 'Unknown')}",
                value=f"Best: **{d.get('best_streak', 0)}** | Current: **{d.get('current_streak', 0)}**",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="rlb")
    async def rlb(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access")

        leaderboard["servers"][str(ctx.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send("🧹 Leaderboard has been reset.")

    @commands.command(name="lb-best", aliases=["leaderboard-best"])
    async def lb_best(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        srv = get_server_lb(ctx.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_best = srv[uid].get("best_streak", 0)
        srv[uid]["best_streak"] = num
        srv[uid]["username"] = user.name
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`")

    @commands.command(name="lb-current", aliases=["leaderboard-current"])
    async def lb_current(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        srv = get_server_lb(ctx.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_current = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name

        if num > srv[uid].get("best_streak", 0):
            srv[uid]["best_streak"] = num

        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send(f"✅ Updated **{user.name}** current streak: `{old_current}` → `{num}`")

    @app_commands.command(name="leaderboard", description="Show the server wordle leaderboard")
    async def lb_slash(self, interaction: discord.Interaction):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        srv = leaderboard["servers"].get(str(interaction.guild.id), {})
        if not srv:
            return await interaction.response.send_message("🏆 No stats yet!", ephemeral=True)

        sorted_lb = sorted(srv.items(), key=lambda x: x[1].get("best_streak", 0), reverse=True)[:10]

        embed = discord.Embed(title=f"🏆 Best Streaks - {interaction.guild.name}", color=0x2f3136)
        for i, (uid, d) in enumerate(sorted_lb, 1):
            embed.add_field(
                name=f"{i}. {d.get('username', 'Unknown')}",
                value=f"Best: **{d.get('best_streak', 0)}** | Current: **{d.get('current_streak', 0)}**",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rlb", description="Reset the server leaderboard (admin only)")
    async def rlb_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        leaderboard["servers"][str(interaction.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message("🧹 Leaderboard has been reset.", ephemeral=True)

    @app_commands.command(name="lb-best", description="Set a user's best streak (admin only)")
    @app_commands.describe(user="Target user", num="New best streak value")
    async def lb_best_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        srv = get_server_lb(interaction.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_best = srv[uid].get("best_streak", 0)
        srv[uid]["best_streak"] = num
        srv[uid]["username"] = user.name
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`", ephemeral=True)

    @app_commands.command(name="lb-current", description="Set a user's current streak (admin only)")
    @app_commands.describe(user="Target user", num="New current streak value")
    async def lb_current_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        srv = get_server_lb(interaction.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_current = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name

        if num > srv[uid].get("best_streak", 0):
            srv[uid]["best_streak"] = num

        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message(f"✅ Updated **{user.name}** current streak: `{old_current}` → `{num}`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
