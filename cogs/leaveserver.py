import discord
from discord.ext import commands
import string
import secrets
import json
import os
import pytz
from datetime import datetime
from functions import is_op, is_admin, load_stats, send_debug_msg

LEAVE_LOG_FILE = "leave_log.json"


def load_leave_log():
    if not os.path.exists(LEAVE_LOG_FILE):
        return {"entries": {}}
    try:
        with open(LEAVE_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"entries": {}}


def save_leave_log(data):
    with open(LEAVE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def generate_leave_code():
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(5))


def get_leave_timestamp():
    try:
        stats = load_stats()
        tz_name = stats.get("timezone", "America/Los_Angeles")
        tz = pytz.timezone(tz_name)
        return datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def log_leave(server_id: str, server_name: str):
    data = load_leave_log()
    entries = data.setdefault("entries", {})

    if server_id in entries:
        entries[server_id]["count"] += 1
        entries[server_id]["timestamp"] = get_leave_timestamp()
        entries[server_id]["server_name"] = server_name
    else:
        entries[server_id] = {
            "code": generate_leave_code(),
            "server_name": server_name,
            "timestamp": get_leave_timestamp(),
            "count": 1
        }

    save_leave_log(data)
    return entries[server_id]["code"]


LEAVE_LIST_PER_PAGE = 10


class LeaveListView(discord.ui.View):
    def __init__(self, entries_list, author_id):
        super().__init__(timeout=120)
        self.entries_list = entries_list
        self.author_id = author_id
        self.current_page = 0
        self.total_pages = max(1, -(-len(entries_list) // LEAVE_LIST_PER_PAGE))
        self._update_buttons()

    def _build_embed(self):
        start = self.current_page * LEAVE_LIST_PER_PAGE
        page_entries = self.entries_list[start:start + LEAVE_LIST_PER_PAGE]
        lines = []
        for sid, info in page_entries:
            code = info.get("code", "?????")
            name = info.get("server_name", "Unknown")
            ts = info.get("timestamp", "?")
            count = info.get("count", 1)
            lines.append(f"`{code}` | `{sid}`\n> {name} | {ts} | left x{count}")
        embed = discord.Embed(
            title=f"🗑️ Leave History — Page {self.current_page + 1}/{self.total_pages}",
            description="\n\n".join(lines) if lines else "No entries.",
            color=0x2f3136
        )
        embed.set_footer(text=f"Total entries: {len(self.entries_list)}")
        return embed

    def _update_buttons(self):
        self.clear_items()

        prev = discord.ui.Button(
            label="<", style=discord.ButtonStyle.secondary,
            disabled=(self.current_page == 0), row=0
        )
        async def prev_cb(interaction: discord.Interaction, v=self):
            if interaction.user.id != v.author_id:
                return await interaction.response.send_message("❌ Not your list.", ephemeral=True)
            v.current_page = max(0, v.current_page - 1)
            v._update_buttons()
            await interaction.response.edit_message(embed=v._build_embed(), view=v)
        prev.callback = prev_cb
        self.add_item(prev)

        nxt = discord.ui.Button(
            label=">", style=discord.ButtonStyle.secondary,
            disabled=(self.current_page >= self.total_pages - 1), row=0
        )
        async def nxt_cb(interaction: discord.Interaction, v=self):
            if interaction.user.id != v.author_id:
                return await interaction.response.send_message("❌ Not your list.", ephemeral=True)
            v.current_page = min(v.total_pages - 1, v.current_page + 1)
            v._update_buttons()
            await interaction.response.edit_message(embed=v._build_embed(), view=v)
        nxt.callback = nxt_cb
        self.add_item(nxt)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class LeaveConfirmationView(discord.ui.View):
    def __init__(self, cog, ctx, target_mode, guild_obj=None):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.target_mode = target_mode
        self.guild_obj = guild_obj

        yes = discord.ui.Button(label="Yes", style=discord.ButtonStyle.success, emoji="✅")
        yes.callback = self.on_yes_click
        self.add_item(yes)

        no = discord.ui.Button(label="No", style=discord.ButtonStyle.danger, emoji="❌")
        no.callback = self.on_no_click
        self.add_item(no)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return False
        return True

    async def on_yes_click(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        if self.target_mode == "all":
            await self.cog.execute_leave_all(self.ctx)
        else:
            await self.cog.execute_leave_single(self.ctx, self.guild_obj)

    async def on_no_click(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(title="🛸 Cancelled", description="The request has been cancelled.", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


class LeaveServerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.MAIN_SERVER_ID = 1503365316065890364

    @commands.command(name="leave")
    async def leave_prefix(self, ctx, target: str = None, action: str = None):
        if not is_op(ctx.author.id):
            return

        if not target:
            return await ctx.send(
                "❌ Usage:\n"
                "`.leave <serverID>` — leave a server\n"
                "`.leave all` — leave all servers\n"
                "`.leave server list` — show leave history"
            )

        target_clean = target.strip().lower()
        action_clean = action.strip().lower() if action else None

        # ── .leave server list ──
        if target_clean == "server" and action_clean == "list":
            data = load_leave_log()
            entries = data.get("entries", {})
            if not entries:
                return await ctx.send("📋 No leave history found.")

            entries_list = list(entries.items())
            view = LeaveListView(entries_list, ctx.author.id)
            return await ctx.send(embed=view._build_embed(), view=view)

        # ── .leave all ──
        if target_clean == "all":
            embed = discord.Embed(
                title="⚠️ Leave ALL servers ⚠️",
                description="Are you sure you want to leave **ALL** servers?",
                color=discord.Color.dark_red()
            )
            view = LeaveConfirmationView(self, ctx, "all")
            return await ctx.send(embed=embed, view=view)

        # ── .leave <serverID> ──
        if not target_clean.isdigit():
            return await ctx.send("❌ Invalid server ID. Use a number or `all`.")

        guild_id = int(target_clean)

        if guild_id == self.MAIN_SERVER_ID:
            return await ctx.send("🗣️🔥")

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send("❌ I am not in a server with that ID.")

        embed = discord.Embed(
            title="⚠️ Leave a server ⚠️",
            description=f"Are you sure you want to leave **{guild.name}** (`{guild.id}`)?",
            color=discord.Color.orange()
        )
        view = LeaveConfirmationView(self, ctx, "single", guild_obj=guild)
        await ctx.send(embed=embed, view=view)

    async def execute_leave_all(self, ctx):
        left_count = 0
        for guild in list(self.bot.guilds):
            if guild.id != self.MAIN_SERVER_ID:
                try:
                    log_leave(str(guild.id), guild.name)
                    await guild.leave()
                    left_count += 1
                    print(f"✅ Left: {guild.name} ({guild.id})")
                except Exception as e:
                    print(f"❌ Failed to leave {guild.name}: {e}")

        log_leave("all", f"ALL ({left_count} servers)")
        await ctx.send(f"✅ Successfully left **{left_count}** servers.")
        await send_debug_msg(self.bot, f"🚪 `.leave all` | {ctx.author} (`{ctx.author.id}`) left **{left_count}** servers")

    async def execute_leave_single(self, ctx, guild):
        try:
            log_leave(str(guild.id), guild.name)
            await guild.leave()
            await ctx.send(f"✅ Successfully left **{guild.name}** (`{guild.id}`)")
            print(f"✅ Left via command: {guild.name} ({guild.id})")
            await send_debug_msg(self.bot, f"🚪 `.leave` | {ctx.author} (`{ctx.author.id}`) left **{guild.name}** (`{guild.id}`)")
        except Exception as e:
            await ctx.send(f"❌ Failed to leave server: {e}")


async def setup(bot):
    await bot.add_cog(LeaveServerCog(bot))
