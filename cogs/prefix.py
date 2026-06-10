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
        current = data.get("prefix", ".")
        await ctx.send(f"Current prefix: `{current}`\nUsage: `.prefix set <new_prefix>`")

    @prefix_group.command(name="set")
    async def prefix_set(self, ctx, new_prefix: str = None):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        if not new_prefix:
            return await ctx.send("Usage: `.prefix set <new_prefix>`  e.g. `.prefix set !`")

        if len(new_prefix) > 5:
            return await ctx.send("❌ Prefix must be 5 characters or fewer.")

        data = load_stats()
        old_prefix = data.get("prefix", ".")
        data["prefix"] = new_prefix
        save_stats(data)

        # Hot-reload the bot's prefix
        self.bot.command_prefix = lambda bot, msg: new_prefix

        await ctx.send(f"✅ Prefix changed from `{old_prefix}` → `{new_prefix}`")

async def setup(bot):
    await bot.add_cog(PrefixCog(bot))
