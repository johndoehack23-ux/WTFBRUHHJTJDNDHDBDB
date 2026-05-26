import os
import discord
from discord.ext import commands
from functions import *

TOKEN = os.getenv("token")
bot_ready = False
MAINTENANCE_MODE = False

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

@bot.event
async def on_ready():
    global bot_ready, MAINTENANCE_MODE
    # Load maintenance state on startup
    m_data = load_json(MAINTENANCE_FILE, dict)
    MAINTENANCE_MODE = m_data.get("enabled", False)
    
    bot_ready = True
    print(f"Logged in as {bot.user}")

@bot.event
async def setup_hook():
    # This connects your commands.py file and syncs Slash commands
    await bot.load_extension("commands")
    await bot.tree.sync()

@bot.event
async def on_message(message):
    if message.author.bot or not bot_ready:
        return

    channel_id = message.channel.id
    content = message.content.strip().lower()

    # List of your actual command names (without the dot)
    valid_commands = {
        "wordle", "mode", "category", "hint", "reveal", 
        "endgame", "rlb", "leaderboard", "lb", "test", 
        "maintenance", "help", "adminhelp", "wordlelimit", 
        "wlimit", "limit", "resetalllimits", "rlimitall",
        "lb-best", "leaderboard-best", "lb-current", 
        "leaderboard-current", "resetwordlelimit", "resetlimit", "rlimit",
        "shutdown"
    }

    # Extract command word if a dot is used
    first_word = content[1:].split()[0] if content.startswith(".") and len(content) > 1 else ""
    is_prefix_cmd = first_word in valid_commands

    # ===================== SHUTDOWN CHECK =====================
    if is_shutdown_mode():
        if is_prefix_cmd:
            await message.channel.send("🚨 This bot is officially shutdown and cannot be used anymore 🚨\nPlease contact owner of this bot to turn it off")
        return  # Stops game handling and normal commands safely

    # Maintenance check
    if MAINTENANCE_MODE and not is_admin(message.author.id):
        return

    # ===================== SERVER BLACKLIST INTERCEPTION =====================
    if message.guild and is_server_blacklisted(message.guild.id):
        is_potential_guess = (channel_id in active_1v1_matches or channel_id in active_games) and content.isalpha()
        if is_prefix_cmd or is_potential_guess:
            await message.channel.send("❌ This server is blacklisted from using the bot.\nContact the bot owner for details.")
        return

    # ===================== 1V1 MATCH LOGIC =====================
    if channel_id in active_1v1_matches:
        match = active_1v1_matches[channel_id]
        if match.get("guessed"):
            return

        if len(content) == match["length"] and content.isalpha() and not content.startswith("."):
            if message.author.id != match["p1"]["id"] and message.author.id != match["p2"]["id"]:
                return

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
                    cog = bot.get_cog("BotCommands")
                    if cog:
                        await cog.start_1v1_round(message.channel, channel_id)
            else:
                await message.channel.send(feedback)
            return

    # ===================== NORMAL WORDLE LOGIC =====================
    if channel_id in active_games:
        game = active_games[channel_id]
        
        if game.get("processing_win"):
            return

        if len(content) == game["length"] and content.isalpha() and not content.startswith("."):
            secret = game["secret"]
            feedback = get_feedback(content, secret)

            if content == secret:
                game["processing_win"] = True
                del active_games[channel_id]
                
                record_win(message.guild, message.author.id, message.author.name)
                await message.channel.send(f"{feedback}\n<@{message.author.id}> guessed the correct word!")
            else:
                if "revealed_indices" not in game:
                    game["revealed_indices"] = []
                for i in range(len(content)):
                    if content[i] == secret[i] and i not in game["revealed_indices"]:
                        game["revealed_indices"].append(i)
                
                await message.channel.send(feedback)
            return

    # ===================== CUT IN PIECES: AUTO RESPONSES BLOCK =====================
    if not is_shutdown_mode():  # <-- EXTRA SAFETY LOCK: Auto-responses physically won't run if shutdown
        content_raw = message.content.lower()
        auto_responses = load_auto_responses()

        for key, data in auto_responses.items():
            trigger = data.get("trigger", "").lower()
            
            if trigger and trigger in content_raw:
                allowed_servers = data.get("servers", [])
                if allowed_servers and str(message.guild.id) not in allowed_servers:
                    continue

                if data.get("response"):
                    await message.channel.send(data["response"])

                if data.get("react"):
                    try:
                        await message.add_reaction(data["react"])
                    except:
                        pass
                break

    # Process prefix commands
    await bot.process_commands(message)