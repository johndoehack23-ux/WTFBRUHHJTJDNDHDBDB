import discord
from discord.ext import commands
from discord import app_commands
import math
import json
import os
from functions import *

ENTRIES_PER_PAGE = 10

emojis = {
    "statics": "<:Statics:1516148634675187883>",
    "storage": "<:Storage:1516148728845828116>",
    "apps": "<:Apps:1516149116453912576>",
    "members": "<:Members:1516149148326301756>",
}


class StatsLeaderboardView(discord.ui.View):
    def __init__(self, bot, initial_interaction):
        super().__init__(timeout=120)
        self.bot = bot
        self.initial_interaction = initial_interaction
        self.mode = "stats"

        self.lb_mode = "global"
        self.current_page = 0
        self.total_pages = 1
        self.entries = []

        self.update_view_items()

    def _build_global_entries(self):
        best_per_user = {}
        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        for gid, users in data.get("servers", {}).items():
            guild = self.bot.get_guild(int(gid))
            server_name = guild.name if guild else "Unknown Server"
            for uid, d in users.items():
                current = d.get("current_streak", 0)
                if current > 0:
                    if (
                        uid not in best_per_user
                        or current > best_per_user[uid]["current_streak"]
                    ):
                        best_per_user[uid] = {
                            "username": d.get("username", "Unknown"),
                            "current_streak": current,
                            "server_name": server_name,
                        }
        return sorted(
            best_per_user.values(), key=lambda x: x["current_streak"], reverse=True
        )

    def build_stats_embed(self):
        try:
            if self.initial_interaction.guild_id is None or is_admin(
                self.initial_interaction.user.id
            ):
                try:
                    stats_data = {}
                    if os.path.exists("stats.json"):
                        with open("stats.json", "r", encoding="utf-8") as f:
                            stats_data = json.load(f)

                    if "user_apps" not in stats_data:
                        stats_data["user_apps"] = []

                    user_id = str(self.initial_interaction.user.id)
                    if user_id not in stats_data["user_apps"]:
                        stats_data["user_apps"].append(user_id)
                        with open("stats.json", "w", encoding="utf-8") as f:
                            json.dump(stats_data, f, indent=4)
                except:
                    pass

            try:
                with open("stats.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    apps_count = len(data.get("user_apps", []))
            except:
                apps_count = 0

            apps_display = str(apps_count) if apps_count > 0 else "SOON"
            server_count = len(self.bot.guilds)

            total_members = 0
            for guild in self.bot.guilds:
                if guild.member_count is not None:
                    total_members += guild.member_count

            embed = discord.Embed(
                title=f"{emojis['statics']} Bot statistics.", color=0x2F3136
            )
            embed.description = (
                f"{emojis['storage']} **Total Servers:** `{server_count}`\n"
                f"{emojis['apps']} **Total User Apps:** `{apps_display}`\n"
                f"{emojis['members']} **Total Members:** `{total_members}`"
            )
            return embed
        except:
            return discord.Embed(title="Error loading stats", color=0x2F3136)

    def build_lb_embed(self):
        start = self.current_page * ENTRIES_PER_PAGE
        end = start + ENTRIES_PER_PAGE
        page_entries = self.entries[start:end]
        page_label = f"Page {self.current_page + 1}/{self.total_pages}"

        title = f"🏆 Global Leaderboard — {page_label}"
        embed = discord.Embed(title=title, color=0x2F3136)

        if not page_entries:
            embed.description = "No entries found."
            return embed

        streak_emojis = {}
        try:
            with open("emoji.json", "r", encoding="utf-8") as f:
                streak_emojis = json.load(f).get("streaks", {})
        except:
            pass

        lines = []
        start_rank = self.current_page * ENTRIES_PER_PAGE
        for i, entry in enumerate(page_entries, start_rank + 1):
            username = entry.get("username", "Unknown")
            current = entry.get("current_streak", 0)

            streak_emoji = ""
            if current > 0:
                for key, val in streak_emojis.items():
                    if "-" in key:
                        try:
                            low, high = map(int, key.split("-"))
                            if low <= current <= high:
                                streak_emoji = f" {val}" if val.strip() else " 🔥"
                                break
                        except ValueError:
                            continue

            server_name = entry.get("server_name", "Unknown Server")
            lines.append(
                f"**{i}.** {username} — Streak: **{current}**{streak_emoji} — {server_name}"
            )

        embed.description = "\n".join(lines)
        return embed

    def build_servers_embed(self):
        embed = discord.Embed(title=f"{emojis['storage']} Connected Servers List", color=0x2F3136)
        server_names = [guild.name for guild in self.bot.guilds]

        if server_names:
            embed.description = f"**Servers:**\n" + "\n".join(server_names)
        else:
            embed.description = "The bot is not currently in any servers."

        return embed

    def update_view_items(self):
        self.clear_items()

        if self.mode == "stats":
            lb_button = discord.ui.Button(
                label="Leaderboard", style=discord.ButtonStyle.primary, row=0
            )

            async def lb_callback(interaction: discord.Interaction):
                self.entries = self._build_global_entries()
                self.total_pages = max(
                    1, math.ceil(len(self.entries) / ENTRIES_PER_PAGE)
                )
                self.current_page = 0
                self.mode = "leaderboard"
                self.update_view_items()
                await interaction.response.edit_message(
                    embed=self.build_lb_embed(), view=self
                )

            lb_button.callback = lb_callback
            self.add_item(lb_button)

            srv_button = discord.ui.Button(
                label="Servers", style=discord.ButtonStyle.secondary, row=0
            )

            async def srv_callback(interaction: discord.Interaction):
                if not is_op(interaction.user.id):
                    self.mode = "no_permission"
                    self.update_view_items()
                    return await interaction.response.edit_message(
                        content="You do not have permission to enter here",
                        embed=None,
                        view=self,
                    )

                self.mode = "servers"
                self.update_view_items()
                await interaction.response.edit_message(
                    embed=self.build_servers_embed(), view=self
                )

            srv_button.callback = srv_callback
            self.add_item(srv_button)

        elif self.mode == "leaderboard":
            prev_btn = discord.ui.Button(
                label="<",
                style=discord.ButtonStyle.secondary,
                disabled=(self.current_page == 0),
                row=0,
            )

            async def prev_callback(interaction: discord.Interaction):
                self.current_page = max(0, self.current_page - 1)
                self.update_view_items()
                await interaction.response.edit_message(
                    embed=self.build_lb_embed(), view=self
                )

            prev_btn.callback = prev_callback
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(
                label=">",
                style=discord.ButtonStyle.secondary,
                disabled=(self.current_page >= self.total_pages - 1),
                row=0,
            )

            async def next_callback(interaction: discord.Interaction):
                self.current_page = min(self.total_pages - 1, self.current_page + 1)
                self.update_view_items()
                await interaction.response.edit_message(
                    embed=self.build_lb_embed(), view=self
                )

            next_btn.callback = next_callback
            self.add_item(next_btn)

            back_btn = discord.ui.Button(
                label="Go Back", style=discord.ButtonStyle.danger, row=1
            )

            async def back_callback(interaction: discord.Interaction):
                self.mode = "stats"
                self.update_view_items()
                await interaction.response.edit_message(
                    embed=self.build_stats_embed(), view=self
                )

            back_btn.callback = back_callback
            self.add_item(back_btn)

        elif self.mode == "servers":
            back_btn = discord.ui.Button(
                label="Go Back", style=discord.ButtonStyle.danger, row=0
            )

            async def back_callback(interaction: discord.Interaction):
                self.mode = "stats"
                self.update_view_items()
                await interaction.response.edit_message(
                    embed=self.build_stats_embed(), view=self
                )

            back_btn.callback = back_callback
            self.add_item(back_btn)

        elif self.mode == "no_permission":
            back_btn = discord.ui.Button(
                label="Go Back", style=discord.ButtonStyle.danger, row=0
            )

            async def back_callback(interaction: discord.Interaction):
                self.mode = "stats"
                self.update_view_items()
                # Clear the text content field back out when returning to the original embed layout
                await interaction.response.edit_message(
                    content=None, embed=self.build_stats_embed(), view=self
                )

            back_btn.callback = back_callback
            self.add_item(back_btn)

    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True
            await self.initial_interaction.edit_original_response(view=self)
        except:
            pass


class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="stats", description="Displays the bot's current statistics"
    )
    async def show_stats(self, interaction: discord.Interaction):
        try:
            view = StatsLeaderboardView(self.bot, interaction)
            await interaction.response.send_message(
                embed=view.build_stats_embed(), view=view
            )
        except:
            pass


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
    