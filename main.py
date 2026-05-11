import os
import discord
from discord.ext import commands
import random
import json

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

WORD_CATEGORIES = {
    "easy": [
        "ball", "cake", "fire", "fish", "gold", "home", "king", "lake", "lamp", "land",
        "leaf", "lion", "love", "moon", "rain", "ring", "road", "rock", "rose", "sand",
        "ship", "snow", "song", "star", "time", "tree", "wind", "wolf", "wood", "word",
        "book", "bird", "bear", "barn", "boat", "bone", "cave", "coat", "coin", "dark",
        "deer", "door", "duck", "farm", "flag", "frog", "game", "gate", "gift", "hand",
        "head", "heat", "hero", "hill", "hole", "hook", "hope", "horn", "hunt", "iron",
        "jump", "knee", "luck", "meal", "milk", "mind", "mint", "mood", "moss", "move",
        "nail", "neck", "nest", "news", "note", "page", "pain", "palm", "park", "path",
        "peak", "pick", "pine", "pink", "plan", "play", "pole", "pool", "pray", "pull",
        "pump", "push", "race", "rage", "rank", "rate", "read", "real", "rice", "ride",
        "ripe", "risk", "roar", "role", "roof", "room", "rope", "rule", "rush", "safe",
        "sail", "sale", "save", "seal", "seat", "seed", "shoe", "shop", "show", "sick",
        "side", "sign", "silk", "sing", "sink", "size", "skin", "slow", "snap", "soap",
        "soft", "soil", "soul", "soup", "spin", "spot", "step", "stop", "surf", "swim",
        "tail", "tale", "talk", "tall", "tape", "task", "team", "tell", "tent", "test",
        "tide", "tiny", "tire", "toll", "tone", "tool", "toss", "tour", "town", "trap",
        "trim", "trip", "tube", "tune", "twin", "type", "vine", "vote", "wade", "wake",
        "walk", "wall", "warm", "wave", "wear", "weed", "well", "wide", "wife", "wild",
        "wind", "wine", "wing", "wise", "wish", "year", "zone", "zoom", "drum", "dust",
    ],
    "medium": [
        "apple", "arrow", "badge", "blade", "blast", "blaze", "blend", "blood", "bloom",
        "board", "brace", "brand", "brave", "bread", "break", "breed", "brick", "bride",
        "bring", "broad", "brook", "brown", "brush", "build", "burst", "cabin", "candy",
        "carry", "catch", "chain", "chair", "charm", "chase", "cheap", "check", "cheer",
        "chest", "chief", "child", "claim", "class", "clean", "clear", "click", "cliff",
        "climb", "clock", "close", "cloud", "coach", "coast", "coral", "count", "court",
        "cover", "crack", "craft", "crane", "crash", "cream", "crime", "cross", "crowd",
        "crown", "crush", "cycle", "dance", "depth", "devil", "dirty", "dodge", "draft",
        "drain", "drama", "dread", "dream", "drift", "drink", "drive", "eagle", "earth",
        "ember", "empty", "enemy", "entry", "equal", "essay", "event", "exact", "extra",
        "fable", "fairy", "faith", "fancy", "feast", "fever", "field", "fight", "final",
        "flame", "flash", "flesh", "flick", "float", "flood", "floor", "flour", "flute",
        "force", "forge", "found", "frame", "fresh", "frost", "fruit", "funny", "ghost",
        "giant", "glass", "gloom", "glory", "glove", "grace", "grade", "grain", "grand",
        "grant", "grape", "grasp", "grass", "grave", "great", "green", "grief", "grind",
        "group", "grove", "growl", "guard", "guest", "guide", "guilt", "happy", "harsh",
        "haven", "heart", "heavy", "heist", "hence", "honor", "horse", "hotel", "house",
        "human", "humor", "hurry", "image", "inner", "jewel", "joint", "joker", "judge",
        "juice", "jumbo", "knife", "knock", "known", "label", "large", "laser", "layer",
        "learn", "legal", "level", "light", "limit", "local", "lodge", "logic", "lower",
        "loyal", "lucky", "lunar", "lunch", "lyric", "magic", "major", "manor", "maple",
        "match", "mayor", "media", "mercy", "merit", "metal", "might", "minor", "model",
        "money", "month", "moral", "motor", "mount", "mouse", "mouth", "movie", "music",
        "nerve", "never", "night", "noble", "noise", "north", "novel", "nurse", "ocean",
        "offer", "olive", "opera", "orbit", "order", "outer", "owner", "paint", "panel",
        "panic", "paper", "party", "pause", "peace", "pearl", "phase", "phone", "photo",
        "piano", "pilot", "pitch", "pixel", "pizza", "place", "plain", "plane", "plant",
        "plate", "point", "polar", "pound", "power", "press", "price", "pride", "prime",
        "print", "prize", "proof", "prose", "proud", "punch", "queen", "quest", "quiet",
        "quote", "radar", "radio", "raise", "rally", "rapid", "raven", "reach", "realm",
        "rebel", "reign", "relax", "renew", "reply", "ridge", "rifle", "right", "risky",
        "rival", "river", "robot", "rough", "round", "royal", "ruler", "sadly", "saint",
        "salad", "sauce", "scale", "scare", "scene", "score", "scout", "sense", "serve",
        "shade", "shake", "shame", "shape", "share", "shark", "sharp", "shelf", "shell",
        "shift", "shine", "shirt", "short", "shout", "sight", "silly", "skill", "skull",
        "slate", "sleep", "slice", "slide", "slope", "smart", "smash", "smile", "smoke",
        "solid", "solve", "spare", "spark", "speak", "speed", "spell", "spend", "spice",
        "spine", "spite", "split", "spray", "squad", "stair", "stake", "stamp", "stand",
        "stare", "stark", "start", "state", "steam", "steel", "stern", "stick", "still",
        "sting", "stock", "stone", "storm", "story", "stout", "strap", "straw", "strip",
        "study", "style", "sugar", "sunny", "super", "swamp", "swear", "sweet", "swift",
        "sword", "syrup", "table", "teach", "tense", "thank", "theme", "thick", "thing",
        "think", "thorn", "three", "throw", "thumb", "tiger", "title", "token", "torch",
        "touch", "tough", "tower", "toxic", "trace", "track", "trade", "trail", "train",
        "trait", "treat", "trend", "trial", "tribe", "trick", "troop", "truck", "truly",
        "trunk", "trust", "truth", "twice", "twist", "ultra", "under", "union", "unity",
        "until", "upper", "upset", "urban", "usual", "utter", "valor", "value", "vapor",
        "vault", "verse", "video", "viral", "virus", "visit", "vital", "vivid", "voice",
        "waste", "watch", "water", "weary", "weird", "whale", "wheat", "wheel", "white",
        "whole", "witch", "woman", "world", "worry", "worse", "wrath", "write", "young",
        "youth", "zebra",
    ],
    "hard": [
        "ablaze", "abrupt", "accuse", "adjust", "aerial", "afford", "agenda", "ambush",
        "anthem", "antler", "appear", "archery", "ardent", "armour", "ascend", "ashore",
        "assert", "assess", "assist", "attain", "attack", "auburn", "avenue", "babble",
        "ballot", "banter", "battle", "beacon", "beauty", "beckon", "belief", "blight",
        "bother", "bottle", "bounce", "branch", "breach", "breath", "breeze", "bridge",
        "bright", "broken", "bronze", "bucket", "bundle", "bunker", "burden", "butler",
        "button", "candle", "castle", "caught", "cellar", "chorus", "circle", "cobalt",
        "coffin", "column", "combat", "commit", "compel", "comply", "condor", "convoy",
        "copper", "corner", "costly", "cotton", "covert", "crafty", "crater", "crisis",
        "darken", "dagger", "debate", "decade", "decide", "defend", "desert", "design",
        "detail", "devour", "differ", "divert", "divide", "dollar", "domain", "double",
        "dragon", "driven", "easily", "embark", "empire", "enable", "endure", "engine",
        "enough", "escape", "excite", "expect", "export", "expose", "extend", "fallen",
        "falter", "famine", "fathom", "feline", "fervor", "fierce", "figure", "filter",
        "finite", "fleece", "flight", "flinch", "footer", "forbid", "forest", "formal",
        "fossil", "foster", "freeze", "frenzy", "fulfill", "gallop", "gambit", "garnet",
        "gather", "gentle", "goblin", "golden", "gossip", "gothic", "govern", "gravel",
        "groove", "grudge", "grumpy", "hasten", "hazard", "hearth", "herald", "hermit",
        "heroic", "hidden", "hollow", "horror", "humble", "hustle", "impact", "impede",
        "import", "ignite", "infant", "injure", "insult", "invade", "invent", "island",
        "jester", "jostle", "jungle", "kettle", "kindle", "knight", "lavish", "lessen",
        "listen", "loosen", "lunacy", "lurker", "mangle", "marble", "marvel", "mayhem",
        "menace", "method", "mighty", "mobile", "modern", "mortal", "mumble", "murmur",
        "mutiny", "mystic", "narrow", "native", "nature", "nectar", "needle", "negate",
        "nether", "nimble", "normal", "object", "obtain", "offend", "offset", "onward",
        "ordeal", "origin", "outrun", "outlaw", "pardon", "patrol", "permit", "pillar",
        "pirate", "plague", "planet", "pledge", "plunge", "portal", "potent", "praise",
        "prison", "profit", "prompt", "proper", "punish", "pursue", "puzzle", "quartz",
        "radiant", "ransom", "rapids", "reason", "recall", "reduce", "reform", "refuge",
        "regime", "reject", "render", "reside", "resist", "result", "retort", "reveal",
        "revive", "reward", "riddle", "ritual", "robust", "rotund", "rubble", "ruling",
        "savage", "scorch", "scroll", "search", "sector", "secure", "seldom", "select",
        "serial", "settle", "severe", "shadow", "shiver", "shrine", "signal", "simmer",
        "simple", "single", "somber", "source", "stitch", "stolen", "strain", "stride",
        "strife", "strike", "strong", "submit", "subtle", "suffer", "summer", "supply",
        "sunset", "swerve", "symbol", "tackle", "talent", "tangle", "target", "temple",
        "tender", "terror", "thrash", "threat", "thrive", "throne", "thrust", "tingle",
        "topple", "tremor", "tribal", "trophy", "tundra", "turret", "unique", "unlock",
        "upbeat", "uphold", "utmost", "vanish", "varied", "venom", "verify", "vessel",
        "victor", "vortex", "voyage", "wander", "warden", "weapon", "wither", "wizard",
        "wonder", "worthy", "wraith", "zealot",
    ],
    "impossible": [
        "abolish", "absolve", "acclaim", "acquire", "advance", "afflict", "agonize",
        "almanac", "anatomy", "anarchy", "ancient", "anxiety", "archive", "ascribe",
        "astound", "balance", "banquet", "bargain", "battery", "beguile", "beneath",
        "berserk", "bewitch", "calcify", "clarity", "command", "compass", "complex",
        "conceal", "condemn", "conduit", "confide", "conjure", "consent", "consume",
        "contend", "contest", "control", "corrupt", "counsel", "crimson", "crucial",
        "dazzle", "deadlock", "decorum", "deflect", "delimit", "deliver", "descend",
        "destroy", "develop", "devious", "dictate", "discern", "discord", "dismiss",
        "disturb", "diverge", "dubious", "dungeon", "dynamic", "eclipse", "elevate",
        "embrace", "empower", "enchant", "encrypt", "essence", "eternal", "evident",
        "examine", "exhaust", "exploit", "explore", "extreme", "fantasy", "ferment",
        "fissure", "flicker", "fortune", "frantic", "freedom", "fulfill", "furnace",
        "genesis", "glimmer", "gravity", "hallowed", "harvest", "haunted", "heroism",
        "hostile", "illicit", "illusion", "immerse", "impasse", "implode", "impulse",
        "inspect", "inspire", "intense", "isolate", "journey", "kingdom", "languish",
        "lawless", "liberty", "loathing", "machine", "manifest", "measure", "miracle",
        "mission", "mystery", "narrate", "natural", "nothing", "obscure", "obvious",
        "outrage", "overcome", "overrun", "phantom", "pinnacle", "plunder", "precise",
        "predict", "preside", "prevent", "process", "protect", "prowess", "radiate",
        "rampage", "reality", "rebuild", "reckless", "reclaim", "recover", "reflect",
        "release", "remnant", "renounce", "resolve", "restore", "retract", "revenge",
        "salvage", "sanctify", "scarlet", "scatter", "scourge", "serious", "shelter",
        "shudder", "silence", "sincere", "slumber", "solitude", "sorcery", "splendor",
        "storming", "strategy", "strength", "subject", "supreme", "survival", "sustain",
        "thunder", "torment", "torrent", "tragedy", "traitor", "triumph", "turbulent",
        "unchain", "unravel", "urgency", "usurper", "valiant", "venture", "vibrant",
        "villain", "violent", "virtue", "volcano", "warlord", "wayward", "whisper",
        "wretched", "absolve", "becalmed", "capstone", "dauntless", "embattle",
        "fracture", "garrison", "imprison", "labyrinth", "obsidian", "overpower",
        "perilous", "resilient", "scorched", "shattered", "treachery", "vanguard",
    ],
}

CATEGORIES = list(WORD_CATEGORIES.keys())

def get_random_word(category: str = None):
    if category and category in WORD_CATEGORIES:
        pool = WORD_CATEGORIES[category]
    else:
        pool = [w for words in WORD_CATEGORIES.values() for w in words]
    word = random.choice(pool)
    return word, len(word)

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
    embed.add_field(name=f"{prefix}wordle", value="Start a random Wordle game", inline=False)
    embed.add_field(name=f"{prefix}wordle easy / medium / hard / impossible", value="Start a game with a specific difficulty", inline=False)
    embed.add_field(name=f"{prefix}leaderboard", value="Server leaderboard", inline=False)
    await ctx.send(embed=embed)

CATEGORY_LABELS = {
    "easy": "🟢 Easy",
    "medium": "🟡 Medium",
    "hard": "🔴 Hard",
    "impossible": "💀 Impossible",
}

@bot.command(name="wordle")
async def start_wordle(ctx, arg1: str = None, private_id: int = None, public_id: int = None):
    gid = str(ctx.guild.id)

    if arg1 == "set":
        if not is_admin(ctx.author.id): return
        if private_id is None or public_id is None:
            await ctx.send(f"❌ Usage: `{prefix}wordle set <private_channelID> <wordle_channelID>`")
            return
        server_config[gid] = {"private": private_id, "public": public_id}
        save_config(server_config)
        await ctx.send("✅ Channels configured for this server!")
        return

    config = server_config.get(gid, {})
    private_chan = config.get("private")
    public_chan = config.get("public")

    category = None
    secret = None

    if arg1 and arg1.lower() in WORD_CATEGORIES:
        category = arg1.lower()
        secret, _ = get_random_word(category)
        try: await ctx.message.delete()
        except: pass
        target_id = ctx.channel.id
    elif arg1 and is_admin(ctx.author.id):
        if private_chan and ctx.channel.id != private_chan:
            await ctx.send(f"❌ Manual setup must be done in <#{private_chan}>.")
            return
        secret = arg1.strip().lower()
        try: await ctx.message.delete()
        except: pass
        target_id = public_chan if public_chan else ctx.channel.id
    else:
        secret, _ = get_random_word()
        try: await ctx.message.delete()
        except: pass
        target_id = ctx.channel.id

    if target_id in active_games:
        await ctx.send("There's already an active Wordle game in this channel!")
        return

    active_games[target_id] = {
        "secret": secret,
        "length": len(secret),
        "guesses": [],
        "player_id": str(ctx.author.id),
        "guild_id": ctx.guild.id,
        "category": category,
    }

    label = CATEGORY_LABELS.get(category, "🎲 Random") if category else "🎲 Random"
    target_channel = bot.get_channel(target_id)
    if target_channel:
        await target_channel.send(
            f"## New Wordle game started!\n"
            f"Difficulty: **{label}** — Word length: **{len(secret)}**"
        )

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