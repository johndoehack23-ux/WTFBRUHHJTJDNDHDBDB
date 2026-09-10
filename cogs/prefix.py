import discord
from discord.ext import commands
from functions import *

class PrefixCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="prefix", invoke_without_command=True)
    async def prefix_group(self, ctx):
        data = load_stats()
        global_prefix = data.get("prefix", ".")
        server_prefix = data.get("server_prefixes", {}).get(str(ctx.guild.id))

        is_bot_admin = is_admin(ctx.author.id)

        stats_data = load_stats()
        trusted_list = stats_data.get("trusted_users", {}).get(str(ctx.guild.id), [])
        is_server_trusted = str(ctx.author.id) in trusted_list

        current_p = stats_data.get("server_prefixes", {}).get(str(ctx.guild.id)) or stats_data.get("prefix", ".")
        usage = ""
        
        if is_bot_admin or is_server_trusted:
            usage = f"Usage: `{current_p}prefix set <new_prefix> [global/server]`"

        msg = f"**Current prefix:** `{global_prefix}` (global)\n\n{usage}"
        await ctx.send(msg)

    @prefix_group.command(name="set")
    async def prefix_set(self, ctx, new_prefix: str = None, scope: str = "server"):
        # Explicit checks
        bot_admin = is_admin(ctx.author.id)
        
        # Check if they are explicitly inside the server's trusted user list
        stats_data = load_stats()
        trusted_list = stats_data.get("trusted_users", {}).get(str(ctx.guild.id), [])
        is_server_trusted = str(ctx.author.id) in trusted_list

        # Deny access if they are neither an admin nor a trusted user
        if not bot_admin and not is_server_trusted:
            return await ctx.send("You do not have permission to use this command.")

        # Dynamically fetch the current active prefix for this server to show accurate usage
        current_p = stats_data.get("server_prefixes", {}).get(str(ctx.guild.id)) or stats_data.get("prefix", ".")

        if not new_prefix:
            return await ctx.send(
                f"Usage: `{current_p}prefix set <new_prefix> [global/server]`\n"
                f"Examples:\n"
                f"`{current_p}prefix set ! server`\n"
                f"`{current_p}prefix set ! global`\n"
                f"`{current_p}prefix set !`"
            )

        if len(new_prefix) > 5:
            return await ctx.send("❌ Prefix must be 5 characters or fewer.")

        scope = scope.lower()
        if scope not in ("global", "server"):
            return await ctx.send("❌ Scope must be `global` or `server`.")

        # FIXED PERMISSION LOGIC GATE: If setting server prefix, they must be either a trusted user OR a global admin
        if scope == "server" and not (is_server_trusted or bot_admin):
            return await ctx.send("You do not have permission to use this command.")

        # Restrict changing global scope exclusively to global bot admins
        if scope == "global" and not bot_admin:
            return await ctx.send("You do not have permission to change the global prefix.")

        if "server_prefixes" not in stats_data:
            stats_data["server_prefixes"] = {}

        if scope == "global":
            old_prefix = stats_data.get("prefix", ".")
            stats_data["prefix"] = new_prefix
            
            # Clear all custom server overrides so everyone defaults back to the new global prefix
            stats_data["server_prefixes"] = {}
            
            save_stats(stats_data)
            await ctx.send(f"✅ Global prefix changed from `{old_prefix}` → `{new_prefix}`")

        else:  # server
            old_prefix = stats_data["server_prefixes"].get(str(ctx.guild.id)) or stats_data.get("prefix", ".")
            stats_data["server_prefixes"][str(ctx.guild.id)] = new_prefix
            save_stats(stats_data)
            await ctx.send(f"✅ Server prefix changed from `{old_prefix}` → `{new_prefix}`")

async def setup(bot):
    await bot.add_cog(PrefixCog(bot))