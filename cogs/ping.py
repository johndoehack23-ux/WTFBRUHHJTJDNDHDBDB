import discord
from discord.ext import commands
from discord import app_commands
import pytz
import json
from functions import *

TIMEZONE_FILE = "timezone_config.json"

TIMEZONE_MAP = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "est": "America/New_York",
    "edt": "America/New_York",
    "gmt": "UTC",
    "utc": "UTC",
    "jst": "Asia/Tokyo",
    "aest": "Australia/Sydney",
    "cet": "Europe/Paris",
    "ist": "Asia/Kolkata",
    "bst": "Europe/London",
    "hst": "Pacific/Honolulu",
    "akst": "America/Anchorage",
    "sgt": "Asia/Singapore",
    "pht": "Asia/Manila",
}

def save_timezone(tz_name: str):
    with open(TIMEZONE_FILE, "w") as f:
        json.dump({"timezone": tz_name}, f, indent=4)

def get_current_timezone() -> str:
    try:
        with open(TIMEZONE_FILE, "r") as f:
            return json.load(f).get("timezone", "America/Los_Angeles")
    except Exception:
        return "America/Los_Angeles"

def resolve_timezone(region: str):
    """Resolves a short abbreviation or full IANA name. Returns (iana_name, display_name) or None."""
    clean = region.strip().lower()
    if clean in TIMEZONE_MAP:
        return TIMEZONE_MAP[clean], region.upper()
    # Try as raw IANA name
    try:
        pytz.timezone(region)
        return region, region
    except pytz.UnknownTimeZoneError:
        return None, None


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        await ctx.send(f"Pong! {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.bot.latency * 1000)}ms")

    @commands.command(name="timezone")
    async def timezone_prefix(self, ctx, region: str = None):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access.")

        current_iana = get_current_timezone()
        current_abbr = next((k.upper() for k, v in TIMEZONE_MAP.items() if v == current_iana), current_iana)

        if not region:
            return await ctx.send(
                f"🕐 Current timezone: **{current_abbr}** (`{current_iana}`)\n"
                f"Usage: `.timezone <region>` — e.g. `.timezone PST`, `.timezone EST`, `.timezone JST`"
            )

        iana, display = resolve_timezone(region)
        if not iana:
            return await ctx.send(
                f"❌ Unknown timezone `{region}`.\n"
                f"Try: `PST`, `EST`, `CST`, `MST`, `GMT`, `UTC`, `JST`, `IST`, `SGT`, `PHT`, `AEST`, `BST`, `CET`, `HST`, `AKST`"
            )

        save_timezone(iana)
        await ctx.send(f"✅ Self-ping timezone set to **{display}** (`{iana}`)")

    @app_commands.command(name="timezone", description="Set the self-ping clock timezone (admin only)")
    @app_commands.describe(region="Timezone abbreviation e.g. PST, EST, JST, UTC")
    async def timezone_slash(self, interaction: discord.Interaction, region: str = None):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("🔐 Denied Access.", ephemeral=True)

        current_iana = get_current_timezone()
        current_abbr = next((k.upper() for k, v in TIMEZONE_MAP.items() if v == current_iana), current_iana)

        if not region:
            return await interaction.response.send_message(
                f"🕐 Current timezone: **{current_abbr}** (`{current_iana}`)\n"
                f"Usage: `/timezone <region>` — e.g. `PST`, `EST`, `JST`",
                ephemeral=True
            )

        iana, display = resolve_timezone(region)
        if not iana:
            return await interaction.response.send_message(
                f"❌ Unknown timezone `{region}`.\n"
                f"Try: `PST`, `EST`, `CST`, `MST`, `GMT`, `UTC`, `JST`, `IST`, `SGT`, `PHT`, `AEST`, `BST`, `CET`, `HST`, `AKST`",
                ephemeral=True
            )

        save_timezone(iana)
        await interaction.response.send_message(
            f"✅ Self-ping timezone set to **{display}** (`{iana}`)",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(PingCog(bot))
