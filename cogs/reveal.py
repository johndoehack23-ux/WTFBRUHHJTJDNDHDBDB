import discord
from discord.ext import commands
from functions import *
from editrespond import r


class RevealCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reveal")
    async def reveal_prefix(self, ctx):
        if not is_admin(ctx.author.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send(r("maintenance", "on"))

        channel_id = ctx.channel.id

        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            secret = match['secret'].upper() if match.get('secret') else 'Not started yet'
            await ctx.send(f"🔍 **1v1 Secret word:** **{secret}**")
            await send_debug_msg(self.bot, f"🔍 `.reveal` (1v1) | {ctx.author} (`{ctx.author.id}`) revealed `{secret}` | #{ctx.channel.name} | {ctx.guild.name}")
            return

        g = next((v for v in active_games.values() if v["guild_id"] == ctx.guild.id), None)
        if g and g.get("secret"):
            await ctx.send(f"🔍 Secret word: **{g['secret'].upper()}**")
            await send_debug_msg(self.bot, f"🔍 `.reveal` | {ctx.author} (`{ctx.author.id}`) revealed `{g['secret']}` | #{ctx.channel.name} | {ctx.guild.name}")
            return

        await ctx.send("❌ No active game or 1v1 match in this channel.")



async def setup(bot):
    await bot.add_cog(RevealCog(bot))
