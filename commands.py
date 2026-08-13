import discord
from discord.ext import commands
from discord import app_commands
import random
from functions import *

class BotCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ===================== 1V1 HELPER METHODS =====================
    async def start_1v1_round(self, channel, channel_id):
        match = active_1v1_matches[channel_id]
        match["current_round"] += 1
        match["guessed"] = False

        word, length = get_random_word_1v1(match["guild_id"], match.get("length"))
        match["secret"] = word
        match["length"] = length

        await channel.send(f"**Round {match['current_round']}/{match['max_rounds']}** | **Length:** {length}\n"
                          f"**{match['p1']['name']}** vs **{match['p2']['name']}** — Guess the word!")

    async def end_1v1_match(self, channel, channel_id):
        if channel_id in active_1v1_matches:
            del active_1v1_matches[channel_id]
    @commands.command(name="mode")
    async def mode_1v1(self, ctx, mode: str = None, length: int = None):
        # Server Blacklist Check
        if is_server_blacklisted(ctx.guild.id):
            return

        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if not mode:
            return await ctx.send("✅ Usage: `.mode 1v1` (Start) or `.mode end` (Force end game/lobby)")

        mode_action = mode.lower().strip()
        channel_id = ctx.channel.id

        # ===================== MODE END LOGIC =====================
        if mode_action == "end":
            # FIXED: Uses your existing admin check directly
            if not is_admin(ctx.author.id):
                return await ctx.send("You do not have permission to use this command.")

            ended_something = False
            
            if channel_id in active_1v1_lobbies:
                del active_1v1_lobbies[channel_id]
                await ctx.send("1v1 Wordle ended")
                ended_something = True
                
            if channel_id in active_1v1_matches:
                del active_1v1_matches[channel_id]
                await ctx.send("1v1 Wordle ended")
                ended_something = True
                
            if not ended_something:
                await ctx.send("❌ There is no active 1v1 lobby or match running in this channel.")
            return

        # Ensure valid mode entry
        if mode_action != "1v1": return await ctx.send("Usage: .mode 1v1 or .mode 1v1 <number>")

        if channel_id in active_games or channel_id in active_1v1_lobbies or channel_id in active_1v1_matches:
            return await ctx.send("❌ A game or lobby is already active in this channel!")

        embed = discord.Embed(
            title="🔥 Wordle 1v1 Matchmaking",
            description="**React with 🔥 to join!**\nTwo random players from the reactions will be selected.\nBest of 3 rounds — first correct guess wins the round.",
            color=0xff0000
        )
        embed.add_field(name="Scoring", value="• +**5 points** per round win\n• First to 2 round wins takes the match", inline=False)

        lobby_msg = await ctx.send(embed=embed)
        await lobby_msg.add_reaction("🔥")

        active_1v1_lobbies[channel_id] = {
            "lobby_msg": lobby_msg,
            "length": length,
            "guild_id": ctx.guild.id
        }

        await ctx.send("⏳ **Matchmaking started!** Waiting 10 seconds...")

        # Wait 10 seconds then process reactions
        await asyncio.sleep(10)

        try:
            # Check if lobby wasn't deleted mid-wait by `.mode end`
            if channel_id not in active_1v1_lobbies:
                return
                
            lobby = active_1v1_lobbies.pop(channel_id, None)

            # Fetch fresh reactions
            fresh_msg = await ctx.channel.fetch_message(lobby_msg.id)
            reaction = discord.utils.get(fresh_msg.reactions, emoji="🔥")

            users = []
            if reaction:
                async for user in reaction.users():
                    if not user.bot:  # Ignore bot reaction
                        users.append(user)

            if len(users) < 2:
                await ctx.send("❌ Not enough players joined the 1v1 lobby (need 2).")
                return

            # Shuffle pool so active clickers don't hog matches 3 times in a row!
            random.shuffle(users)
            p1 = users[0]
            p2 = users[1]

            active_1v1_matches[channel_id] = {
                "p1": {"id": p1.id, "name": p1.name, "score": 0, "wins": 0},
                "p2": {"id": p2.id, "name": p2.name, "score": 0, "wins": 0},
                "current_round": 0,
                "max_rounds": 3,
                "length": lobby["length"],
                "guild_id": ctx.guild.id,
                "secret": None,
                "guessed": False
            }

            await ctx.send(f"## 🔥 **1v1 Match Started!**\n**{p1.mention}** vs **{p2.mention}**\nFirst to **2 round wins**!")
            await self.start_1v1_round(ctx.channel, channel_id)

        except Exception as e:
            await ctx.send("❌ Error starting match.")
            print(f"1v1 Error: {e}")

    # ===================== PREFIX WORDLE COMMAND =====================
    @commands.command(name="wordle")
    async def wordle_prefix(self, ctx, option: str = None):
        # Strict server block lookup
        if is_server_blacklisted(ctx.guild.id):
            return

        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        target_channel = ctx.channel
        target_id = target_channel.id

        if option:
            option_clean = option.lower().strip()
            
            # ROUTE 2: end Execution
            if option_clean == "end":
                if not is_admin(ctx.author.id, ctx.guild):
                    return await ctx.send("🔐 **Denied Access.**")
                
                ended = 0
                for k in list(active_games.keys()):
                    if isinstance(active_games[k], dict) and active_games[k].get("guild_id") == ctx.guild.id:
                        del active_games[k]
                        ended += 1
                if ended:
                    return await ctx.send(f"✅ Ended {ended} game(s) in this server.")
                else:
                    return await ctx.send("❌ No active game found in this server.")
            else:
                return await ctx.send("❌ Invalid option. Use: `.wordle` to start a game or `.wordle end` to stop running games.")

        # ROUTE 1: Normal Base Play Deployment
        else:
            if not is_admin(ctx.author.id, ctx.guild):
                if get_user_game_count(ctx.author.id) >= 3:
                    return await ctx.send("❌ You have reached the maximum limit of **3** Wordle games today.")

            gid = str(ctx.guild.id)
            configured_target = server_config.get(gid, {}).get("public")
            if configured_target:
                target_id = configured_target
                resolved_channel = ctx.bot.get_channel(target_id) or ctx.channel
            else:
                resolved_channel = target_channel

            if target_id in active_games:
                return await ctx.send("❌ A game is already running in that channel!")

            default_mode = server_config.get("default_modes", {}).get(gid)
            secret, _ = get_random_word(ctx.guild.id, default_mode)

            active_games[target_id] = {
                "secret": secret, 
                "length": len(secret), 
                "guild_id": ctx.guild.id,
                "revealed_indices": [], 
                "processing_win": False,
                "practice": False,
                "author_id": ctx.author.id
            }

            increment_user_game_count(ctx.author.id)
                
            return await resolved_channel.send(f"## New Wordle by <@{ctx.author.id}>\n**Length:** {len(secret)}")
    @commands.command(name="admin")#, aliases=["wlimit", "limit"])
    async def wordle_limit(self, ctx, user: discord.Member = None, action: str = None):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        if not user or not action:
            return await ctx.send("**Usage:** `.wlimit <@user> <infinite|reset>`\n"
                                "`infinite` = Toggle infinite plays\n"
                                "`reset` = Reset limit + remove infinite")

        action = action.lower().strip()

        if action == "infinite":
            new_state = toggle_infinite_wordle(user.id)
            status = "Infinite wordle enabled" if new_state else "Infinite wordle disabled*"
            await ctx.send(f"{status} for **{user.name}**.")
        
        elif action == "reset":
            if reset_user_wordle_limit(user.id):
                await ctx.send(f"Reseted {user.name} wordle uses (Includes removing infinite)")
            else:
                await ctx.send(f"{user.name} - no wordle limit to reset")
        else:
            await ctx.send("❌ Invalid action! Use `infinite` or `reset`.")

    # Optional: Global reset (kept for safety)
    @commands.command(name="adminall")#, aliases=["rlimitall"])
    async def reset_wordle_limit_all(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        data = load_wordle_limits()
        data["users"] = {}
        data["infinite"] = {} if "infinite" in data else {}
        data["last_reset"] = datetime.datetime.now().isoformat()
        save_wordle_limits(data)
        
        await ctx.send("✅ **ALL** Wordle limits have been reset globally.")

    # ===================== MAINTENANCE =====================
    def check_maintenance(self, ctx_or_itn):
        if not is_maintenance_mode():
            return False
        
        if isinstance(ctx_or_itn, discord.Interaction):
            user_id = ctx_or_itn.user.id
        else:
            user_id = ctx_or_itn.author.id
            
        return not is_admin(user_id)

    @commands.command(name="difficulty")
    async def difficulty(self, ctx, mode: str = "default"):
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.** Only admins can use commands.")

        mode = mode.lower().strip()
        valid = ["easy", "medium", "hard", "impossible", "default"]
        if mode not in valid:
            return await ctx.send("❌ Invalid mode!")

        if mode == "default":
            mode = random.choice(["medium", "hard"])

        gid = str(ctx.guild.id)
        if "default_modes" not in server_config:
            server_config["default_modes"] = {}
        server_config["default_modes"][gid] = mode
        save_json(CONFIG_FILE, server_config)

        await ctx.send(f"✅ Default mode set to **{mode.upper()}**")

    @commands.command(name="hint")
    async def hint(self, ctx):
        if not is_admin(ctx.author.id):
            return
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        g = next((v for v in active_games.values() if v["guild_id"] == ctx.guild.id), None)
        if not g:
            return await ctx.send("🔐 No game running.")

        avail = [i for i in range(g["length"]) if i not in g.get("revealed_indices", [])]
        if not avail:
            return await ctx.send("💎 No more hints.")

        idx = random.choice(avail)
        g.setdefault("revealed_indices", []).append(idx)
        await ctx.send(f"💡 Letter {idx+1} is **{g['secret'][idx].upper()}**")

    @commands.command(name="reveal")
    async def reveal(self, ctx):
        if not is_admin(ctx.author.id):
            return
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        channel_id = ctx.channel.id

        # Check 1v1 first
        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            await ctx.send(f"🔍 **1v1 Secret word:** **{match['secret'].upper() if match.get('secret') else 'Not started yet'}**")
            return

        # Normal Wordle
        g = next((v for v in active_games.values() if v["guild_id"] == ctx.guild.id), None)
        if g and g.get("secret"):
            await ctx.send(f"🔍 Secret word: **{g['secret'].upper()}**")
            return  # <-- FIXED: Added missing return here so it exits cleanly

        # If neither game type was found
        await ctx.send("❌ No active game or 1v1 match in this channel.")

        # ===================== PREFIX ENDGAME =====================
    @commands.command(name="eg")
    async def endgame(self, ctx, scope: str = "server"):
        if not is_admin(ctx.author.id):
            return

        scope = scope.lower()

        if scope == "global":
            count = len(active_games)
            active_games.clear()
            return await ctx.send(f"✅ **Global Endgame** - Ended {count} game(s) across all servers.")

        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == ctx.guild.id:
                    del active_games[k]
                    ended += 1
            return await ctx.send(f"✅ Ended {ended} game(s) in this server." if ended else "No active game found in this server.")

        else:
            await ctx.send("❌ Invalid option. Use: `endgame server` or `endgame global`")

    @commands.command(name="rlb")
    async def rlb(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access")

        leaderboard["servers"][str(ctx.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send("🧹 Leaderboard has been reset.")

    @commands.command(name="leaderboard", aliases=["lb"])
    async def lb(self, ctx):
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        srv = leaderboard["servers"].get(str(ctx.guild.id), {})
        if not srv:
            return await ctx.send("🏆 No stats yet!")

        sorted_lb = sorted(srv.items(), key=lambda x: x[1].get("best_streak", 0), reverse=True)[:10]

        embed = discord.Embed(title=f"🏆 Best Streaks - {ctx.guild.name}", color=0x2f3136)
        for i, (uid, d) in enumerate(sorted_lb, 1):
            embed.add_field(
                name=f"{i}. {d.get('username', 'Unknown')}",
                value=f"Best: **{d.get('best_streak', 0)}** | Current: **{d.get('current_streak', 0)}**",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="adminsecret1", aliases=["maintenance"])
    async def test(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access")

        new_state = toggle_maintenance()
        status = "🔐 **ENABLED**" if new_state else "🔓 **DISABLED**"
        blocked = "Non-admins are now blocked." if new_state else ""
        await ctx.send(f"**Maintenance Mode:** {status}\n\n{blocked}")

    @commands.command(name="help")
    async def help(self, ctx):
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.** Only admins can use commands.")

        embed = discord.Embed(title="Wordle Help", color=0x2f3136)
        embed.description = "wordle — Enter to play the wordle.\ndifficulty — Sets a difficulties (easy, medium, hard, impossible)\nleaderboard/lb — Shows a leaderboard people (1-10 only)\nmode 1v1 <length> — Starts a wordle 1v1 mode\nmode end — Ends the current 1v1 mode"
        await ctx.send(embed=embed)

    # lb-best and lb-current
    @commands.command(name="lb-best", aliases=["leaderboard-best"])
    async def lb_best(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You cant access this command. Please contact the bot owner to get access")

        srv = get_server_lb(ctx.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}
        
        old_best = srv[uid].get("best_streak", 0)
        srv[uid]["best_streak"] = num
        srv[uid]["username"] = user.name
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`")

    @commands.command(name="lb-current", aliases=["leaderboard-current"])
    async def lb_current(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You cant access this command. Please contact the bot owner to get access")

        srv = get_server_lb(ctx.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}
        
        old_current = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name
        
        if num > srv[uid].get("best_streak", 0):
            srv[uid]["best_streak"] = num
        
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send(f"✅ Updated **{user.name}** current streak: `{old_current}` → `{num}`")

    @commands.command(name="adminsecret2")#, aliases=["resetlimit", "rlimit"])
    async def reset_wordle_limit(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You cant access this command. Please contact the bot owner to get access")

        data = load_wordle_limits()
        data["users"] = {}
        data["last_reset"] = datetime.datetime.now().isoformat()
        save_wordle_limits(data)
        
        await ctx.send("✅ **Wordle limits have been manually reset for all users.**")

    # ===================== SLASH COMMANDS =====================

    @app_commands.command(name="adminhelp", description="Show admin commands")
    async def adminhelp_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access", ephemeral=True)
        embed = discord.Embed(title="🔧 Admin Commands", color=0x2f3136)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="difficulty", description="Set default mode")
    @app_commands.describe(mode="easy | medium | hard | impossible | default")
    async def difficulty_slash(self, interaction: discord.Interaction, mode: str):
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance. Only admins allowed.", ephemeral=True)

        mode = mode.lower().strip()
        valid = ["easy", "medium", "hard", "impossible", "default"]
        if mode not in valid:
            return await interaction.response.send_message("❌ Invalid mode!", ephemeral=True)

        if mode == "default":
            mode = random.choice(["medium", "hard"])

        gid = str(interaction.guild.id)
        if "default_modes" not in server_config:
            server_config["default_modes"] = {}
        server_config["default_modes"][gid] = mode
        save_json(CONFIG_FILE, server_config)

        await interaction.response.send_message(f"✅ Default mode set to **{mode.upper()}**", ephemeral=True)

    @app_commands.command(name="wordle", description="Play a game of wordle")
    @app_commands.describe(
        option='Enter a custom word for the wordle, or enter "end" to end the wordle, or enter "globalend" to end on all server wordle.',
        channel="Enter the channel for the wordle.",
        practice="Practice Mode"
    )
    async def wordle_slash(
        self, 
        interaction: discord.Interaction, 
        option: str = None, 
        channel: discord.TextChannel = None, 
        practice: bool = False
    ):
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        target_channel = channel if channel else interaction.channel
        target_id = target_channel.id

        if option:
            option_clean = option.lower().strip()
            
            # ROUTE 1: globalend Execution
            if option_clean == "globalend":
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
                count = len(active_games)
                active_games.clear()
                return await interaction.response.send_message(f"Wordle ended ({count})", ephemeral=True)

            # ROUTE 2: end Execution (FIXED ERROR CHECK)
            elif option_clean == "end":
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
                
                ended = 0
                for k in list(active_games.keys()):
                    # Added a safe dictionary check so it doesn't crash the bot
                    if isinstance(active_games[k], dict) and active_games[k].get("guild_id") == interaction.guild.id:
                        del active_games[k]
                        ended += 1
                if ended:
                    return await interaction.response.send_message(f"Wordle ended", ephemeral=False)
                else:
                    return await interaction.response.send_message("No active game found in this server.", ephemeral=True)

            # ROUTE 3: Custom Word Allocation
            else:
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
                
                game_key = f"{target_id}_practice_{interaction.user.id}" if practice else target_id

                if game_key in active_games:
                    return await interaction.response.send_message(f"❌ A game is already running for you in {target_channel.mention}!", ephemeral=True)

                if not option_clean.isalpha():
                    return await interaction.response.send_message("❌ Custom words must only contain alphabetic letters.", ephemeral=True)

                active_games[game_key] = {
                    "secret": option_clean, 
                    "length": len(option_clean), 
                    "guild_id": interaction.guild.id,
                    "revealed_indices": [], 
                    "processing_win": False,
                    "practice": practice,
                    "author_id": interaction.user.id
                }
                
                practice_label = " [PRACTICE MODE]" if practice else ""
                await target_channel.send(f"## New Wordle{practice_label} by <@{interaction.user.id}>\nLength: {len(option_clean)}")
                return await interaction.response.send_message(f"✅ Custom game loaded into {target_channel.mention}!", ephemeral=True)

        # ROUTE 4: Normal Base / Practice Play Deployment
        else:
            if not practice and not is_admin(interaction.user.id, interaction.guild):
                if get_user_game_count(interaction.user.id) >= 3:
                    return await interaction.response.send_message("❌ You have reached the maximum limit of **3** Wordle games today.\n\nJoin this discord server for events stuff! → ||https://discord.gg/2J6HkXvTmX||\n`We do event here and whoever wins gets a prize!`", ephemeral=True)

            gid = str(interaction.guild.id)
            configured_target = server_config.get(gid, {}).get("public")
            if configured_target and not channel:
                target_id = configured_target
                resolved_channel = interaction.client.get_channel(target_id) or interaction.channel
            else:
                resolved_channel = target_channel

            game_key = f"{target_id}_practice_{interaction.user.id}" if practice else target_id

            if game_key in active_games:
                return await interaction.response.send_message(f"❌ A game is already running for you in that channel!", ephemeral=True)

            default_mode = server_config.get("default_modes", {}).get(gid)
            secret, _ = get_random_word(interaction.guild.id, default_mode)

            active_games[game_key] = {
                "secret": secret, 
                "length": len(secret), 
                "guild_id": interaction.guild.id,
                "revealed_indices": [], 
                "processing_win": False,
                "practice": practice,
                "author_id": interaction.user.id
            }

            if not practice:
                increment_user_game_count(interaction.user.id)
                
            practice_label = " [PRACTICE MODE]" if practice else ""
            await resolved_channel.send(f"## New Wordle{practice_label} by <@{interaction.user.id}>\nLength: {len(secret)}")
            await interaction.response.send_message(f"✅ Game started!", ephemeral=True)
    @app_commands.command(name="help", description="Wordle Help")
    async def help_slash(self, interaction: discord.Interaction):
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        embed = discord.Embed(title="COMING SOON", color=0x2f3136)
        embed.description = "This command is being wip. Please comeback when it's done"
        await interaction.response.send_message(embed=embed)

        # ===================== SLASH HINT =====================
    # This has been removed due to something...

    # ===================== SLASH REVEAL (Supports 1v1 + Normal) =====================
    @app_commands.command(name="reveal", description="···")
    async def reveal_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
        
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        channel_id = interaction.channel.id

        # Check 1v1 match first
        if channel_id in active_1v1_matches:
            match = active_1v1_matches[channel_id]
            await interaction.response.send_message(
                f"🔍 **1v1 Secret word:** **{match['secret'].upper() if match.get('secret') else 'Not started yet'}**", 
                ephemeral=True
            )
            return

        # Normal Wordle game
        g = next((v for v in active_games.values() if v["guild_id"] == interaction.guild.id), None)
        if g and g.get("secret"):
            await interaction.response.send_message(
                f"🔍 Secret word: **{g['secret'].upper()}**", 
                ephemeral=True
            )
            return

        await interaction.response.send_message("❌ No active game or 1v1 match in this channel.", ephemeral=True)

    # ===================== SLASH AUTORESPONDER COMMAND =====================
    @app_commands.command(name="autoresponder", description="Create an autoresponder.")

    @app_commands.describe(
        action="add | edit | list",
        trigger="when the bot will respond to",
        new_trigger="Edit trigger",
        reply="Bot's reply",
        matchmode="contains | exact | startswith | endswith",
        react="The emoji the bot will react with [WIP]",
        channel="···",
        cooldown="···",
        global_server="···"
    )
    async def autoresponder(
        self, interaction: discord.Interaction, action: str,
        trigger: str = None, new_trigger: str = None, reply: str = None,
        matchmode: str = "contains", react: str = None, 
        channel: discord.TextChannel = None, cooldown: str = None, 
        global_server: bool = False
    ):
        # Swapped to check for Administrator permission
        if not interaction.permissions.administrator:
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        action = action.lower().strip()
        guild_id = str(interaction.guild.id)
        channel_id = str(channel.id) if channel else None

        # ===================== ACTIONS VERIFICATIONS =====================
        if action in ["removeall", "global_removeall"]:
            if action == "global_removeall":
                # Block TRUSTED_IDS from global deletion resets
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                if remove_all_auto_responses(global_all=True):
                    await interaction.response.send_message("🗑️ **ALL auto responders deleted globally.**", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Failed global reset operation.", ephemeral=True)
            else:  # removeall (server only)
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                if remove_all_auto_responses(guild_id=guild_id):
                    await interaction.response.send_message(f"🗑️ **All auto responders for this server deleted.**", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Failed server reset operation.", ephemeral=True)
            return

        # Block TRUSTED_IDS from initializing global fields
        if global_server and not is_admin(interaction.user.id, interaction.guild, check_global=True):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        if action == "add":
            if not trigger or not reply:
                return await interaction.response.send_message("❌ Need `trigger` + `reply`", ephemeral=True)
            
            # Enforce local fallback server parameters unless verified global admin
            is_global = global_server if is_admin(interaction.user.id, interaction.guild, check_global=True) else False

            add_auto_response(
                trigger=trigger, 
                reply=reply, 
                matchmode=matchmode, 
                react=react, 
                channel=channel_id, 
                cooldown=cooldown, 
                global_server=is_global, 
                guild_id=interaction.guild.id
            )
            global_label = " 🌐 [GLOBAL]" if is_global else ""
            await interaction.response.send_message(f"✅ Autoresponder added{global_label} for: `{trigger}`", ephemeral=True)

        elif action == "edit":
            if not trigger:
                return await interaction.response.send_message("❌ Need current trigger to locate the dataset entry.", ephemeral=True)
            
            all_responses = get_all_auto_responses()
            if trigger.lower().strip() in all_responses:
                if all_responses[trigger.lower().strip()].get("global") and not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

            edit_auto_response(trigger, new_trigger, reply, matchmode, react, channel_id, cooldown, global_server)
            await interaction.response.send_message(f"✅ Updated autoresponder setup: `{trigger}`", ephemeral=True)

        elif action == "list":
            data = get_all_auto_responses()
            if not data:
                return await interaction.response.send_message("No auto responders set.", ephemeral=True)
            
            embed = discord.Embed(title="Auto Responders Configuration", color=0x2f3136)
            for t, d in data.items():
                is_item_global = d.get("global", False)
                item_guild = str(d.get("guild_id", guild_id))
                
                if is_item_global or item_guild == guild_id:
                    ch = f"#{interaction.client.get_channel(int(d.get('channel'))).name}" if d.get('channel') and interaction.client.get_channel(int(d.get('channel'))) else "All Channels"
                    cd = f"{d.get('cooldown')}s" if d.get('cooldown') else "None"
                    global_tag = " 🌐 [Global]" if is_item_global else ""
                    
                    embed.add_field(
                        name=f"`{t}`{global_tag}", 
                        value=f"Reply: {d.get('response')[:100]}...\nChannel: {ch}\nCooldown: {cd}", 
                        inline=False
                    )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Use: `add | edit | list` (Use `/deleteautoresponder` to remove entries)", ephemeral=True)

    # ===================== DELETEAUTORESPONDER COMMAND =====================
    @app_commands.command(name="deleteautoresponder", description="Delete an autoresponder trigger")
    
    @app_commands.describe(
        trigger="The trigger word/phrase to remove",
        delete_all_globally="Delete this trigger globally across ALL servers (Admin only)"
    )
    async def deleteautoresponder(
        self, interaction: discord.Interaction, 
        trigger: str, 
        delete_all_globally: bool = False
    ):
        # Swapped to check for Administrator permission
        if not interaction.permissions.administrator:
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        target_trigger = trigger.lower().strip()
        guild_id = str(interaction.guild.id)
        all_responses = get_all_auto_responses()

        if target_trigger not in all_responses:
            return await interaction.response.send_message(f"❌ Autoresponder for `{trigger}` not found.", ephemeral=True)

        is_item_global = all_responses[target_trigger].get("global", False)
        item_guild = all_responses[target_trigger].get("guild_id")

        if delete_all_globally:
            if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
            
            remove_auto_response(target_trigger)
            return await interaction.response.send_message(f"🗑️ Global Autoresponder `{trigger}` has been deleted across all servers.", ephemeral=True)
        
        else:
            if is_item_global:
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                
                remove_auto_response(target_trigger)
                return await interaction.response.send_message(f"🗑️ Global Autoresponder `{trigger}` completely removed.", ephemeral=True)
            
            else:
                if item_guild and item_guild != guild_id:
                    return await interaction.response.send_message(f"❌ Autoresponder for `{trigger}` not found on this server.", ephemeral=True)
                
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                
                remove_auto_response(target_trigger)
                return await interaction.response.send_message(f"🗑️ Local Autoresponder `{trigger}` successfully removed.", ephemeral=True)
        
    # ===================== UPDATED SLASH SAY COMMAND =====================
    @app_commands.command(name="say", description="···")
    @app_commands.describe(
        message='···',
        channel="···",
        message_id="···"
    )
    async def say_slash(
        self, 
        interaction: discord.Interaction, 
        message: str, 
        channel: discord.TextChannel = None,
        message_id: str = None
    ):
        # Admin / Whitelist / Trusted / Server Owner check
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        #if not is_admin(interaction.guild):
            #return await interaction.response.send_message("❌ Server has been blacklisted. Please contact the bot owner for details.", ephemeral=True)

        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        # 1. Determine the target channel context
        target_channel = channel if channel else interaction.channel

        # 2. Check if the user ran the slash command *while replying* to a message via Discord UI
        target_message = None
        resolved_msg_id = None

        if message_id:
            resolved_msg_id = message_id.strip()
        elif interaction.data.get("resolved", {}).get("messages"):
            # Discord automatically includes the message context if executed as a reply context action
            resolved_msg_id = list(interaction.data["resolved"]["messages"].keys())[0]

        # 3. Attempt to fetch the target reference message if an ID was discovered
        if resolved_msg_id:
            try:
                target_message = await target_channel.fetch_message(int(resolved_msg_id))
            except Exception:
                # Fallback to current channel just in case the message belongs there instead
                try:
                    target_message = await interaction.channel.fetch_message(int(resolved_msg_id))
                    target_channel = interaction.channel
                except Exception:
                    return await interaction.response.send_message("❌ **Error:** Could not locate that Message ID in this environment.", ephemeral=True)

        try:
            # 4. Deliver the message payload
            if target_message:
                # Bot responds as a direct reply to the found message target
                await target_message.reply(message)
                await interaction.response.send_message(f"✅ Successfully replied to message `{target_message.id}` in {target_channel.mention}!", ephemeral=True)
            else:
                # Standard raw message post
                await target_channel.send(message)
                await interaction.response.send_message(f"✅ Message successfully sent to {target_channel.mention}!", ephemeral=True)
                
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages or reply in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to deliver message payload: {e}", ephemeral=True)
    
        # ===================== SLASH ADMINHELP =====================
    @app_commands.command(name="brick", description="···")
    async def adminhelp_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
            
        embed = discord.Embed(title="🔧 Admin Commands [SOON]", color=0x2f3136)
        embed.add_field(name="SOON", value="SOON", inline=False)
        embed.add_field(name="SOON", value="SOON", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # ===================== SLASH LB BEST =====================
    @app_commands.command(name="soon2", description="···")
    async def lb_best_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        srv = get_server_lb(interaction.guild.id)
        uid = str(user.id)
        
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}
        
        old_best = srv[uid].get("best_streak", 0)
        srv[uid]["best_streak"] = num
        srv[uid]["username"] = user.name
        
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`", ephemeral=True)

    # ===================== SLASH LB CURRENT =====================
    @app_commands.command(name="soon1", description="···")
    async def lb_current_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        srv = get_server_lb(interaction.guild.id)
        uid = str(user.id)
        
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}
        
        old_current = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name
        
        if num > srv[uid].get("best_streak", 0):
            srv[uid]["best_streak"] = num
        
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message(f"✅ Updated **{user.name}** current streak: `{old_current}` → `{num}`", ephemeral=True)

    # ===================== SLASH RLB =====================
    @app_commands.command(name="soon3", description="···")
    async def rlb_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        leaderboard["servers"][str(interaction.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message("🧹 Leaderboard has been reset.", ephemeral=True)

# ===================== PREFIX WHITE-LIST MANAGEMENT =====================
    @commands.command(name="trusted")
    async def idk(self, ctx, user_input: str = None, action: str = None):
        if is_server_blacklisted(ctx.guild.id):
            return

        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        # STRICT LOCK: Only true hardcoded IDs in ADMIN_IDS can configure whitelists.
        # Server owners are blocked unless their ID is hardcoded in ADMIN_IDS.
        if str(ctx.author.id) not in ADMIN_IDS:
            return await ctx.send("You do not have permission to use this command.")

        if not user_input:
            return await ctx.send("trusted <@user/userID/all>\nwadmin <@user/userID> remove")

        gid_str = str(ctx.guild.id)
        if gid_str not in server_config:
            server_config[gid_str] = {}
        if "trusted_users" not in server_config[gid_str]:
            server_config[gid_str]["trusted_users"] = []

        trusted_pool = server_config[gid_str]["trusted_users"]
        input_clean = user_input.strip().lower()

        # --- ROUTE 1: CLEAR ALL TRUSTED USERS FOR THIS SERVER ---
        if input_clean == "all" or (action and action.strip().lower() == "all"):
            if not trusted_pool:
                return await ctx.send("ℹ️ There are no whitelisted users configured on this server to remove.")
            
            server_config[gid_str]["trusted_users"] = []
            save_json(CONFIG_FILE, server_config)
            return await ctx.send("🗑️ Successfully **removed all** users from this server's whitelist configuration.")

        # --- EXTRACT USER ID FROM MENTION OR RAW STRING ---
        target_uid = user_input.replace("<@", "").replace("!", "").replace(">", "").strip()
        if not target_uid.isdigit():
            return await ctx.send("❌ Please provide a valid user mention or numerical User ID.")

        action_clean = action.lower().strip() if action else None

        # --- ROUTE 2: EXPLICIT REMOVE TARGET ---
        if action_clean == "remove":
            if target_uid in trusted_pool:
                trusted_pool.remove(target_uid)
                save_json(CONFIG_FILE, server_config)
                return await ctx.send(f"Successfully removed")
            else:
                return await ctx.send(f"Not in the trusted")

        # --- ROUTE 3: TOGGLE AUTOMATION ---
        if target_uid in trusted_pool:
            trusted_pool.remove(target_uid)
            status_msg = f"Successfully removed"
        else:
            trusted_pool.append(target_uid)
            status_msg = f" Successfully added (this server)"

        save_json(CONFIG_FILE, server_config)
        await ctx.send(status_msg)


    # ===================== PREFIX BLACKLIST MANAGEMENT =====================
    @commands.command(name="adminbl")
    async def admin_blacklist(self, ctx, server_id: str = None, action: str = None):
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        # STRICT LOCK: Only true hardcoded IDs in ADMIN_IDS can manage blacklists.
        # Server owners are blocked unless their ID is hardcoded in ADMIN_IDS.
        if str(ctx.author.id) not in ADMIN_IDS:
            return await ctx.send("You do not have permission to use this command.")

        if not server_id:
            return await ctx.send("❌ **Usage:** `.adminbl <serverID/all>` or `.adminbl <serverID> remove`")

        if "blacklisted_servers" not in server_config:
            server_config["blacklisted_servers"] = []

        blacklist_pool = server_config["blacklisted_servers"]
        input_clean = server_id.strip().lower()

        # --- ROUTE 1: CLEAR ALL BLACKLISTED SERVERS ---
        if input_clean == "all" or (action and action.strip().lower() == "all"):
            if not blacklist_pool:
                return await ctx.send("ℹ️ The blacklist is already completely empty.")
            
            server_config["blacklisted_servers"] = []
            save_json(CONFIG_FILE, server_config)
            return await ctx.send("🔓 Successfully **wiped the blacklist**. All servers are now unbanished globally.")

        target_sid = server_id.strip()
        action_clean = action.lower().strip() if action else None

        # --- ROUTE 2: EXPLICIT REMOVE TARGET ---
        if action_clean == "remove":
            if target_sid in blacklist_pool:
                blacklist_pool.remove(target_sid)
                save_json(CONFIG_FILE, server_config)
                return await ctx.send(f"🔓 Server ID `{target_sid}` has been successfully **removed** from the blacklist.")
            else:
                return await ctx.send(f"❌ Server ID `{target_sid}` was not found in the blacklist pool.")

        # --- ROUTE 3: TOGGLE AUTOMATION ---
        if target_sid in blacklist_pool:
            blacklist_pool.remove(target_sid)
            status_msg = f"🔓 Server ID `{target_sid}` was already blacklisted. **Removed** from blacklist."
        else:
            blacklist_pool.append(target_sid)
            status_msg = f"🚫 Server ID `{target_sid}` has been **added** to the blacklist."

        save_json(CONFIG_FILE, server_config)
        await ctx.send(status_msg)

    # pong
    @commands.command(name="ping")
    async def ping(self, ctx):
        #if self.check_maintenance(ctx):
            #)return await ctx.send("🛠️ **Bot is under maintenance.**")

        #if str(ctx.author.id) not in ADMIN_IDS:
            #return await ctx.send("You do not have permission to use this command.")

        await ctx.send(f"Pong! {round(self.bot.latency * 1000)}ms")

# ===================== INVITE & SERVER MANAGEMENT SYSTEM =====================
    @commands.command(name="addinvite")
    async def add_invite_management(self, ctx, category: str = None, target_id: str = None, action: str = None):
        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if str(ctx.author.id) not in ADMIN_IDS:
            return await ctx.send("You do not have permission to use this command.")

        if not category:
            return await ctx.send("❌ **Usage:**\n`.addinvite user <userID>`\n`.addinvite user <userID> remove`\n`.addinvite server <serverID>`\n`.addinvite server <serverID> remove`\n`.addinvite cleanall` (wipes users)")

        # Handle wipe quickly
        if category.lower().strip() == "cleanall":
            stats = load_stats()
            stats["invited_users"] = []
            save_stats(stats)
            return await ctx.send("🔓 Successfully **wiped the user invite whitelist**.")

        if not target_id:
            return await ctx.send("❌ Please provide a valid User ID or Server ID.")

        category = category.lower().strip()
        clean_id = "".join(char for char in str(target_id) if char.isdigit())
        if not clean_id:
            return await ctx.send(f"❌ `{target_id}` is not a valid numeric ID.")

        # --- USER MANAGEMENT ---
        if category == "user":
            stats = load_stats()
            pool = [str(value) for value in stats.get("invited_users", []) if str(value).isdigit()]
            stats["invited_users"] = pool
            
            if action and action.lower().strip() == "remove":
                if clean_id in pool:
                    pool.remove(clean_id)
                    save_stats(stats)
                    return await ctx.send(f"❌ User ID `{clean_id}` removed from invite whitelist.")
                return await ctx.send("❌ User not found in whitelist.")

            if clean_id in pool:
                return await ctx.send("ℹ️ User is already whitelisted.")
            
            pool.append(clean_id)
            save_stats(stats)
            return await ctx.send(f"✅ User ID `{clean_id}` added to invite whitelist!")

        # --- SERVER MANAGEMENT ---
        elif category == "server":
            stats = load_stats()
            pool = [str(value) for value in stats.get("allowed_servers", []) if str(value).isdigit()]
            stats["allowed_servers"] = pool

            if action and action.lower().strip() == "remove":
                if clean_id in pool:
                    pool.remove(clean_id)
                    save_stats(stats)
                    return await ctx.send(f"❌ Server ID `{clean_id}` removed from allowed servers list.")
                return await ctx.send("❌ Server not found in allowed list.")

            if clean_id in pool:
                return await ctx.send("ℹ️ Server is already whitelisted.")
            
            pool.append(clean_id)
            save_stats(stats)
            return await ctx.send(f"✅ Server ID `{clean_id}` added to allowed servers list!")
        
        else:
            return await ctx.send("❌ Invalid category. Choose `user` or `server`.")

    # ===================== SECURED SLASH INVITE COMMAND =====================
    @app_commands.command(name="invite", description="Generates a secure link to invite the bot to your server.")
    async def invite_slash_cmd(self, interaction: discord.Interaction):
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ **Bot is under maintenance.**", ephemeral=True)

        invited_pool = server_config.get("invited_users", [])
        user_id_str = str(interaction.user.id)

        # Secure authorization wall check
        if user_id_str not in invited_pool and user_id_str not in ADMIN_IDS:
            return await interaction.response.send_message(
                "❌ You are not authorized to invite this bot. Please contact the administrator.", 
                ephemeral=True
            )

        await interaction.response.send_message(
            "👋 Click the button below to authorize adding the bot into your chosen server:", 
            view=InviteBotView(),
            ephemeral=True
        )

# --- Define the Interactive Button Object Layout ---
class InviteBotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Optimized layout configuration link to bypass client integrations caches
        self.add_item(discord.ui.Button(
            label="Authorize Bot", 
            url="https://discord.com/api/oauth2/authorize?client_id=1502654737219321926&permissions=6755418768566336&scope=bot",
            style=discord.ButtonStyle.link
        ))

async def setup(launch):
    await launch.add_cog(BotCommands(launch))