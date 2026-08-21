import os
import math
import secrets
import string
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient

# Import your custom configuration checks from functions.py
from functions import is_admin, is_op, is_maintenance_mode, load_stats

ENTRIES_PER_PAGE = 10
MAX_LEADERBOARD_PAGES = 1000

# ─── MONGODB CONNECTION INITIALIZATION ───
MONGO_URI = os.environ.get("MONGO_URI")
cluster = MongoClient(MONGO_URI)
db = cluster["WordleBotDB"]

# Database collections replacing your JSON files
leaderboard_col = db["wordle_leaderboards"]
deleted_col = db["deleted_leaderboards"]
page_cache_col = db["page_cache"]


def generate_undo_code():
    """Generates a random 5-character string (e.g., 'iq04b')"""
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(5))


class LeaderboardResetConfirmView(discord.ui.View):
    def __init__(self, ctx, scope: str):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.scope = scope

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ This confirmation window is not for you.", ephemeral=True)

        if self.scope == "global" and not is_op(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command as globally", ephemeral=True)
        if self.scope == "server" and not (is_admin(interaction.user.id, self.ctx.guild) or is_op(interaction.user.id)):
            return await interaction.response.send_message("You do not have permission to use this command", ephemeral=True)

        now_str = datetime.date.today().isoformat()
        undo_code = generate_undo_code()

        if self.scope == "global":
            all_documents = list(leaderboard_col.find({}, {"_id": 0}))
            server_names = []
            for doc in all_documents:
                gid = doc.get("guild_id")
                guild = self.ctx.bot.get_guild(int(gid)) if gid else None
                server_names.append(guild.name if guild else f"Unknown Server ({gid})")
            
            if not server_names:
                server_names = ["No Active Servers"]

            deleted_col.update_one(
                {"_id": "global_history"},
                {"$set": {f"global.{undo_code}": {
                    "backup_data": all_documents,
                    "server_names": server_names,
                    "date": now_str
                }}},
                upsert=True
            )

            leaderboard_col.delete_many({})
            await interaction.response.edit_message(content="🧹 **Global** leaderboard has been completely reset.", embed=None, view=None)
        else:
            gid_str = str(self.ctx.guild.id)
            server_docs = list(leaderboard_col.find({"guild_id": gid_str}, {"_id": 0}))

            deleted_col.update_one(
                {"_id": "server_history"},
                {"$set": {f"server.{gid_str}.{undo_code}": {
                    "backup_data": server_docs,
                    "server_name": self.ctx.guild.name,
                    "date": now_str
                }}},
                upsert=True
            )

            leaderboard_col.delete_many({"guild_id": gid_str})
            await interaction.response.edit_message(content="🧹 **Server** leaderboard has been reset.", embed=None, view=None)
        
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def confirm_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ This confirmation window is not for you.", ephemeral=True)
        
        await interaction.response.edit_message(content="❌ Leaderboard reset cancelled.", embed=None, view=None)
        self.stop()


class PageModal(discord.ui.Modal, title="Go to Page"):
    page_input = discord.ui.TextInput(
        label="Page Number",
        placeholder="Select a page (1-1000)",
        min_length=1,
        max_length=4
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
                f"❌ Page must be between 1 and {min(self.lb_view.total_pages, MAX_LEADERBOARD_PAGES)}.",
                ephemeral=True
            )
        self.lb_view.current_page = page
        self.lb_view.update_buttons()
        await interaction.response.edit_message(embed=self.lb_view.build_embed(), view=self.lb_view)


class LeaderboardView(discord.ui.View):
    def __init__(self, entries, mode, guild_name=""):
        super().__init__(timeout=120)
        self.entries = entries
        self.mode = mode
        self.guild_name = guild_name
        self.current_page = 0
        self.total_pages = min(
            MAX_LEADERBOARD_PAGES,
            max(1, math.ceil(len(entries) / ENTRIES_PER_PAGE)),
        )
        self.update_buttons()

    def build_embed(self):
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

        import json
        streak_emojis = {}
        try:
            with open("emoji.json", "r", encoding="utf-8") as f:
                streak_emojis = json.load(f).get("streaks", {})
        except Exception:
            pass

        lines = []
        for i, entry in enumerate(page_entries, start_rank + 1):
            username = entry.get("display_name") or entry.get("username", "Unknown")
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

            if self.mode == "global":
                server_name = entry.get("server_name", "Unknown Server")
                lines.append(f"**{i}.** {username} — Streak: **{current}**{streak_emoji} — {server_name}")
            else:
                lines.append(f"**{i}.** {username} — Streak: **{current}**{streak_emoji}")

        embed.description = "\n".join(lines)
        return embed

    def update_buttons(self):
        self.clear_items()

        for p in range(1, 11):
            is_cur = (self.current_page == p - 1)
            b = discord.ui.Button(
                label=str(p),
                style=discord.ButtonStyle.primary if is_cur else discord.ButtonStyle.secondary,
                disabled=(p > self.total_pages),
                row=0 if p <= 5 else 1
            )
            async def _pcb(interaction: discord.Interaction, pg=p - 1, v=self):
                v.current_page = pg
                v.update_buttons()
                await interaction.response.edit_message(embed=v.build_embed(), view=v)
            b.callback = _pcb
            self.add_item(b)

        jump_back = discord.ui.Button(label="<<", style=discord.ButtonStyle.secondary, disabled=(self.current_page < 10), row=2)
        async def jump_back_cb(interaction: discord.Interaction, v=self):
            v.current_page = max(0, v.current_page - 10)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        jump_back.callback = jump_back_cb
        self.add_item(jump_back)
        prev = discord.ui.Button(label="<", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0), row=2)
        async def prev_cb(interaction: discord.Interaction, v=self):
            v.current_page = max(0, v.current_page - 1)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        prev.callback = prev_cb
        self.add_item(prev)

        nxt = discord.ui.Button(label=">", style=discord.ButtonStyle.secondary, disabled=(self.current_page >= self.total_pages - 1), row=2)
        async def next_cb(interaction: discord.Interaction, v=self):
            v.current_page = min(v.total_pages - 1, v.current_page + 1)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        nxt.callback = next_cb
        self.add_item(nxt)

        jump_fwd = discord.ui.Button(label=">>", style=discord.ButtonStyle.secondary, disabled=(self.current_page >= self.total_pages - 10), row=2)
        async def jump_fwd_cb(interaction: discord.Interaction, v=self):
            v.current_page = min(self.total_pages - 1, v.current_page + 10)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        jump_fwd.callback = jump_fwd_cb
        self.add_item(jump_fwd)

        ep = discord.ui.Button(label="Select a page (1-1000)", style=discord.ButtonStyle.secondary, row=2)
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

    def _display_user(self, user_id, username, guild=None):
        member = guild.get_member(int(user_id)) if guild and str(user_id).isdigit() else None
        user = member or (self.bot.get_user(int(user_id)) if str(user_id).isdigit() else None)
        if user:
            return user.mention
        return f"{username} (`{user_id}`)"

    def _sync_page_cache(self, scope, entries, guild_id=None):
        cache_id = f"server_{guild_id}" if scope == "server" else "global"
        page_map = {}

        for page_num in range(1, 11):
            start = (page_num - 1) * ENTRIES_PER_PAGE
            page_map[str(page_num)] = entries[start:start + ENTRIES_PER_PAGE]

        page_cache_col.update_one({"_id": cache_id}, {"$set": {"pages": page_map}}, upsert=True)

    def _build_global_entries(self):
        cursor = leaderboard_col.find({"current_streak": {"$gt": 0}}).sort("current_streak", -1)
        
        best_per_user = {}
        for doc in cursor:
            uid = doc.get("user_id")
            current = doc.get("current_streak", 0)
            gid = doc.get("guild_id")
            guild = self.bot.get_guild(int(gid)) if gid else None
            server_name = guild.name if guild else "Unknown Server"

            if uid not in best_per_user or current > best_per_user[uid]["current_streak"]:
                display_name = self._display_user(uid, doc.get("username", "Unknown"), guild)
                best_per_user[uid] = {
                    "user_id": uid,
                    "username": doc.get("username", "Unknown"),
                    "display_name": display_name,
                    "current_streak": current,
                    "server_name": server_name
                }
        
        return sorted(best_per_user.values(), key=lambda x: x["current_streak"], reverse=True)

    def _build_server_entries(self, guild_id):
        cursor = leaderboard_col.find({
            "guild_id": str(guild_id), 
            "current_streak": {"$gt": 0}
        }).sort("current_streak", -1)

        entries = []
        guild = self.bot.get_guild(int(guild_id))
        for doc in cursor:
            uid = doc.get("user_id")
            entries.append({
                "user_id": uid,
                "username": doc.get("username", "Unknown"),
                "display_name": self._display_user(uid, doc.get("username", "Unknown"), guild),
                "current_streak": doc.get("current_streak", 0),
            })
        return entries

    @commands.group(name="streak", invoke_without_command=True)
    async def streak_group(self, ctx):
        await ctx.send("❓ **Usage:**\n`.streak set <@user> <number>`\n`.streak reset <@user>`")

    @streak_group.command(name="set")
    async def streak_set_prefix(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("You do not have permission to use this command.")

        gid_str = str(ctx.guild.id)
        uid_str = str(user.id)
        doc_id = f"{gid_str}_{uid_str}"

        old_doc = leaderboard_col.find_one({"_id": doc_id})
        old_streak = old_doc.get("current_streak", 0) if old_doc else 0

        leaderboard_col.update_one(
            {"_id": doc_id},
            {"$set": {
                "guild_id": gid_str,
                "user_id": uid_str,
                "username": user.name,
                "current_streak": num
            }},
            upsert=True
        )
        await ctx.send(f"✅ Updated **{user.name}** streak: `{old_streak}` → `{num}`")

    @streak_group.command(name="reset")
    async def streak_reset_prefix(self, ctx, user: discord.Member):
        if not is_admin(ctx.author.id):
            return await ctx.send("You do not have permission to use this command.")

        uid_str = str(user.id)
        result = leaderboard_col.update_many(
            {"user_id": uid_str},
            {"$set": {"current_streak": 0}}
        )
        await ctx.send(f"Reset streak for {user.name} across {result.modified_count} servers.")

    @commands.command(name="leaderboard", aliases=["lb"])
    async def lb(self, ctx, scope: str = "global"):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        stats = load_stats()
        allowed = stats.get("allowed_servers", [])
        if str(ctx.guild.id) not in allowed:
            return

        scope = scope.lower().strip()
        if scope not in ("global", "server"):
            return await ctx.send("❌ Usage: `+leaderboard global` or `+leaderboard server` (default: global)")

        if scope == "global":
            entries = self._build_global_entries()
            if not entries:
                return await ctx.send("🏆 No stats yet globally!")
            view = LeaderboardView(entries, mode="global")
            self._sync_page_cache("global", entries)
        else:
            entries = self._build_server_entries(ctx.guild.id)
            if not entries:
                return await ctx.send("🏆 No stats yet for this server!")
            view = LeaderboardView(entries, mode="server", guild_name=ctx.guild.name)
            self._sync_page_cache("server", entries, ctx.guild.id)

        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name="rlb", aliases=["resetleaderboard"])
    async def rlb(self, ctx, scope: str = "server", action: str = None, undo_string: str = None):
        scope = scope.lower().strip()
        if scope not in ("server", "global"):
            return await ctx.send("❌ Usage: `.rlb server [undo] [code]` or `.rlb global [undo] [code]` (default: server)")

        if action and action.lower().strip() == "undo":
            if scope == "global":
                if not is_op(ctx.author.id):
                    return await ctx.send("You do not have permission to use this command as globally")
                
                history_doc = deleted_col.find_one({"_id": "global_history"}) or {}
                global_history = history_doc.get("global", {})
                
                if not undo_string:
                    if not global_history:
                        return await ctx.send("❌ No global reset history records found.")
                    
                    description_lines = []
                    for code, info in global_history.items():
                        try:
                            ts = int(datetime.datetime.fromisoformat(info.get("date", "2026-01-01")).timestamp())
                        except Exception:
                            ts = 0
                        description_lines.append(f"`{code}` — {info.get('date')} <t:{ts}:f> | {', '.join(info.get('server_names', ['Unknown']))}")
                    
                    embed = discord.Embed(title="Global Reset History", description="\n".join(description_lines), color=0x2f3136)
                    pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)

                    view = discord.ui.View(timeout=120)
                    delete_all_btn = discord.ui.Button(label="Delete all global", style=discord.ButtonStyle.red)
                    
                    async def delete_all_callback(interaction: discord.Interaction):
                        if interaction.user.id != ctx.author.id:
                            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
                        deleted_col.delete_one({"_id": "global_history"})
                        await interaction.response.edit_message(content="🗑️ **All global reset records have been deleted.**", embed=None, view=None)
                    
                    delete_all_btn.callback = delete_all_callback
                    view.add_item(delete_all_btn)
                    return await ctx.send(embed=embed, view=view)

                target_code = undo_string.lower().strip()
                    else:
                if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
                    return await ctx.send("You do not have permission to use this command")
                
                gid_str = str(ctx.guild.id)
                history_doc = deleted_col.find_one({"_id": "server_history"}) or {}
                server_history = history_doc.get("server", {}).get(gid_str, {})

                if not undo_string:
                    if not server_history:
                        return await ctx.send("❌ No local reset history records found for this server.")
                    
                    description_lines = []
                    for code, info in server_history.items():
                        ts = int(datetime.datetime.fromisoformat(info.get('date', '2026-01-01')).timestamp())
                        description_lines.append(f"`{code}` — {info.get('date')} <t:{ts}:f> | {info.get('server_name', 'Unknown')}")
                    
                    embed = discord.Embed(title=f"{ctx.guild.name} Reset History", description="\n".join(description_lines), color=0x2f3136)
                    pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
                    return await ctx.send(embed=embed)

                target_code = undo_string.lower().strip()
                if target_code not in server_history:
                    return await ctx.send(f"❌ Invalid code! No record found matching code `{target_code}` for this server.")

                selected_record = server_history.pop(target_code)
                
                leaderboard_col.delete_many({"guild_id": gid_str})
                backup_data = selected_record.get("backup_data", [])
                if backup_data:
                    for item in backup_data:
                        item["_id"] = f"{item['guild_id']}_{item['user_id']}"
                    leaderboard_col.insert_many(backup_data)

                deleted_col.update_one({"_id": "server_history"}, {"$set": {f"server.{gid_str}": server_history}})

                embed = discord.Embed(
                    title="Server Restore",
                    description=f"{selected_record.get('server_name')} | {selected_record.get('date')}\n\n🔄 Current server streaks successfully restored using code `{target_code}`!",
                    color=0x00ff00
                )
                pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
                return await ctx.send(embed=embed)

        if scope == "global" and not is_op(ctx.author.id):
            return await ctx.send("You do not have permission to use this command as globally")
        if scope == "server" and not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
            return await ctx.send("You do not have permission to use this command")

        title = "⚠️☠️ Reset Global Leaderboards ☠️⚠️" if scope == "global" else "⚠️ Reset Current Server Leaderboards ⚠️"
        embed = discord.Embed(title=title, description="Are you sure you want to do it?", color=0xff0000 if scope == "global" else 0xfaa61a)
        
        pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)

        view = LeaderboardResetConfirmView(ctx, scope)
        await ctx.send(embed=embed, view=view)
        @commands.command(name="secretcommand")
    async def lb_best(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        gid_str = str(ctx.guild.id)
        uid_str = str(user.id)
        doc_id = f"{gid_str}_{uid_str}"

        old_doc = leaderboard_col.find_one({"_id": doc_id}) or {}
        old_best = old_doc.get("best_streak", 0)

        leaderboard_col.update_one(
            {"_id": doc_id},
            {"$set": {
                "guild_id": gid_str,
                "user_id": uid_str,
                "username": user.name,
                "best_streak": num
            }},
            upsert=True
        )
        await ctx.send(f"✅ Updated **{user.name}** best streak: `{old_best}` → `{num}`")

    @commands.command(name="secretcommand1")
    async def lb_current(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        gid_str = str(ctx.guild.id)
        uid_str = str(user.id)
        doc_id = f"{gid_str}_{uid_str}"

        old_doc = leaderboard_col.find_one({"_id": doc_id}) or {}
        old_current = old_doc.get("current_streak", 0)
        best_streak = old_doc.get("best_streak", 0)

        if num > best_streak:
            best_streak = num

        leaderboard_col.update_one(
            {"_id": doc_id},
            {"$set": {
                "guild_id": gid_str,
                "user_id": uid_str,
                "username": user.name,
                "current_streak": num,
                "best_streak": best_streak
            }},
            upsert=True
        )
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
            self._sync_page_cache("global", entries)
        else:
            entries = self._build_server_entries(interaction.guild.id)
            if not entries:
                return await interaction.response.send_message("🏆 No stats yet for this server!", ephemeral=True)
            view = LeaderboardView(entries, mode="server", guild_name=interaction.guild.name)
            self._sync_page_cache("server", entries, interaction.guild.id)

        await interaction.response.send_message(embed=view.build_embed(), view=view)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
