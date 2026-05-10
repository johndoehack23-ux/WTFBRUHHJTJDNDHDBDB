import os
import discord
from discord.ext import commands
import random
import json
import nltk

nltk.download('words', quiet=True)
from nltk.corpus import words as nltk_words

TOKEN = os.environ.get("DISCORD_TOKEN")
prefix = "-"

ADMIN_IDS = {"1465295674768883889", "1275741025905803275"}

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=prefix, intents=intents, help_command=None)

# Game storage
active_games = {}

# Next forced word (set by admin with -sw)
next_word = None

# Leaderboard structure:
# {
#   "servers": { "guild_id": { "user_id": { username, current_streak, best_streak } } },
#   "global":  { "user_id": { username, current_streak, best_streak } }
# }
LEADERBOARD_FILE = "wordle_leaderboard.json"
leaderboard = {"servers": {}, "global": {}}

# ====================== WORD POOL ======================
print("Loading word pool...")
WORD_POOL = {}
all_words_set = set()
for w in nltk_words.words():
    w = w.lower()
    if w.isalpha() and 4 <= len(w) <= 9:
        WORD_POOL.setdefault(len(w), []).append(w)
        all_words_set.add(w)
print(f"✅ Word pool ready: {sum(len(v) for v in WORD_POOL.values())} words across lengths 4–9")

def get_random_word():
    length = random.randint(4, 9)
    return random.choice(WORD_POOL[length]), length

def is_valid_word(word):
    return word in all_words_set

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

# ====================== LEADERBOARD HELPERS ======================
def load_leaderboard():
    global leaderboard
    try:
        if os.path.exists(LEADERBOARD_FILE):
            with open(LEADERBOARD_FILE, "r") as f:
                data = json.load(f)
            # Migrate old flat structure
            if "servers" not in data and "global" not in data:
                leaderboard = {"servers": {}, "global": data}
            else:
                leaderboard = data
            total = sum(len(v) for v in leaderboard["servers"].values()) + len(leaderboard["global"])
            print(f"✅ Loaded leaderboard ({total} entries)")
    except Exception as e:
        print("Error loading leaderboard:", e)
        leaderboard = {"servers": {}, "global": {}}

def save_leaderboard():
    try:
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(leaderboard, f, indent=4)
    except Exception as e:
        print("Error saving leaderboard:", e)

def get_server_lb(guild_id):
    gid = str(guild_id)
    if gid not in leaderboard["servers"]:
        leaderboard["servers"][gid] = {}
    return leaderboard["servers"][gid]

def record_win(guild_id, user_id, username):
    uid = str(user_id)
    gid = str(guild_id)

    # Server entry
    srv = get_server_lb(gid)
    if uid not in srv:
        srv[uid] = {"username": username, "current_streak": 0, "best_streak": 0}
    srv[uid]["current_streak"] += 1
    if srv[uid]["current_streak"] > srv[uid]["best_streak"]:
        srv[uid]["best_streak"] = srv[uid]["current_streak"]
    srv[uid]["username"] = username

    # Global entry — always stays in sync with server streak
    if uid not in leaderboard["global"]:
        leaderboard["global"][uid] = {"username": username, "current_streak": 0, "best_streak": 0}
    # Sync global current_streak to match server so resets are reflected correctly
    leaderboard["global"][uid]["current_streak"] = srv[uid]["current_streak"]
    if leaderboard["global"][uid]["current_streak"] > leaderboard["global"][uid]["best_streak"]:
        leaderboard["global"][uid]["best_streak"] = leaderboard["global"][uid]["current_streak"]
    leaderboard["global"][uid]["username"] = username

    save_leaderboard()
    return srv[uid]["current_streak"]

def record_loss(guild_id, user_id):
    uid = str(user_id)
    gid = str(guild_id)

    srv = get_server_lb(gid)
    if uid in srv:
        srv[uid]["current_streak"] = 0

    if uid in leaderboard["global"]:
        leaderboard["global"][uid]["current_streak"] = 0

    save_leaderboard()

def build_lb_embed(title, data, color):
    if not data:
        return None
    # Deduplicate: if same username appears under multiple IDs, keep highest best_streak
    seen = {}
    for uid, d in data.items():
        name = d.get("username", f"User {uid}")
        if name not in seen or d["best_streak"] > seen[name]["best_streak"]:
            seen[name] = d
    sorted_players = sorted(
        seen.items(),
        key=lambda x: (x[1]["best_streak"], x[1]["current_streak"]),
        reverse=True
    )
    embed = discord.Embed(title=title, color=color)
    for rank, (name, d) in enumerate(sorted_players[:10], 1):
        embed.add_field(
            name=f"#{rank} {name}",
            value=f"**Best:** {d['best_streak']} 🔥   Current: {d['current_streak']}",
            inline=False
        )
    return embed

async def try_delete(msg):
    try:
        await msg.delete()
    except discord.Forbidden:
        pass

# ====================== ON READY ======================
@bot.event
async def on_ready():
    load_leaderboard()
    print(f"Logged in as {bot.user}")
    print(f"------ Wordle Bot Ready | Prefix: {prefix} ------")

# ====================== PUBLIC HELP ======================
@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="🤖 Wordle Bot Commands", color=0x00ff00)
    embed.add_field(name=f"{prefix}wordle", value="Start a new Wordle game (random 4–9 letter word)", inline=False)
    embed.add_field(name=f"{prefix}endgame", value="End the current game (also: endwordle, exitgame)", inline=False)
    embed.add_field(name=f"{prefix}leaderboard", value="Show this server's leaderboard (aliases: lb, top)", inline=False)
    embed.add_field(name=f"{prefix}glb", value="Show the global leaderboard (also: globallb, global-lb)", inline=False)
    embed.add_field(name=f"{prefix}help", value="Show this help message", inline=False)
    embed.set_footer(text="Type any word during an active game to guess! Colors only — no letters shown.")
    await ctx.send(embed=embed)

# ====================== ADMIN HELP ======================
@bot.command(name="adminhelp")
async def admin_help(ctx):
    if not is_admin(ctx.author.id):
        return
    embed = discord.Embed(title="🔐 Admin Commands", color=0xFF4500)
    embed.add_field(name=f"{prefix}reveal", value="Reveal the current secret word", inline=False)
    embed.add_field(name=f"{prefix}hint", value="Give a hint (reveals one correct letter's position)", inline=False)
    embed.add_field(name=f"{prefix}reset-leaderboard / {prefix}rlb", value="Reset this server's leaderboard", inline=False)
    embed.add_field(name=f"{prefix}resetglobal-leaderboard / {prefix}rglb", value="Reset the ENTIRE global leaderboard", inline=False)
    embed.set_footer(text="These commands are restricted to admins only.")
    await ctx.send(embed=embed)

# ====================== REVEAL (ADMIN) ======================
@bot.command(name="reveal", hidden=True)
async def reveal_word(ctx):
    if not is_admin(ctx.author.id):
        return
    channel_id = ctx.channel.id
    if channel_id in active_games:
        secret = active_games[channel_id]["secret"]
        await ctx.send(f"🔍 The secret word is: **{secret.upper()}**")
    else:
        await ctx.send("❌ No active Wordle game in this channel.")

# ====================== HINT (ADMIN) ======================
@bot.command(name="hint")
async def hint_word(ctx):
    if not is_admin(ctx.author.id):
        return
    channel_id = ctx.channel.id
    if channel_id not in active_games:
        await ctx.send("❌ No active Wordle game in this channel.")
        return
    secret = active_games[channel_id]["secret"]
    pos = random.randint(0, len(secret) - 1)
    await ctx.send(f"💡 Hint: Letter **{pos + 1}** is **{secret[pos].upper()}**")

# ====================== SERVER LEADERBOARD ======================
@bot.command(name="leaderboard", aliases=["lb", "top"])
async def show_server_leaderboard(ctx):
    if ctx.guild is None:
        await ctx.send("❌ This command can only be used in a server.")
        return
    srv = get_server_lb(ctx.guild.id)
    embed = build_lb_embed(f"🏆 {ctx.guild.name} — Wordle Leaderboard", srv, 0xFFD700)
    if embed is None:
        await ctx.send("🏆 No wins recorded in this server yet!")
        return
    await ctx.send(embed=embed)

# ====================== GLOBAL LEADERBOARD ======================
@bot.command(name="globallb", aliases=["glb", "global-lb", "global-leaderboard"])
async def show_global_leaderboard(ctx):
    embed = build_lb_embed("🌍 Global Wordle Leaderboard", leaderboard["global"], 0x1E90FF)
    if embed is None:
        await ctx.send("🌍 No global wins recorded yet!")
        return
    await ctx.send(embed=embed)

# ====================== RESET SERVER LEADERBOARD (ADMIN) ======================
@bot.command(name="reset-leaderboard", aliases=["rlb"])
async def reset_server_leaderboard(ctx):
    if not is_admin(ctx.author.id):
        return
    if ctx.guild is None:
        await ctx.send("❌ This command can only be used in a server.")
        return
    gid = str(ctx.guild.id)
    # Reset global current_streak for users in this server before clearing
    srv = leaderboard["servers"].get(gid, {})
    for uid in srv:
        if uid in leaderboard["global"]:
            leaderboard["global"][uid]["current_streak"] = 0
    leaderboard["servers"][gid] = {}
    save_leaderboard()
    await ctx.send(f"✅ **{ctx.guild.name}** server leaderboard has been reset.")

# ====================== RESET GLOBAL LEADERBOARD (ADMIN) ======================
@bot.command(name="rglb", aliases=["resetglobal-leaderboard", "resetgloballb"])
async def reset_global_leaderboard(ctx):
    if not is_admin(ctx.author.id):
        return
    # Also reset current_streak in all server leaderboards
    for gid in leaderboard["servers"]:
        for uid in leaderboard["servers"][gid]:
            leaderboard["servers"][gid][uid]["current_streak"] = 0
    leaderboard["global"] = {}
    save_leaderboard()
    await ctx.send("✅ **Global** leaderboard has been completely reset.")

# ====================== SET WORD (ADMIN) ======================
@bot.command(name="sw", aliases=["set-word", "setword"])
async def set_word(ctx, *, word: str = None):
    if not is_admin(ctx.author.id):
        return
    global next_word
    if not word:
        await ctx.send("❌ Usage: `-sw <word>`")
        return
    next_word = word.strip().lower()
    await ctx.send(f"✅ Next wordle word set to **{next_word.upper()}** (length: **{len(next_word)}**) — will be used on the next `-wordle`, then back to random.")

# ====================== WORDLE START ======================
@bot.command(name="wordle")
async def start_wordle(ctx):
    global next_word
    await try_delete(ctx.message)
    channel_id = ctx.channel.id
    if channel_id in active_games:
        await ctx.send("There's already an active Wordle game in this channel!")
        return

    if next_word:
        secret = next_word
        length = len(secret)
        next_word = None
    else:
        secret, length = get_random_word()

    active_games[channel_id] = {
        "secret": secret,
        "length": length,
        "guesses": [],
        "player_id": str(ctx.author.id),
        "guild_id": ctx.guild.id if ctx.guild else None
    }

    await ctx.send(
        f"## New wordle game started by {ctx.author.mention}\n"
        f"Word length: **{length}**"
    )

# ====================== GUESS HANDLER ======================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    content = message.content.strip().lower()

    if channel_id in active_games:
        game = active_games[channel_id]
        length = game["length"]

        if len(content) == length and content.isalpha() and not content.startswith(prefix):
            secret = game["secret"]
            player_id = game["player_id"]
            guild_id = game.get("guild_id")

            if not is_valid_word(content):
                await message.channel.send(f"**{content.upper()}** is not a valid English word!")
                return

            if content in game["guesses"]:
                await message.channel.send(f"**{content.upper()}** was already guessed!")
                return

            game["guesses"].append(content)
            feedback = get_feedback(content, secret)
            response = feedback

            if content == secret:
                streak = record_win(guild_id, player_id, message.author.name)
                response += f"\n\n🎉 **{message.author.mention}** got it! The word was **{secret.upper()}**\n"
                response += f"🔥 Current streak: **{streak}**"
                del active_games[channel_id]

            await message.channel.send(response)
            return

    await bot.process_commands(message)

# ====================== END GAME ======================
@bot.command(name="endwordle", aliases=["endgame", "exitgame"])
async def end_wordle(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games:
        game = active_games[channel_id]
        secret = game["secret"]
        player_id = game["player_id"]
        guild_id = game.get("guild_id")

        record_loss(guild_id, player_id)
        del active_games[channel_id]
        await ctx.send(f"✅ Game ended. The word was **{secret.upper()}**")
    else:
        await ctx.send("No active Wordle game in this channel.")

bot.run(TOKEN)
