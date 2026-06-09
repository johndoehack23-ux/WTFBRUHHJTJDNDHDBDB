import discord
from discord.ext import commands
import random
import asyncio
from functions import *


class ModeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def start_1v1_round(self, channel, channel_id):
        match = active_1v1_matches[channel_id]
        match["current_round"] += 1
        match["guessed"] = False

        word, length = get_random_word_1v1(match["guild_id"], match.get("length"))
        match["secret"] = word
        match["length"] = length

        await channel.send(
            f"**Round {match['current_round']}/{match['max_rounds']}** | **Length:** {length}\n"
            f"**{match['p1']['name']}** vs **{match['p2']['name']}** — Guess the word!"
        )

    async def end_1v1_match(self, channel, channel_id):
        if channel_id in active_1v1_matches:
            del active_1v1_matches[channel_id]

    @commands.command(name="mode")
    async def mode_1v1(self, ctx, mode: str = None, length: int = None):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if not mode:
            return await ctx.send("✅ Usage: `.mode 1v1` (Start) or `.mode end` (Force end game/lobby)")

        mode_action = mode.lower().strip()
        channel_id = ctx.channel.id

        if mode_action == "end":
            if not is_admin(ctx.author.id):
                return await ctx.send("You do not have permission to use this command.")

            ended_something = False

            if channel_id in active_1v1_lobbies:
                del active_1v1_lobbies[channel_id]
                await ctx.send("1v1 Wordle ended")
                ended_something = True

            if channel_id in active_1v1_matches:
                del active_1v1_matches[channel_id]
                await ctx.send("1v1 Wordle ended")
                ended_something = True

            if not ended_something:
                await ctx.send("❌ There is no active 1v1 lobby or match running in this channel.")
            return

        if mode_action != "1v1":
            return await ctx.send("Usage: .mode 1v1 or .mode 1v1 <number>")

        if channel_id in active_games or channel_id in active_1v1_lobbies or channel_id in active_1v1_matches:
            return await ctx.send("❌ A game or lobby is already active in this channel!")

        embed = discord.Embed(
            title="🔥 Wordle 1v1 Matchmaking",
            description="**React with 🔥 to join!**\nTwo random players from the reactions will be selected.\nBest of 3 rounds — first correct guess wins the round.",
            color=0xff0000
        )
        embed.add_field(name="Scoring", value="• +**5 points** per round win\n• First to 2 round wins takes the match", inline=False)

        lobby_msg = await ctx.send(embed=embed)
        await lobby_msg.add_reaction("🔥")

        active_1v1_lobbies[channel_id] = {
            "lobby_msg": lobby_msg,
            "length": length,
            "guild_id": ctx.guild.id
        }

        await ctx.send("⏳ **Matchmaking started!** Waiting 10 seconds...")
        await asyncio.sleep(10)

        try:
            if channel_id not in active_1v1_lobbies:
                return

            lobby = active_1v1_lobbies.pop(channel_id, None)
            fresh_msg = await ctx.channel.fetch_message(lobby_msg.id)
            reaction = discord.utils.get(fresh_msg.reactions, emoji="🔥")

            users = []
            if reaction:
                async for user in reaction.users():
                    if not user.bot:
                        users.append(user)

            if len(users) < 2:
                await ctx.send("❌ Not enough players joined the 1v1 lobby (need 2).")
                return

            random.shuffle(users)
            p1 = users[0]
            p2 = users[1]

            active_1v1_matches[channel_id] = {
                "p1": {"id": p1.id, "name": p1.name, "score": 0, "wins": 0},
                "p2": {"id": p2.id, "name": p2.name, "score": 0, "wins": 0},
                "current_round": 0,
                "max_rounds": 3,
                "length": lobby["length"],
                "guild_id": ctx.guild.id,
                "secret": None,
                "guessed": False
            }

            await ctx.send(f"## 🔥 **1v1 Match Started!**\n**{p1.mention}** vs **{p2.mention}**\nFirst to **2 round wins**!")
            await self.start_1v1_round(ctx.channel, channel_id)

        except Exception as e:
            await ctx.send("❌ Error starting match.")
            print(f"1v1 Error: {e}")


async def setup(bot):
    await bot.add_cog(ModeCog(bot))
