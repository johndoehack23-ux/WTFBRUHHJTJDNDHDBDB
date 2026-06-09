import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class WordleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="wordle")
    async def wordle_prefix(self, ctx, option: str = None):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        target_channel = ctx.channel
        target_id = target_channel.id

        if option:
            option_clean = option.lower().strip()

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

    @app_commands.command(name="wordle", description="Play a game of wordle")
    @app_commands.describe(
        option='Custom word, "end" to end, or "globalend" to end all server wordles.',
        channel="Channel for the wordle.",
        practice="Practice Mode"
    )
    async def wordle_slash(
        self,
        interaction: discord.Interaction,
        option: str = None,
        channel: discord.TextChannel = None,
        practice: bool = False
    ):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        target_channel = channel if channel else interaction.channel
        target_id = target_channel.id

        if option:
            option_clean = option.lower().strip()

            if option_clean == "globalend":
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
                count = len(active_games)
                active_games.clear()
                return await interaction.response.send_message(f"Wordle ended ({count})", ephemeral=True)

            elif option_clean == "end":
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

                ended = 0
                for k in list(active_games.keys()):
                    if isinstance(active_games[k], dict) and active_games[k].get("guild_id") == interaction.guild.id:
                        del active_games[k]
                        ended += 1
                if ended:
                    return await interaction.response.send_message("Wordle ended", ephemeral=False)
                else:
                    return await interaction.response.send_message("No active game found in this server.", ephemeral=True)

            else:
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

                game_key = f"{target_id}_practice_{interaction.user.id}" if practice else target_id

                if game_key in active_games:
                    return await interaction.response.send_message(f"❌ A game is already running in {target_channel.mention}!", ephemeral=True)

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

        else:
            if not practice and not is_admin(interaction.user.id, interaction.guild):
                if get_user_game_count(interaction.user.id) >= 3:
                    return await interaction.response.send_message(
                        "❌ You have reached the maximum limit of **3** Wordle games today.\n\nJoin this discord server for events stuff! → ||https://discord.gg/2J6HkXvTmX||\n`We do event here and whoever wins gets a prize!`",
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
                return await interaction.response.send_message("❌ A game is already running in that channel!", ephemeral=True)

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
            await interaction.response.send_message("✅ Game started!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WordleCog(bot))
