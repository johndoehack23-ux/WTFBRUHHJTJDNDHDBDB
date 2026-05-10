import os
import discord
from discord.ext import commands
import random
import json

TOKEN = os.environ.get("DISCORD_TOKEN")
prefix = "-"                  # ← Change prefix here easily!

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=prefix, intents=intents, help_command=None)

# Game storage
active_games = {}

# Persistent Leaderboard
LEADERBOARD_FILE = "wordle_leaderboard.json"
leaderboard = {}

def load_leaderboard():
    global leaderboard
    try:
        if os.path.exists(LEADERBOARD_FILE):
            with open(LEADERBOARD_FILE, "r") as f:
                leaderboard = json.load(f)
            print(f"✅ Loaded {len(leaderboard)} players from leaderboard")
    except Exception as e:
        print("Error loading leaderboard:", e)
        leaderboard = {}

def save_leaderboard():
    try:
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(leaderboard, f, indent=4)
    except Exception as e:
        print("Error saving leaderboard:", e)

# 5-letter word list
WORD_LIST = [
    "pizza", "apple", "brain", "crane", "delta", "eagle", "flame", "ghost", "house", "image",
    "joker", "knife", "lemon", "magic", "night", "ocean", "peace", "queen", "river", "stone",
    "tiger", "voice", "world", "youth", "zebra", "about", "beach", "black", "bread", "break",
    "chair", "clean", "clock", "cloud", "dance", "dream", "earth", "faith", "field", "fight",
    "glass", "green", "happy", "heart", "horse", "hotel", "human", "laugh", "learn", "light",
    "money", "music", "night", "ocean", "paper", "party", "peace", "plant", "power", "queen",
    "river", "robot", "smile", "stone", "sugar", "table", "water", "world"
]

def get_feedback(guess, secret):
    feedback = ""
    secret_list = list(secret)
    guess_list = list(guess)

    for i in range(5):
        if guess_list[i] == secret_list[i]:
            feedback += "🟩"
            secret_list[i] = None
        else:
            feedback += " "

    result = list(feedback)
    for i in range(5):
        if result[i] == " ":
            if guess_list[i] in secret_list:
                result[i] = "🟨"
                secret_list[secret_list.index(guess_list[i])] = None
            else:
                result[i] = "⬛"
    return "".join(result)

@bot.event
async def on_ready():
    load_leaderboard()
    print(f"Logged in as {bot.user}")
    print(f"------ Unlimited Wordle Bot Ready | Prefix: {prefix} ------")

# ====================== HELP ======================
@bot.command(name="help")
async def custom_help(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    embed = discord.Embed(
        title="🤖 Wordle Bot Commands",
        description="Here are the available commands:",
        color=0x00ff00
    )
    embed.add_field(name=f"{prefix}wordle", value="Start a new Wordle game", inline=False)
    embed.add_field(name=f"{prefix}endgame", value="End the current game (also: endwordle, exitgame)", inline=False)
    embed.add_field(name=f"{prefix}leaderboard", value="Show global win streak leaderboard (aliases: lb, top)", inline=False)
    embed.add_field(name=f"{prefix}help", value="Show this help message", inline=False)
    embed.add_field(name=f"{prefix}reveal", value="Secret command - reveals the word (only during active game)", inline=False)
    embed.set_footer(text="Tip: When a game is active, just type any 5-letter word to guess!")
    await ctx.send(embed=embed)

# ====================== SECRET REVEAL ======================
@bot.command(name="reveal", hidden=True)
async def reveal_word(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    channel_id = ctx.channel.id
    if channel_id in active_games:
        secret = active_games[channel_id]["secret"]
        await ctx.send(f"🔍 The secret word is: **{secret.upper()}**")

# ====================== LEADERBOARD ======================
@bot.command(name="leaderboard", aliases=["lb", "top"])
async def show_leaderboard(ctx):
    # Messages are NOT deleted for leaderboard
    if not leaderboard:
        await ctx.send("🏆 No wins recorded yet!")
        return

    sorted_players = sorted(
        leaderboard.items(),
        key=lambda x: (x[1]["best_streak"], x[1]["current_streak"]),
        reverse=True
    )

    embed = discord.Embed(title="🏆 Global Wordle Win Streak Leaderboard", color=0xFFD700)
    for rank, (user_id, data) in enumerate(sorted_players[:10], 1):
        name = data.get("username", f"User {user_id}")
        current = data["current_streak"]
        best = data["best_streak"]
        embed.add_field(
            name=f"#{rank} {name}",
            value=f"**Best:** {best} 🔥   Current: {current}",
            inline=False
        )
    await ctx.send(embed=embed)

# ====================== WORDLE ======================
@bot.command(name="wordle")
async def start_wordle(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    channel_id = ctx.channel.id
    if channel_id in active_games:
        await ctx.send("There's already an active Wordle game in this channel!")
        return

    secret = random.choice(WORD_LIST).lower()
    active_games[channel_id] = {"secret": secret, "guesses": [], "player_id": str(ctx.author.id)}

    await ctx.send(
        f"## New wordle game started by {ctx.author.mention}\n"
        f"Word length: **5**\n\n"
        f"Just type any **5-letter word** to guess! • End with `{prefix}endgame`"
    )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    content = message.content.strip().lower()

    if channel_id in active_games and len(content) == 5 and content.isalpha():
        guess = content
        game = active_games[channel_id]
        secret = game["secret"]
        player_id = game["player_id"]

        # Delete the guess message instantly
        try:
            await message.delete()
        except Exception:
            pass

        if guess in game["guesses"]:
            await message.channel.send(f"**{guess.upper()}** was already guessed!")
            return

        game["guesses"].append(guess)
        feedback = get_feedback(guess, secret)

        response = f"`{guess.upper()}` {feedback}"

        if guess == secret:
            if player_id not in leaderboard:
                leaderboard[player_id] = {"username": message.author.name, "current_streak": 0, "best_streak": 0}

            leaderboard[player_id]["current_streak"] += 1
            if leaderboard[player_id]["current_streak"] > leaderboard[player_id]["best_streak"]:
                leaderboard[player_id]["best_streak"] = leaderboard[player_id]["current_streak"]

            leaderboard[player_id]["username"] = message.author.name
            save_leaderboard()

            response += f"\n\n🎉 **Congratulations {message.author.mention}!** You solved it!\n"
            response += f"🔥 Current streak: **{leaderboard[player_id]['current_streak']}**"

            del active_games[channel_id]

        await message.channel.send(response)
        return

    await bot.process_commands(message)

# ====================== END GAME ======================
@bot.command(name="endwordle", aliases=["endgame", "exitgame"])
async def end_wordle(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    channel_id = ctx.channel.id
    if channel_id in active_games:
        game = active_games[channel_id]
        secret = game["secret"]
        player_id = game["player_id"]

        if player_id in leaderboard:
            leaderboard[player_id]["current_streak"] = 0
            save_leaderboard()

        del active_games[channel_id]
        await ctx.send(f"✅ Game ended. The word was **{secret.upper()}**")
    else:
        await ctx.send("No active Wordle game in this channel.")

bot.run(TOKEN)
