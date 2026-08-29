import asyncio
import discord
from discord import app_commands
from discord.ext import commands

STATUS_NAMES = {"online", "idle", "dnd", "offline"}
STATUS_OWNER_ID = 1465295674768883889

ACTIVITY_PREFIXES = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "streaming": discord.ActivityType.streaming,
}

SUPPORTED_GAMES = {"among us", "roblox"}


def make_activity(text):
    text = str(text).strip()
    if not text:
        return None, "Please provide activity text."

    lowered = text.lower()
    for prefix, activity_type in ACTIVITY_PREFIXES.items():
        if lowered == prefix:
            return None, f"Please add text after `{prefix.title()}`."
        if lowered.startswith(prefix + " "):
            label = text[len(prefix):].strip()
            return discord.Activity(type=activity_type, name=label), None

    return discord.Game(name=text), None


class GameSetupView(discord.ui.View):
    def __init__(self, cog, author_id, game):
        super().__init__(timeout=120)
        self.cog = cog
        self.author_id = author_id
        self.game = game

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who ran the command can choose this.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Lobby", style=discord.ButtonStyle.green)
    async def lobby(self, interaction, button):
        await interaction.response.defer()
        await self.cog.finish_game_setup(interaction, self.game, "Lobby")
        self.stop()

    @discord.ui.button(label="Ingame", style=discord.ButtonStyle.blurple)
    async def ingame(self, interaction, button):
        await interaction.response.defer()
        await self.cog.finish_game_setup(interaction, self.game, "Ingame")
        self.stop()


class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_activity = None
        self.game_setup = {}

    def allowed(self, user, guild=None):
        return user.id == STATUS_OWNER_ID

    async def apply_status(self, status, text):
        status = status.lower().strip()
        if status not in STATUS_NAMES:
            return None, "Status must be `online`, `idle`, `dnd`, or `offline`."

        text = str(text).strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            text = text[1:-1].strip()

        activity, error = make_activity(text)
        if error:
            return None, error

        await self.bot.change_presence(
            status=getattr(discord.Status, status),
            activity=activity,
        )
        self.current_activity = activity

        activity_label = str(activity) if activity else "No activity"
        return (
            f"✅ Status set to **{status}**\n"
            f"Activity: **{activity_label}**",
            None,
        )

    def normalize_game(self, text):
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            text = text[1:-1].strip()
        return text.lower()

    async def start_game_setup(self, ctx, status, game):
        normalized = self.normalize_game(game)

        if normalized not in SUPPORTED_GAMES:
            return await ctx.send(
                "❌ Supported games are currently `Among Us` and `Roblox`."
            )

        result, error = await self.apply_status(status, game)
        if error:
            return await ctx.send(error)

        self.game_setup[ctx.author.id] = {
            "game": "Among Us" if normalized == "among us" else "Roblox",
            "status": status.lower(),
            "channel_id": ctx.channel.id,
        }

        view = GameSetupView(self, ctx.author.id, self.game_setup[ctx.author.id]["game"])
        await ctx.send(
            f"🎮 **{self.game_setup[ctx.author.id]['game']}** setup started.\n"
            f"**Lobby or Ingame?**",
            view=view,
        )

    async def finish_game_setup(self, interaction, game, game_type):
        if game_type == "Lobby":
            if game == "Among Us":
                message = (
                    "🟢 **Among Us — Lobby**\n\n"
                    "👥 Players: **1/15**\n"
                    "🔑 Code: **`SUSSY`**"
                )
            else:
                message = (
                    "🟢 **Roblox — Lobby**\n\n"
                    "👥 Players: **1**\n"
                    "🔑 Code: **`SUSSY`**"
                )
        else:
            message = (
                f"🔵 **{game} — Ingame**\n\n"
                "🎮 Status: **Ingame**"
            )

        await interaction.followup.send(message)
        self.game_setup.pop(interaction.user.id, None)

    @commands.command(name="stopstatus")
    async def stop_status(self, ctx):
        if ctx.author.id != STATUS_OWNER_ID:
            return await ctx.send("❌ Only the bot owner can stop the bot status.")

        await self.bot.change_presence(
            status=discord.Status.online,
            activity=None,
        )
        self.current_activity = None
        self.game_setup.pop(ctx.author.id, None)
        await ctx.send("✅ Bot status and activity stopped.")

    @commands.command(name="status", aliases=["starus"])
    async def status_prefix(self, ctx, status: str = None, *, text: str = None):
        if not self.allowed(ctx.author, ctx.guild):
            return await ctx.send("❌ Only the bot owner can change the bot status.")

        if not status or not text:
            return await ctx.send(
                "Usage: `.status <online|idle|dnd|offline> \"<Game>\"`\n"
                "Example: `.status online \"Among Us\"`"
            )

        game = self.normalize_game(text)

        if game in SUPPORTED_GAMES:
            await self.start_game_setup(ctx, status, text)
            return

        result, error = await self.apply_status(status, text)
        await ctx.send(error or result)

    @app_commands.command(
        name="status",
        description="Change the bot's status/activity or start a game setup",
    )
    @app_commands.describe(
        status="online, idle, dnd, or offline",
        text="For example: Among Us, Roblox, or Watching YouTube",
    )
    async def status_slash(
        self,
        interaction: discord.Interaction,
        status: str,
        text: str,
    ):
        if not self.allowed(interaction.user, interaction.guild):
            return await interaction.response.send_message(
                "❌ Only the bot owner can change the bot status.",
                ephemeral=True,
            )

        game = self.normalize_game(text)

        if game in SUPPORTED_GAMES:
            await interaction.response.defer()
            normalized_game = "Among Us" if game == "among us" else "Roblox"

            result, error = await self.apply_status(status, normalized_game)
            if error:
                return await interaction.followup.send(error)

            self.game_setup[interaction.user.id] = {
                "game": normalized_game,
                "status": status.lower(),
                "channel_id": interaction.channel_id,
            }

            view = GameSetupView(
                self,
                interaction.user.id,
                normalized_game,
            )
            await interaction.followup.send(
                f"🎮 **{normalized_game}** setup started.\n"
                f"**Lobby or Ingame?**",
                view=view,
            )
            return

        result, error = await self.apply_status(status, text)
        await interaction.response.send_message(
            error or result,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(StatusCog(bot))
