"""
Utility module for editable response texts stored in MongoDB stats.
This module exists so that `from editrespond import get_response` works
(as expected by some entrypoints / older main.py versions).
"""
from functions import load_stats, save_stats

# Keys in the stats doc that hold editable response texts
RESPOND_KEYS = {
    "wordle":       "wordle_responses",
    "win":          "win_responses",
    "lose":         "lose_responses",
    "maintenance":  "maintenance_responses",
    "hint":         "hint_responses",
    "leaderboard":  "leaderboard_responses",
    "invite":       "invite_responses",
}

# Default texts used when a category is empty / missing
DEFAULT_RESPONSES = {
    "wordle": {
        "start": "## New Wordle by <@{user_id}>\nLength: {length}",
        "start_practice": "## New Wordle [PRACTICE MODE] by <@{user_id}>\nLength: {length}",
        "already_running": "A game is already running in that channel!",
        "no_game": "🔐 No game running.",
    },
    "win": {
        "correct": "## {feedback}\n<@{user_id}> guessed the correct word!",
        "correct_practice": "## {feedback}\n<@{user_id}> guessed the correct practice word!",
        "1v1_round": "{feedback}\n**{winner_name}** guessed it first! (+5 points)",
        "1v1_match": "## 🎉 **MATCH OVER!**\n**{winner_name}** wins the 1v1 match against **{loser_name}**!",
    },
    "lose": {
        "max_guesses": "You ran out of guesses! The word was **{secret}**.",
        "gave_up": "Game ended. The word was **{secret}**.",
    },
    "maintenance": {
        "on": "🛠️ **Bot is under maintenance.**",
        "on_admin": "🛠️ **Bot is under maintenance.** Only admins can use commands.",
        "toggled_on": "🔧 Maintenance mode is now **ON**.",
        "toggled_off": "🔧 Maintenance mode is now **OFF**.",
    },
    "hint": {
        "no_game": "🔐 No game running.",
        "no_more": "💎 No more hints.",
        "reveal": "💡 Letter {position} is **{letter}**",
    },
    "leaderboard": {
        "empty": "📭 No leaderboard data yet.",
        "header": "🏆 **Wordle Leaderboard**",
        "entry": "**#{rank}** {username} — Best: **{best}** | Current: **{current}**",
    },
    "invite": {
        "bot_invite": "👋 Click the button below to authorize adding the bot into your chosen server:",
        "user_added": "✅ User ID `{id}` added to invite whitelist!",
        "user_removed": "❌ User ID `{id}` removed from invite whitelist.",
        "user_exists": "ℹ️ User is already whitelisted.",
        "server_added": "✅ Server ID `{id}` added to allowed servers list!",
        "server_removed": "❌ Server ID `{id}` removed from allowed servers list.",
        "server_exists": "ℹ️ Server is already whitelisted.",
        "wiped": "🔓 Successfully **wiped the user invite whitelist**.",
        "no_permission": "You do not have permission to use this command.",
    },
}


def get_responds(category: str) -> dict:
    """
    Returns the dict of {key: text} for the given category.
    If the category is empty / missing in MongoDB, returns the built-in defaults.
    """
    stats = load_stats()
    key = RESPOND_KEYS.get(category.lower())
    if not key:
        return {}

    stored = stats.get(key, {})
    if not stored:  # empty or missing → use defaults
        return DEFAULT_RESPONSES.get(category.lower(), {}).copy()
    return stored


# Alias expected by the failing import in main.py
get_response = get_responds


def r(category: str, key: str, **kwargs) -> str:
    """
    Convenience helper: get a response text and format it with kwargs.
    Example: r("win", "correct", feedback=fb, user_id=123)
    Falls back to the key name if somehow missing.
    """
    text = get_responds(category).get(key)
    if text is None:
        # ultimate fallback
        text = DEFAULT_RESPONSES.get(category.lower(), {}).get(key, key)
    try:
        return text.format(**kwargs)
    except Exception:
        return text  # if formatting fails, return raw text


def set_respond(category: str, respond_key: str, new_text: str) -> bool:
    """Updates a single response text in MongoDB. Returns True on success."""
    key = RESPOND_KEYS.get(category.lower())
    if not key:
        return False
    stats = load_stats()
    if key not in stats or not isinstance(stats[key], dict):
        # Start from defaults so we don't lose the other keys
        stats[key] = DEFAULT_RESPONSES.get(category.lower(), {}).copy()
    stats[key][respond_key] = new_text
    save_stats(stats)
    return True


def delete_respond(category: str, respond_key: str) -> bool:
    """
    Deletes a single response entry.
    After deletion, if the category becomes empty it will fall back to defaults
    the next time get_responds() is called.
    """
    key = RESPOND_KEYS.get(category.lower())
    if not key:
        return False
    stats = load_stats()
    if key not in stats or respond_key not in stats.get(key, {}):
        return False
    del stats[key][respond_key]
    save_stats(stats)
    return True


def reset_category_to_defaults(category: str) -> bool:
    """Force a category back to the built-in defaults."""
    key = RESPOND_KEYS.get(category.lower())
    if not key:
        return False
    stats = load_stats()
    stats[key] = DEFAULT_RESPONSES.get(category.lower(), {}).copy()
    save_stats(stats)
    return True
