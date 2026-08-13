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


def make_activity(text):
    text = str(text).strip()
    if not text:
        return None, "Please provide activity text, for example `Watching YouTube`."

    lowered = text.lower()
    for prefix, activity_type in ACTIVITY_PREFIXES.items():
        if lowered == prefix:
            return None, f"Please add text after `{prefix.title()}`."
        if lowered.startswith(prefix + " "):
            label = text[len(prefix):].strip()
            return discord.Activity(type=activity_type, name=label), None

    # If no type is supplied, use Discord's standard Playing activity.
    return discord.Game(name=text), None


class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_activity = None

    def allowed(self, user, guild=None):
        return user.id == STATUS_OWNER_ID

    async def apply_status(self, status, text):
        status = status.lower().strip()
        if status not in STATUS_NAMES:
            return None, "Status must be `online`, `idle`, `dnd`, or `offline`."

        text = str(text).strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"\"", "'"}:
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

    @commands.command(name="stopstatus")
    async def stop_status(self, ctx):
        if ctx.author.id != STATUS_OWNER_ID:
            return await ctx.send("❌ Only the bot owner can stop the bot status.")

        await self.bot.change_presence(status=discord.Status.online, activity=None)
        self.current_activity = None
        await ctx.send("✅ Bot status and activity stopped.")

    @commands.command(name="status", aliases=["starus"])
    async def status_prefix(self, ctx, status: str = None, *, text: str = None):
        if not self.allowed(ctx.author, ctx.guild):
            return await ctx.send("❌ Only the bot owner can change the bot status.")
        if not status or not text:
            return await ctx.send(
                "Usage: `.status <online|idle|dnd|offline> \"<activity text>\"`\n"
                "Example: `.status online \"Watching YouTube\"`"
            )

        result, error = await self.apply_status(status, text)
        await ctx.send(error or result)

    @app_commands.command(name="status", description="Change the bot's status and activity")
    @app_commands.describe(
        status="online, idle, dnd, or offline",
        text="For example: Watching YouTube or Playing Among Us",
    )
    async def status_slash(
        self,
        interaction: discord.Interaction,
        status: str,
        text: str,
    ):
        if not self.allowed(interaction.user, interaction.guild):
            return await interaction.response.send_message(
                "❌ Only the bot owner can change the bot status.", ephemeral=True
            )
        result, error = await self.apply_status(status, text)
        await interaction.response.send_message(error or result, ephemeral=True)


async def setup(bot):
    await bot.add_cog(StatusCog(bot))