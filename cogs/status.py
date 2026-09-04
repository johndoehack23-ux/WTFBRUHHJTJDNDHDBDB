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


def make_activity(text: str):
    text = str(text).strip()
    if not text:
        return None, "Please provide activity text."

    # Special case: railway.com → Listening (purple icon)
    if text.lower() in {"railway.com", "railway"}:
        return discord.Activity(
            type=discord.ActivityType.listening,
            name="railway.com",
        ), None

    lowered = text.lower()
    for prefix, activity_type in ACTIVITY_PREFIXES.items():
        if lowered == prefix:
            return None, f"Please add text after `{prefix.title()}`."
        if lowered.startswith(prefix + " "):
            label = text[len(prefix):].strip()
            return discord.Activity(type=activity_type, name=label), None

    # Default to Playing
    return discord.Game(name=text), None


class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_activity = None

    def allowed(self, user, guild=None):
        return user.id == STATUS_OWNER_ID

    async def apply_status(self, status: str, text: str = None):
        status = status.lower().strip()
        if status not in STATUS_NAMES:
            return None, "Status must be `online`, `idle`, `dnd`, or `offline`."

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

        # Nice label for the reply
        if activity.type == discord.ActivityType.listening:
            activity_label = f"Listening to **{activity.name}** 🟣"
        else:
            activity_label = str(activity)

        return (
            f"✅ Status set to **{status}**\n"
            f"Activity: {activity_label}",
            None,
        )

    @commands.command(name="stopstatus")
    async def stop_status(self, ctx):
        if ctx.author.id != STATUS_OWNER_ID:
            return await ctx.send("❌ Only the bot owner can stop the bot status.")

        await self.bot.change_presence(
            status=discord.Status.online,
            activity=None,
        )
        self.current_activity = None
        await ctx.send("✅ Bot status and activity stopped.")

    @commands.command(name="status", aliases=["starus"])
    async def status_prefix(self, ctx, status: str = None, *, text: str = None):
        if not self.allowed(ctx.author, ctx.guild):
            return await ctx.send("❌ Only the bot owner can change the bot status.")

        if not status:
            return await ctx.send(
                "Usage:\n"
                "• `.status <online|idle|dnd|offline>` → just color (🟢🟡🔴⚫)\n"
                "• `.status <status> \"railway.com\"` → Listening to railway.com (🟣)\n"
                "• `.status <status> \"Watching YouTube\"` → custom activity\n"
                "Example: `.status online \"railway.com\"`"
            )

        result, error = await self.apply_status(status, text)
        await ctx.send(error or result)

    @app_commands.command(
        name="status",
        description="Change the bot's status/activity",
    )
    @app_commands.describe(
        status="online, idle, dnd, or offline",
        text="Leave empty for just color. Use \"railway.com\" for Listening.",
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

        result, error = await self.apply_status(status, text)
        await interaction.response.send_message(
            error or result,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(StatusCog(bot))
