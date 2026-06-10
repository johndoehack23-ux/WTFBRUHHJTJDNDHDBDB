import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class InviteBotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Authorize Bot",
            url="https://discord.com/api/oauth2/authorize?client_id=1502654737219321926&permissions=6755418768566336&scope=bot",
            style=discord.ButtonStyle.link
        ))


class InviteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addinvite")
    async def add_invite_management(self, ctx, category: str = None, target_id: str = None, action: str = None):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if str(ctx.author.id) not in ADMIN_IDS:
            return await ctx.send("You do not have permission to use this command.")

        if not category or not target_id:
            return await ctx.send(
                "❌ **Usage:**\n`.addinvite user <userID>`\n`.addinvite user <userID> remove`\n"
                "`.addinvite server <serverID>`\n`.addinvite server <serverID> remove`\n"
                "`.addinvite cleanall` (wipes users)"
            )

        if category.lower().strip() == "cleanall":
            stats = load_stats()
            stats["invited_users"] = []
            save_stats(stats)
            return await ctx.send("🔓 Successfully **wiped the user invite whitelist**.")

        category = category.lower().strip()
        clean_id = target_id.replace("<@", "").replace("!", "").replace(">", "").strip()

        if category == "user":
            stats = load_stats()
            if "invited_users" not in stats:
                stats["invited_users"] = []
            pool = stats["invited_users"]

            if action and action.lower().strip() == "remove":
                if clean_id in pool:
                    pool.remove(clean_id)
                    save_stats(stats)
                    return await ctx.send(f"❌ User ID `{clean_id}` removed from invite whitelist.")
                return await ctx.send("❌ User not found in whitelist.")

            if clean_id in pool:
                return await ctx.send("ℹ️ User is already whitelisted.")

            pool.append(clean_id)
            save_stats(stats)
            return await ctx.send(f"✅ User ID `{clean_id}` added to invite whitelist!")

        elif category == "server":
            stats = load_stats()
            if "allowed_servers" not in stats:
                stats["allowed_servers"] = []
            pool = stats["allowed_servers"]

            if action and action.lower().strip() == "remove":
                if clean_id in pool:
                    pool.remove(clean_id)
                    save_stats(stats)
                    guild_to_leave = ctx.bot.get_guild(int(clean_id))
                    if guild_to_leave:
                        try:
                            await guild_to_leave.leave()
                        except Exception:
                            pass
                    return await ctx.send(f"❌ Server ID `{clean_id}` removed from allowed servers list.")
                return await ctx.send("❌ Server not found in allowed list.")

            if clean_id in pool:
                return await ctx.send("ℹ️ Server is already whitelisted.")

            pool.append(clean_id)
            save_stats(stats)
            return await ctx.send(f"✅ Server ID `{clean_id}` added to allowed servers list!")

        else:
            return await ctx.send("❌ Invalid category. Choose `user` or `server`.")

    @app_commands.command(name="invite", description="Generates a secure link to invite the bot to your server.")
    async def invite_slash_cmd(self, interaction: discord.Interaction):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ **Bot is under maintenance.**", ephemeral=True)

        stats = load_stats()
        invited_pool = stats.get("invited_users", [])
        user_id_str = str(interaction.user.id)

        if user_id_str not in invited_pool and user_id_str not in ADMIN_IDS:
            return await interaction.response.send_message(
                "❌ You are not authorized to invite this bot. Please contact the administrator.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "👋 Click the button below to authorize adding the bot into your chosen server:",
            view=InviteBotView(),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(InviteCog(bot))
