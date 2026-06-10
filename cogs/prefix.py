import discord
from discord.ext import commands
import json
from functions import *

STATS_FILE = "stats.json"

def load_stats():
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_stats(data: dict):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f, indent=4)

class PrefixCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="prefix", invoke_without_command=True)
    async def prefix_group(self, ctx):
        data = load_stats()
        global_prefix = data.get("prefix", ".")
        server_prefix = data.get("server_prefixes", {}).get(str(ctx.guild.id))

        if server_prefix:
            await ctx.send(
                f"**This server's prefix:** `{server_prefix}`\n"
                f"**Global prefix:** `{global_prefix}`\n\n"
                f"Usage: `.prefix set <new_prefix> [global/server]`"
            )
        else:
            await ctx.send(
                f"**Current prefix:** `{global_prefix}` (global)\n\n"
                f"Usage: `.prefix set <new_prefix> [global/server]`"
            )

    @prefix_group.command(name="set")
    async def prefix_set(self, ctx, new_prefix: str = None, scope: str = "server"):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        if not new_prefix:
            return await ctx.send(
                "Usage: `.prefix set <new_prefix> [global/server]`\n"
                "Examples:\n"
                "`.prefix set ! server` — only this server\n"
                "`.prefix set ! global` — all servers\n"
                "`.prefix set !` — defaults to server"
            )

        if len(new_prefix) > 5:
            return await ctx.send("❌ Prefix must be 5 characters or fewer.")

        scope = scope.lower()
        if scope not in ("global", "server"):
            return await ctx.send("❌ Scope must be `global` or `server`.")

        data = load_stats()
        if "server_prefixes" not in data:
            data["server_prefixes"] = {}

        if scope == "global":
            old_prefix = data.get("prefix", ".")
            data["prefix"] = new_prefix
            save_stats(data)
            await ctx.send(f"✅ Global prefix changed from `{old_prefix}` → `{new_prefix}` (affects all servers without a custom prefix)")

        else:  # server
            old_prefix = data["server_prefixes"].get(str(ctx.guild.id)) or data.get("prefix", ".")
            data["server_prefixes"][str(ctx.guild.id)] = new_prefix
            save_stats(data)
            await ctx.send(f"✅ Server prefix changed from `{old_prefix}` → `{new_prefix}` (this server only)")

async def setup(bot):
    await bot.add_cog(PrefixCog(bot))
