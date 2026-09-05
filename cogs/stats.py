import discord
from discord.ext import commands
from discord import app_commands
import math
import json
import os

try:
    from functions import *
except ImportError:
    pass

LEADERBOARD_FILE = globals().get("LEADERBOARD_FILE", "leaderboard.json")
ENTRIES_PER_PAGE = 10

# Fixed emoji dictionary
emojis = {
    "statics": "<:Statics:1516148634675187883>",
    "storage": "<:Storage:1516148728845828116>",
    "apps": "<:Apps:1516149116453912576>",
    "members": "<:Members:1516149148326301756>",
}


def safe_load_json(filename, default=None):
    """Utility helper to safely read JSON files without crashing (used for emoji.json, not stats.json)."""
    if default is None:
        default = {}
    if not os.path.exists(filename):
        return default
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def record_user_app(user_id: int):
    """Separated function to safely track user app statistics."""
    stats_data = load_stats()
    if "user_apps" not in stats_data:
        stats_data["user_apps"] = []

    uid_str = str(user_id)
    if uid_str not in stats_data["user_apps"]:
        stats_data["user_apps"].append(uid_str)
        save_stats(stats_data)


class StatsLeaderboardView(discord.ui.View):
    def __init__(self, bot, initial_interaction: discord.Interaction = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.initial_interaction = initial_interaction
        self.message: discord.Message | None = None
        self.mode = "stats"
        self.current_page = 0
        self.total_pages = 1
        self.entries = []
        self.update_buttons()

    def _build_global_entries(self):
        best_per_user = {}
        for doc in leaderboard_col.find({"current_streak": {"$gt": 0}}):
            uid = doc.get("user_id")
            current = doc.get("current_streak", 0)
            gid = doc.get("guild_id")
            guild = self.bot.get_guild(int(gid)) if gid else None
            server_name = guild.name if guild else "Unknown Server"

            if uid not in best_per_user or current > best_per_user[uid]["current_streak"]:
                best_per_user[uid] = {
                    "username": doc.get("username", "Unknown"),
                    "current_streak": current,
                    "server_name": server_name,
                }
        return sorted(best_per_user.values(), key=lambda x: x["current_streak"], reverse=True)

    def build_stats_embed(self):
        stats_data = load_stats()
        apps_count = len(stats_data.get("user_apps", []))

        apps_display = str(apps_count) if apps_count > 0 else "SOON"
        server_count = len(self.bot.guilds)
        total_members = sum(getattr(g, "member_count", 0) or 0 for g in self.bot.guilds)

        embed = discord.Embed(title=f"{emojis['statics']} Bot Statistics", color=0x2F3136)
        embed.description = (
            f"{emojis['storage']} **Total Servers:** `{server_count}`\n"
            f"{emojis['apps']} **Total User Apps:** `{apps_display}`\n"
            f"{emojis['members']} **Total Members:** `{total_members}`"
        )
        return embed

    def build_lb_embed(self):
        start = self.current_page * ENTRIES_PER_PAGE
        end = start + ENTRIES_PER_PAGE
        page_entries = self.entries[start:end]
        page_label = f"Page {self.current_page + 1}/{self.total_pages}"

        embed = discord.Embed(title=f"🏆 Global Leaderboard — {page_label}", color=0x2F3136)

        if not page_entries:
            embed.description = "No entries found."
            return embed

        emoji_data = safe_load_json("emoji.json", {})
        streak_emojis = emoji_data.get("streaks", {}) if isinstance(emoji_data, dict) else {}

        lines = []
        for i, entry in enumerate(page_entries, start + 1):
            username = entry.get("username", "Unknown")
            current = entry.get("current_streak", 0)

            streak_emoji = ""
            if current > 0:
                for key, val in streak_emojis.items():
                    if "-" in key:
                        try:
                            low, high = map(int, key.split("-"))
                            if low <= current <= high:
                                streak_emoji = f" {val}" if str(val).strip() else " 🔥"
                                break
                        except ValueError:
                            continue

            server_name = entry.get("server_name", "Unknown Server")
            lines.append(f"**{i}.** {username} — Streak: **{current}**{streak_emoji} — *{server_name}*")

        embed.description = "\n".join(lines)
        return embed

    def build_servers_embed(self):
        embed = discord.Embed(title=f"{emojis['storage']} Connected Servers List", color=0x2F3136)
        server_names = [g.name for g in self.bot.guilds]
        
        if not server_names:
            embed.description = "No connected servers found."
            return embed

        formatted_list = []
        current_len = 0
        for name in server_names:
            line = f"• {name}\n"
            if current_len + len(line) > 3800:
                formatted_list.append(f"\n*...and {len(server_names) - len(formatted_list)} more servers.*")
                break
            formatted_list.append(line)
            current_len += len(line)

        embed.description = "".join(formatted_list)
        return embed

    def update_buttons(self):
        self.clear_items()

        if self.mode == "stats":
            btn1 = discord.ui.Button(label="Leaderboard", style=discord.ButtonStyle.primary, row=0)
            btn1.callback = self.lb_callback
            self.add_item(btn1)

            btn2 = discord.ui.Button(label="Servers", style=discord.ButtonStyle.secondary, row=0)
            btn2.callback = self.srv_callback
            self.add_item(btn2)

        elif self.mode == "leaderboard":
            prev = discord.ui.Button(label="<", style=discord.ButtonStyle.secondary, disabled=self.current_page == 0, row=0)
            prev.callback = self.prev_callback
            self.add_item(prev)

            nextb = discord.ui.Button(label=">", style=discord.ButtonStyle.secondary, disabled=self.current_page >= self.total_pages - 1, row=0)
            nextb.callback = self.next_callback
            self.add_item(nextb)

            back = discord.ui.Button(label="Go Back", style=discord.ButtonStyle.danger, row=1)
            back.callback = self.back_callback
            self.add_item(back)

        elif self.mode in ("servers", "no_permission"):
            back = discord.ui.Button(label="Go Back", style=discord.ButtonStyle.danger, row=0)
            back.callback = self.back_callback
            self.add_item(back)

    async def safe_edit(self, interaction: discord.Interaction, **kwargs):
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(**kwargs)
            else:
                await interaction.followup.edit_message(message_id=interaction.message.id, **kwargs)
        except Exception as e:
            try:
                await interaction.followup.send(f"An error occurred: `{e}`", ephemeral=True)
            except Exception:
                pass

    async def lb_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.entries = self._build_global_entries()
        self.total_pages = max(1, math.ceil(len(self.entries) / ENTRIES_PER_PAGE))
        self.current_page = 0
        self.mode = "leaderboard"
        self.update_buttons()
        await self.safe_edit(interaction, content=None, embed=self.build_lb_embed(), view=self)

    async def srv_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        is_operator = globals().get("is_op", lambda uid: True)(interaction.user.id)

        if not is_operator:
            self.mode = "no_permission"
            self.update_buttons()
            await self.safe_edit(interaction, content="❌ You do not have permission to view server details.", embed=None, view=self)
            return

        self.mode = "servers"
        self.update_buttons()
        await self.safe_edit(interaction, content=None, embed=self.build_servers_embed(), view=self)

    async def prev_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await self.safe_edit(interaction, embed=self.build_lb_embed(), view=self)

    async def next_callback(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.total_pages + 1)
        self.update_buttons()
        await self.safe_edit(interaction, embed=self.build_lb_embed(), view=self)

    async def back_callback(self, interaction: discord.Interaction):
        self.mode = "stats"
        self.update_buttons()
        await self.safe_edit(interaction, content=None, embed=self.build_stats_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
            else:
                await self.initial_interaction.edit_original_response(view=self)
        except Exception:
            pass


class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Displays the bot's current statistics")
    async def show_stats(self, interaction: discord.Interaction):
        await interaction.response.defer()

        record_user_app(interaction.user.id)

        view = StatsLeaderboardView(self.bot, interaction)
        embed = view.build_stats_embed()

        view.message = await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
