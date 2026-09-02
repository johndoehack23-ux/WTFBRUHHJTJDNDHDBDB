import discord
from discord.ext import commands
from functions import *

CREATOR_ID = 1465295674768883889
MONGO_KEY = "editrespond_overrides"

DEFAULTS = {
    "wordle": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_permission":        "You do not have permission to use this command.",
        "no_permission_custom": "❌ You do not have permission to use a custom word.",
        "blacklisted":          "❌ This server is blacklisted.",
        "globalend_done":       "All active Wordle games ended globally ({count} game(s)).",
        "denied_access":        "❌ You do not have access to this command.",
        "ended_server":         "✅ Ended {count} game(s) in this server.",
        "no_active_server":     "❌ No active games in this server.",
        "edit_usage":           "❌ Usage: `.wordle edit <word> [guildID]`",
        "invalid_word":         "❌ Invalid word. Must be alphabetic only.",
        "edit_no_game":         "❌ No active game found in guild `{gid}`.",
        "edit_done":            "✅ Word changed from `{old}` → `{new}` (length: {length})",
        "emoji_reaction":       "❌ Only emoji reactions are supported for that option.",
        "invalid_command":      "❌ Invalid command. Use `.wordle`, `.wordle end`, or `.wordle globalend`.",
        "game_started":         "🎮 Wordle game started! Guess the **{length}**-letter word.",
        "game_ended":           "✅ Game ended.",
        "game_not_started":     "❌ No active game found in this channel.",
        "correct_word":         "## {feedback}\n<@{user_id}> guessed the correct word!",
        "correct_practice":     "## {feedback}\n<@{user_id}> guessed the correct practice word!",
        "1v1_correct":          "{feedback}\n**{winner}** guessed it first! (+5 points)",
        "1v1_match_over":       "## 🎉 **MATCH OVER!**\n**{winner}** wins the 1v1 match against **{loser}**!",
        "custom_game_loaded":   "✅ Custom word loaded ({length} letters). Game starting...",
        "custom_alpha_only":    "❌ Custom word must contain only letters.",
    },
    "hint": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_game":              "🔐 No game running.",
        "no_hints":             "💎 No more hints.",
        "hint_msg":             "💡 Letter {idx} is **{letter}**",
    },
    "reveal": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_permission":        "You do not have permission to use this command.",
        "no_game":              "❌ No active game or 1v1 match in this channel.",
        "secret_1v1":           "🔍 **1v1 Secret word:** **{secret}**",
        "secret_word":          "🔍 Secret word: **{secret}**",
    },
    "leaderboard": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_permission":        "You do not have permission to use this command.",
        "no_stats_global":      "🏆 No stats yet globally!",
        "no_stats_server":      "🏆 No stats yet for this server!",
    },
    "mode": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_permission":        "You do not have permission to use this command.",
        "lobby_ended":          "1v1 lobby ended.",
        "match_ended":          "1v1 match ended.",
        "no_active":            "❌ No active 1v1 lobby or match in this channel.",
        "already_active":       "❌ A game or lobby is already active in this channel!",
        "not_found_users":      "❌ Could not find one or both users in this server.",
        "no_bots":              "❌ Bots cannot participate in 1v1.",
        "same_user":            "❌ Cannot 1v1 the same user twice.",
        "matchmaking_wait":     "⏳ **Matchmaking started!** Waiting 10 seconds...",
        "not_enough":           "❌ Not enough players joined the 1v1 lobby (need at least 2).",
        "error_match":          "❌ Error starting match.",
        "force_1v1":            "🔥 **Force 1v1!** {p1} vs {p2}",
    },
    "invite": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_permission":        "You do not have permission to use this command.",
        "not_authorized":       "❌ You are not authorized to invite this bot. Please contact the administrator.",
        "user_added":           "✅ User ID `{uid}` added to invite whitelist!",
        "user_removed":         "❌ User ID `{uid}` removed from invite whitelist.",
        "user_exists":          "ℹ️ User is already whitelisted.",
        "user_not_found":       "❌ User not found in whitelist.",
        "server_added":         "✅ Server ID `{uid}` added to allowed servers list!",
        "server_removed":       "❌ Server ID `{uid}` removed from allowed servers list.",
        "server_exists":        "ℹ️ Server is already whitelisted.",
        "server_not_found":     "❌ Server not found in allowed list.",
        "cleanall_done":        "🔓 Successfully **wiped the user invite whitelist**.",
    },
    "admin": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
        "no_permission":        "You do not have permission to use this command.",
        "infinite_enabled":     "Infinite wordle enabled for user ID `{uid}`.",
        "infinite_removed":     "Successfully removed infinite wordle and reset limits for user ID `{uid}`.",
        "infinite_all":         "Successfully removed infinite wordle for all users globally.",
        "limit_reset":          "Successfully reset daily wordle uses for user ID `{uid}`.",
        "limit_reset_full":     "Successfully reset and removed limits for user ID `{uid}`.",
        "added_global":         "Successfully added as {role} globally",
        "removed_global":       "Successfully removed",
        "not_in_list":          "Not in the global {role} list",
    },
    "prefix": {
        "no_permission":        "You do not have permission to use this command.",
        "no_global_perm":       "You do not have permission to change the global prefix.",
        "changed_server":       "✅ Server prefix changed from `{old}` → `{new}`",
        "changed_global":       "✅ Global prefix changed from `{old}` → `{new}`",
    },
    "autoresponder": {
        "no_permission":        "❌ You do not have permission to use this command.",
        "added":                "✅ Autoresponder added for: `{trigger}`",
        "added_global":         "✅ Autoresponder added 🌐 [GLOBAL] for: `{trigger}`",
        "edited":               "✅ Updated autoresponder setup: `{trigger}`",
        "deleted_local":        "🗑️ Local Autoresponder `{trigger}` successfully removed.",
        "deleted_global":       "🗑️ Global Autoresponder `{trigger}` completely removed.",
        "all_deleted_server":   "🗑️ **All auto responders for this server deleted.**",
        "all_deleted_global":   "🗑️ **ALL auto responders deleted globally.**",
    },
    "selfpromo": {
        "no_permission":        "❌ You do not have permission to use this command.",
        "invite_warning":       "❌ Only Discord server invite links are allowed in this channel.",
        "links_warning":        "❌ Only platform links (YouTube, TikTok, Twitch, etc.) are allowed in this channel.",
        "set_invite":           "✅ {channel} set as invite self-promo channel.",
        "set_links":            "✅ {channel} set as links self-promo channel.",
        "already_set":          "❌ {channel} is already a self-promo channel with that mode.",
        "removed":              "✅ {channel} removed from self-promo channels.",
        "not_found":            "❌ {channel} is not a self-promo channel.",
    },
    "difficulty": {
        "maintenance":          "🛠️ **Bot is under maintenance.** Only admins can use commands.",
        "invalid_mode":         "❌ Invalid mode!",
        "mode_set":             "✅ Default mode set to **{mode}**",
    },
    "endgame": {
        "no_permission":        "You do not have permission to use this command.",
        "global_done":          "✅ **Global Endgame** - Ended {count} game(s) across all servers.",
        "server_done":          "✅ Ended {count} game(s) in this server.",
        "no_active":            "No active game found in this server.",
        "invalid_option":       "❌ Invalid option. Use: `endgame server` or `endgame global`",
    },
    "name": {
        "no_permission":        "You do not have permission to use this command",
        "too_long":             "❌ Name must be 32 characters or fewer.",
        "reset_done":           "✅ Bot nickname has been reset in this server.",
        "set_done":             "✅ Bot nickname set to **{name}** in this server.",
        "no_perm_nick":         "❌ I don't have permission to change my own nickname in this server.",
    },
    "say": {
        "no_permission":        "You do not have permission to use this command.",
        "maintenance":          "🛠️ Bot is under maintenance.",
        "no_webhook":           "Discord bots does not support replying with webhook.",
        "no_webhook_perm":      "Bot doesn't have permission called: Manage Webhooks.",
        "sent_webhook":         "✅ Message sent via webhook as {user}!",
        "sent_channel":         "✅ Message successfully sent to {channel}!",
        "sent_reply":           "✅ Successfully replied to message `{msg_id}` in {channel}!",
        "no_msg_perm":          "❌ I don't have permission to send messages in that channel.",
    },
    "ping": {
        "debug_sent":           "✅ Debug test message sent to debug channel. Label: {tag}",
    },
    "help_cmd": {
        "maintenance":          "🛠️ **Bot is under maintenance.**",
    },
    "whato": {
        "no_permission":        "You do not have permission to use this command.",
        "disabled":             "❌ Wordle commands are currently disabled in this server.",
        "enabled":              "✅ Wordle commands have been enabled in this server.",
    },
    "leaveserver": {
        "no_permission":        "You do not have permission to use this command.",
        "not_your_list":        "❌ Not your list.",
        "not_your_confirm":     "❌ This confirmation is not for you.",
        "no_history":           "📋 No leave history found.",
        "invalid_id":           "❌ Invalid server ID. Use a number or `all`.",
        "fire":                 "🗣️🔥",
        "not_in_server":        "❌ I am not in a server with that ID.",
        "left_all":             "✅ Successfully left **{count}** servers.",
        "left_one":             "✅ Successfully left **{name}** (`{id}`)",
        "leave_failed":         "❌ Failed to leave server: {error}",
    },
    "secrettesting": {
        "no_permission":        "You do not have permission to use this command.",
        "maintenance":          "🛠️ Bot is under maintenance.",
        "stopped":              "🛑 Stopped.",
        "confirm_only":         "Only the command user can confirm.",
        "respond_only":         "Only the command user can respond.",
    },
    "values": {
        "no_permission":        "You do not have permission to use this command.",
        "owner_only":           "❌ Only the bot owner can use this command.",
        "dm_failed":            "❌ I could not DM you. Please enable DMs from this server.",
        "export_failed":        "❌ The JSON export failed.",
        "export_sent":          "✅ Sent `{count}` JSON file(s) to your DMs.",
        "import_failed":        "❌ Import failed. Upload a valid ZIP containing valid JSON files.",
        "import_empty":         "❌ The ZIP did not contain any JSON files.",
        "import_write_failed":  "❌ The JSON files could not be written to the project.",
        "import_done":          "✅ Imported `{count}` JSON file(s) into the project.",
        "not_zip":              "❌ Upload a `.zip` file containing JSON files.",
    },
}


def get_all_overrides() -> dict:
    try:
        stats = load_stats()
        return stats.get(MONGO_KEY, {})
    except Exception:
        return {}


def get_response(file: str, key: str, **kwargs) -> str:
    """Returns edited text from MongoDB, falls back to default. Never returns empty."""
    try:
        overrides = get_all_overrides()
        text = overrides.get(file, {}).get(key) or DEFAULTS.get(file, {}).get(key)
        if not text:
            return f"[{file}.{key}]"
        return text.format(**kwargs) if kwargs else text
    except (KeyError, ValueError):
        return DEFAULTS.get(file, {}).get(key, f"[{file}.{key}]")


def set_override(file: str, key: str, text: str):
    stats = load_stats()
    if MONGO_KEY not in stats or not isinstance(stats[MONGO_KEY], dict):
        stats[MONGO_KEY] = {}
    if file not in stats[MONGO_KEY]:
        stats[MONGO_KEY][file] = {}
    stats[MONGO_KEY][file][key] = text
    save_stats(stats)


def delete_override(file: str, key: str) -> bool:
    stats = load_stats()
    overrides = stats.get(MONGO_KEY, {})
    if file not in overrides or key not in overrides.get(file, {}):
        return False
    del overrides[file][key]
    stats[MONGO_KEY] = overrides
    save_stats(stats)
    return True


def reset_file_overrides(file: str):
    stats = load_stats()
    overrides = stats.get(MONGO_KEY, {})
    if file in overrides:
        del overrides[file]
    stats[MONGO_KEY] = overrides
    save_stats(stats)


class EditRespondCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _check(self, ctx) -> bool:
        return ctx.author.id == CREATOR_ID

    @commands.group(name="editrespond", invoke_without_command=True)
    async def editrespond(self, ctx, file: str = None, key: str = None):
        if not self._check(ctx):
            return

        # .editrespond wordle win → show current value of that specific key
        if file and key:
            file = file.lower()
            key = key.lower()
            if file not in DEFAULTS:
                return await ctx.send(f"❌ Unknown file `{file}`. Use `.editrespond list` to see all.")
            if key not in DEFAULTS[file]:
                keys = ", ".join(f"`{k}`" for k in DEFAULTS[file])
                return await ctx.send(f"❌ Unknown key `{key}` for `{file}`.\nAvailable: {keys}")
            overrides = get_all_overrides().get(file, {})
            current = overrides.get(key, DEFAULTS[file][key])
            is_edited = key in overrides
            status = "✏️ **Edited**" if is_edited else "📄 **Default**"
            embed = discord.Embed(
                title=f"`{file}` → `{key}`",
                description=f"{status}\n\n**Current text:**\n{current}",
                color=0x00ff00 if is_edited else 0x2f3136
            )
            if "{" in DEFAULTS[file][key]:
                placeholders = [p.split("}")[0] for p in DEFAULTS[file][key].split("{")[1:]]
                embed.set_footer(text=f"Placeholders: {{{', '.join(placeholders)}}}")
            embed.add_field(name="To edit:", value=f"`.editrespond edit {file} {key} <new text>`", inline=False)
            return await ctx.send(embed=embed)

        # .editrespond wordle → show all keys for that file
        if file:
            file = file.lower()
            if file not in DEFAULTS:
                return await ctx.send(f"❌ Unknown file `{file}`. Use `.editrespond list` to see all files.")
            overrides = get_all_overrides().get(file, {})
            defaults = DEFAULTS[file]
            lines = []
            for k, default_text in defaults.items():
                current = overrides.get(k, default_text)
                marker = "✏️" if k in overrides else "📄"
                short = current[:80] + ("..." if len(current) > 80 else "")
                lines.append(f"{marker} **`{k}`** → {short}")
            chunks, cur = [], f"📋 **{file}** (✏️=edited, 📄=default):\n\n"
            for line in lines:
                if len(cur) + len(line) + 2 > 1900:
                    chunks.append(cur)
                    cur = ""
                cur += line + "\n"
            if cur:
                chunks.append(cur)
            for chunk in chunks:
                await ctx.send(chunk)
            return

        # .editrespond → show usage
        files_list = ", ".join(f"`{k}`" for k in DEFAULTS)
        await ctx.send(
            f"**Usage:**\n"
            f"`.editrespond list` — Show all files and their response keys\n"
            f"`.editrespond <file>` — Show all responses for that file\n"
            f"`.editrespond <file> <key>` — Show current value of one response\n"
            f"`.editrespond edit <file> <key> <new text>` — Edit a response\n"
            f"`.editrespond reset <file> <key>` — Reset one to default\n"
            f"`.editrespond resetall <file>` — Reset all overrides for a file\n\n"
            f"**Files:** {files_list}"
        )

    @editrespond.command(name="list")
    async def editrespond_list(self, ctx):
        if not self._check(ctx):
            return

        overrides = get_all_overrides()
        lines = []
        for file, keys in DEFAULTS.items():
            edited = sum(1 for k in keys if k in overrides.get(file, {}))
            total = len(keys)
            marker = "✏️" if edited else "📄"
            lines.append(f"{marker} **`{file}`** — {total} responses ({edited} edited)")

        embed = discord.Embed(
            title="📋 EditRespond — All Files",
            description="\n".join(lines),
            color=0x2f3136
        )
        embed.set_footer(text="Use .editrespond <file> to see all responses in a file")
        await ctx.send(embed=embed)

    @editrespond.command(name="edit")
    async def editrespond_edit(self, ctx, file: str = None, key: str = None, *, new_text: str = None):
        if not self._check(ctx):
            return

        if not file or not key or not new_text:
            return await ctx.send("❌ Usage: `.editrespond edit <file> <key> <new text>`")

        file, key = file.lower(), key.lower()
        if file not in DEFAULTS:
            return await ctx.send(f"❌ Unknown file `{file}`. Use `.editrespond list`.")
        if key not in DEFAULTS[file]:
            keys = ", ".join(f"`{k}`" for k in DEFAULTS[file])
            return await ctx.send(f"❌ Unknown key `{key}` for `{file}`.\nAvailable: {keys}")

        old_text = get_all_overrides().get(file, {}).get(key, DEFAULTS[file][key])
        set_override(file, key, new_text)

        embed = discord.Embed(title=f"✅ Updated `{file}` → `{key}`", color=0x00ff00)
        embed.add_field(name="Before", value=old_text[:1024], inline=False)
        embed.add_field(name="After", value=new_text[:1024], inline=False)
        placeholders = [p.split("}")[0] for p in DEFAULTS[file][key].split("{")[1:]]
        if placeholders:
            embed.set_footer(text=f"Placeholders available: {{{', '.join(placeholders)}}}")
        await ctx.send(embed=embed)

    @editrespond.command(name="reset")
    async def editrespond_reset(self, ctx, file: str = None, key: str = None):
        if not self._check(ctx):
            return
        if not file or not key:
            return await ctx.send("❌ Usage: `.editrespond reset <file> <key>`")
        file, key = file.lower(), key.lower()
        if file not in DEFAULTS:
            return await ctx.send(f"❌ Unknown file `{file}`.")
        ok = delete_override(file, key)
        if not ok:
            return await ctx.send(f"ℹ️ `{key}` in `{file}` was already at default.")
        await ctx.send(f"✅ Reset `{key}` in `{file}` to default:\n> {DEFAULTS[file].get(key, '')}")

    @editrespond.command(name="resetall")
    async def editrespond_resetall(self, ctx, file: str = None):
        if not self._check(ctx):
            return
        if not file:
            return await ctx.send("❌ Usage: `.editrespond resetall <file>`")
        file = file.lower()
        if file not in DEFAULTS:
            return await ctx.send(f"❌ Unknown file `{file}`.")
        reset_file_overrides(file)
        await ctx.send(f"✅ All overrides for `{file}` reset to defaults.")


async def setup(bot):
    await bot.add_cog(EditRespondCog(bot))
