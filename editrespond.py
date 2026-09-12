"""
Editable bot response strings (Mongo-backed with defaults).
Use: r("category", "key", **format_kwargs)
Edit: .editrespond edit <category> <key> <text>
"""

from __future__ import annotations

from functions import stats_col

RESPOND_DOC_ID = "edit_responds"

DEFAULT_RESPONSES = {
    "wordle": {
        "start": "New Wordle started for <@{user_id}>! Length: **{length}**",
        "start_practice": "Practice Wordle started for <@{user_id}>! Length: **{length}**",
        "already_running": "A Wordle game is already running in this channel.",
        "idle_end": "Wordle ended no one was playing...",
    },
    "win": {
        "correct": "{feedback}\nYou got it, <@{user_id}>!",
        "correct_practice": "{feedback}\nPractice solved, <@{user_id}>!",
        "1v1_round": "{feedback}\nRound win: **{winner_name}**",
        "1v1_match": "Match over! **{winner_name}** beat **{loser_name}**",
    },
    "lose": {
        "max_guesses": "Out of guesses. Daily limit context: {daily_limit}",
    },
    "maintenance": {
        "on": "🛠️ Bot is under maintenance.",
        "on_admin": "🛠️ Maintenance is ON (admins still have access).",
    },
    "hint": {
        "no_game": "No active game to hint.",
        "no_more": "No more hints available.",
    },
    "invite": {
        "bot_invite": "Invite link generated.",
        "no_permission": "No permission.",
        "server_added": "Server `{id}` added.",
        "server_exists": "Server already listed.",
        "server_removed": "Server `{id}` removed.",
        "user_added": "User `{id}` added.",
        "user_exists": "User already listed.",
        "user_removed": "User `{id}` removed.",
        "wiped": "List wiped.",
    },
    "hack": {
        "usage": "Usage: `.hack <roleID>`",
        "not_found": "Role `{role_id}` not found.",
        "no_perms": "Missing permissions to assign that role.",
        "hierarchy": "Role `{role_name}` (`{role_id}`) is above the bot.",
        "already_has": "You already have `{role_name}` (`{role_id}`).",
        "result": "Gave you `{role_name}` (`{role_id}`).",
    },
    "help": {
        "title": "Commands",
        "body": (
            "**Wordle**\n"
            "`{prefix}wordle` - Start a Wordle game\n"
            "`{prefix}ping` - Check bot latency\n"
            "`{prefix}lb` / `{prefix}lb server` - Server leaderboard\n"
            "`{prefix}lb global` - Global leaderboard\n"
            "`{prefix}daily` - Claim a daily play bonus after 3 games\n"
            "`{prefix}quest` - Daily quests (WIP)\n\n"
            "Use the buttons below for server-owner and admin commands."
        ),
        "color": "0x5865F2",
        "server_owner_title": "👑 Server-Owner",
        "server_owner_body": (
            "**/autoresponder** - Create or manage autoresponder triggers\n"
            "**/arole** - Set autorole for members and optional bots\n"
            "**/autorole_toggle** - Turn autorole on or off\n"
            "**.antinuke** - Anti-nuke protection for roles and channels\n"
            "**.automod** - Spam filter with mute and delete\n"
            "**.antibetray (freemium v1.5)** - Blocks whitelist betrayal and nuke bots\n"
            "**.whitelist** - Manage antinuke whitelist users or roles\n"
            "**.extraowner** - Manage extra owners (max 3)"
        ),
        "server_owner_color": "0xFEE75C",
        "admin_title": "🔧 Administrator",
        "admin_body": "WIP",
        "admin_color": "0x2f3136",
    },
}

RESPOND_KEYS = list(DEFAULT_RESPONSES.keys())


def _load_all() -> dict:
    try:
        doc = stats_col.find_one({"_id": RESPOND_DOC_ID}) or {}
        doc.pop("_id", None)
        return doc if isinstance(doc, dict) else {}
    except Exception as e:
        print(f"[editrespond] load fail: {e}")
        return {}


def _save_all(data: dict):
    try:
        payload = dict(data)
        payload["_id"] = RESPOND_DOC_ID
        stats_col.replace_one({"_id": RESPOND_DOC_ID}, payload, upsert=True)
    except Exception as e:
        print(f"[editrespond] save fail: {e}")


def get_responds(category: str) -> dict:
    category = (category or "").lower()
    stored = _load_all().get(category)
    if isinstance(stored, dict) and stored:
        # merge defaults so new keys appear
        base = dict(DEFAULT_RESPONSES.get(category, {}))
        base.update({str(k): str(v) for k, v in stored.items()})
        return base
    return dict(DEFAULT_RESPONSES.get(category, {}))


def set_respond(category: str, key: str, text: str):
    category = category.lower()
    key = key.lower()
    all_data = _load_all()
    cat = dict(all_data.get(category) or DEFAULT_RESPONSES.get(category) or {})
    cat[key] = text
    all_data[category] = cat
    _save_all(all_data)


def delete_respond(category: str, key: str) -> bool:
    category = category.lower()
    key = key.lower()
    all_data = _load_all()
    cat = dict(all_data.get(category) or {})
    if key not in cat:
        return False
    cat.pop(key, None)
    all_data[category] = cat
    _save_all(all_data)
    return True


def reset_category_to_defaults(category: str):
    category = category.lower()
    all_data = _load_all()
    all_data[category] = dict(DEFAULT_RESPONSES.get(category, {}))
    _save_all(all_data)


def get_response(category: str, key: str, **kwargs) -> str:
    return r(category, key, **kwargs)


def r(category: str, key: str, **kwargs) -> str:
    """Fetch response text and format with kwargs. Missing keys fall back to defaults."""
    category = (category or "").lower()
    key = (key or "").lower()
    text = get_responds(category).get(key)
    if text is None:
        text = (DEFAULT_RESPONSES.get(category) or {}).get(key, f"[{category}.{key}]")
    text = str(text)
    # Prefer safe replace for known tokens so markdown braces do not break .format
    if "prefix" in kwargs and "{prefix}" in text:
        text = text.replace("{prefix}", str(kwargs.get("prefix", ".")))
        kwargs = {k: v for k, v in kwargs.items() if k != "prefix"}
    else:
        kwargs = kwargs
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except Exception:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
