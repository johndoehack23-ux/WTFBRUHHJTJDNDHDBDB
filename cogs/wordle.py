import discord
from discord.ext import commands
from discord import app_commands
import json
import random
from functions import *


def has_admin(user, guild):
    if not guild:
        return False
    if isinstance(user, discord.Member):
        return user.guild_permissions.administrator
    return False


class WordleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addwordle")
    async def addwordle_prefix(self, ctx, category: str, difficulty: str, word: str):
        try:
            with open("wordlecategories.json", "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"meme": {"easy": [], "hard": [], "extreme": [], "impossible": []}}

        category = category.lower().strip()
        difficulty = difficulty.lower().strip()

        if category not in data:
            data[category] = {"easy": [], "hard": [], "extreme": [], "impossible": []}
            
        if difficulty not in data[category]:
            await ctx.send("🥀")
            return

        clean_word = "".join(char.lower() for char in word if char.isalnum())
        
        if clean_word and clean_word not in data[category][difficulty]:
            data[category][difficulty].append(clean_word)
            with open("wordlecategories.json", "w") as f:
                json.dump(data, f, indent=4)
            await ctx.send(f"Successfully added `{clean_word}` to {category} [{difficulty}]!")
        else:
            await ctx.send("Are we serious right now BRO? 😭")

    @commands.command(name="wordle")
    async def wordle_prefix(self, ctx, mode_or_option: str = None, category: str = None, difficulty: str = "easy"):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("Bot is under maintenance.")

        target_channel = ctx.channel
        target_id = target_channel.id

        if mode_or_option and mode_or_option.lower().strip() == "end":
            if not (is_admin(ctx.author.id, ctx.guild) or has_admin(ctx.author, ctx.guild)):
                return await ctx.send("Denied Access.")

            ended = 0
            for k in list(active_games.keys()):
                if isinstance(active_games[k], dict) and active_games[k].get("guild_id") == ctx.guild.id:
                    del active_games[k]
                    ended += 1
            if ended:
                return await ctx.send(f"Ended {ended} game(s) in this server.")
            else:
                return await ctx.send("No active game found in this server.")

        # ── .wordle edit <word> [serverID] — debug channel only ──
        if mode_or_option and mode_or_option.lower().strip() == "edit":
            if ctx.channel.id != DEBUG_CHANNEL_ID:
                return
            if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
                return

            if not category:
                return await ctx.send("❌ Usage: `.wordle edit <word> [serverID]`")

            word_clean = "".join(c for c in category.lower() if c.isalpha())
            if not word_clean:
                return await ctx.send("❌ Invalid word — alphabetic characters only.")

            target_gid = None
            if difficulty and difficulty.strip().isdigit():
                target_gid = int(difficulty.strip())
            else:
                target_gid = ctx.guild.id

            game_key_found = None
            for k, g in list(active_games.items()):
                if isinstance(g, dict) and g.get("guild_id") == target_gid and not g.get("practice"):
                    game_key_found = k
                    break

            if game_key_found is None:
                return await ctx.send(f"❌ No active game found for server `{target_gid}`.")

            old_word = active_games[game_key_found]["secret"]
            active_games[game_key_found]["secret"] = word_clean
            active_games[game_key_found]["length"] = len(word_clean)
            await ctx.send(f"✅ `{old_word}` → `{word_clean}` (length: {len(word_clean)})")

            debug_msg_id = active_games[game_key_found].get("debug_msg_id")
            debug_ch_id = active_games[game_key_found].get("debug_msg_channel_id")
            if debug_msg_id and debug_ch_id:
                try:
                    debug_ch = self.bot.get_channel(debug_ch_id)
                    if debug_ch:
                        dm = await debug_ch.fetch_message(debug_msg_id)
                        guild_obj = self.bot.get_guild(target_gid)
                        gname = guild_obj.name if guild_obj else str(target_gid)
                        await dm.edit(content=f"🔐 `{word_clean}` | {target_gid} ({gname}) *(edited)*")
                except Exception:
                    pass
            return

        secret_word = None
        if mode_or_option and mode_or_option.lower().strip() == "mode":
            stats = load_stats()
            gid_str = str(ctx.guild.id)
            uid_str = str(ctx.author.id)
            trusted_pool = stats.get("trusted_users", {}).get(gid_str, [])

            is_user_trusted = uid_str in trusted_pool
            is_user_admin = is_admin(ctx.author.id, ctx.guild)
            is_user_op = is_op(ctx.author.id)

            if not (is_user_admin or is_user_op or is_user_trusted or has_admin(ctx.author, ctx.guild)):
                return await ctx.send("You do not have permission to use this command")

            if not category:
                return await ctx.send("😭🙏")

            clean_cat = category.lower().strip()
            clean_diff = difficulty.lower().strip() if difficulty else "easy"

            try:
                with open("wordlecategories.json", "r", encoding="utf-8") as f:
                    cats_data = json.load(f)
            except Exception:
                return await ctx.send("❌ Failed to load category configuration file.")

            if clean_cat not in cats_data:
                available_cats = ", ".join(f"`{c}`" for c in cats_data.keys())
                return await ctx.send(f"❌ Unknown category! Available: {available_cats}")

            available_diffs = list(cats_data[clean_cat].keys())
            if clean_diff not in available_diffs:
                clean_diff = available_diffs[0] if available_diffs else "easy"

            word_pool = cats_data[clean_cat].get(clean_diff, [])
            if not word_pool:
                return await ctx.send(f"❌ No words found for `{clean_cat} / {clean_diff}`.")

            secret_word = random.choice(word_pool).lower().replace(" ", "").replace("-", "")

        elif mode_or_option and mode_or_option.lower().strip() in ("easy", "hard", "extreme", "impossible"):
            return await ctx.send("😭🙏")

        stats = load_stats()
        gid_str_limit = str(ctx.guild.id)
        uid_str_limit = str(ctx.author.id)
        trusted_pool_limit = stats.get("trusted_users", {}).get(gid_str_limit, [])
        is_user_trusted_limit = uid_str_limit in trusted_pool_limit
        is_user_admin_limit = is_admin(ctx.author.id, ctx.guild, check_global=True)
        can_bypass = is_user_admin_limit or (is_infinite_wordle(ctx.author.id) and not is_user_trusted_limit)
        if not can_bypass:
            count = get_user_game_count(ctx.author.id)
            daily_limit = TRUSTED_DAILY_LIMIT if is_user_trusted_limit else REGULAR_DAILY_LIMIT
            if count >= daily_limit:
                return await ctx.send(f"You have reached the maximum limit of {daily_limit} Wordle games today.")

        gid = str(ctx.guild.id)
        configured_target = server_config.get(gid, {}).get("public")
        if configured_target:
            target_id = configured_target
            resolved_channel = ctx.bot.get_channel(target_id) or ctx.channel
        else:
            resolved_channel = target_channel

        if target_id in active_games:
            return await ctx.send("A game is already running in that channel!")

        if not secret_word:
            default_mode = server_config.get("default_modes", {}).get(gid)
            secret_word, _ = get_random_word(ctx.guild.id, default_mode)

        active_games[target_id] = {
            "secret": secret_word,
            "length": len(secret_word),
            "guild_id": ctx.guild.id,
            "revealed_indices": [],
            "processing_win": False,
            "practice": False,
            "author_id": ctx.author.id
        }

        increment_user_game_count(ctx.author.id)

        mode_label = f" [{category.title()} - {difficulty.title()}]" if mode_or_option and mode_or_option.lower().strip() == "mode" else ""
        await resolved_channel.send(f"## New Wordle{mode_label} by <@{ctx.author.id}>\nLength: {len(secret_word)}")

        if is_debug_mode():
            debug_ch = self.bot.get_channel(DEBUG_CHANNEL_ID)
            if debug_ch:
                try:
                    dm = await debug_ch.send(f"🔐 `{secret_word}` | {ctx.guild.id} ({ctx.guild.name})")
                    active_games[target_id]["debug_msg_id"] = dm.id
                    active_games[target_id]["debug_msg_channel_id"] = debug_ch.id
                except Exception:
                    pass

    @app_commands.command(name="wordle", description="Play a game of wordle")
    @app_commands.describe(
        word='Enter the word for wordle, or enter "end" to end the wordle.',
        channel="Enter the channel for the wordle.",
        category="...",
        difficulty="...",
        practice="Practice Mode"
    )
    async def wordle_slash(
        self,
        interaction: discord.Interaction,
        word: str = None,
        channel: discord.TextChannel = None,
        category: str = None,
        difficulty: str = "easy",
        practice: bool = False
    ):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("Bot is under maintenance.", ephemeral=True)

        target_channel = channel if channel else interaction.channel
        target_id = target_channel.id

        if word:
            word_clean = word.lower().strip()

            if word_clean == "globalend":
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
                count = len(active_games)
                active_games.clear()
                return await interaction.response.send_message(f"Wordle ended ({count})", ephemeral=True)

            elif word_clean == "end":
                if not (is_admin(interaction.user.id, interaction.guild) or has_admin(interaction.user, interaction.guild)):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

                ended = 0
                for k in list(active_games.keys()):
                    if isinstance(active_games[k], dict) and active_games[k].get("guild_id") == interaction.guild.id:
                        del active_games[k]
                        ended += 1
                if ended:
                    return await interaction.response.send_message("Wordle ended", ephemeral=False)
                else:
                    return await interaction.response.send_message("Wordle hasn't been started.", ephemeral=True)

            else:
                # Custom Wordle
                stats = load_stats()
                gid_str = str(interaction.guild.id)
                uid_str = str(interaction.user.id)
                trusted_pool = stats.get("trusted_users", {}).get(gid_str, [])

                is_user_trusted = uid_str in trusted_pool
                is_user_admin = is_admin(interaction.user.id, interaction.guild)
                is_user_op = is_op(interaction.user.id)
                is_guild_admin = has_admin(interaction.user, interaction.guild)

                if not (is_user_admin or is_user_op or is_user_trusted or is_guild_admin):
                    return await interaction.response.send_message("You do not have permission to start a custom Wordle.", ephemeral=True)

                word_clean = "".join(c for c in word_clean if c.isalpha())
                if not word_clean:
                    return await interaction.response.send_message("Custom words must only contain alphabetic letters.", ephemeral=True)

                game_key = f"{target_id}_practice_{interaction.user.id}" if practice else target_id

                if game_key in active_games:
                    return await interaction.response.send_message(f"A game is already running in {target_channel.mention}!", ephemeral=True)

                active_games[game_key] = {
                    "secret": word_clean,
                    "length": len(word_clean),
                    "guild_id": interaction.guild.id,
                    "revealed_indices": [],
                    "processing_win": False,
                    "practice": practice,
                    "author_id": interaction.user.id
                }

                practice_label = " [PRACTICE MODE]" if practice else ""
                await target_channel.send(f"## New Wordle{practice_label} by <@{interaction.user.id}>\nLength: {len(word_clean)}")

                if not practice and is_debug_mode():
                    debug_ch = self.bot.get_channel(DEBUG_CHANNEL_ID)
                    if debug_ch:
                        try:
                            dm = await debug_ch.send(f"🔐 `{word_clean}` | {interaction.guild.id} ({interaction.guild.name})")
                            active_games[game_key]["debug_msg_id"] = dm.id
                            active_games[game_key]["debug_msg_channel_id"] = debug_ch.id
                        except Exception:
                            pass

                return await interaction.response.send_message(f"Custom game loaded into {target_channel.mention}!", ephemeral=True)

        else:
            gid_str_s = str(interaction.guild.id)
            uid_str_s = str(interaction.user.id)
            trusted_pool_s = load_stats().get("trusted_users", {}).get(gid_str_s, [])
            is_user_trusted_s = uid_str_s in trusted_pool_s
            is_user_admin_s = is_admin(interaction.user.id, interaction.guild, check_global=True)
            can_bypass_s = is_user_admin_s or (is_infinite_wordle(interaction.user.id) and not is_user_trusted_s)
            if not practice and not can_bypass_s:
                count_s = get_user_game_count(interaction.user.id)
                daily_limit_s = TRUSTED_DAILY_LIMIT if is_user_trusted_s else REGULAR_DAILY_LIMIT
                if count_s >= daily_limit_s:
                    return await interaction.response.send_message(
                        f"You have reached the maximum limit of {daily_limit_s} Wordle games today.\n\nJoin this discord server for events stuff! → ||https://discord.gg/2J6HkXvTmX||\nWe do event here and whoever wins gets a prize!",
                        ephemeral=True
                    )

            gid = str(interaction.guild.id)
            configured_target = server_config.get(gid, {}).get("public")
            if configured_target and not channel:
                target_id = configured_target
                resolved_channel = interaction.client.get_channel(target_id) or interaction.channel
            else:
                resolved_channel = target_channel

            game_key = f"{target_id}_practice_{interaction.user.id}" if practice else target_id

            if game_key in active_games:
                return await interaction.response.send_message("A game is already running in that channel!", ephemeral=True)

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

            if not practice and is_debug_mode():
                debug_ch = self.bot.get_channel(DEBUG_CHANNEL_ID)
                if debug_ch:
                    try:
                        dm = await debug_ch.send(f"🔐 `{secret}` | {interaction.guild.id} ({interaction.guild.name})")
                        active_games[game_key]["debug_msg_id"] = dm.id
                        active_games[game_key]["debug_msg_channel_id"] = debug_ch.id
                    except Exception:
                        pass

            await interaction.response.send_message("Game started!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WordleCog(bot))