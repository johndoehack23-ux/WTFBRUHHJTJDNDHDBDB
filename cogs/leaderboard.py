import discord
from discord.ext import commands
from discord import app_commands
import math
from functions import *

ENTRIES_PER_PAGE = 10


class PageModal(discord.ui.Modal, title="Go to Page"):
    page_input = discord.ui.TextInput(
        label="Page Number",
        placeholder="Enter a page number...",
        min_length=1,
        max_length=6
    )

    def __init__(self, view):
        super().__init__()
        self.lb_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_input.value) - 1
        except ValueError:
            return await interaction.response.send_message("❌ Invalid page number.", ephemeral=True)
        if page < 0 or page >= self.lb_view.total_pages:
            return await interaction.response.send_message(
                f"❌ Page must be between 1 and {self.lb_view.total_pages}.", ephemeral=True
            )
        self.lb_view.current_page = page
        self.lb_view.show_all = False
        self.lb_view.update_buttons()
        await interaction.response.edit_message(embed=self.lb_view.build_embed(), view=self.lb_view)


class LeaderboardView(discord.ui.View):
    def __init__(self, entries, mode, guild_name=""):
        super().__init__(timeout=120)
        self.entries = entries
        self.mode = mode
        self.guild_name = guild_name
        self.current_page = 0
        self.show_all = False
        self.total_pages = max(1, math.ceil(len(entries) / ENTRIES_PER_PAGE))
        self.update_buttons()

    def build_embed(self):
        if self.show_all:
            page_entries = self.entries
            page_label = "All"
            start_rank = 0
        else:
            start = self.current_page * ENTRIES_PER_PAGE
            end = start + ENTRIES_PER_PAGE
            page_entries = self.entries[start:end]
            page_label = f"Page {self.current_page + 1}/{self.total_pages}"
            start_rank = self.current_page * ENTRIES_PER_PAGE

        if self.mode == "global":
            title = f"🏆 Global Leaderboard — {page_label}"
        else:
            title = f"🏆 {self.guild_name} — {page_label}"

        embed = discord.Embed(title=title, color=0x2f3136)

        if not page_entries:
            embed.description = "No entries found."
            return embed

        lines = []
        for i, entry in enumerate(page_entries, start_rank + 1):
            username = entry.get("username", "Unknown")
            best = entry.get("best_streak", 0)
            current = entry.get("current_streak", 0)
            if self.mode == "global":
                server_name = entry.get("server_name", "Unknown Server")
                lines.append(
                    f"**{i}.** {username} — Best: **{best}** | Current: **{current}** — {server_name} 👍"
                )
            else:
                lines.append(
                    f"**{i}.** {username} — Best: **{best}** | Current: **{current}**"
                )

        embed.description = "\n".join(lines)
        return embed

    def update_buttons(self):
        self.clear_items()

        # ── Row 0: < 1 2 3 4 5 ──
        prev = discord.ui.Button(
            label="<",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page == 0 or self.show_all),
            row=0
        )
        async def prev_cb(interaction: discord.Interaction, v=self):
            v.current_page = max(0, v.current_page - 1)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        prev.callback = prev_cb
        self.add_item(prev)

        for p in range(1, 6):
            is_cur = (not self.show_all and self.current_page == p - 1)
            b = discord.ui.Button(
                label=str(p),
                style=discord.ButtonStyle.primary if is_cur else discord.ButtonStyle.secondary,
                disabled=(p > self.total_pages or self.show_all),
                row=0
            )
            async def _pcb(interaction: discord.Interaction, pg=p - 1, v=self):
                v.current_page = pg
                v.show_all = False
                v.update_buttons()
                await interaction.response.edit_message(embed=v.build_embed(), view=v)
            b.callback = _pcb
            self.add_item(b)

        # ── Row 1: 6 7 8 9 10 > ──
        for p in range(6, 11):
            is_cur = (not self.show_all and self.current_page == p - 1)
            b = discord.ui.Button(
                label=str(p),
                style=discord.ButtonStyle.primary if is_cur else discord.ButtonStyle.secondary,
                disabled=(p > self.total_pages or self.show_all),
                row=1
            )
            async def _pcb2(interaction: discord.Interaction, pg=p - 1, v=self):
                v.current_page = pg
                v.show_all = False
                v.update_buttons()
                await interaction.response.edit_message(embed=v.build_embed(), view=v)
            b.callback = _pcb2
            self.add_item(b)

        nxt = discord.ui.Button(
            label=">",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page >= self.total_pages - 1 or self.show_all),
            row=1
        )
        async def next_cb(interaction: discord.Interaction, v=self):
            v.current_page = min(v.total_pages - 1, v.current_page + 1)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        nxt.callback = next_cb
        self.add_item(nxt)

        # ── Row 2: Infinite | Enter Page ──
        inf = discord.ui.Button(
            label="Paginated" if self.show_all else "Infinite",
            style=discord.ButtonStyle.success if self.show_all else discord.ButtonStyle.secondary,
            row=2
        )
        async def inf_cb(interaction: discord.Interaction, v=self):
            v.show_all = not v.show_all
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        inf.callback = inf_cb
        self.add_item(inf)

        ep = discord.ui.Button(
            label="Enter Page",
            style=discord.ButtonStyle.secondary,
            disabled=self.show_all,
            row=2
        )
        async def ep_cb(interaction: discord.Interaction, v=self):
            await interaction.response.send_modal(PageModal(v))
        ep.callback = ep_cb
        self.add_item(ep)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _build_global_entries(self):
        entries = []
        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        for gid, users in data.get("servers", {}).items():
            guild = self.bot.get_guild(int(gid))
            server_name = guild.name if guild else f"Server {gid}"
            for uid, d in users.items():
                entries.append({
                    "username": d.get("username", "Unknown"),
                    "best_streak": d.get("best_streak", 0),
                    "current_streak": d.get("current_streak", 0),
                    "server_name": server_name
                })
        entries.sort(key=lambda x: x["best_streak"], reverse=True)
        return entries

    def _build_server_entries(self, guild_id):
        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        srv = data.get("servers", {}).get(str(guild_id), {})
        entries = []
        for uid, d in srv.items():
            entries.append({
                "username": d.get("username", "Unknown"),
                "best_streak": d.get("best_streak", 0),
                "current_streak": d.get("current_streak", 0),
            })
        entries.sort(key=lambda x: x["best_streak"], reverse=True)
        return entries

    @commands.command(name="leaderboard", aliases=["lb"])
    async def lb(self, ctx, scope: str = "global"):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        scope = scope.lower().strip()
        if scope not in ("global", "server"):
            return await ctx.send("❌ Usage: `+leaderboard global` or `+leaderboard server` (default: global)")

        if scope == "global":
            entries = self._build_global_entries()
            if not entries:
                return await ctx.send("🏆 No stats yet globally!")
            view = LeaderboardView(entries, mode="global")
        else:
            entries = self._build_server_entries(ctx.guild.id)
            if not entries:
                return await ctx.send("🏆 No stats yet for this server!")
            view = LeaderboardView(entries, mode="server", guild_name=ctx.guild.name)

        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name="rlb")
    async def rlb(self, ctx):
        if not is_admin(ctx.author.id):
            return await ctx.send("🔐 Denied Access")

        leaderboard["servers"][str(ctx.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send("🧹 Leaderboard has been reset.")

    @commands.command(name="lb-best", aliases=["leaderboard-best"])
    async def lb_best(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        srv = get_server_lb(ctx.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_best = srv[uid].get("best_streak", 0)
        srv[uid]["best_streak"] = num
        srv[uid]["username"] = user.name
        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`")

    @commands.command(name="lb-current", aliases=["leaderboard-current"])
    async def lb_current(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        srv = get_server_lb(ctx.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_current = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name

        if num > srv[uid].get("best_streak", 0):
            srv[uid]["best_streak"] = num

        save_json(LEADERBOARD_FILE, leaderboard)
        await ctx.send(f"✅ Updated **{user.name}** current streak: `{old_current}` → `{num}`")

    @app_commands.command(name="leaderboard", description="Show the wordle leaderboard")
    @app_commands.describe(scope="global (all servers) or server (this server only)")
    async def lb_slash(self, interaction: discord.Interaction, scope: str = "global"):
        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        scope = scope.lower().strip()
        if scope not in ("global", "server"):
            scope = "global"

        if scope == "global":
            entries = self._build_global_entries()
            if not entries:
                return await interaction.response.send_message("🏆 No stats yet globally!", ephemeral=True)
            view = LeaderboardView(entries, mode="global")
        else:
            entries = self._build_server_entries(interaction.guild.id)
            if not entries:
                return await interaction.response.send_message("🏆 No stats yet for this server!", ephemeral=True)
            view = LeaderboardView(entries, mode="server", guild_name=interaction.guild.name)

        await interaction.response.send_message(embed=view.build_embed(), view=view)

    @app_commands.command(name="rlb", description="Reset the server leaderboard (admin only)")
    async def rlb_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        leaderboard["servers"][str(interaction.guild.id)] = {}
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message("🧹 Leaderboard has been reset.", ephemeral=True)

    @app_commands.command(name="lb-best", description="Set a user's best streak (admin only)")
    @app_commands.describe(user="Target user", num="New best streak value")
    async def lb_best_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        srv = get_server_lb(interaction.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_best = srv[uid].get("best_streak", 0)
        srv[uid]["best_streak"] = num
        srv[uid]["username"] = user.name
        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`", ephemeral=True)

    @app_commands.command(name="lb-current", description="Set a user's current streak (admin only)")
    @app_commands.describe(user="Target user", num="New current streak value")
    async def lb_current_slash(self, interaction: discord.Interaction, user: discord.Member, num: int):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        srv = get_server_lb(interaction.guild.id)
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0, "best_streak": 0}

        old_current = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name

        if num > srv[uid].get("best_streak", 0):
            srv[uid]["best_streak"] = num

        save_json(LEADERBOARD_FILE, leaderboard)
        await interaction.response.send_message(f"✅ Updated **{user.name}** current streak: `{old_current}` → `{num}`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
