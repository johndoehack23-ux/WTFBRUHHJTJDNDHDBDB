import discord
from discord.ext import commands
import random
import asyncio
from functions import *

# Per-guild tracking of who played in the last 1v1 match (for 20% repeat penalty)
_1v1_recent: dict = {}  # guild_id (int) -> set of user_ids


def weighted_pick_two(users: list, recent_ids: set):
    """
    Weighted random selection of 2 unique players.
    Users who played in the last match get 20% weight; fresh players get 100%.
    Returns (p1, p2).
    """
    weights = [0.2 if u.id in recent_ids else 1.0 for u in users]
    p1 = random.choices(users, weights=weights, k=1)[0]
    remaining = [u for u in users if u.id != p1.id]
    remaining_weights = [0.2 if u.id in recent_ids else 1.0 for u in remaining]
    p2 = random.choices(remaining, weights=remaining_weights, k=1)[0]
    return p1, p2


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
        await send_debug_msg(
            self.bot,
            f"🥊 **1v1 Round {match['current_round']}** | `{word}` (len {length}) | "
            f"**{match['p1']['name']}** vs **{match['p2']['name']}** | #{channel.name}"
        )

    async def end_1v1_match(self, channel, channel_id):
        if channel_id in active_1v1_matches:
            del active_1v1_matches[channel_id]

    async def _launch_match(self, ctx, channel_id, p1, p2, length):
        """Shared logic: register match, announce, debug log, start first round."""
        active_1v1_matches[channel_id] = {
            "p1": {"id": p1.id, "name": p1.display_name, "score": 0, "wins": 0},
            "p2": {"id": p2.id, "name": p2.display_name, "score": 0, "wins": 0},
            "current_round": 0,
            "max_rounds": 3,
            "length": length,
            "guild_id": ctx.guild.id,
            "secret": None,
            "guessed": False
        }
        _1v1_recent[ctx.guild.id] = {p1.id, p2.id}

        await ctx.send(
            f"## 🔥 **1v1 Match Started!**\n"
            f"**{p1.mention}** vs **{p2.mention}**\n"
            f"First to **2 round wins**!"
        )
        await send_debug_msg(
            self.bot,
            f"🥊 **1v1 match started** | **{p1.display_name}** (`{p1.id}`) vs "
            f"**{p2.display_name}** (`{p2.id}`) | #{ctx.channel.name} | {ctx.guild.name}"
        )
        await self.start_1v1_round(ctx.channel, channel_id)

    @commands.command(name="mode")
    async def mode_1v1(self, ctx, mode: str = None, arg1: str = None, arg2: str = None, arg3: str = None):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        # Admin or Op required for all mode sub-commands
        if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
            return await ctx.send("You do not have permission to use this command.")

        if not mode:
            return await ctx.send(
                "✅ Usage:\n"
                "`.mode 1v1` — Random matchmaking\n"
                "`.mode 1v1 <length>` — Matchmaking with word length\n"
                "`.mode 1v1 <@user1> <@user2> [length]` — Force 1v1 two specific players\n"
                "`.mode end` — Force-end the active 1v1"
            )

        mode_action = mode.lower().strip()
        channel_id = ctx.channel.id

        # ── END ──
        if mode_action == "end":
            ended_something = False

            if channel_id in active_1v1_lobbies:
                del active_1v1_lobbies[channel_id]
                await ctx.send("1v1 lobby ended.")
                ended_something = True

            if channel_id in active_1v1_matches:
                del active_1v1_matches[channel_id]
                await ctx.send("1v1 match ended.")
                ended_something = True

            if ended_something:
                await send_debug_msg(
                    self.bot,
                    f"⚡ `.mode end` | {ctx.author} (`{ctx.author.id}`) force-ended 1v1 "
                    f"| #{ctx.channel.name} | {ctx.guild.name}"
                )
            else:
                await ctx.send("❌ No active 1v1 lobby or match in this channel.")
            return

        if mode_action != "1v1":
            return await ctx.send("Usage: `.mode 1v1`, `.mode 1v1 <length>`, or `.mode 1v1 <@user1> <@user2> [length]`")

        if channel_id in active_games or channel_id in active_1v1_lobbies or channel_id in active_1v1_matches:
            return await ctx.send("❌ A game or lobby is already active in this channel!")

        # ── FORCE 1v1: .mode 1v1 <userID1/mention> <userID2/mention> [length] ──
        if arg1 and arg2:
            uid1 = arg1.replace("<@", "").replace("!", "").replace(">", "").strip()
            uid2 = arg2.replace("<@", "").replace("!", "").replace(">", "").strip()

            if uid1.isdigit() and uid2.isdigit() and len(uid1) >= 15 and len(uid2) >= 15:
                try:
                    member1 = ctx.guild.get_member(int(uid1)) or await ctx.guild.fetch_member(int(uid1))
                    member2 = ctx.guild.get_member(int(uid2)) or await ctx.guild.fetch_member(int(uid2))
                except Exception:
                    return await ctx.send("❌ Could not find one or both users in this server.")

                if member1.bot or member2.bot:
                    return await ctx.send("❌ Bots cannot participate in 1v1.")
                if member1.id == member2.id:
                    return await ctx.send("❌ Cannot 1v1 the same user twice.")

                # Optional length from arg3 (or leftover arg2 position if arg3 has it)
                force_length = None
                if arg3 and arg3.isdigit() and len(arg3) <= 4:
                    force_length = int(arg3)

                await ctx.send(f"🔥 **Force 1v1!** {member1.mention} vs {member2.mention}" +
                               (f" | Length: **{force_length}**" if force_length else " | Length: **random**"))
                await self._launch_match(ctx, channel_id, member1, member2, force_length)
                return

        # ── RANDOM MATCHMAKING with optional length ──
        length = None
        if arg1 and arg1.isdigit() and len(arg1) <= 4:
            length = int(arg1)

        recent_ids = _1v1_recent.get(ctx.guild.id, set())

        embed = discord.Embed(
            title="🔥 Wordle 1v1 Matchmaking",
            description=(
                "**React with 🔥 to join!**\n"
                "Two players will be selected after 10 seconds.\n"
                "Best of 3 rounds — first correct guess wins the round."
            ),
            color=0xff0000
        )
        embed.add_field(
            name="Scoring",
            value="• +**5 points** per round win\n• First to 2 round wins takes the match",
            inline=False
        )
        if recent_ids:
            embed.set_footer(text="⚠️ Players from the last match have a lower re-selection chance.")

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

            active_1v1_lobbies.pop(channel_id, None)
            fresh_msg = await ctx.channel.fetch_message(lobby_msg.id)
            reaction = discord.utils.get(fresh_msg.reactions, emoji="🔥")

            users = []
            if reaction:
                async for user in reaction.users():
                    if not user.bot:
                        users.append(user)

            if len(users) < 2:
                await ctx.send("❌ Not enough players joined the 1v1 lobby (need at least 2).")
                return

            p1, p2 = weighted_pick_two(users, recent_ids)
            await self._launch_match(ctx, channel_id, p1, p2, length)

        except Exception as e:
            await ctx.send("❌ Error starting match.")
            print(f"1v1 Error: {e}")


async def setup(bot):
    await bot.add_cog(ModeCog(bot))
