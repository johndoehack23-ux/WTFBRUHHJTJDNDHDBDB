import time

import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _ws_ms(self) -> int:
        try:
            ws = self.bot.latency
            if ws is not None and ws == ws and ws != float("inf"):
                return max(0, round(ws * 1000))
        except Exception:
            pass
        return -1

    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        stats = load_stats()
        prefix = stats.get("prefix", ".")

        # Real REST RTT (more accurate than WS heartbeat alone)
        t0 = time.perf_counter()
        msg = await ctx.send("…")
        rest_ms = max(0, round((time.perf_counter() - t0) * 1000))
        ws_ms = self._ws_ms()
        latency = rest_ms if rest_ms > 0 else (ws_ms if ws_ms >= 0 else 0)

        embed = discord.Embed(title="Pong", color=discord.Color.random())
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)

        avatar_url = ctx.author.display_avatar.url if ctx.author.display_avatar else None
        embed.set_footer(text=str(ctx.author), icon_url=avatar_url)

        await msg.edit(content=None, embed=embed)

    @app_commands.command(name="ping", description="Check the bot's latency and prefix info")
    async def ping_slash(self, interaction: discord.Interaction):
        stats = load_stats()
        prefix = stats.get("prefix", ".")

        t0 = time.perf_counter()
        await interaction.response.defer(thinking=False)
        rest_ms = max(0, round((time.perf_counter() - t0) * 1000))
        ws_ms = self._ws_ms()
        latency = rest_ms if rest_ms > 0 else (ws_ms if ws_ms >= 0 else 0)

        embed = discord.Embed(title="🏓 Pong!", color=0x2f3136)
        embed.add_field(name="Latency", value=f"`{latency}ms`", inline=True)
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
        embed.add_field(name="Global Prefix", value=f"`{prefix}`", inline=True)
        embed.add_field(name="Bot", value=f"{self.bot.user.name}", inline=True)
        embed.add_field(name="Bot ID", value=f"`{self.bot.user.id}`", inline=True)
        await interaction.followup.send(embed=embed)

    @commands.command(name="debugtest")
    async def debugtest(self, ctx, label: str = None):
        if not is_admin(ctx.author.id, ctx.guild):
            return

        tag = f"`{label}`" if label else "*(no label)*"
        msg = f"🧪 **Debug Test** | {tag} | sent by {ctx.author} (`{ctx.author.id}`) | #{ctx.channel.name} | {ctx.guild.name}"
        await send_debug_msg(self.bot, msg)
        await ctx.send(f"✅ Debug test message sent to debug channel. Label: {tag}")


async def setup(bot):
    await bot.add_cog(PingCog(bot))
