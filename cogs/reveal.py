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

        # 1v1 in this channel still takes priority for this channel only
        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            secret = match["secret"].upper() if match.get("secret") else "Not started yet"
            await ctx.send(f"<#{channel_id}>: **{secret}**")
            await send_debug_msg(
                self.bot,
                f"🔍 `.reveal` (1v1) | {ctx.author} (`{ctx.author.id}`) revealed `{secret}` "
                f"| #{ctx.channel.name} | {ctx.guild.name}",
                guild_id=ctx.guild.id,
            )
            return

        # All non-practice Wordle games in this server
        games = []
        for key, g in list(active_games.items()):
            if not isinstance(g, dict):
                continue
            if g.get("guild_id") != ctx.guild.id:
                continue
            if g.get("practice"):
                continue
            try:
                cid = int(key)
            except (TypeError, ValueError):
                continue
            if g.get("secret"):
                games.append((cid, g["secret"].upper()))

        if not games:
            return await ctx.send("❌ No active game or 1v1 match in this server.")

        lines = [f"<#{cid}>: **{word}**" for cid, word in games]
        await ctx.send("\n".join(lines))
        await send_debug_msg(
            self.bot,
            f"🔍 `.reveal` | {ctx.author} (`{ctx.author.id}`) revealed {len(games)} word(s) "
            f"| #{ctx.channel.name} | {ctx.guild.name}",
            guild_id=ctx.guild.id,
        )


async def setup(bot):
    await bot.add_cog(RevealCog(bot))
