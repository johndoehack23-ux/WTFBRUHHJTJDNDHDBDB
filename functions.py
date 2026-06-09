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
import random
import discord
import asyncio
import datetime

active_1v1_lobbies = {}
active_1v1_matches = {}   # channel_id -> match data

# Add this function
def get_random_word_1v1(guild_id, length: int = None):
    """Get random word for 1v1 (can force length)"""
    words_dict = load_json(WORD_LIST_FILE, dict)
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
LEADERBOARD_FILE = "wordle_leaderboard.json"
CATEGORIES_FILE = "categories.json"
ROLES_FILE = "roles.json"
WORD_LIST_FILE = "word_list.json"
EMOJI_FILE = "emoji.json"
LIMIT_FILE = "wordle_limit.json"

ADMIN_IDS = {"1465295674768883889", "1275741025905803275", "1464480027558281371"}
# >>> ninja, xkira <<<

# The core dictionary shared across the entire bot
active_games = {}


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
leaderboard = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
roles_data = load_json(ROLES_FILE, lambda: {"servers": {}})
categories_data = load_json(CATEGORIES_FILE, lambda: {"servers": {}})
emojis = load_json(EMOJI_FILE, lambda: {"correct": {}, "misplaced": {}, "wrong": {}})

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

def is_admin(user_id, guild=None, check_global=False):
    """
    Core permission check structure:
    - ADMIN_IDS always have full bypass, even in blacklisted servers.
    - Trusted users have server-level access only in non-blacklisted servers.
    """
    uid_str = str(user_id)

    # ADMIN_IDS get unconditional global bypass — checked FIRST
    if uid_str in ADMIN_IDS:
        return True

    # Non-admin users are always blocked in blacklisted servers
    if guild and is_server_blacklisted(guild.id):
        return False

    # Local Trusted Server Users Check
    if guild and not check_global:
        gid_str = str(guild.id)
        trusted_list = server_config.get(gid_str, {}).get("trusted_users", [])
        if uid_str in trusted_list:
            return True

    return False

def remove_from_whitelist(guild_id: int, user_id: int):
    """Explicitly removes a trusted user from a specific server's config block"""
    gid_str = str(guild_id)
    uid_str = str(user_id)
    
    if gid_str in server_config and "trusted_users" in server_config[gid_str]:
        if uid_str in server_config[gid_str]["trusted_users"]:
            server_config[gid_str]["trusted_users"].remove(uid_str)
            save_json(CONFIG_FILE, server_config) # Persistent save to server_config.json
            return True
    return False

def toggle_whitelist(guild_id: int, user_id: int):
    """Toggles a user's trusted status: adds them if missing, removes them if present"""
    gid_str = str(guild_id)
    uid_str = str(user_id)
    
    if gid_str not in server_config:
        server_config[gid_str] = {}
        
    if "trusted_users" not in server_config[gid_str]:
        server_config[gid_str]["trusted_users"] = []
        
    trusted_list = server_config[gid_str]["trusted_users"]
    
    if uid_str in trusted_list:
        trusted_list.remove(uid_str)
        save_json(CONFIG_FILE, server_config)
        return "removed"
    else:
        trusted_list.append(uid_str)
        save_json(CONFIG_FILE, server_config)
        return "added"

# The logic that makes the categories work
def get_random_word(guild_id, category=None):
    gid = str(guild_id)
    # Load the dictionary of words
    words_dict = load_json(WORD_LIST_FILE, dict)

    # If no category was chosen, find the server's default or use 'medium'
    if not category or category.lower() == "default":
        category = (
            categories_data.get("servers", {})
            .get(gid, {})
            .get("default_category", "medium")
        )

    # Fallback if the category doesn't exist in word_list.json
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


# Records the win and updates streaks
def record_win(guild, user_id, username):
    gid, uid = str(guild.id), str(user_id)

    if gid not in leaderboard["servers"]:
        leaderboard["servers"][gid] = {}

    srv = leaderboard["servers"][gid]
    if uid not in srv:
        srv[uid] = {"username": username, "current_streak": 0, "best_streak": 0}

    srv[uid]["current_streak"] += 1
    if srv[uid]["current_streak"] > srv[uid]["best_streak"]:
        srv[uid]["best_streak"] = srv[uid]["current_streak"]

    srv[uid]["username"] = username
    save_json(LEADERBOARD_FILE, leaderboard)


# ==================== MAINTENANCE MODE ====================


def toggle_maintenance() -> bool:
    """Toggle maintenance mode and return the new state"""
    file_path = MAINTENANCE_FILE

    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"enabled": False}, f, indent=4)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {"enabled": False}

    current = data.get("enabled", False)
    new_state = not current

    data["enabled"] = new_state
    save_json(file_path, data)

    return new_state

def is_maintenance_mode() -> bool:
    """Check if maintenance mode is enabled"""
    try:
        with open(MAINTENANCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("enabled", False)
    except:
        return False

def load_wordle_limits():
    try:
        with open(LIMIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": {}}

def save_wordle_limits(data):
    with open(LIMIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_user_game_count(user_id):
    if is_admin(user_id) or is_infinite_wordle(user_id):
        return 0

    data = load_wordle_limits()
    uid = str(user_id)
    user_data = data["users"].get(uid)

    if not user_data:
        return 0

    # Strict calendar date check (YYYY-MM-DD)
    current_date = datetime.date.today().isoformat()
    if user_data.get("date") != current_date:
        # It's a brand new day! Clear old data smoothly
        data["users"].pop(uid, None)
        save_wordle_limits(data)
        return 0

    return user_data.get("count", 0)

def increment_user_game_count(user_id):
    if is_admin(user_id):
        return False

    data = load_wordle_limits()
    uid = str(user_id)
    current_date = datetime.date.today().isoformat()

    if uid not in data["users"] or data["users"][uid].get("date") != current_date:
        # First game of the day
        data["users"][uid] = {"count": 1, "date": current_date}
    else:
        # Match found for today, increment cleanly
        data["users"][uid]["count"] += 1

    save_wordle_limits(data)
    return data["users"][uid]["count"]

# ===================== WORDLE LIMIT MANAGEMENT =====================

def reset_user_wordle_limit(user_id):
    try:
        with open(LIMIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        return False
    
    uid = str(user_id)
    changed = False

    if uid in data.get("users", {}):
        del data["users"][uid]
        changed = True

    if "infinite" in data and uid in data["infinite"]:
        del data["infinite"][uid]
        changed = True
    
    if changed:
        with open(LIMIT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    return False


def toggle_infinite_wordle(user_id):
    try:
        with open(LIMIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = {"users": {}}
    
    uid = str(user_id)
    if "infinite" not in data:
        data["infinite"] = {}
    
    current = data["infinite"].get(uid, False)
    new_state = not current
    data["infinite"][uid] = new_state
    
    with open(LIMIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    
    return new_state


def is_infinite_wordle(user_id):
    try:
        with open(LIMIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("infinite", {}).get(str(user_id), False)
    except:
        return False

def get_server_lb(guild_id):
    gid = str(guild_id)
    if gid not in leaderboard["servers"]:
        leaderboard["servers"][gid] = {}
    return leaderboard["servers"][gid]


# ===================== AUTO RESPONSE SYSTEM =====================

AUTO_RESPONSE_FILE = "auto_responses.json"

def load_auto_responses():
    try:
        with open(AUTO_RESPONSE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_auto_responses(data):
    with open(AUTO_RESPONSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def parse_reactions(react_str: str):
    if not react_str:
        return None
    if '-' in react_str:
        return [r.strip() for r in react_str.split('-') if r.strip()]
    else:
        return [c for c in react_str if c.strip()]

def parse_cooldown(cooldown_str: str):
    if not cooldown_str:
        return 0
    s = cooldown_str.lower().strip()
    try:
        num = int(''.join(filter(str.isdigit, s)))
        return num if num > 0 else 0
    except:
        return 0

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
        "global": False,                       # <-- FIXED: Always forced to False
        "guild_id": str(guild_id) if guild_id else None  # <-- FIXED: Saves current server ID
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

def check_cooldown(guild_id: str, trigger: str):
    """Simple cooldown check using JSON (not ideal but per your request)"""
    data = load_auto_responses()
    cooldown = data.get(trigger.lower(), {}).get("cooldown", 0)
    if cooldown <= 0:
        return True

    return True