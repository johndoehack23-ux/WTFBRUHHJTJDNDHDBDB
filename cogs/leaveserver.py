import discord
from discord.ext import commands
import string
import secrets
import json
import os
import pytz
from datetime import datetime
from functions import is_op, is_admin, load_stats

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
        with open("stats.json", "r") as f:
            tz_name = json.load(f).get("timezone", "America/Los_Angeles")
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

    def _get_invite_url(self):
        return discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(administrator=True),
            scopes=("bot", "applications.commands")
        )

    @commands.command(name="leave")
    async def leave_prefix(self, ctx, target: str = None, action: str = None):
        if not is_op(ctx.author.id):
            return

        if not target:
            return await ctx.send(
                "❌ Usage:\n"
                "`.leave <serverID>` — leave a server\n"
                "`.leave <serverID> undo` — get rejoin link\n"
                "`.leave all` — leave all servers\n"
                "`.leave all undo` — get rejoin links for all\n"
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

            lines = []
            for sid, info in entries.items():
                code = info.get("code", "?????")
                name = info.get("server_name", "Unknown")
                ts = info.get("timestamp", "?")
                count = info.get("count", 1)
                lines.append(f"`{code}` | `{sid}` ({name}) | {ts} | x{count}")

            embed = discord.Embed(
                title="🗑️ Leave History",
                description="\n".join(lines),
                color=0x2f3136
            )
            return await ctx.send(embed=embed)

        # ── .leave all undo ──
        if target_clean == "all" and action_clean == "undo":
            data = load_leave_log()
            entries = data.get("entries", {})
            if not entries:
                return await ctx.send("📋 No leave history to undo.")

            invite_url = self._get_invite_url()
            server_lines = []
            for sid, info in entries.items():
                name = info.get("server_name", "Unknown")
                count = info.get("count", 1)
                server_lines.append(f"• `{sid}` — {name} (left x{count})")

            embed = discord.Embed(
                title="🔄 Rejoin All Servers",
                description=(
                    "⚠️ Discord bots **cannot auto-rejoin** servers — a server admin must invite the bot back.\n\n"
                    f"**Servers in leave history:**\n" + "\n".join(server_lines) +
                    f"\n\n**Bot Invite Link:**\n{invite_url}"
                ),
                color=0x57F287
            )
            return await ctx.send(embed=embed)

        # ── .leave <serverID> undo ──
        if target_clean != "all" and action_clean == "undo":
            if not target_clean.isdigit():
                return await ctx.send("❌ Invalid server ID.")

            data = load_leave_log()
            entries = data.get("entries", {})
            info = entries.get(target_clean, {})
            server_name = info.get("server_name", "Unknown")
            count = info.get("count", 1)

            invite_url = self._get_invite_url()
            embed = discord.Embed(
                title=f"🔄 Rejoin: {server_name}",
                description=(
                    "⚠️ Discord bots **cannot auto-rejoin** servers — a server admin must invite the bot back.\n\n"
                    f"**Server:** `{target_clean}` — {server_name} (left x{count})\n\n"
                    f"**Bot Invite Link:**\n{invite_url}"
                ),
                color=0x57F287
            )
            return await ctx.send(embed=embed)

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

    async def execute_leave_single(self, ctx, guild):
        try:
            log_leave(str(guild.id), guild.name)
            await guild.leave()
            await ctx.send(f"✅ Successfully left **{guild.name}** (`{guild.id}`)")
            print(f"✅ Left via command: {guild.name} ({guild.id})")
        except Exception as e:
            await ctx.send(f"❌ Failed to leave server: {e}")


async def setup(bot):
    await bot.add_cog(LeaveServerCog(bot))
