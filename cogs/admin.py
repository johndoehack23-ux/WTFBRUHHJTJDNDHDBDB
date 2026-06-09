import discord
from discord.ext import commands
from discord import app_commands
import datetime
from functions import *


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="admin")
    async def wordle_limit(self, ctx, user: discord.Member = None, action: str = None):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        if not user or not action:
            return await ctx.send(
                "**Usage:** `.admin <@user> <infinite|reset>`\n"
                "`infinite` = Toggle infinite plays\n"
                "`reset` = Reset limit + remove infinite"
            )

        action = action.lower().strip()

        if action == "infinite":
            new_state = toggle_infinite_wordle(user.id)
            status = "Infinite wordle enabled" if new_state else "Infinite wordle disabled"
            await ctx.send(f"{status} for **{user.name}**.")

        elif action == "reset":
            if reset_user_wordle_limit(user.id):
                await ctx.send(f"Reset {user.name} wordle uses (includes removing infinite)")
            else:
                await ctx.send(f"{user.name} - no wordle limit to reset")
        else:
            await ctx.send("❌ Invalid action! Use `infinite` or `reset`.")

    @commands.command(name="adminall")
    async def reset_wordle_limit_all(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        data = load_wordle_limits()
        data["users"] = {}
        data["infinite"] = {} if "infinite" in data else {}
        data["last_reset"] = datetime.datetime.now().isoformat()
        save_wordle_limits(data)

        await ctx.send("✅ **ALL** Wordle limits have been reset globally.")

    @commands.command(name="adminsecret1", aliases=["maintenance"])
    async def maintenance_toggle(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access")

        new_state = toggle_maintenance()
        status = "🔐 **ENABLED**" if new_state else "🔓 **DISABLED**"
        blocked = "Non-admins are now blocked." if new_state else ""
        await ctx.send(f"**Maintenance Mode:** {status}\n\n{blocked}")

    @commands.command(name="adminsecret2")
    async def reset_wordle_limit(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        data = load_wordle_limits()
        data["users"] = {}
        data["last_reset"] = datetime.datetime.now().isoformat()
        save_wordle_limits(data)

        await ctx.send("✅ **Wordle limits have been manually reset for all users.**")

    @commands.command(name="trusted")
    async def trusted(self, ctx, user_input: str = None, action: str = None):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if str(ctx.author.id) not in ADMIN_IDS:
            return await ctx.send("You do not have permission to use this command.")

        if not user_input:
            return await ctx.send("trusted <@user/userID/all>\ntrusted <@user/userID> remove")

        gid_str = str(ctx.guild.id)
        if gid_str not in server_config:
            server_config[gid_str] = {}
        if "trusted_users" not in server_config[gid_str]:
            server_config[gid_str]["trusted_users"] = []

        trusted_pool = server_config[gid_str]["trusted_users"]
        input_clean = user_input.strip().lower()

        if input_clean == "all" or (action and action.strip().lower() == "all"):
            if not trusted_pool:
                return await ctx.send("ℹ️ There are no whitelisted users configured on this server to remove.")
            server_config[gid_str]["trusted_users"] = []
            save_json(CONFIG_FILE, server_config)
            return await ctx.send("🗑️ Successfully **removed all** users from this server's whitelist configuration.")

        target_uid = user_input.replace("<@", "").replace("!", "").replace(">", "").strip()
        if not target_uid.isdigit():
            return await ctx.send("❌ Please provide a valid user mention or numerical User ID.")

        action_clean = action.lower().strip() if action else None

        if action_clean == "remove":
            if target_uid in trusted_pool:
                trusted_pool.remove(target_uid)
                save_json(CONFIG_FILE, server_config)
                return await ctx.send("Successfully removed")
            else:
                return await ctx.send("Not in the trusted list")

        if target_uid in trusted_pool:
            trusted_pool.remove(target_uid)
            status_msg = "Successfully removed"
        else:
            trusted_pool.append(target_uid)
            status_msg = "Successfully added (this server)"

        save_json(CONFIG_FILE, server_config)
        await ctx.send(status_msg)

    @commands.command(name="adminbl")
    async def admin_blacklist(self, ctx, server_id: str = None, action: str = None):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if str(ctx.author.id) not in ADMIN_IDS:
            return await ctx.send("You do not have permission to use this command.")

        if not server_id:
            return await ctx.send("❌ **Usage:** `.adminbl <serverID/all>` or `.adminbl <serverID> remove`")

        if "blacklisted_servers" not in server_config:
            server_config["blacklisted_servers"] = []

        blacklist_pool = server_config["blacklisted_servers"]
        input_clean = server_id.strip().lower()

        if input_clean == "all" or (action and action.strip().lower() == "all"):
            if not blacklist_pool:
                return await ctx.send("ℹ️ The blacklist is already completely empty.")
            server_config["blacklisted_servers"] = []
            save_json(CONFIG_FILE, server_config)
            return await ctx.send("🔓 Successfully **wiped the blacklist**. All servers are now unbanished globally.")

        target_sid = server_id.strip()
        action_clean = action.lower().strip() if action else None

        if action_clean == "remove":
            if target_sid in blacklist_pool:
                blacklist_pool.remove(target_sid)
                save_json(CONFIG_FILE, server_config)
                return await ctx.send(f"🔓 Server ID `{target_sid}` has been successfully **removed** from the blacklist.")
            else:
                return await ctx.send(f"❌ Server ID `{target_sid}` was not found in the blacklist pool.")

        if target_sid in blacklist_pool:
            blacklist_pool.remove(target_sid)
            status_msg = f"🔓 Server ID `{target_sid}` was already blacklisted. **Removed** from blacklist."
        else:
            blacklist_pool.append(target_sid)
            status_msg = f"🚫 Server ID `{target_sid}` has been **added** to the blacklist."

        save_json(CONFIG_FILE, server_config)
        await ctx.send(status_msg)

    @app_commands.command(name="adminhelp", description="Show admin commands")
    async def adminhelp_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access", ephemeral=True)

        embed = discord.Embed(title="🔧 Admin Commands [SOON]", color=0x2f3136)
        embed.add_field(name="SOON", value="SOON", inline=False)
        embed.add_field(name="SOON", value="SOON", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="brick", description="···")
    async def brick_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        embed = discord.Embed(title="🔧 Admin Commands [SOON]", color=0x2f3136)
        embed.add_field(name="SOON", value="SOON", inline=False)
        embed.add_field(name="SOON", value="SOON", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="admin-limit", description="Manage a user's wordle limit (admin only)")
    @app_commands.describe(user="Target user", action="infinite | reset")
    async def admin_limit_slash(self, interaction: discord.Interaction, user: discord.Member, action: str):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

        action = action.lower().strip()

        if action == "infinite":
            new_state = toggle_infinite_wordle(user.id)
            status = "Infinite wordle enabled" if new_state else "Infinite wordle disabled"
            await interaction.response.send_message(f"{status} for **{user.name}**.", ephemeral=True)

        elif action == "reset":
            if reset_user_wordle_limit(user.id):
                await interaction.response.send_message(f"Reset {user.name} wordle uses (includes removing infinite)", ephemeral=True)
            else:
                await interaction.response.send_message(f"{user.name} - no wordle limit to reset", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Invalid action! Use `infinite` or `reset`.", ephemeral=True)

    @app_commands.command(name="maintenance", description="Toggle maintenance mode (admin only)")
    async def maintenance_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access", ephemeral=True)

        new_state = toggle_maintenance()
        status = "🔐 **ENABLED**" if new_state else "🔓 **DISABLED**"
        blocked = "Non-admins are now blocked." if new_state else ""
        await interaction.response.send_message(f"**Maintenance Mode:** {status}\n\n{blocked}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
