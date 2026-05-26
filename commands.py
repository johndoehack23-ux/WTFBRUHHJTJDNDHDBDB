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
                return await ctx.send("🔐 **Denied Access.** Only admins can end active modes.")

            ended_something = False
            
            if channel_id in active_1v1_lobbies:
                del active_1v1_lobbies[channel_id]
                await ctx.send("🛑 **1v1 Lobby matchmaking has been canceled.**")
                ended_something = True
                
            if channel_id in active_1v1_matches:
                del active_1v1_matches[channel_id]
                await ctx.send("🛑 **Active 1v1 Match has been forcefully ended.**")
                ended_something = True
                
            if not ended_something:
                await ctx.send("❌ There is no active 1v1 lobby or match running in this channel.")
            return

        # Ensure valid mode entry
        if mode_action != "1v1":
            return await ctx.send("✅ Usage: `.mode 1v1` or `.mode 1v1 5` (for specific length)")

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
    @commands.command(name="wordlelimit", aliases=["wlimit", "limit"])
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
            status = "✅ **Infinite** Wordle plays **enabled**" if new_state else "✅ **Infinite** Wordle plays **disabled**"
            await ctx.send(f"{status} for **{user.name}**.")
        
        elif action == "reset":
            if reset_user_wordle_limit(user.id):
                await ctx.send(f"✅ Fully reset Wordle data for **{user.name}** (count + infinite removed).")
            else:
                await ctx.send(f"ℹ️ **{user.name}** had no active limits to reset.")
        else:
            await ctx.send("❌ Invalid action! Use `infinite` or `reset`.")

    # Optional: Global reset (kept for safety)
    @commands.command(name="resetalllimits", aliases=["rlimitall"])
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

    # ===================== NORMAL PREFIX COMMANDS =====================
    @commands.command(name="adminhelp")
    async def adminhelp(self, ctx):
        if not is_admin(ctx.author.id):
            return
        embed = discord.Embed(title="🔧 Admin Commands", color=0x2f3136)
        embed.add_field(name="Channel Setup", value="`.setwordle <private_id> <public_id>`", inline=False)
        embed.add_field(name="Tools", value="`.test` `.maintenance` `.hint` `.reveal` `.endgame` `.rlb`", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="category")
    async def category(self, ctx, mode: str = "default"):
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

        # ===================== PREFIX WORDLE (Per User 3 Limit) =====================
    @commands.command(name="wordle")
    async def wordle(self, ctx, *, option: str = None):
        if not is_admin(ctx.author.id):
            if get_user_game_count(ctx.author.id) >= 3:
                return await ctx.send("❌ You have reached the maximum limit of **3** Wordle games today.")

        if self.check_maintenance(ctx):
            return await ctx.send("🛠️ **Bot is under maintenance.** Only admins can use commands.")

        if option and not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        gid = str(ctx.guild.id)
        target_id = server_config.get(gid, {}).get("public") or ctx.channel.id

        if target_id in active_games:
            return await ctx.send("❌ A game is already running in this channel!")

        default_mode = server_config.get("default_modes", {}).get(gid)
        secret = (option.lower().strip() if option else get_random_word(ctx.guild.id, default_mode)[0])

        active_games[target_id] = {
            "secret": secret, "length": len(secret), "guild_id": ctx.guild.id,
            "revealed_indices": [], "processing_win": False
        }

        increment_user_game_count(ctx.author.id)   # Increase count

        chan = ctx.bot.get_channel(target_id) or ctx.channel
        await chan.send(f"## New Wordle by <@{ctx.author.id}>\n**Length:** {len(secret)}")

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
    @commands.command(name="endgame")
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

    @commands.command(name="test", aliases=["maintenance"])
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
        embed.description = "`.wordle` - Start game\n`.category <mode>` - Set mode\n`.leaderboard` - View ranks"
        await ctx.send(embed=embed)

    # lb-best and lb-current
    @commands.command(name="lb-best", aliases=["leaderboard-best"])
    async def lb_best(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ Admin only.")

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
            return await ctx.send("❌ Admin only.")

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

    @commands.command(name="resetwordlelimit", aliases=["resetlimit", "rlimit"])
    async def reset_wordle_limit(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

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

    @app_commands.command(name="category", description="Set default mode")
    @app_commands.describe(mode="easy | medium | hard | impossible | default")
    async def category_slash(self, interaction: discord.Interaction, mode: str):
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

        # ===================== SLASH WORDLE (Per User 3 Limit) =====================
    @app_commands.command(name="wordle", description="Start Wordle game")
    @app_commands.describe(option="Custom word (Admin only)")
    async def wordle_slash(self, interaction: discord.Interaction, option: str = None):
        if not is_admin(interaction.user.id):
            if get_user_game_count(interaction.user.id) >= 3:
                return await interaction.response.send_message("❌ You have reached the maximum limit of **3** Wordle games today.")

        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        if option and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

         
        gid = str(interaction.guild.id)
        target_id = server_config.get(gid, {}).get("public") or interaction.channel.id

        if target_id in active_games:
            return await interaction.response.send_message("❌ A game is already running in this channel!", ephemeral=True)

        default_mode = server_config.get("default_modes", {}).get(gid)
        secret = (option.lower().strip() if option else get_random_word(interaction.guild.id, default_mode)[0])

        active_games[target_id] = {
            "secret": secret, "length": len(secret), "guild_id": interaction.guild.id,
            "revealed_indices": [], "processing_win": False
        }

        increment_user_game_count(interaction.user.id)

        chan = interaction.client.get_channel(target_id) or interaction.channel
        await chan.send(f"## New Wordle by <@{interaction.user.id}>\n**Length:** {len(secret)}")

        await interaction.response.send_message("✅ Game started!", ephemeral=True)

    @app_commands.command(name="help", description="Wordle Help")
    async def help_slash(self, interaction: discord.Interaction):
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        embed = discord.Embed(title="Wordle Help", color=0x2f3136)
        embed.description = "`.wordle` - Start game\n`.category <mode>` - Set mode\n`.leaderboard` - View ranks"
        await interaction.response.send_message(embed=embed)

        # ===================== SLASH HINT =====================
    @app_commands.command(name="hint", description="Get a hint (Admin only)")
    async def hint_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)
        
        if self.check_maintenance(interaction):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        g = next((v for v in active_games.values() if v["guild_id"] == interaction.guild.id), None)
        if not g:
            return await interaction.response.send_message("🔐 No game running.", ephemeral=True)

        avail = [i for i in range(g["length"]) if i not in g.get("revealed_indices", [])]
        if not avail:
            return await interaction.response.send_message("No more hints.", ephemeral=True)

        idx = random.choice(avail)
        g.setdefault("revealed_indices", []).append(idx)
        await interaction.response.send_message(f"💡 Letter {idx+1} is **{g['secret'][idx].upper()}**", ephemeral=True)

    # ===================== SLASH REVEAL (Supports 1v1 + Normal) =====================
    @app_commands.command(name="reveal", description="Reveal secret word (Admin only)")
    async def reveal_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)
        
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
            return  # <-- FIXED: Added missing return here so it doesn't run into the error block below
        
        await interaction.response.send_message("❌ No active game or 1v1 match in this channel.", ephemeral=True)

        # ===================== SLASH ADMINHELP =====================
    @app_commands.command(name="adminhelp", description="Show admin commands")
    async def adminhelp_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)
            
        embed = discord.Embed(title="🔧 Admin Commands", color=0x2f3136)
        embed.add_field(name="Channel Setup", value="/setwordle", inline=False)
        embed.add_field(name="Tools", value="/hint /reveal /endgame /test /rlb /lb-best /lb-current", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # ===================== SLASH LB BEST =====================
    @app_commands.command(name="lb-best", description="Update user's best streak")
    async def lb_best_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

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
    @app_commands.command(name="lb-current", description="Update user's current streak")
    async def lb_current_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

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

            # ===================== SLASH ENDGAME =====================
    @app_commands.command(name="endgame", description="End game(s)")
    @app_commands.describe(scope="server or global")
    async def endgame_slash(self, interaction: discord.Interaction, scope: str = "server"):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

        scope = scope.lower()

        if scope == "global":
            count = len(active_games)
            active_games.clear()
            await interaction.response.send_message(f"✅ **Global Endgame** - Ended {count} game(s).", ephemeral=True)

        elif scope == "server":
            ended = 0
            for k in list(active_games.keys()):
                if active_games[k]["guild_id"] == interaction.guild.id:
                    del active_games[k]
                    ended += 1
            await interaction.response.send_message(
                f"✅ Ended {ended} game(s) in this server." if ended else "No active game found.", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Invalid option. Use: `server` or `global`", ephemeral=True)

    # ===================== SLASH RLB =====================
    @app_commands.command(name="rlb", description="Reset leaderboard (Admin only)")
    async def rlb_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

        leaderboard["servers"][str(interaction.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message("🧹 Leaderboard has been reset.", ephemeral=True)

async def setup(launch):
    await launch.add_cog(BotCommands(launch))