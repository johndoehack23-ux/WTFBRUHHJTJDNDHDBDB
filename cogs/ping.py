import discord
from discord.ext import commands
from discord import app_commands
from functions import *
from editrespond import get_response

F = "ping"
from editrespond import get_response


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        stats = load_stats()
        prefix = stats.get("prefix", ".")
        latency = round(self.bot.latency * 1000)

        embed = discord.Embed(title="Pong", color=discord.Color.random())
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        
        avatar_url = ctx.author.display_avatar.url if ctx.author.display_avatar else None
        embed.set_footer(text=str(ctx.author), icon_url=avatar_url)
        
        await ctx.send(embed=embed)

    @app_commands.command(name="ping", description="Check the bot's latency and prefix info")
    async def ping_slash(self, interaction: discord.Interaction):
        stats = load_stats()
        prefix = stats.get("prefix", ".")
        latency = round(self.bot.latency * 1000)

        embed = discord.Embed(title="🏓 Pong!", color=0x2f3136)
        embed.add_field(name="Latency", value=f"`{latency}ms`", inline=True)
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
        embed.add_field(name="Global Prefix", value=f"`{prefix}`", inline=True)
        embed.add_field(name="Bot", value=f"{self.bot.user.name}", inline=True)
        embed.add_field(name="Bot ID", value=f"`{self.bot.user.id}`", inline=True)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="debugtest")
    async def debugtest(self, ctx, label: str = None):
        if not is_admin(ctx.author.id, ctx.guild):
            return

        tag = f"`{label}`" if label else "*(no label)*"
        msg = f"🧪 **Debug Test** | {tag} | sent by {ctx.author} (`{ctx.author.id}`) | #{ctx.channel.name} | {ctx.guild.name}"
        await send_debug_msg(self.bot, msg)
        await ctx.send(get_response(F, "debug_sent", tag=tag))


async def setup(bot):
    await bot.add_cog(PingCog(bot))
