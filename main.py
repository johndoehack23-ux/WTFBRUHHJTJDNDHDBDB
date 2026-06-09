import os
import discord
import flask
from discord.ext import commands
from functions import *

# ===================== SELF-CONTAINED 24/7 BYPASS =====================
from flask import Flask
from threading import Thread
import time
import requests

app = Flask('')

@app.route('/')
def home():
    return "Self-pinging engine operational."

def run_server():
    # Keep the local web server alive on port 8080
    app.run(host='0.0.0.0', port=8080)

def ping_loop():
    print("Pong")
    while True:
        try: 
            requests.get("http://127.0.0.1:8080/")
            print("Pong")
        except Exception as e:
            print(f"⚠️ Self-ping missed: {e}")
        
        time.sleep(290)

print("Pong")
time.sleep(60)

def keep_alive():
    """Launches both the web server and the auto-pinger in separate execution threads"""
    server_thread = Thread(target=run_server)
    ping_thread = Thread(target=ping_loop)
    
    server_thread.daemon = True
    ping_thread.daemon = True
    
    server_thread.start()
    ping_thread.start()

# Fire up the self-contained hosting lock right before execution
keep_alive()

TOKEN = os.getenv("token")
bot_ready = False
MAINTENANCE_MODE = False

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# --- INITIALIZE INVITE LIST HERE ---
server_config = load_json(CONFIG_FILE, dict) if 'CONFIG_FILE' in globals() else {}
if "invited_users" not in server_config:
    server_config["invited_users"] = []

@bot.event
async def on_guild_join(guild: discord.Guild):
    # Initialize list if missing
    if "allowed_servers" not in server_config:
        server_config["allowed_servers"] = []

    # If it's not whitelisted, kick the bot out instantly and silently
    if str(guild.id) not in server_config["allowed_servers"]:
        print(f"⚠️ Bot joined unauthorized server: {guild.name} ({guild.id}). Leaving instantly.")
        await guild.leave()


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
                            cog = bot.get_cog("BotCommands")
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