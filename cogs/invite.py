import discord
from discord.ext import commands
from discord import app_commands
import re
from functions import *
from editrespond import get_response

F = "invite"


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

    @staticmethod
    def normalize_id(value):
        """Accept raw IDs plus common Discord formatting/backticks."""
        cleaned = re.sub(r"\D", "", str(value))
        return cleaned or None

    @commands.command(name="addinvite")
    async def add_invite_management(self, ctx, category: str = None, target_id: str = None, action: str = None):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.")
            
        if not is_op(ctx.author.id):
            return await ctx.send(get_response(F, "no_permission"))

        if not category:
            return await ctx.send(
                "❌ **Usage:**\n`.addinvite user <userID>`\n`.addinvite user <userID> remove`\n"
                "`.addinvite server <serverID>`\n`.addinvite server <serverID> remove`\n"
                "`.addinvite cleanall`"
            )

        category = category.lower().strip()

        # Handle cleanall safely without requiring a target_id
        if category == "cleanall":
            stats = load_stats()
            stats["invited_users"] = []
            save_stats(stats)
            return await ctx.send("🔓 Successfully **wiped the user invite whitelist**.")

        # If it's not cleanall, we strictly REQUIRE the target_id
        if not target_id:
            return await ctx.send("❌ Please provide a valid User ID or Server ID.")

        # Scrub the ID completely of channels, roles, or accidental copy-paste symbols
        clean_id = self.normalize_id(target_id)

        # Final sanity check: Ensure the serverID consists ONLY of numbers
        if not clean_id:
            return await ctx.send(f"❌ `{target_id}` is not a valid numeric ID. Make sure it contains only numbers.")

        if category == "user":
            stats = load_stats()
            pool = [str(value) for value in stats.get("invited_users", []) if str(value).isdigit()]
            stats["invited_users"] = pool

            if action and action.lower().strip() == "remove":
                if clean_id in pool:
                    pool.remove(clean_id)
                    save_stats(stats)
                    return await ctx.send(get_response(F, "user_removed", uid=clean_id))
                return await ctx.send(get_response(F, "user_not_found"))

            if clean_id in pool:
                return await ctx.send(get_response(F, "user_exists"))

            pool.append(clean_id)
            save_stats(stats)
            return await ctx.send(get_response(F, "user_added", uid=clean_id))

        elif category == "server":
            # Use atomic MongoDB operations to avoid race conditions with on_guild_join
            stats = load_stats()
            pool = [str(value) for value in stats.get("allowed_servers", []) if str(value).isdigit()]

            if action and action.lower().strip() == "remove":
                if clean_id not in pool:
                    return await ctx.send(get_response(F, "server_not_found"))
                pool.remove(clean_id)
                stats["allowed_servers"] = pool
                save_stats(stats)
                guild_to_leave = ctx.bot.get_guild(int(clean_id))
                if guild_to_leave:
                    try:
                        await guild_to_leave.leave()
                    except Exception:
                        pass
                return await ctx.send(get_response(F, "server_removed", uid=clean_id))

            if clean_id in pool:
                return await ctx.send(get_response(F, "server_exists"))

            pool.append(clean_id)
            stats["allowed_servers"] = pool
            save_stats(stats)
            # Confirm it was actually saved before reporting success
            verify = load_stats()
            saved_pool = [str(v) for v in verify.get("allowed_servers", [])]
            if clean_id not in saved_pool:
                return await ctx.send(f"⚠️ Server ID `{clean_id}` may not have saved correctly — please try again or check MongoDB connection.")
            return await ctx.send(get_response(F, "server_added", uid=clean_id))

        else:
            return await ctx.send("❌ Invalid category. Choose `user` or `server`.")

    @app_commands.command(name="invite", description="Generates a secure link to invite the bot to your server.")
    async def invite_slash_cmd(self, interaction: discord.Interaction):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ **Bot is under maintenance.**", ephemeral=True)

        stats = load_stats()
        invited_pool = stats.get("invited_users", [])
        user_id_str = str(interaction.user.id)

        if user_id_str not in invited_pool and not is_admin(interaction.user.id):
            return await interaction.response.send_message(get_response(F, "not_authorized"), ephemeral=True)

        await interaction.response.send_message(
            "👋 Click the button below to authorize adding the bot into your chosen server:",
            view=InviteBotView(),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(InviteCog(bot))