import asyncio
import time
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

# ~999 years in seconds (basically forever until stopped)
MAX_TIMER_SECONDS = 999 * 365 * 24 * 60 * 60


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


def format_elapsed(seconds: int) -> str:
    """Turn seconds into a readable timer string."""
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h < 24:
        return f"{h:02d}:{m:02d}:{s:02d}"
    d, h = divmod(h, 24)
    return f"{d}d {h:02d}:{m:02d}"


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
        self._timer_task = None
        self._timer_start = None
        self._timer_game = None
        self._timer_type = None
        self._timer_status = None

    def allowed(self, user, guild=None):
        return user.id == STATUS_OWNER_ID

    async def _cancel_timer(self):
        """Stop any running lobby/ingame timer."""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
        self._timer_task = None
        self._timer_start = None
        self._timer_game = None
        self._timer_type = None
        self._timer_status = None

    async def _timer_loop(self):
        """
        Keep updating presence with live elapsed time.
        Discord bots only reliably show the `name` field, so we pack
        Lobby / players / code / timer all into the name.
        """
        try:
            while True:
                elapsed = int(time.time() - self._timer_start)
                if elapsed >= MAX_TIMER_SECONDS:
                    # Hit the "999 year" limit — stop playing
                    await self.bot.change_presence(
                        status=discord.Status.online,
                        activity=None,
                    )
                    self.current_activity = None
                    break

                timer_str = format_elapsed(elapsed)
                game = self._timer_game
                game_type = self._timer_type
                status = self._timer_status

                if game_type == "Lobby":
                    if game == "Among Us":
                        # Everything goes in `name` so it actually shows
                        name = f"Among Us | Lobby • 1/15 • SUSSY • {timer_str}"
                    else:
                        name = f"Roblox | Lobby • 1 • SUSSY • {timer_str}"
                else:  # Ingame
                    name = f"{game} | Ingame • {timer_str}"

                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=name,
                )

                await self.bot.change_presence(status=status, activity=activity)
                self.current_activity = activity

                await asyncio.sleep(10)  # update every 10 seconds
        except asyncio.CancelledError:
            pass

    async def apply_status(self, status, text=None):
        """Set status (+ optional activity). Cancels any running game timer."""
        status = status.lower().strip()
        if status not in STATUS_NAMES:
            return None, "Status must be `online`, `idle`, `dnd`, or `offline`."

        await self._cancel_timer()

        # Just status color, no activity
        if text is None or str(text).strip() == "":
            await self.bot.change_presence(
                status=getattr(discord.Status, status),
                activity=None,
            )
            self.current_activity = None
            color_names = {
                "online": "🟢 green (online)",
                "idle": "🟡 yellow (idle)",
                "dnd": "🔴 red (dnd)",
                "offline": "⚫ gray (offline)",
            }
            return (
                f"✅ Status set to **{status}** — {color_names.get(status, status)}\n"
                f"Activity cleared.",
                None,
            )

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
        setup = self.game_setup.get(interaction.user.id, {})
        status_name = setup.get("status", "online")
        status = getattr(discord.Status, status_name, discord.Status.online)

        await self._cancel_timer()

        # Start live timer
        self._timer_start = time.time()
        self._timer_game = game
        self._timer_type = game_type
        self._timer_status = status
        self._timer_task = asyncio.create_task(self._timer_loop())

        if game_type == "Lobby":
            if game == "Among Us":
                message = (
                    "🟢 **Among Us — Lobby**\n\n"
                    "👥 Players: **1/15**\n"
                    "🔑 Code: **`SUSSY`**\n"
                    "⏱️ Live timer started (updates every 10s)\n\n"
                    "💡 Discord only shows the **name** for bots, so it will look like:\n"
                    "`Playing Among Us | Lobby • 1/15 • SUSSY • 00:42`"
                )
            else:
                message = (
                    "🟢 **Roblox — Lobby**\n\n"
                    "👥 Players: **1**\n"
                    "🔑 Code: **`SUSSY`**\n"
                    "⏱️ Live timer started (updates every 10s)\n\n"
                    "💡 Discord only shows the **name** for bots, so it will look like:\n"
                    "`Playing Roblox | Lobby • 1 • SUSSY • 00:42`"
                )
        else:
            message = (
                f"🔵 **{game} — Ingame**\n\n"
                "🎮 Status: **Ingame**\n"
                "⏱️ Live timer started (updates every 10s)\n\n"
                "💡 Discord only shows the **name** for bots, so it will look like:\n"
                f"`Playing {game} | Ingame • 00:42`"
            )

        await interaction.followup.send(message)
        self.game_setup.pop(interaction.user.id, None)

    @commands.command(name="stopstatus")
    async def stop_status(self, ctx):
        if ctx.author.id != STATUS_OWNER_ID:
            return await ctx.send("❌ Only the bot owner can stop the bot status.")

        await self._cancel_timer()
        await self.bot.change_presence(
            status=discord.Status.online,
            activity=None,
        )
        self.current_activity = None
        self.game_setup.pop(ctx.author.id, None)
        await ctx.send("✅ Bot status, activity and timer stopped.")

    @commands.command(name="status", aliases=["starus"])
    async def status_prefix(self, ctx, status: str = None, *, text: str = None):
        if not self.allowed(ctx.author, ctx.guild):
            return await ctx.send("❌ Only the bot owner can change the bot status.")

        if not status:
            return await ctx.send(
                "Usage:\n"
                "• `.status <online|idle|dnd|offline>` → just color (🟢🟡🔴⚫)\n"
                "• `.status <status> \"Among Us\"` → start game setup + timer\n"
                "• `.status <status> \"Watching YouTube\"` → custom activity\n"
                "Example: `.status online \"Among Us\"`"
            )

        # Only status given → just set the color, clear activity
        if text is None or str(text).strip() == "":
            result, error = await self.apply_status(status, None)
            return await ctx.send(error or result)

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
        text="Leave empty for just color. Or: Among Us, Roblox, Watching YouTube, etc.",
    )
    async def status_slash(
        self,
        interaction: discord.Interaction,
        status: str,
        text: str = None,
    ):
        if not self.allowed(interaction.user, interaction.guild):
            return await interaction.response.send_message(
                "❌ Only the bot owner can change the bot status.",
                ephemeral=True,
            )

        # Only status → just color
        if text is None or str(text).strip() == "":
            result, error = await self.apply_status(status, None)
            return await interaction.response.send_message(
                error or result,
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
