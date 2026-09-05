import os
import io
import json
import math
import secrets
import string
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from functions import is_admin, is_op, is_maintenance_mode, load_stats

ENTRIES_PER_PAGE = 10
MAX_LEADERBOARD_PAGES = 1000

def generate_undo_code():
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

        leaderboard_col = self.ctx.bot.db["wordle_leaderboards"]
        deleted_col = self.ctx.bot.db["deleted_leaderboards"]

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
        self.leaderboard_col = self.bot.db["wordle_leaderboards"]
        self.deleted_col = self.bot.db["deleted_leaderboards"]
        self.page_cache_col = self.bot.db["page_cache"]

    def _resolve_user_obj(self, user_id, guild=None):
        if not str(user_id).isdigit():
            return None
        member = guild.get_member(int(user_id)) if guild else None
        return member or self.bot.get_user(int(user_id))

    def _display_user(self, user_id, username, guild=None):
        user = self._resolve_user_obj(user_id, guild)
        if user:
            return user.mention
        return f"{username} (`{user_id}`)"

    def _sync_page_cache(self, scope, entries, guild_id=None):
        cache_id = f"server_{guild_id}" if scope == "server" else "global"
        page_map = {}

        for page_num in range(1, 11):
            start = (page_num - 1) * ENTRIES_PER_PAGE
            page_map[str(page_num)] = entries[start:start + ENTRIES_PER_PAGE]

        self.page_cache_col.update_one({"_id": cache_id}, {"$set": {"pages": page_map}}, upsert=True)

    def _archive_server_leaderboard(self, guild_id, server_name=None):
        """Move a server's leaderboard docs into deleted_leaderboards instead of wiping them."""
        gid_str = str(guild_id)
        server_docs = list(self.leaderboard_col.find({"guild_id": gid_str}, {"_id": 0}))
        if not server_docs:
            return 0

        now_str = datetime.date.today().isoformat()
        self.deleted_col.update_one(
            {"_id": "left_servers"},
            {"$set": {
                f"servers.{gid_str}": {
                    "backup_data": server_docs,
                    "server_name": server_name or f"Unknown Server ({gid_str})",
                    "left_at": now_str,
                }
            }},
            upsert=True,
        )
        self.leaderboard_col.delete_many({"guild_id": gid_str})
        return len(server_docs)

    def _restore_server_leaderboard(self, guild_id):
        """If this serverID was archived in deleted_leaderboards, put its data back."""
        gid_str = str(guild_id)
        left_doc = self.deleted_col.find_one({"_id": "left_servers"}) or {}
        servers = left_doc.get("servers", {})
        record = servers.get(gid_str)
        if not record:
            return 0

        backup_data = record.get("backup_data", [])
        if backup_data:
            for item in backup_data:
                item["_id"] = f"{item.get('guild_id', gid_str)}_{item.get('user_id')}"
            # Avoid duplicates if something partially restored already
            for item in backup_data:
                self.leaderboard_col.update_one(
                    {"_id": item["_id"]},
                    {"$set": item},
                    upsert=True,
                )

        # Remove this server from the left_servers archive
        servers.pop(gid_str, None)
        self.deleted_col.update_one(
            {"_id": "left_servers"},
            {"$set": {"servers": servers}},
            upsert=True,
        )
        return len(backup_data)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """When the bot leaves a server, archive its leaderboard instead of losing it."""
        try:
            count = self._archive_server_leaderboard(guild.id, guild.name)
            if count:
                print(f"📦 Archived {count} leaderboard entries for left server {guild.name} ({guild.id})")
            else:
                print(f"ℹ️  No leaderboard data to archive for left server {guild.name} ({guild.id})")
        except Exception as e:
            print(f"❌ Failed to archive leaderboard for {guild.name} ({guild.id}): {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """When the bot rejoins a server, restore any archived leaderboard for that serverID."""
        try:
            count = self._restore_server_leaderboard(guild.id)
            if count:
                print(f"🔄 Restored {count} leaderboard entries for rejoined server {guild.name} ({guild.id})")
        except Exception as e:
            print(f"❌ Failed to restore leaderboard for {guild.name} ({guild.id}): {e}")

    def _build_global_entries(self):
        cursor = self.leaderboard_col.find({"current_streak": {"$gt": 0}}).sort("current_streak", -1)

        best_per_user = {}
        # Group orphaned docs by guild so we can archive whole servers instead of hard-deleting
        orphaned_by_guild = {}
        to_delete_users = []

        for doc in cursor:
            uid = doc.get("user_id")
            current = doc.get("current_streak", 0)
            gid = doc.get("guild_id")
            guild = self.bot.get_guild(int(gid)) if gid else None

            if not guild:
                # Bot is no longer in this guild — archive later, don't wipe permanently
                orphaned_by_guild.setdefault(str(gid), []).append(doc)
                continue

            user = self._resolve_user_obj(uid, guild)
            if not user:
                # User didn't load properly — drop only that entry
                to_delete_users.append(doc["_id"])
                continue

            server_name = guild.name

            if uid not in best_per_user or current > best_per_user[uid]["current_streak"]:
                best_per_user[uid] = {
                    "user_id": uid,
                    "username": doc.get("username", "Unknown"),
                    "display_name": user.mention,
                    "current_streak": current,
                    "server_name": server_name
                }

        # Archive any servers the bot is no longer in (safety net if on_guild_remove was missed)
        for gid_str, docs in orphaned_by_guild.items():
            try:
                self._archive_server_leaderboard(gid_str, f"Unknown Server ({gid_str})")
                print(f"📦 Safety-archive: moved {len(docs)} orphaned entries for guild {gid_str}")
            except Exception as e:
                print(f"❌ Safety-archive failed for guild {gid_str}: {e}")

        if to_delete_users:
            self.leaderboard_col.delete_many({"_id": {"$in": to_delete_users}})

        return sorted(best_per_user.values(), key=lambda x: x["current_streak"], reverse=True)

    def _build_server_entries(self, guild_id):
        cursor = self.leaderboard_col.find({
            "guild_id": str(guild_id), 
            "current_streak": {"$gt": 0}
        }).sort("current_streak", -1)

        entries = []
        to_delete = []
        guild = self.bot.get_guild(int(guild_id))
        for doc in cursor:
            uid = doc.get("user_id")

            user = self._resolve_user_obj(uid, guild)
            if not user:
                # User didn't load properly — drop the entry.
                to_delete.append(doc["_id"])
                continue

            entries.append({
                "user_id": uid,
                "username": doc.get("username", "Unknown"),
                "display_name": user.mention,
                "current_streak": doc.get("current_streak", 0),
            })

        if to_delete:
            self.leaderboard_col.delete_many({"_id": {"$in": to_delete}})

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

        old_doc = self.leaderboard_col.find_one({"_id": doc_id})
        old_streak = old_doc.get("current_streak", 0) if old_doc else 0

        self.leaderboard_col.update_one(
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
        result = self.leaderboard_col.update_many(
            {"user_id": uid_str},
            {"$set": {"current_streak": 0}}
        )
        await ctx.send(f"Reset streak for {user.name} across {result.modified_count} servers.")

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
                
                history_doc = self.deleted_col.find_one({"_id": "global_history"}) or {}
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
                        self.deleted_col.delete_one({"_id": "global_history"})
                        await interaction.response.edit_message(content="🗑️ **All global reset records have been deleted.**", embed=None, view=None)
                    
                    delete_all_btn.callback = delete_all_callback
                    view.add_item(delete_all_btn)
                    return await ctx.send(embed=embed, view=view)

                target_code = undo_string.lower().strip()
                if target_code not in global_history:
                    return await ctx.send(f"❌ Invalid code! No record found matching code `{target_code}`.")

                selected_record = global_history.pop(target_code)
                
                self.leaderboard_col.delete_many({})
                backup_data = selected_record.get("backup_data", [])
                if backup_data:
                    for item in backup_data:
                        item["_id"] = f"{item['guild_id']}_{item['user_id']}"
                    self.leaderboard_col.insert_many(backup_data)
                
                self.deleted_col.update_one({"_id": "global_history"}, {"$set": {"global": global_history}})

                names_string = ", ".join(selected_record.get("server_names", []))
                embed = discord.Embed(
                    title="Global Restore",
                    description=f"{names_string} | {selected_record.get('date')}\n\n🔄 Global leaderboards successfully restored!",
                    color=0x00ff00
                )
                pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
                return await ctx.send(embed=embed)
            else:
                if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
                    return await ctx.send("You do not have permission to use this command")
                
                gid_str = str(ctx.guild.id)
                history_doc = self.deleted_col.find_one({"_id": "server_history"}) or {}
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
                
                self.leaderboard_col.delete_many({"guild_id": gid_str})
                backup_data = selected_record.get("backup_data", [])
                if backup_data:
                    for item in backup_data:
                        item["_id"] = f"{item['guild_id']}_{item['user_id']}"
                    self.leaderboard_col.insert_many(backup_data)

                self.deleted_col.update_one({"_id": "server_history"}, {"$set": {f"server.{gid_str}": server_history}})

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

    def _import_leaderboard_data(self, data):
        servers = data.get("servers", {})
        if not servers:
            return 0, 0, "No `servers` key found in that file."

        to_insert = []
        skipped = 0
        for gid, users in servers.items():
            gid_str = str(gid)
            for uid, info in users.items():
                uid_str = str(uid)
                doc_id = f"{gid_str}_{uid_str}"

                if self.leaderboard_col.find_one({"_id": doc_id}, {"_id": 1}):
                    skipped += 1
                    continue

                current = info.get("current_streak", 0)
                to_insert.append({
                    "_id": doc_id,
                    "guild_id": gid_str,
                    "user_id": uid_str,
                    "username": info.get("username", "Unknown"),
                    "current_streak": current,
                    "best_streak": info.get("best_streak", current),
                })

        inserted = 0
        if to_insert:
            result = self.leaderboard_col.insert_many(to_insert, ordered=False)
            inserted = len(result.inserted_ids)

        return inserted, skipped, None

    @commands.command(name="addlb")
    async def add_leaderboard(self, ctx):
        if ctx.author.id != 1465295674768883889:
            return await ctx.send("You do not have permission to use this command")

        if not ctx.message.attachments:
            return await ctx.send("❌ Attach a `wordle_leaderboard.json` or a `.zip` file with this command.")

        attachment = ctx.message.attachments[0]
        filename = attachment.filename.lower()

        try:
            raw = await attachment.read()
            if filename.endswith(".json"):
                data = json.loads(raw.decode("utf-8"))
                inserted, skipped, error = self._import_leaderboard_data(data)
            elif filename.endswith(".zip"):
                import zipfile
                import io
                imported = []
                with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
                    for member in archive.infolist():
                        if member.is_dir() or not member.filename.lower().endswith(".json"):
                            continue
                        try:
                            data = json.loads(archive.read(member).decode("utf-8"))
                        except Exception:
                            continue
                        if isinstance(data, dict) and data.get("servers"):
                            imported.append(data)

                if not imported:
                    return await ctx.send("❌ The ZIP did not contain a valid leaderboard JSON file.")

                inserted = skipped = 0
                error = None
                for data in imported:
                    added, already, import_error = self._import_leaderboard_data(data)
                    inserted += added
                    skipped += already
                    if import_error:
                        error = import_error
                        break
            else:
                return await ctx.send("❌ Attach a `.json` or `.zip` file.")
        except Exception as e:
            return await ctx.send(f"❌ Failed to read/parse the file: `{e}`")

        if error:
            return await ctx.send(f"❌ {error}")

        embed = discord.Embed(
            title="📥 Leaderboard Import Complete",
            description=f"✅ Added: **{inserted}**\n⏭️ Skipped (already existed): **{skipped}**",
            color=0x00ff00
        )
        pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
        await ctx.send(embed=embed)

    @commands.command(name="secretcommand")
    async def lb_best(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        gid_str = str(ctx.guild.id)
        uid_str = str(user.id)
        doc_id = f"{gid_str}_{uid_str}"

        old_doc = self.leaderboard_col.find_one({"_id": doc_id}) or {}
        old_best = old_doc.get("best_streak", 0)

        self.leaderboard_col.update_one(
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

        old_doc = self.leaderboard_col.find_one({"_id": doc_id}) or {}
        old_current = old_doc.get("current_streak", 0)
        best_streak = old_doc.get("best_streak", 0)

        if num > best_streak:
            best_streak = num

        self.leaderboard_col.update_one(
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



async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
