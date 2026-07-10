import discord
from discord.ext import commands
from discord import app_commands
import math
from functions import *

ENTRIES_PER_PAGE = 10

import secrets
import string
import datetime

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

        file_target = "wordle_leaderboard.json"
        deleted_file = "wordle_deletedboard.json"
        
        data = load_json(file_target, lambda: {"servers": {}})
        deleted_data = load_json(deleted_file, lambda: {"server": {}, "global": {}})

        now_str = datetime.date.today().isoformat()  # e.g., 2026-06-27
        undo_code = generate_undo_code()

        if self.scope == "global":
            server_names = []
            for gid in data.get("servers", {}).keys():
                guild = self.ctx.bot.get_guild(int(gid))
                server_names.append(guild.name if guild else f"Unknown Server ({gid})")
            
            if not server_names:
                server_names = ["No Active Servers"]

            # Save full global data mapping to the persistent deleted JSON file
            if "global" not in deleted_data:
                deleted_data["global"] = {}
                
            deleted_data["global"][undo_code] = {
                "backup_data": data.get("servers", {}),
                "server_names": server_names,
                "date": now_str
            }
            save_json(deleted_file, deleted_data)

            # Wipe board file entirely
            data = {"servers": {}}
            save_json(file_target, data)
            await interaction.response.edit_message(content="🧹 **Global** leaderboard has been completely reset.", embed=None, view=None)
        else:
            if "servers" not in data:
                data["servers"] = {}
            
            gid_str = str(self.ctx.guild.id)
            current_server_data = data["servers"].get(gid_str, {})

            if "server" not in deleted_data:
                deleted_data["server"] = {}
            if gid_str not in deleted_data["server"]:
                deleted_data["server"][gid_str] = {}

            # Save specific server mapping into persistent deleted JSON file
            deleted_data["server"][gid_str][undo_code] = {
                "backup_data": current_server_data,
                "server_name": self.ctx.guild.name,
                "date": now_str
            }
            save_json(deleted_file, deleted_data)

            # Reset current target server
            data["servers"][gid_str] = {}
            save_json(file_target, data)
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

        # Load emoji configuration
        import json
        streak_emojis = {}
        try:
            with open("emoji.json", "r", encoding="utf-8") as f:
                streak_emojis = json.load(f).get("streaks", {})
        except Exception:
            pass

        lines = []
        for i, entry in enumerate(page_entries, start_rank + 1):
            username = entry.get("username", "Unknown")
            current = entry.get("current_streak", 0)
            
            # Determine the streak emoji when streak is greater than 0
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
                lines.append(
                    f"**{i}.** {username} — Streak: **{current}**{streak_emoji} — {server_name}"
                )
            else:
                lines.append(
                    f"**{i}.** {username} — Streak: **{current}**{streak_emoji}"
                )

        embed.description = "\n".join(lines)
        return embed

    def update_buttons(self):
        self.clear_items()

        # ── Row 0: 1 2 3 4 5 (max 5 per row) ──
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

        # ── Row 1: 6 7 8 9 10 ──
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

        # ── Row 2: < > Enter Page ──
        prev = discord.ui.Button(
            label="<",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page == 0),
            row=2
        )
        async def prev_cb(interaction: discord.Interaction, v=self):
            v.current_page = max(0, v.current_page - 1)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        prev.callback = prev_cb
        self.add_item(prev)

        nxt = discord.ui.Button(
            label=">",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page >= self.total_pages - 1),
            row=2
        )
        async def next_cb(interaction: discord.Interaction, v=self):
            v.current_page = min(v.total_pages - 1, v.current_page + 1)
            v.update_buttons()
            await interaction.response.edit_message(embed=v.build_embed(), view=v)
        nxt.callback = next_cb
        self.add_item(nxt)

        ep = discord.ui.Button(
            label="Enter Page",
            style=discord.ButtonStyle.secondary,
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
        best_per_user = {}
        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        for gid, users in data.get("servers", {}).items():
            guild = self.bot.get_guild(int(gid))
            server_name = guild.name if guild else "Unknown Server"
            for uid, d in users.items():
                current = d.get("current_streak", 0)
                # FIXED: Strictly ensures only streaks GREATER THAN 0 can make it to global leaderboard
                if current > 0:
                    if uid not in best_per_user or current > best_per_user[uid]["current_streak"]:
                        best_per_user[uid] = {
                            "username": d.get("username", "Unknown"),
                            "current_streak": current,
                            "server_name": server_name
                        }
        entries = sorted(best_per_user.values(), key=lambda x: x["current_streak"], reverse=True)
        return entries

    def _build_server_entries(self, guild_id):
        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        srv = data.get("servers", {}).get(str(guild_id), {})
        entries = []
        for uid, d in srv.items():
            current = d.get("current_streak", 0)
            # FIXED: Strictly ensures only streaks GREATER THAN 0 can make it to local server leaderboard
            if current > 0:
                entries.append({
                    "username": d.get("username", "Unknown"),
                    "current_streak": current,
                })
        entries.sort(key=lambda x: x["current_streak"], reverse=True)
        return entries

    @commands.group(name="streak", invoke_without_command=True)
    async def streak_group(self, ctx):
        await ctx.send("❓ **Usage:**\n`.streak set <@user> <number>`\n`.streak reset <@user>`")
    @streak_group.command(name="set")
    async def streak_set_prefix(self, ctx, user: discord.Member, num: int):
        if not is_admin(ctx.author.id):
            return await ctx.send("You do not have permission to use this command.")

        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        gid_str = str(ctx.guild.id)
        if "servers" not in data:
            data["servers"] = {}
        if gid_str not in data["servers"]:
            data["servers"][gid_str] = {}

        srv = data["servers"][gid_str]
        uid = str(user.id)
        if uid not in srv:
            srv[uid] = {"username": user.name, "current_streak": 0}

        old_streak = srv[uid].get("current_streak", 0)
        srv[uid]["current_streak"] = num
        srv[uid]["username"] = user.name

        save_json(LEADERBOARD_FILE, data)
        await ctx.send(f"✅ Updated **{user.name}** streak: `{old_streak}` → `{num}`")
    @streak_group.command(name="reset")
    async def streak_reset_prefix(self, ctx, user: discord.Member):
        if not is_admin(ctx.author.id):
            return await ctx.send("You do not have permission to use this command.")

        # Resets globally across all servers in the leaderboard file
        data = load_json(LEADERBOARD_FILE, lambda: {"servers": {}})
        modified = False
        
        for gid, users in data.get("servers", {}).items():
            uid = str(user.id)
            if uid in users:
                users[uid]["current_streak"] = 0
                modified = True
                
        if modified:
            save_json(LEADERBOARD_FILE, data)
        await ctx.send(f"Reset streak for {user.name}.")

    @commands.command(name="leaderboard", aliases=["lb"])
    async def lb(self, ctx, scope: str = "global"):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        # Only allowed servers can access the leaderboard
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
        else:
            entries = self._build_server_entries(ctx.guild.id)
            if not entries:
                return await ctx.send("🏆 No stats yet for this server!")
            view = LeaderboardView(entries, mode="server", guild_name=ctx.guild.name)

        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name="rlb", aliases=["resetleaderboard"])
    async def rlb(self, ctx, scope: str = "server", action: str = None, undo_string: str = None):
        scope = scope.lower().strip()
        
        if scope not in ("server", "global"):
            return await ctx.send("❌ Usage: `.rlb server [undo] [code]` or `.rlb global [undo] [code]` (default: server)")

        file_target = "wordle_leaderboard.json"
        deleted_file = "wordle_deletedboard.json"

        # --- DYNAMIC BACKUP LOGIC ROUTER ---
        if action and action.lower().strip() == "undo":
            data = load_json(file_target, lambda: {"servers": {}})
            deleted_data = load_json(deleted_file, lambda: {"server": {}, "global": {}})

            if scope == "global":
                if not is_op(ctx.author.id):
                    return await ctx.send("You do not have permission to use this command as globally")
                
                global_history = deleted_data.get("global", {})
                
                # If no specific tracking ID is passed, list every single global deletion record
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
                    
                    embed = discord.Embed(
                        title="Global Reset History",
                        description="\n".join(description_lines),
                        color=0x2f3136
                    )
                    pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)

                    view = discord.ui.View(timeout=120)
                    delete_all_btn = discord.ui.Button(label="Delete all global", style=discord.ButtonStyle.red)
                    
                    async def delete_all_callback(interaction: discord.Interaction):
                        if interaction.user.id != ctx.author.id:
                            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
                        deleted_data["global"] = {}
                        save_json(deleted_file, deleted_data)
                        await interaction.response.edit_message(content="🗑️ **All global reset records have been deleted.**", embed=None, view=None)
                    
                    delete_all_btn.callback = delete_all_callback
                    view.add_item(delete_all_btn)

                    return await ctx.send(embed=embed, view=view)

                # Recover selected global backup item match
                target_code = undo_string.lower().strip()
                if target_code not in global_history:
                    return await ctx.send(f"❌ Invalid code! No record found matching code `{target_code}`.")

                selected_record = global_history.pop(target_code)
                data["servers"] = selected_record["backup_data"]
                
                save_json(file_target, data)
                save_json(deleted_file, deleted_data)

                names_string = ", ".join(selected_record.get("server_names", []))
                embed = discord.Embed(
                    title="Global Restore",
                    description=f"{names_string} | {selected_record.get('date')}\n\n🔄 Global leaderboards successfully restored using code `{target_code}`!",
                    color=0x00ff00
                )
                pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
                return await ctx.send(embed=embed)

            else:  # SERVER SCOPE UNDO
                if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
                    return await ctx.send("You do not have permission to use this command")
                
                gid_str = str(ctx.guild.id)
                server_history = deleted_data.get("server", {}).get(gid_str, {})

                # If no specific tracking ID is passed, list every server deletion record for current serverID
                if not undo_string:
                    if not server_history:
                        return await ctx.send("❌ No local reset history records found for this server.")
                    
                    description_lines = []
                    for code, info in server_history.items():
                        ts = int(datetime.datetime.fromisoformat(info.get('date', '2026-01-01')).timestamp())
                        description_lines.append(f"`{code}` — {info.get('date')} <t:{ts}:f> | {info.get('server_name', 'Unknown')}")
                    
                    embed = discord.Embed(
                        title=f"{ctx.guild.name} Reset History",
                        description="\n".join(description_lines),
                        color=0x2f3136
                    )
                    pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
                    return await ctx.send(embed=embed)

                # Recover selected local server backup item match
                target_code = undo_string.lower().strip()
                if target_code not in server_history:
                    return await ctx.send(f"❌ Invalid code! No record found matching code `{target_code}` for this server.")

                selected_record = server_history.pop(target_code)
                if "servers" not in data:
                    data["servers"] = {}
                data["servers"][gid_str] = selected_record["backup_data"]

                save_json(file_target, data)
                save_json(deleted_file, deleted_data)

                embed = discord.Embed(
                    title="Server Restore",
                    description=f"{selected_record.get('server_name')} | {selected_record.get('date')}\n\n🔄 Current server streaks successfully restored using code `{target_code}`!",
                    color=0x00ff00
                )
                pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)
                return await ctx.send(embed=embed)

        # --- STANDARD RESET DIALOG ROUTER ---
        if scope == "global" and not is_op(ctx.author.id):
            return await ctx.send("You do not have permission to use this command as globally")
        if scope == "server" and not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
            return await ctx.send("You do not have permission to use this command")

        title = "⚠️☠️ Reset Global Leaderboards ☠️⚠️" if scope == "global" else "⚠️ Reset Current Server Leaderboards ⚠️"
        embed = discord.Embed(
            title=title,
            description="Are you sure you want to do it?",
            color=0xff0000 if scope == "global" else 0xfaa61a
        )
        
        pfp_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=pfp_url)

        view = LeaderboardResetConfirmView(ctx, scope)
        await ctx.send(embed=embed, view=view)
    @commands.command(name="secretcommand")
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

    @commands.command(name="secretcommand1")
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


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))