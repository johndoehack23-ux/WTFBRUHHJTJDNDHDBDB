import os
import discord
from discord.ext import commands
import random
import json
import nltk

nltk.download('words', quiet=True)
from nltk.corpus import words as nltk_words

TOKEN = "MTUwMjY1NDczNzIxOTMyMTkyNg.GDEjks.7CXLPrk5_TUPzggHXvkldNRkb2p0GihV9YAVA0"
prefix = "."

bot_ready = False

MAINTENANCE_MODE = False
MAINTENANCE_FILE = "maintenance_mode.json"
CONFIG_FILE = "server_config.json"

ADMIN_IDS = {"1465295674768883889", "1275741025905803275"}

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

server_config = load_config()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=prefix, intents=intents, help_command=None)

AUTO_RESPONSES = {
    "xkira": {
        "reply": "<:absolutecinema:1484234420725616861> XKira is the goat 🔥 <:absolutecinema:1484234420725616861>",
        "server_ids": ["1481930888702070815", "1481930889691795540"],
        "reactions": ["🔥", "<:absolutecinema:1484234420725616861>"]
    },
    "ninja": {
        "reply": "test",
        "server_ids": ["1481930888702070815"],
        "reactions": ["👀"]
    }
}

active_games = {}

LEADERBOARD_FILE = "wordle_leaderboard.json"
leaderboard = {"servers": {}}

@bot.event
async def on_ready():
    global bot_ready
    load_leaderboard()
    load_maintenance_mode()
    print(f"Logged in as {bot.user}")
    bot_ready = True

print("Loading word pool...")
WORD_POOL = {}
all_words_set = set()
for w in nltk_words.words():
    w = w.lower()
    if w.isalpha() and 4 <= len(w) <= 9:
        WORD_POOL.setdefault(len(w), []).append(w)
        all_words_set.add(w)
print(f"✅ Word pool ready: {sum(len(v) for v in WORD_POOL.values())} words")

def get_random_word():
    length = random.randint(4, 9)
    return random.choice(WORD_POOL[length]), length

def get_feedback(guess, secret):
    secret_list = list(secret)
    guess_list = list(guess)
    result = [""] * len(guess)

    for i in range(len(guess)):
        if guess_list[i] == secret_list[i]:
            result[i] = "🟩"
            secret_list[i] = None

    for i in range(len(guess)):
        if result[i] == "":
            if guess_list[i] in secret_list:
                result[i] = "🟨"
                secret_list[secret_list.index(guess_list[i])] = None
            else:
                result[i] = "⬜"

    return "".join(result)

def get_server_lb(guild_id):
    gid = str(guild_id)
    if gid not in leaderboard["servers"]:
        leaderboard["servers"][gid] = {}
    return leaderboard["servers"][gid]

def load_leaderboard():
    global leaderboard
    try:
        if os.path.exists(LEADERBOARD_FILE):
            with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "servers" in data:
                leaderboard = data
            else:
                leaderboard = {"servers": data if isinstance(data, dict) else {}}
        else:
            leaderboard = {"servers": {}}
    except:
        leaderboard = {"servers": {}}

def load_maintenance_mode():
    global MAINTENANCE_MODE
    try:
        if os.path.exists(MAINTENANCE_FILE):
            with open(MAINTENANCE_FILE, "r") as f:
                data = json.load(f)
                MAINTENANCE_MODE = data.get("enabled", False)
    except:
        MAINTENANCE_MODE = False

def save_maintenance_mode():
    try:
        with open(MAINTENANCE_FILE, "w") as f:
            json.dump({"enabled": MAINTENANCE_MODE}, f, indent=4)
    except:
        pass

def save_leaderboard():
    try:
        os.makedirs(os.path.dirname(LEADERBOARD_FILE) or ".", exist_ok=True)
        with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(leaderboard, f, indent=4, ensure_ascii=False)
    except:
        pass

def record_win(guild_id, user_id, username):
    if not guild_id:
        return 0
    uid = str(user_id)
    gid = str(guild_id)
    srv = get_server_lb(gid)

    if uid not in srv:
        srv[uid] = {"username": username, "current_streak": 0, "best_streak": 0}
    
    srv[uid]["current_streak"] += 1
    if srv[uid]["current_streak"] > srv[uid]["best_streak"]:
        srv[uid]["best_streak"] = srv[uid]["current_streak"]
    srv[uid]["username"] = username

    save_leaderboard()
    return srv[uid]["current_streak"]

def record_loss(guild_id, user_id):
    if not guild_id or not user_id:
        return
    uid = str(user_id)
    gid = str(guild_id)
    srv = get_server_lb(gid)
    if uid in srv:
        srv[uid]["current_streak"] = 0
    save_leaderboard()

def build_lb_embed(title, data, color):
    if not data:
        return None
    seen = {}
    for uid, d in data.items():
        name = d.get("username", f"User {uid}")
        if name not in seen or d["best_streak"] > seen[name]["best_streak"]:
            seen[name] = d
    sorted_players = sorted(seen.items(), key=lambda x: (x[1]["best_streak"], x[1]["current_streak"]), reverse=True)
    
    embed = discord.Embed(title=title, color=color)
    for rank, (name, d) in enumerate(sorted_players[:10], 1):
        embed.add_field(
            name=f"Top {rank}: {name}",
            value=f"**Best:** {d['best_streak']} 🔥   Current: {d['current_streak']}",
            inline=False
        )
    return embed

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not bot_ready:
        await message.channel.send("⏳ Please wait, the bot is still starting up!")
        return

    content = message.content.strip().lower()

    if message.guild:
        for trigger, data in AUTO_RESPONSES.items():
            if trigger in content:
                if str(message.guild.id) in data["server_ids"]:
                    await message.channel.send(data["reply"])
                    for emoji in data["reactions"]:
                        try: await message.add_reaction(emoji)
                        except: pass
                    break

    channel_id = message.channel.id
    if channel_id in active_games:
        game = active_games[channel_id]
        length = game["length"]
        secret = game["secret"]

        if len(content) == length and content.isalpha() and not content.startswith(prefix):
            if content in game.get("guesses", []):
                await message.channel.send(f"**{content.upper()}** was already guessed!")
                return

            game.setdefault("guesses", []).append(content)
            feedback = get_feedback(content, secret)

            if content == secret:
                winner_id = str(message.author.id)
                winner_name = message.author.name
                streak = record_win(game.get("guild_id"), winner_id, winner_name)
                await message.channel.send(f"{feedback}\n\n🎉 **{message.author.mention}** got it! The word was **{secret.upper()}**\n🔥 Current streak: **{streak}**")
                del active_games[channel_id]
            else:
                await message.channel.send(feedback)
            return

    if MAINTENANCE_MODE and not is_admin(message.author.id):
        return

    await bot.process_commands(message)

@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="🤖 Wordle Bot Commands", color=0x00ff00)
    embed.add_field(name=f"{prefix}wordle", value="Start a new Wordle game", inline=False)
    embed.add_field(name=f"{prefix}leaderboard", value="Server leaderboard", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="wordle")
async def start_wordle(ctx, word_or_set: str = None, private_id: int = None, public_id: int = None):
    gid = str(ctx.guild.id)
    
    if word_or_set == "set":
        if not is_admin(ctx.author.id): return
        if private_id is None or public_id is None:
            await ctx.send(f"❌ Usage: `{prefix}wordle set <private_channelID> <wordle_channelID>`")
            return
        server_config[gid] = {"private": private_id, "public": public_id}
        save_config(server_config)
        await ctx.send(f"✅ Channels configured for this server!")
        return

    config = server_config.get(gid, {})
    private_chan = config.get("private")
    public_chan = config.get("public")

    if word_or_set and is_admin(ctx.author.id):
        if private_chan and ctx.channel.id != private_chan:
            await ctx.send(f"❌ Manual setup must be done in <#{private_chan}>.")
            return

        secret = word_or_set.strip().lower()
        try: await ctx.message.delete()
        except: pass
        target_id = public_chan if public_chan else ctx.channel.id
    else:
        try: await ctx.message.delete()
        except: pass
        secret, _ = get_random_word()
        target_id = ctx.channel.id

    if target_id in active_games:
        await ctx.send("There's already an active Wordle game there!")
        return

    active_games[target_id] = {
        "secret": secret,
        "length": len(secret),
        "guesses": [],
        "player_id": str(ctx.author.id),
        "guild_id": ctx.guild.id
    }

    target_channel = bot.get_channel(target_id)
    if target_channel:
        await target_channel.send(f"## New wordle game started!\nWord length: **{len(secret)}**")

@bot.command(name="endwordle", aliases=["endgame", "exitgame"])
async def end_wordle(ctx):
    if ctx.channel.id in active_games:
        game = active_games[ctx.channel.id]
        record_loss(game.get("guild_id"), game.get("player_id"))
        secret = game["secret"]
        del active_games[ctx.channel.id]
        await ctx.send(f"✅ Game ended. Word was **{secret.upper()}**")

@bot.command(name="reveal")
async def reveal_word(ctx):
    if is_admin(ctx.author.id) and ctx.channel.id in active_games:
        await ctx.send(f"🔍 Secret word: **{active_games[ctx.channel.id]['secret'].upper()}**")

@bot.command(name="hint")
async def hint_word(ctx):
    if is_admin(ctx.author.id) and ctx.channel.id in active_games:
        secret = active_games[ctx.channel.id]["secret"]
        pos = random.randint(0, len(secret)-1)
        await ctx.send(f"💡 Hint: Letter {pos+1} is **{secret[pos].upper()}**")

@bot.command(name="leaderboard", aliases=["lb", "top"])
async def show_server_leaderboard(ctx):
    if ctx.guild is None: return
    srv = get_server_lb(ctx.guild.id)
    embed = build_lb_embed(f"🏆 {ctx.guild.name} Leaderboard", srv, 0xFFD700)
    if embed:
        await ctx.send(embed=embed)
    else:
        await ctx.send("No wins yet!")

@bot.command(name="reset-leaderboard", aliases=["rlb"])
async def reset_server_leaderboard(ctx):
    if is_admin(ctx.author.id) and ctx.guild:
        leaderboard["servers"][str(ctx.guild.id)] = {}
        save_leaderboard()
        await ctx.send("✅ Leaderboard reset.")

@bot.command(name="leaderboard-best", aliases=["lb-best"])
async def set_best_streak(ctx, user: discord.User, number: int):
    if is_admin(ctx.author.id) and ctx.guild:
        srv = get_server_lb(ctx.guild.id)
        srv[str(user.id)] = {"username": user.name, "current_streak": srv.get(str(user.id), {}).get("current_streak", 0), "best_streak": number}
        save_leaderboard()
        await ctx.send(f"✅ Best streak set for {user}.")

@bot.command(name="leaderboard-current", aliases=["lb-current"])
async def set_current_streak(ctx, user: discord.User, number: int):
    if is_admin(ctx.author.id) and ctx.guild:
        srv = get_server_lb(ctx.guild.id)
        data = srv.get(str(user.id), {"username": user.name, "current_streak": 0, "best_streak": 0})
        data["current_streak"] = number
        if number > data["best_streak"]: data["best_streak"] = number
        srv[str(user.id)] = data
        save_leaderboard()
        await ctx.send(f"✅ Current streak updated for {user}.")

@bot.command(name="adminhelp")
async def admin_help(ctx):
    if not is_admin(ctx.author.id): return
    embed = discord.Embed(title="🔐 Admin Commands", color=0xFF4500)
    embed.add_field(name=f"{prefix}reveal", value="Reveal word", inline=False)
    embed.add_field(name=f"{prefix}hint", value="Give hint", inline=False)
    embed.add_field(name=f"{prefix}rlb", value="Reset LB", inline=False)
    embed.add_field(name=f"{prefix}lb-best", value="Set best streak", inline=False)
    embed.add_field(name=f"{prefix}lb-current", value="Set current streak", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="test")
async def toggle_test_mode(ctx):
    if is_admin(ctx.author.id):
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        save_maintenance_mode()
        await ctx.send(f"🔧 Maintenance Mode: {'ON' if MAINTENANCE_MODE else 'OFF'}")

bot.run(TOKEN)