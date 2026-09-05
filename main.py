import os
import discord
import asyncio
from discord.ext import commands
from discord.ext import tasks
from functions import *
from editrespond import get_response, r

from flask import Flask
from threading import Thread
import time
import requests
import logging
import pytz
from datetime import datetime as dt_class # Alias it here

def get_bot_time():
    """Gets the current datetime adjusted to the configured timezone (MongoDB)."""
    try:
        tz_name = load_stats().get("timezone", "America/Los_Angeles")
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("America/Los_Angeles")
    return dt_class.now(tz)

def get_local_now():
    try:
        tz_name = load_stats().get("timezone", "America/Los_Angeles")
        btz = pytz.timezone(tz_name)
    except Exception:
        btz = pytz.timezone("America/Los_Angeles")
    
    # Use the alias
    return dt_class.now(btz)

# ===================== KEEP-ALIVE + HOST PONG =====================
_keep_alive_started = False
app = Flask('')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def home():
    return "Self-pinging engine operational."

HOST_CHANNEL_ID = 1506947901178253424
STATUS_CHANNEL_ID = 1545349899850227794  # statusID — online/offline status message channel
_cached_status_message_id = None  # in-memory copy so shutdown doesn't need MongoDB

async def send_to_host_channel(message: str):
    """Safely send message to host channel"""
    try:
        channel = bot.get_channel(HOST_CHANNEL_ID)
        if not channel:
            print(f"⚠️ Host channel {HOST_CHANNEL_ID} not found")
            return
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(message)
            print(f"📨 Host: {message}")
        else:
            print(f"⚠️ Host channel is not text-based ({type(channel).__name__})")
    except Exception as e:
        print(f"❌ Failed to send to host channel: {e}")


async def update_status_message(text: str, allow_send_new: bool = True):
    """
    Edit the saved status message in STATUS_CHANNEL_ID, or send a new one
    if no message_id is saved / the old message is gone. Persists message_id
    in MongoDB stats so restarts can keep editing the same message.

    allow_send_new=False is used on shutdown so we only edit (never create
    a new message while the process is dying).
    """
    try:
        channel = bot.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(STATUS_CHANNEL_ID)
            except Exception as e:
                print(f"⚠️ Status channel {STATUS_CHANNEL_ID} not found: {e}")
                return

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            print(f"⚠️ Status channel is not text-based ({type(channel).__name__})")
            return

        global _cached_status_message_id

        # Prefer in-memory cache (works during shutdown even if Mongo is slow/unreachable)
        msg_id = _cached_status_message_id
        if not msg_id:
            try:
                stats = load_stats()
                msg_id = stats.get("status_message_id")
                if msg_id:
                    _cached_status_message_id = str(msg_id)
            except Exception as e:
                print(f"⚠️ load_stats for status_message_id failed: {e}")

        # Try to edit existing message first (partial message = no extra fetch, faster on shutdown)
        if msg_id:
            try:
                partial = channel.get_partial_message(int(msg_id))
                await partial.edit(content=text)
                print(f"✅ Status message edited → {text}")
                return
            except (discord.NotFound, discord.HTTPException, ValueError) as e:
                print(f"⚠️ Could not edit old status message ({msg_id}): {e}")
                if not allow_send_new:
                    return
                print("   → sending a new status message instead")

        if not allow_send_new:
            print("⚠️ No valid status_message_id and allow_send_new=False — skipping")
            return

        # No valid message_id → send a new status message and save its ID
        new_msg = await channel.send(text)
        _cached_status_message_id = str(new_msg.id)
        try:
            stats = load_stats()
            stats["status_message_id"] = str(new_msg.id)
            save_stats(stats)
        except Exception as e:
            print(f"⚠️ Could not persist status_message_id to Mongo: {e}")
        print(f"✅ New status message sent (id={new_msg.id}) → {text}")
    except Exception as e:
        print(f"❌ Failed to update status message: {e}")

def start_keep_alive():
    """Starts Flask webserver and initiates the background loop."""
    global _keep_alive_started
    if _keep_alive_started:
        return
    _keep_alive_started = True

    def run_server():
        app.run(host='0.0.0.0', port=5000, use_reloader=False)

    def get_now_str():
        try:
            tz_name = load_stats().get("timezone", "America/Los_Angeles")
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.timezone("America/Los_Angeles")
        return dt_class.now(tz).strftime("%-I:%M %p")

    async def ping_loop():
        await bot.wait_until_ready()
        await asyncio.sleep(10)
        
        while not bot.is_closed():
            # A global try-except ensures the loop NEVER dies, no matter what goes wrong
            try:
                now = get_now_str()
                
                # 1. Local HTTP Ping (with strict connect & read timeout)
                try:
                    # (5, 5) means 5 seconds to connect, 5 seconds to get data. Absolute max 10s.
                    await bot.loop.run_in_executor(
                        None, lambda: requests.get("http://127.0.0.1:5000/", timeout=(5, 5))
                    )
                    print(f"🟢 Self-ping OK | {now}")
                except Exception as e:
                    print(f"⚠️ Self-ping missed or timed out: {e}")

                # 2. Discord Channel Ping
                try:
                    await send_to_host_channel("Pong!")
                except Exception as e:
                    print(f"❌ Failed to send Pong to Discord: {e}")

            except Exception as global_error:
                print(f"🚨 Critical loop error caught (Loop preserved): {global_error}")

            # 3. Sleep is outside the internal try/except so it always delays safely
            await asyncio.sleep(252)

    # Start Flask server thread
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Schedule the asynchronous loop onto the bot's existing event loop
    bot.loop.create_task(ping_loop())
    print("✅ Keep-alive + Host Pong task initialized (Interval: 390s)")

# ===================== BOT SETUP =====================
TOKEN = os.getenv("token")
MAINTENANCE_MODE = False


def get_prefix(bot, message):
    try:
        data = load_stats()
        if message.guild:
            server_prefix = data.get("server_prefixes", {}).get(str(message.guild.id))
            if server_prefix:
                return server_prefix
        return data.get("prefix", ".")
    except Exception:
        return "."
        
import certifi
from pymongo import MongoClient

# Initialize Discord Bot instance
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

# Initialize MongoDB Connection
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000
)
bot.db = client["WordleBotDB"]  # Attached to Discord bot instance

server_config = load_json(CONFIG_FILE, dict)
if "invited_users" not in server_config:
    server_config["invited_users"] = []

# These server IDs will NEVER be left, no matter what allowed_servers contains
PROTECTED_SERVERS = {"1503365316065890364"}

@bot.event
async def on_guild_join(guild: discord.Guild):
    if str(guild.id) in PROTECTED_SERVERS:
        return

    # Give any pending .addinvite writes plenty of time to land, and keep
    # re-checking MongoDB until we either find this server on the whitelist
    # or genuinely run out of chances. We do NOT stop early just because the
    # list has *some* servers in it — a fresh add can still be a beat behind.
    allowed = []
    for attempt in range(6):
        await asyncio.sleep(5 if attempt == 0 else 3)
        fresh_config = load_stats()
        allowed = [str(x) for x in fresh_config.get("allowed_servers", []) if str(x).isdigit()]
        if str(guild.id) in allowed:
            print(f"✅ Joined whitelisted server: {guild.name} ({guild.id})")
            return

    if not allowed:
        print(f"⚠️  on_guild_join: allowed_servers empty after retries, skipping leave for {guild.name} ({guild.id})")
        return

    if str(guild.id) not in allowed:
        print(f"⛔ Rejected unauthorized server: {guild.name} ({guild.id}). Forcing leave.")
        try:
            await guild.leave()
            print(f"✅ Successfully left: {guild.name} ({guild.id})")
        except Exception as e:
            print(f"❌ Failed to leave {guild.name} ({guild.id}): {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    # Print stats guide so you know what to configure
    try:
        stats = load_stats()
        current_tz = stats.get("timezone", "America/Los_Angeles")
        current_prefix = stats.get("prefix")
    except Exception:
        current_tz = "America/Los_Angeles"
    print("━" * 48)
    print("  📋 STATS.JSON GUIDE — edit to configure bot")
    print(f"  Prefix:   \"{current_prefix}\"  (use .prefix set <x> to change)")
    print(f"  Timezone: \"{current_tz}\"")
    print("━" * 48)
    print("  PST / PDT  →  America/Los_Angeles  (default)")
    print("  EST / EDT  →  America/New_York")
    print("  CST / CDT  →  America/Chicago")
    print("  MST / MDT  →  America/Denver")
    print("  AKST       →  America/Anchorage")
    print("  HST        →  Pacific/Honolulu")
    print("  GMT / UTC  →  UTC")
    print("  BST        →  Europe/London")
    print("  CET        →  Europe/Paris")
    print("  JST        →  Asia/Tokyo")
    print("  SGT        →  Asia/Singapore")
    print("  PHT        →  Asia/Manila")
    print("  IST        →  Asia/Kolkata")
    print("  AEST       →  Australia/Sydney")
    print("━" * 48)

    # Sweep all servers — always read fresh from MongoDB
    fresh_config = load_stats()
    allowed = [str(x) for x in fresh_config.get("allowed_servers", []) if str(x).isdigit()]

    if not allowed:
        print("⚠️  allowed_servers list is empty — skipping startup sweep to avoid leaving all servers.")
    else:
        for guild in list(bot.guilds):
            if str(guild.id) in PROTECTED_SERVERS:
                continue
            if str(guild.id) not in allowed:
                print(f"⛔ Startup sweep — unauthorized: {guild.name} ({guild.id}). Forcing leave.")
                try:
                    await guild.leave()
                    print(f"✅ Successfully left: {guild.name} ({guild.id})")
                except Exception as e:
                    print(f"❌ Failed to leave {guild.name} ({guild.id}): {e}")

    start_keep_alive()

    # Register SIGTERM/SIGINT so Railway stop sets Status: 🔴 before exit
    _register_shutdown_handlers()

    # Online status message in the dedicated status channel
    await update_status_message("Status: 🟢")


@bot.event
async def setup_hook():
    target_folder = "cogs" if os.path.exists("cogs") else "Cog"

    # Auto-discover all .py files in the cogs folder (no hardcoded list needed)
    cog_files = sorted(
        f for f in os.listdir(target_folder)
        if f.endswith(".py") and not f.startswith("_")
    )
    cogs = [f"{target_folder}.{f[:-3]}" for f in cog_files]

    for cog in cogs:
        try:
            await bot.load_extension(cog)
        except Exception as e:
            print(f"❌ Failed to load extension {cog}: {e}")

    await bot.tree.sync()
    print("🚀 Bot application commands synced successfully!")

@bot.tree.error
async def on_tree_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ This server is blacklisted from using the bot.\nContact the bot owner for details.",
                ephemeral=True
            )
        return
    raise error

async def global_slash_blacklist_check(interaction: discord.Interaction):
    if interaction.guild_id and is_server_blacklisted(interaction.guild_id):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ This server is blacklisted from using the bot.\nContact the bot owner for details.",
                ephemeral=True
            )
        return False
    return True

bot.tree.interaction_check = global_slash_blacklist_check

@bot.check
async def global_prefix_blacklist_check(ctx: commands.Context):
    if ctx.guild and is_server_blacklisted(ctx.guild.id):
        await ctx.send("❌ This server is blacklisted from using the bot.\nContact the bot owner for details.")
        return False
    return True

# Whato exempt commands — always allowed even when whato is toggled off
_WHATO_EXEMPT = {"wordle", "ping", "stats", "whato", "help", "debugtest", "leaderboard", "lb"}

@bot.check
async def global_whato_check(ctx: commands.Context):
    if ctx.guild is None:
        return True
    if ctx.command is None:
        return True
    if ctx.command.name in _WHATO_EXEMPT:
        return True
    if is_whato_disabled(str(ctx.guild.id)):
        # silently block — no error message so it doesn't spam
        return False
    return True

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Reply with prefix when bot is mentioned alone
    import re
    if re.fullmatch(r'<@!?' + str(bot.user.id) + r'>', message.content.strip()):
        try:
            data = load_stats()

            # Default to global prefix
            prefix = data.get("prefix", ".")
            globalprefix = prefix

            # Check if there is a custom prefix configured for this specific server
            if message.guild:
                server_prefix = data.get("server_prefixes", {}).get(str(message.guild.id))
                if server_prefix:
                    prefix = server_prefix
        except Exception:
            prefix = "."
            
        await message.channel.send(f"My prefix is: `{prefix}`\nGlobal prefix: `{globalprefix}`")
        return

    # Maintenance mode should only suppress the raw-text game logic below
    # (guess detection, 1v1 guesses, autoresponder) — it must NOT swallow
    # the message before it reaches bot.process_commands(), otherwise a
    # command's own maintenance check (e.g. .wordle's) never gets a chance
    # to reply.
    maintenance_block = is_maintenance_mode() and not is_admin(message.author.id)

    if not maintenance_block and not is_server_blacklisted(message.guild.id):
        channel_id = message.channel.id
        content = message.content.strip().lower()

        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            if not match.get("guessed") and len(content) == match["length"] and content.isalpha() and not content.startswith("."):
                if message.author.id == match["p1"]["id"] or message.author.id == match["p2"]["id"]:
                    secret = match["secret"]
                    feedback = get_feedback(content, secret)

                    if content == secret:
                        match["guessed"] = True
                        if message.author.id == match["p1"]["id"]:
                            winner = match["p1"]
                            loser = match["p2"]
                        else:
                            winner = match["p2"]
                            loser = match["p1"]

                        winner["score"] += 5
                        winner["wins"] += 1
                        await message.channel.send(r("win", "1v1_round", feedback=feedback, winner_name=winner['name']))

                        if winner["wins"] >= 2:
                            await message.channel.send(r("win", "1v1_match", winner_name=winner['name'], loser_name=loser['name']))
                            if channel_id in active_1v1_matches:
                                del active_1v1_matches[channel_id]
                        else:
                            await asyncio.sleep(2.5)
                            cog = bot.get_cog("ModeCog")
                            if cog:
                                await cog.start_1v1_round(message.channel, channel_id)
                    else:
                        await message.channel.send(feedback)
                    return

        possible_game_keys = [f"{channel_id}_practice_{message.author.id}", channel_id]
        for game_key in possible_game_keys:
            if game_key not in active_games:
                # Also check if this channel is a guess_channel_id for any active game
                found_key = None
                for k, g in active_games.items():
                    if isinstance(g, dict) and (
                        g.get("guess_channel_id") == channel_id or
                        g.get("guild_id") == (message.guild.id if message.guild else None)
                    ) and (
                        (isinstance(k, str) and k.startswith(f"{channel_id}_practice_")) or
                        k == channel_id
                    ):
                        found_key = k
                        break
                if found_key:
                    game_key = found_key
                else:
                    continue

            game = active_games[game_key]
            if game.get("processing_win"):
                continue

            if len(content) == game["length"] and content.isalpha() and not content.startswith("."):
                is_practice = game.get("practice", False)
                if is_practice and game.get("author_id") and message.author.id != game["author_id"]:
                    continue

                secret = game["secret"]
                feedback = get_feedback(content, secret)

                if is_practice:
                    feedback = f"Practice:\n## {feedback}"

                if content == secret:
                    game["processing_win"] = True

                    # Delete debug channel secret message on solve
                    debug_msg_id = game.get("debug_msg_id")
                    debug_ch_id = game.get("debug_msg_channel_id")
                    if debug_msg_id and debug_ch_id:
                        try:
                            debug_ch = bot.get_channel(debug_ch_id)
                            if debug_ch:
                                dm = await debug_ch.fetch_message(debug_msg_id)
                                await dm.delete()
                        except Exception:
                            pass

                    del active_games[game_key]

                    if not is_practice:
                        record_win(message.guild, message.author.id, message.author.name)
                        await message.channel.send(r("win", "correct", feedback=feedback, user_id=message.author.id))
                    else:
                        await message.channel.send(r("win", "correct_practice", feedback=feedback, user_id=message.author.id))
                else:
                    if "revealed_indices" not in game:
                        game["revealed_indices"] = []
                    for i in range(len(content)):
                        if content[i] == secret[i] and i not in game["revealed_indices"]:
                            game["revealed_indices"].append(i)
                    await message.channel.send(feedback)
                return

        content_lower = message.content.lower().strip()
        auto_responses = load_auto_responses()

        for key, data in auto_responses.items():
            trigger = data.get("trigger", "").lower()
            if not trigger:
                continue

            is_global = data.get("global", False)
            if not is_global and str(message.guild.id) != str(data.get("guild_id", message.guild.id)):
                continue

            target_channel = data.get("channel")
            if target_channel and str(message.channel.id) != target_channel:
                continue

            matchmode = data.get("matchmode", "contains")
            match = False

            if matchmode == "exact":
                match = content_lower == trigger
            elif matchmode == "startswith":
                match = content_lower.startswith(trigger)
            elif matchmode == "endswith":
                match = content_lower.endswith(trigger)
            else:
                match = trigger in content_lower

            if match:
                if not check_cooldown(str(message.guild.id), trigger):
                    continue
                if data.get("response"):
                    await message.channel.send(data["response"])
                if data.get("react"):
                    reactions = data["react"] if isinstance(data["react"], list) else [data["react"]]
                    for emoji in reactions:
                        try:
                            if not is_reaction_allowed(
                                emoji,
                                message.guild,
                                is_global=bool(data.get("global")),
                            ):
                                continue
                            await message.add_reaction(emoji)
                        except:
                            pass
                break

    await bot.process_commands(message)

# ===================== GRACEFUL SHUTDOWN (Railway stop → Status: 🔴) =====================
import signal

_shutting_down = False
_original_bot_close = bot.close


async def _set_offline_status_once():
    """Edit status message to 🔴 exactly once (safe to call from multiple paths)."""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    print("🛑 Setting Status: 🔴 before exit...")
    try:
        await update_status_message("Status: 🔴", allow_send_new=False)
        print("✅ Offline status set to 🔴")
    except Exception as e:
        print(f"❌ Failed to set offline status: {e}")


async def close_with_offline_status(*args, **kwargs):
    """Wrap bot.close so every shutdown path sets Status: 🔴 first."""
    await _set_offline_status_once()
    await _original_bot_close(*args, **kwargs)


# Any call to bot.close() (discord.py's own SIGTERM handler, or ours) sets 🔴 first
bot.close = close_with_offline_status


async def set_status_offline_and_close():
    """Called from our signal handler: set 🔴 then close."""
    await close_with_offline_status()


def _register_shutdown_handlers():
    """
    Register SIGTERM/SIGINT on the running asyncio loop.
    Reliable on Linux/Railway — schedules the coroutine on the event loop
    instead of blocking inside a raw signal handler.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        print("⚠️ No running loop; cannot register asyncio signal handlers")
        return

    def _schedule_shutdown():
        if not _shutting_down:
            loop.create_task(set_status_offline_and_close())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            # Overwrite discord.py's default handlers so we run first
            loop.add_signal_handler(sig, _schedule_shutdown)
            print(f"✅ Registered shutdown handler for {sig.name}")
        except (NotImplementedError, RuntimeError) as e:
            print(f"⚠️ add_signal_handler failed for {sig.name}: {e} — using signal.signal fallback")
            signal.signal(sig, lambda s, f: _schedule_shutdown())


# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)
