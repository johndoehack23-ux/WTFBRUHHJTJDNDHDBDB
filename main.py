import os
import discord
import asyncio
from discord.ext import commands
from discord.ext import tasks
from functions import *

from flask import Flask
from threading import Thread
import time
import requests
import logging
import json
import pytz
from datetime import datetime as dt_class # Alias it here

def get_bot_time():
    """Gets the current datetime adjusted to the user's stats.json timezone."""
    try:
        with open("stats.json", "r") as f:
            tz_name = json.load(f).get("timezone", "America/Los_Angeles")
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("America/Los_Angeles")
    return dt_class.now(tz)

def get_local_now():
    try:
        with open("stats.json", "r") as f:
            tz_name = json.load(f).get("timezone", "America/Los_Angeles")
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
            with open("stats.json", "r") as f:
                tz_name = json.load(f).get("timezone", "America/Los_Angeles")
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

STATS_FILE = "stats.json"

def get_prefix(bot, message):
    try:
        with open(STATS_FILE, "r") as f:
            data = json.load(f)
        if message.guild:
            server_prefix = data.get("server_prefixes", {}).get(str(message.guild.id))
            if server_prefix:
                return server_prefix
        return data.get("prefix", ".")
    except Exception:
        return "."

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

server_config = load_json(CONFIG_FILE, dict)
if "invited_users" not in server_config:
    server_config["invited_users"] = []

@bot.event
async def on_guild_join(guild: discord.Guild):
    # Always read fresh from disk — in-memory cache may be stale
    try:
        with open(STATS_FILE, "r") as f:
            fresh_config = json.load(f)
    except Exception:
        fresh_config = {}
    allowed = fresh_config.get("allowed_servers", [])
    if str(guild.id) not in allowed:
        print(f"⛔ Rejected unauthorized server: {guild.name} ({guild.id}). Forcing leave.")
        try:
            await guild.leave()
            print(f"✅ Successfully left: {guild.name} ({guild.id})")
        except Exception as e:
            print(f"❌ Failed to leave {guild.name} ({guild.id}): {e}")

@bot.event
async def on_ready():
    global MAINTENANCE_MODE
    m_data = load_json(MAINTENANCE_FILE, dict)
    MAINTENANCE_MODE = m_data.get("enabled", False)
    print(f"✅ Logged in as {bot.user}")

    # Print stats.json guide so you know what to put in stats.json
    try:
        with open("stats.json", "r") as f:
            stats = json.load(f)
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

    # Sweep all servers — always read fresh from stats.json
    try:
        with open(STATS_FILE, "r") as f:
            fresh_config = json.load(f)
    except Exception:
        fresh_config = {}
    allowed = fresh_config.get("allowed_servers", [])
    for guild in list(bot.guilds):
        if str(guild.id) not in allowed:
            print(f"⛔ Startup sweep — unauthorized: {guild.name} ({guild.id}). Forcing leave.")
            try:
                await guild.leave()
                print(f"✅ Successfully left: {guild.name} ({guild.id})")
            except Exception as e:
                print(f"❌ Failed to leave {guild.name} ({guild.id}): {e}")

    start_keep_alive()


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

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Reply with prefix when bot is mentioned alone
    import re
    if re.fullmatch(r'<@!?' + str(bot.user.id) + r'>', message.content.strip()):
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
            
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

    if is_maintenance_mode() and not is_admin(message.author.id):
        return

    if not is_server_blacklisted(message.guild.id):
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
                        await message.channel.send(f"{feedback}\n**{winner['name']}** guessed it first! (+5 points)")

                        if winner["wins"] >= 2:
                            await message.channel.send(f"## 🎉 **MATCH OVER!**\n**{winner['name']}** wins the 1v1 match against **{loser['name']}**!")
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
                        await message.channel.send(f"## {feedback}\n<@{message.author.id}> guessed the correct word!")
                    else:
                        await message.channel.send(f"## {feedback}\n<@{message.author.id}> guessed the correct practice word!")
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

            if not check_cooldown(str(message.guild.id), trigger):
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
                if data.get("response"):
                    await message.channel.send(data["response"])
                if data.get("react"):
                    for emoji in data["react"]:
                        try:
                            await message.add_reaction(emoji)
                        except:
                            pass
                break

    await bot.process_commands(message)

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)
