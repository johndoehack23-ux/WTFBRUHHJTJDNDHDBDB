import discord
from discord.ext import commands
import random
from functions import *
from editrespond import r


class DifficultyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="difficulty")
    async def difficulty_prefix(self, ctx, mode: str = "default"):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send(r("maintenance", "on_admin"))

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
        await send_debug_msg(
            self.bot,
            f"⚙️ `.difficulty` | {ctx.author} (`{ctx.author.id}`) set difficulty → **{mode.upper()}** | {ctx.guild.name}"
        )



async def setup(bot):
    await bot.add_cog(DifficultyCog(bot))
