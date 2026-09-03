import os

def remove_copy_files():
    """Deletes any .py files that contain '(copy)' or ' copy' in the filename"""
    deleted = []
    current_dir = os.getcwd()

    for filename in os.listdir(current_dir):
        if filename.endswith(".py") and (
            "(copy)" in filename or " copy" in filename.lower()
        ):
            try:
                filepath = os.path.join(current_dir, filename)
                os.remove(filepath)
                deleted.append(filename)
                print(f"🗑️ Deleted: {filename}")
            except Exception as e:
                print(f"❌ Failed to delete {filename}: {e}")

    return deleted


remove_copy_files()

import json
import re
import random
import discord
import asyncio
import datetime
import time
from pymongo import MongoClient
import certifi

# ===================== MONGODB CONNECTION =====================
# Set the MONGO_URI environment variable to your connection string.
MONGO_URI = os.environ.get("MONGO_URI")
mongo_client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000
)
db = mongo_client["WordleBotDB"]

stats_col = db["stats"]
auto_responses_col = db["auto_responses"]
leaderboard_col = db["wordle_leaderboards"]  # same collection leaderboard.py's cog uses

STATS_DOC_ID = "config"

active_1v1_lobbies = {}
active_1v1_matches = {}   # channel_id -> match data

# Add this function
WORD_LIST_FILES = [f"wordle_list{i}.json" for i in range(1, 6)]


def load_wordle_lists():
    """Combine the numbered Wordle lists into one difficulty mapping."""
    combined = {}
    for filename in WORD_LIST_FILES:
        data = load_json(filename, dict)
        if not isinstance(data, dict):
            continue
        for difficulty, words in data.items():
            if not isinstance(words, list):
                continue
            pool = combined.setdefault(difficulty, [])
            for word in words:
                if isinstance(word, str) and word not in pool:
                    pool.append(word)
    return combined


def get_random_word_1v1(guild_id, length: int = None):
    """Get random word for 1v1 (can force length)"""
    words_dict = load_wordle_lists()
    all_words = []
    for cat in words_dict.values():
        all_words.extend(cat)
    
    if length:
        candidates = [w for w in all_words if len(w) == length]
        if not candidates:
            candidates = all_words
    else:
        candidates = all_words
    
    word = random.choice(candidates).lower()
    return word, len(word)

# File Paths
MAINTENANCE_FILE = "maintenance_mode.json"
CONFIG_FILE = "server_config.json"
STATS_FILE = "stats.json"
LEADERBOARD_FILE = "wordle_leaderboard.json"
CATEGORIES_FILE = "categories.json"
ROLES_FILE = "roles.json"
# Kept as a compatibility alias for older imports; the active source is the
# five numbered files above.
WORD_LIST_FILE = WORD_LIST_FILES[0]
EMOJI_FILE = "emoji.json"
LIMIT_FILE = "wordle_limit.json"

active_games = {}


def load_stats():
    """Load the single shared config/stats document from MongoDB."""
    try:
        doc = stats_col.find_one({"_id": STATS_DOC_ID})
        if not doc:
            return {}
        doc.pop("_id", None)
        return doc
    except Exception:
        return {}

def save_stats(data):
    """Persist the stats/config dict as a single MongoDB document."""
    doc = dict(data)
    doc["_id"] = STATS_DOC_ID
    stats_col.replace_one({"_id": STATS_DOC_ID}, doc, upsert=True)

def load_json(filename, default_factory):
    if not os.path.exists(filename):
        data = default_factory()
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default_factory()


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# Load data into global variables
server_config = load_json(CONFIG_FILE, dict)
roles_data = load_json(ROLES_FILE, lambda: {"servers": {}})
categories_data = load_json(CATEGORIES_FILE, lambda: {"servers": {}})
emojis = load_json(EMOJI_FILE, lambda: {"correct": {}, "misplaced": {}, "wrong": {}})

def is_whato_disabled(guild_id_str: str) -> bool:
    """Returns True if bot commands are toggled off for this server."""
    return server_config.get("whato_disabled", {}).get(str(guild_id_str), False)


def is_server_blacklisted(guild_id):
    """
    Checks if a server ID is present within the global blacklist.
    """
    if not guild_id:
        return False
        
    # Safely extract the pool array from your server config tracking
    blacklist_pool = server_config.get("blacklisted_servers", [])
    
    # Check both string variations and integer values to protect against type errors
    if str(guild_id) in blacklist_pool or guild_id in blacklist_pool:
        return True
        
    return False

TRUSTED_DAILY_LIMIT = 10
REGULAR_DAILY_LIMIT = 3
DEBUG_CHANNEL_ID = 1525186482149658745  # legacy fallback only

def get_debug_channel_ids(guild_id=None) -> list:
    """
    Returns a list of debug channel IDs to send to.
    - global channel  → receives logs from ALL servers
    - server channel  → receives logs only from that server (when guild_id given)
    - fallback        → hardcoded DEBUG_CHANNEL_ID if nothing is configured
    """
    stats = load_stats()
    channel_ids = []

    # Global always receives everything (when set)
    global_ch = stats.get("debug_channel_global")
    if global_ch:
        try:
            channel_ids.append(int(global_ch))
        except (TypeError, ValueError):
            pass

    # Server-specific only for that guild's logs
    if guild_id:
        server_ch = (stats.get("debug_channels") or {}).get(str(guild_id))
        if server_ch:
            try:
                sid = int(server_ch)
                if sid not in channel_ids:
                    channel_ids.append(sid)
            except (TypeError, ValueError):
                pass

    # Legacy fallback only when nothing is configured
    if not channel_ids and DEBUG_CHANNEL_ID:
        channel_ids.append(int(DEBUG_CHANNEL_ID))

    return channel_ids


def get_debug_channel_id(guild_id=None) -> int | None:
    """Backwards-compatible single-ID helper (first match)."""
    ids = get_debug_channel_ids(guild_id)
    return ids[0] if ids else None


def set_debug_channel(channel_id: int, guild_id=None):
    """
    Saves the debug channel to MongoDB.
    - guild_id=None  → sets the global debug channel (all server logs)
    - guild_id given → sets a server-specific channel (only that server's logs)
    """
    stats = load_stats()
    if guild_id:
        if "debug_channels" not in stats or not isinstance(stats["debug_channels"], dict):
            stats["debug_channels"] = {}
        stats["debug_channels"][str(guild_id)] = str(channel_id)
    else:
        stats["debug_channel_global"] = str(channel_id)
    save_stats(stats)

def is_op(user_id):
    uid_str = str(user_id)
    stats = load_stats()
    if uid_str in {"1465295674768883889", "1375782450118000681", "1469939898130895022"}:
        return True
    if uid_str in stats.get("op_users", []):
        return True
    return False

def is_debug_mode() -> bool:
    stats = load_stats()
    return stats.get("debug_mode", True)

def set_debug_mode(enabled: bool):
    stats = load_stats()
    stats["debug_mode"] = enabled
    save_stats(stats)

async def get_debug_channel(bot, guild_id=None):
    """Returns the first debug channel object (backwards compatible)."""
    ch_ids = get_debug_channel_ids(guild_id)
    if not ch_ids:
        return None
    ch = bot.get_channel(ch_ids[0])
    if ch is None:
        try:
            ch = await bot.fetch_channel(ch_ids[0])
        except Exception as e:
            print(f"[get_debug_channel] fetch failed: {e}")
    return ch


async def send_debug_msg(bot, message: str, guild_id=None):
    """
    Sends a debug message to the appropriate channel(s).
    - global channel receives ALL logs
    - server channel receives only that server's logs (when guild_id is passed)
    Always pass guild_id=ctx.guild.id from command handlers so server routing works.
    """
    if not is_debug_mode():
        return

    ch_ids = get_debug_channel_ids(guild_id)
    if not ch_ids:
        return

    for ch_id in ch_ids:
        ch = bot.get_channel(ch_id)
        if ch is None:
            try:
                ch = await bot.fetch_channel(ch_id)
            except Exception as e:
                print(f"[send_debug_msg] fetch failed for {ch_id}: {e}")
                continue
        try:
            await ch.send(message)
        except Exception as e:
            print(f"[send_debug_msg] send failed for {ch_id}: {e}")

def is_admin(user_id, guild=None, check_global=False):
    uid_str = str(user_id)
    stats = load_stats()
    if uid_str in {"1465295674768883889", "1375782450118000681", "1469939898130895022"}:
        return True

    # Check global op_users (If they are OP, they are also Admin)
    stats = load_stats()
    if "op_users" in stats and isinstance(stats["op_users"], list):
        if uid_str in stats["op_users"]:
            return True

    # Check global admin_users from stats.json
    if "admin_users" in stats and isinstance(stats["admin_users"], list):
        if uid_str in stats["admin_users"]:
            return True

    # Non-admin users are always blocked in blacklisted servers
    if guild and is_server_blacklisted(guild.id):
        return False

    # Local Trusted Server Users Check
    if guild and not check_global:
        gid_str = str(guild.id)
        trusted_list = stats.get("trusted_users", {}).get(gid_str, [])
        if uid_str in trusted_list:
            return True

    return False

def remove_from_whitelist(guild_id: int, user_id: int):
    """Explicitly removes a trusted user from stats.json trusted_users"""
    gid_str = str(guild_id)
    uid_str = str(user_id)
    stats = load_stats()
    trusted = stats.get("trusted_users", {})
    if gid_str in trusted and uid_str in trusted[gid_str]:
        trusted[gid_str].remove(uid_str)
        stats["trusted_users"] = trusted
        save_stats(stats)
        return True
    return False

def toggle_whitelist(guild_id: int, user_id: int):
    """Toggles a user's trusted status in stats.json"""
    gid_str = str(guild_id)
    uid_str = str(user_id)
    stats = load_stats()
    if "trusted_users" not in stats:
        stats["trusted_users"] = {}
    if gid_str not in stats["trusted_users"]:
        stats["trusted_users"][gid_str] = []
    trusted_list = stats["trusted_users"][gid_str]
    if uid_str in trusted_list:
        trusted_list.remove(uid_str)
        save_stats(stats)
        return "removed"
    else:
        trusted_list.append(uid_str)
        save_stats(stats)
        return "added"
# The logic that makes the categories work
def get_random_word(guild_id, category=None):
    gid = str(guild_id)
    # Load the dictionary of words
    words_dict = load_wordle_lists()

    # If no category was chosen, find the server's default or use 'medium'
    if not category or category.lower() == "default":
        category = (
            categories_data.get("servers", {})
            .get(gid, {})
            .get("default_category", "medium")
        )

    # Fallback if the category doesn't exist in the numbered Wordle lists.
    if category not in words_dict:
        available = list(words_dict.keys()) if words_dict else ["apple"]
        category = random.choice(available)

    pool = words_dict.get(category, ["apple"])
    word = random.choice(pool).lower()
    return word, len(word)


# The logic that creates the colored letter boxes
def get_feedback(guess, secret):
    secret_list = list(secret)
    guess_list = list(guess)
    result_emojis = [None] * len(guess)

    # Pass 1: Correct position (Green/Lime)
    for i in range(len(guess)):
        if guess_list[i] == secret_list[i]:
            result_emojis[i] = emojis["correct"].get(guess_list[i], "🟩")
            secret_list[i] = None

    # Pass 2: Wrong position or completely wrong
    for i in range(len(guess)):
        if result_emojis[i] is None:
            if guess_list[i] in secret_list:
                result_emojis[i] = emojis["misplaced"].get(guess_list[i], "🟨")
                secret_list[secret_list.index(guess_list[i])] = None
            else:
                result_emojis[i] = emojis["wrong"].get(guess_list[i], "⬜")

    return "".join(result_emojis)


# Records the win and updates streaks (stored in MongoDB, same collection/doc
# shape used by leaderboard.py's cog and /addlb: _id = "{guild_id}_{user_id}")
def record_win(guild, user_id, username):
    gid, uid = str(guild.id), str(user_id)
    doc_id = f"{gid}_{uid}"

    existing = leaderboard_col.find_one({"_id": doc_id})
    new_current = (existing.get("current_streak", 0) if existing else 0) + 1
    best = existing.get("best_streak", 0) if existing else 0
    if new_current > best:
        best = new_current

    leaderboard_col.update_one(
        {"_id": doc_id},
        {"$set": {
            "guild_id": gid,
            "user_id": uid,
            "username": username,
            "current_streak": new_current,
            "best_streak": best,
        }},
        upsert=True
    )


# ==================== MAINTENANCE MODE ====================


MAINTENANCE_DOC_ID = "maintenance"

def toggle_maintenance() -> bool:
    """Toggle maintenance mode in MongoDB and return the new state."""
    try:
        doc = stats_col.find_one({"_id": MAINTENANCE_DOC_ID}) or {}
        current = doc.get("enabled", False)
        new_state = not current
        stats_col.replace_one({"_id": MAINTENANCE_DOC_ID}, {"_id": MAINTENANCE_DOC_ID, "enabled": new_state}, upsert=True)
        return new_state
    except Exception as e:
        print(f"[toggle_maintenance] failed: {e}")
        return False

def is_maintenance_mode() -> bool:
    """Check if maintenance mode is enabled from MongoDB."""
    try:
        doc = stats_col.find_one({"_id": MAINTENANCE_DOC_ID})
        return doc.get("enabled", False) if doc else False
    except Exception:
        return False

WORDLE_LIMITS_DOC_ID = "wordle_limits"

def load_wordle_limits():
    try:
        doc = stats_col.find_one({"_id": WORDLE_LIMITS_DOC_ID})
        if not doc:
            return {"users": {}, "infinite": {}}
        doc.pop("_id", None)
        return doc
    except Exception:
        return {"users": {}, "infinite": {}}

def save_wordle_limits(data):
    try:
        doc = dict(data)
        doc["_id"] = WORDLE_LIMITS_DOC_ID
        stats_col.replace_one({"_id": WORDLE_LIMITS_DOC_ID}, doc, upsert=True)
    except Exception as e:
        print(f"[save_wordle_limits] failed: {e}")

def get_user_game_count(user_id):
    if is_admin(user_id) or is_infinite_wordle(user_id):
        return 0

    data = load_wordle_limits()
    uid = str(user_id)
    user_data = data.get("users", {}).get(uid)

    if not user_data:
        return 0

    current_date = datetime.date.today().isoformat()
    if user_data.get("date") != current_date:
        data.setdefault("users", {}).pop(uid, None)
        save_wordle_limits(data)
        return 0

    return user_data.get("count", 0)

def increment_user_game_count(user_id):
    if is_admin(user_id):
        return False

    data = load_wordle_limits()
    uid = str(user_id)
    current_date = datetime.date.today().isoformat()

    if uid not in data.get("users", {}) or data["users"][uid].get("date") != current_date:
        data.setdefault("users", {})[uid] = {"count": 1, "date": current_date}
    else:
        data["users"][uid]["count"] += 1

    save_wordle_limits(data)
    return data["users"][uid]["count"]

# ===================== WORDLE LIMIT MANAGEMENT =====================

def reset_user_wordle_limit(user_id):
    data = load_wordle_limits()
    uid = str(user_id)
    changed = False

    if uid in data.get("users", {}):
        del data["users"][uid]
        changed = True

    if uid in data.get("infinite", {}):
        del data["infinite"][uid]
        changed = True

    if changed:
        save_wordle_limits(data)
    return changed

def toggle_infinite_wordle(user_id):
    data = load_wordle_limits()
    uid = str(user_id)
    data.setdefault("infinite", {})
    new_state = not data["infinite"].get(uid, False)
    data["infinite"][uid] = new_state
    save_wordle_limits(data)
    return new_state

def is_infinite_wordle(user_id):
    try:
        data = load_wordle_limits()
        return data.get("infinite", {}).get(str(user_id), False)
    except Exception:
        return False

def get_server_lb(guild_id):
    """Returns {user_id: {username, current_streak, best_streak, ...}} for a guild, from MongoDB."""
    gid = str(guild_id)
    docs = leaderboard_col.find({"guild_id": gid})
    return {d["user_id"]: d for d in docs}


# ===================== AUTO RESPONSE SYSTEM =====================

AUTO_RESPONSE_FILE = "auto_responses.json"

def load_auto_responses():
    """Returns {trigger: {...}} built from individual MongoDB documents."""
    result = {}
    for doc in auto_responses_col.find():
        trigger = doc.pop("_id")
        result[trigger] = doc
    return result

def save_auto_responses(data):
    """Full resync of the autoresponder collection from the given dict."""
    auto_responses_col.delete_many({})
    docs = []
    for trigger, content in data.items():
        doc = dict(content)
        doc["_id"] = trigger
        docs.append(doc)
    if docs:
        auto_responses_col.insert_many(docs)

def parse_reactions(react_str: str):
    if not react_str:
        return None
    if isinstance(react_str, (list, tuple)):
        return [str(r).strip() for r in react_str if str(r).strip()]
    react_str = str(react_str).strip()
    if '-' in react_str:
        return [r.strip() for r in react_str.split('-') if r.strip()]
    if re.fullmatch(r"<a?:[A-Za-z0-9_~]+:\d+>", react_str):
        return [react_str]
    return [react_str]


EMOJI_LIST_FILE = "emoji_list.json"


def load_allowed_emoji_list():
    data = load_json(EMOJI_LIST_FILE, list)
    if isinstance(data, dict):
        data = data.get("allowed", [])
    return {str(item).strip() for item in data if str(item).strip()}


def custom_emoji_id(value):
    match = re.fullmatch(r"<a?:[A-Za-z0-9_~]+:(\d+)>", str(value).strip())
    return int(match.group(1)) if match else None


def is_reaction_allowed(value, guild=None, is_global=False):
    """Validate Unicode reactions and server emoji access."""
    value = str(value).strip()
    emoji_id = custom_emoji_id(value)
    if emoji_id is None:
        return bool(value)
    if is_global:
        return value in load_allowed_emoji_list()
    return bool(guild and guild.get_emoji(emoji_id))

COOLDOWN_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*"
    r"(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)\s*$",
    re.IGNORECASE,
)
COOLDOWN_MULTIPLIERS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
}


def is_valid_cooldown(cooldown_str: str) -> bool:
    """Return True for blank cooldowns or supported seconds/minutes/hours values."""
    if cooldown_str is None or not str(cooldown_str).strip():
        return True
    return COOLDOWN_PATTERN.fullmatch(str(cooldown_str)) is not None


def parse_cooldown(cooldown_str: str):
    """Convert 2s/2seconds/2m/2hours into a number of seconds."""
    if cooldown_str is None or not str(cooldown_str).strip():
        return 0

    match = COOLDOWN_PATTERN.fullmatch(str(cooldown_str))
    if not match:
        return 0

    amount = float(match.group(1))
    seconds = amount * COOLDOWN_MULTIPLIERS[match.group(2).lower()]
    return int(seconds) if seconds.is_integer() else seconds

def add_auto_response(trigger: str, reply: str, matchmode: str = "contains", 
                     react: str = None, channel: str = None, cooldown: str = None, 
                     global_server: bool = False, guild_id: str = None):
    """
    Saves a new autoresponder. 
    Forces global configuration to OFF by default and locks it to the current server.
    """
    data = load_auto_responses()
    trigger = trigger.lower().strip()
    
    data[trigger] = {
        "trigger": trigger,
        "response": reply,
        "matchmode": matchmode.lower(),
        "react": parse_reactions(react),
        "channel": str(channel) if channel else None,
        "cooldown": parse_cooldown(cooldown),
        "global": bool(global_server),
        "guild_id": str(guild_id) if guild_id else None
    }
    save_auto_responses(data)
    return True

def remove_auto_response(trigger: str):
    data = load_auto_responses()
    trigger = trigger.lower().strip()
    if trigger in data:
        del data[trigger]
        save_auto_responses(data)
        return True
    return False

def remove_all_auto_responses(guild_id: str = None, global_all: bool = False):
    data = load_auto_responses()
    if global_all:
        save_auto_responses({})
        return True
    
    to_keep = {k: v for k, v in data.items() if v.get("global") or str(v.get("guild_id", "")) != guild_id}
    save_auto_responses(to_keep)
    return True

def edit_auto_response(old_trigger: str, new_trigger: str = None, reply: str = None, 
                      matchmode: str = None, react: str = None, channel: str = None,
                      cooldown: str = None, global_server: bool = None):
    data = load_auto_responses()
    old = old_trigger.lower().strip()
    if old not in data:
        return False
    entry = data[old]
    
    if new_trigger:
        new = new_trigger.lower().strip()
        if new != old:
            data[new] = entry
            del data[old]
            entry = data[new]
            entry["trigger"] = new
    
    if reply is not None: entry["response"] = reply
    if matchmode is not None: entry["matchmode"] = matchmode.lower()
    if react is not None: entry["react"] = parse_reactions(react)
    if channel is not None: entry["channel"] = str(channel) if channel else None
    if cooldown is not None: entry["cooldown"] = parse_cooldown(cooldown)
    if global_server is not None: entry["global"] = global_server
    
    save_auto_responses(data)
    return True

def get_all_auto_responses():
    return load_auto_responses()

_AUTORESPONDER_COOLDOWNS = {}


def check_cooldown(guild_id: str, trigger: str):
    """Allow a matched trigger once per configured interval for each server."""
    data = load_auto_responses()
    trigger_key = trigger.lower().strip()
    cooldown = float(data.get(trigger_key, {}).get("cooldown", 0) or 0)
    if cooldown <= 0:
        return True

    now = time.monotonic()
    cooldown_key = (str(guild_id), trigger_key)
    last_triggered = _AUTORESPONDER_COOLDOWNS.get(cooldown_key)

    if last_triggered is not None and now - last_triggered < cooldown:
        return False

    _AUTORESPONDER_COOLDOWNS[cooldown_key] = now
    return True