import time

import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _ws_ms(self) -> int:
        """Discord gateway heartbeat latency in ms (bot <-> Discord WS)."""
        try:
            lat = self.bot.latency
            if lat is None or lat != lat or lat == float("inf"):  # NaN / inf
                return -1
            return max(0, round(lat * 1000))
        except Exception:
            return -1

    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        stats = load_stats()
        prefix = stats.get("prefix", ".")
        ws_ms = self._ws_ms()

        # Real REST round-trip: time to send a message to Discord's API and get it back
        t0 = time.perf_counter()
        msg = await ctx.send("🏓 Measuring…")
        rest_ms = max(0, round((time.perf_counter() - t0) * 1000))

        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.random())
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(
            name="WebSocket",
            value=f"`{ws_ms}ms`" if ws_ms >= 0 else "`n/a`",
            inline=True,
        )
        embed.add_field(name="REST (real)", value=f"`{rest_ms}ms`", inline=True)
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
        embed.set_footer(
            text=str(ctx.author),
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )

        await msg.edit(content=None, embed=embed)

    @app_commands.command(name="ping", description="Check the bot's real latency (WS + REST)")
    async def ping_slash(self, interaction: discord.Interaction):
        stats = load_stats()
        prefix = stats.get("prefix", ".")
        ws_ms = self._ws_ms()

        # Time from when Discord created the interaction until we respond + REST RTT
        t0 = time.perf_counter()
        await interaction.response.defer(thinking=False)
        # Defer ACK is the first REST call; measure followup as full response path
        embed = discord.Embed(title="🏓 Pong!", color=0x2f3136)
        rest_ms = max(0, round((time.perf_counter() - t0) * 1000))

        # Also show Discord interaction age (how long ago Discord received the slash)
        try:
            interaction_age_ms = max(
                0,
                round((discord.utils.utcnow() - interaction.created_at).total_seconds() * 1000),
            )
        except Exception:
            interaction_age_ms = None

        embed.add_field(
            name="WebSocket",
            value=f"`{ws_ms}ms`" if ws_ms >= 0 else "`n/a`",
            inline=True,
        )
        embed.add_field(name="REST (real)", value=f"`{rest_ms}ms`", inline=True)
        if interaction_age_ms is not None:
            embed.add_field(name="Interaction age", value=f"`{interaction_age_ms}ms`", inline=True)
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
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
