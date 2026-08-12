import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands

from functions import is_admin, is_op


STATUS_NAMES = {"online", "idle", "dnd", "offline"}
ACTIVITY_PREFIXES = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "streaming": discord.ActivityType.streaming,
}
UNIT_SECONDS = {
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "hour": 3600,
    "hours": 3600,
    "day": 86400,
    "days": 86400,
    "week": 604800,
    "weeks": 604800,
    "month": 2592000,
    "months": 2592000,
    "year": 31536000,
    "years": 31536000,
}


def parse_timer(value):
    if value is None or not str(value).strip():
        return None, "Infinite"
    cleaned = str(value).strip().lower()
    if cleaned == "off":
        return None, "No timer"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z]+)", cleaned)
    if not match or match.group(2) not in UNIT_SECONDS:
        return "invalid", None
    seconds = float(match.group(1)) * UNIT_SECONDS[match.group(2)]
    if seconds <= 0:
        return "invalid", None
    return seconds, str(value).strip()


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


def format_duration(seconds):
    remaining = int(seconds)
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, secs = divmod(remaining, 60)
    pieces = []
    if days:
        pieces.append(f"{days}d")
    if hours:
        pieces.append(f"{hours}h")
    if minutes:
        pieces.append(f"{minutes}m")
    if secs or not pieces:
        pieces.append(f"{secs}s")
    return " ".join(pieces)


class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.expiry_task = None
        self.current_activity = None

    def allowed(self, user, guild):
        return bool(guild and (is_admin(user.id, guild) or is_op(user.id)))

    async def apply_status(self, status, text, state, timer, attachment=None):
        status = status.lower().strip()
        state = state.lower().strip()
        if status not in STATUS_NAMES:
            return None, "Status must be `online`, `idle`, `dnd`, or `offline`."
        if state not in {"on", "off"}:
            return None, "Activity must be `on` or `off`."

        timer_seconds, timer_label = parse_timer(timer)
        if timer_seconds == "invalid":
            return None, "Timer must be blank, `off`, or a number followed by min, hour, day, week, month, or year."

        activity = None
        if state == "on":
            activity, error = make_activity(text)
            if error:
                return None, error

        if self.expiry_task:
            self.expiry_task.cancel()
            self.expiry_task = None

        await self.bot.change_presence(
            status=getattr(discord.Status, status),
            activity=activity,
        )
        self.current_activity = activity

        if state == "on" and timer_seconds:
            self.expiry_task = asyncio.create_task(self.clear_after(timer_seconds))

        image_note = ""
        if attachment:
            image_note = (
                f"\nImage received: [open image]({attachment.url})"
                "\nDiscord bot presence cannot display uploaded custom images, so it is shown in this confirmation."
            )
        activity_label = str(activity) if activity else "No activity"
        return (
            f"✅ Status set to **{status}**\n"
            f"Activity: **{activity_label}**\n"
            f"Timer: **{timer_label if state == 'on' else 'Not used'}**"
            f"{image_note}",
            None,
        )

    async def clear_after(self, seconds):
        try:
            await asyncio.sleep(seconds)
            await self.bot.change_presence(status=discord.Status.online, activity=None)
            self.current_activity = None
            self.expiry_task = None
        except asyncio.CancelledError:
            pass

    @commands.command(name="status")
    async def status_prefix(self, ctx, status: str = None, text: str = None, state: str = None, *, timer: str = None):
        if not self.allowed(ctx.author, ctx.guild):
            return await ctx.send("❌ Only an admin or op can change the bot status.")
        if not status or not state:
            return await ctx.send(
                "Usage: `.status <online|idle|dnd|offline> \"<text>\" <on|off> [timer]`\n"
                "Example: `.status online \"Watching YouTube\" on 1 hour`"
            )

        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        result, error = await self.apply_status(status, text, state, timer, attachment)
        await ctx.send(error or result)

    @app_commands.command(name="status", description="Change the bot's status and activity")
    @app_commands.describe(
        status="online, idle, dnd, or offline",
        text="For example: Watching YouTube or Playing Among Us",
        state="Turn the activity on or off",
        timer="Blank, off, or e.g. 10 min, 2 hours, 1 day",
        image="Optional image shown in the confirmation message",
    )
    async def status_slash(
        self,
        interaction: discord.Interaction,
        status: str,
        text: str,
        state: str,
        timer: str = None,
        image: discord.Attachment = None,
    ):
        if not self.allowed(interaction.user, interaction.guild):
            return await interaction.response.send_message(
                "❌ Only an admin or op can change the bot status.", ephemeral=True
            )
        result, error = await self.apply_status(status, text, state, timer, image)
        await interaction.response.send_message(error or result, ephemeral=True)


async def setup(bot):
    await bot.add_cog(StatusCog(bot))