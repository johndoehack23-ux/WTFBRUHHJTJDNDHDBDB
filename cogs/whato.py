import discord
from discord.ext import commands
from functions import *
from editrespond import get_response


class WhatoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="whato")
    async def whato(self, ctx):
        """Toggle all bot commands on/off for this server (admin/op only).
        Exempt commands: ping, stats, whato, help, debugtest."""

        if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
            return

        gid = str(ctx.guild.id)
        current = server_config.get("whato_disabled", {}).get(gid, False)
        new_state = not current

        if "whato_disabled" not in server_config:
            server_config["whato_disabled"] = {}
        server_config["whato_disabled"][gid] = new_state
        save_json(CONFIG_FILE, server_config)

        if new_state:
            embed = discord.Embed(
                title="🔇 Commands Disabled",
                description=(
                    "All bot commands have been **disabled** for this server.\n\n"
                    "Only these still work: `wordle`, `ping`, `stats`, `help`, `whato`, `debugtest`\n\n"
                    "Run `.whato` again to re-enable everything."
                ),
                color=0xFF4500
            )
        else:
            embed = discord.Embed(
                title="✅ Commands Enabled",
                description="All bot commands have been **re-enabled** for this server.",
                color=0x57F287
            )

        await ctx.send(embed=embed)
        state_label = "DISABLED" if new_state else "ENABLED"
        await send_debug_msg(
            self.bot,
            f"🔇 `.whato` | {ctx.author} (`{ctx.author.id}`) toggled commands → **{state_label}** | {ctx.guild.name} (`{ctx.guild.id}`)"
        )


async def setup(bot):
    await bot.add_cog(WhatoCog(bot))
