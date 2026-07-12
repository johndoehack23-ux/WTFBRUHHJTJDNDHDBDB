import discord
import os
from discord.ext import commands
from discord import app_commands
from functions import *

WIP_FILE = "cogs/wipcommand.py"

TEMPLATE = '''import discord
from discord.ext import commands
from discord import app_commands
from functions import *

# ════════════════════════════════════════════════════════════════
#  TEMPLATE COMMAND — rename this file and the command name!
#  File:    cogs/wipcommand.py  →  rename to cogs/yourcommand.py
#  Class:   WipCommandCog       →  rename to YourCommandCog
#  Command: wipcommand          →  rename to yourcommand
# ════════════════════════════════════════════════════════════════
#
#  ACCESS CONTROL QUICK REFERENCE
#  ─────────────────────────────────────────────────────────────
#  Load once at the top of your handler:
#
#      stats       = load_stats()
#      gid_str     = str(ctx.guild.id)          # or interaction.guild.id
#      uid_str     = str(ctx.author.id)          # or interaction.user.id
#      trusted     = stats.get("trusted_users", {}).get(gid_str, [])
#
#      is_trusted  = uid_str in trusted
#      is_adm      = is_admin(ctx.author.id, ctx.guild)
#      is_op_user  = is_op(ctx.author.id)
#
#  Single level checks:
#      Trusted only:           if not is_trusted: return ...
#      Admin only:             if not is_adm: return ...
#      Op only:                if not is_op_user: return ...
#
#  Combined (OR — any one is enough):
#      Trusted OR Admin:       if not (is_trusted or is_adm): return ...
#      Admin OR Op:            if not (is_adm or is_op_user): return ...
#      Trusted OR Admin OR Op: if not (is_trusted or is_adm or is_op_user): return ...
#
#  Combined (AND — must satisfy all):
#      Admin AND Op:           if not (is_adm and is_op_user): return ...
#
#  Guild Discord Administrator check (no bot list, just Discord perm):
#      from cogs.wordle import has_admin
#      if not has_admin(ctx.author, ctx.guild): return ...
#
#  Maintenance guard:
#      if is_maintenance_mode() and not is_adm: return await ctx.send("🛠️ Maintenance.")
#
#  Debug log helper (respects debug_mode toggle):
#      await send_debug_msg(bot, "Your message here")
#
# ════════════════════════════════════════════════════════════════


class WipCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── PREFIX COMMAND ──────────────────────────────────────────
    @commands.command(name="wipcommand")
    async def wip_prefix(self, ctx):
        # ── Paste your access control block here ──
        stats    = load_stats()
        gid_str  = str(ctx.guild.id)
        uid_str  = str(ctx.author.id)
        trusted  = stats.get("trusted_users", {}).get(gid_str, [])

        is_trusted  = uid_str in trusted
        is_adm      = is_admin(ctx.author.id, ctx.guild)
        is_op_user  = is_op(ctx.author.id)

        # Uncomment the level you need:
        # if not is_trusted:                              return await ctx.send("No permission.")
        # if not is_adm:                                  return await ctx.send("No permission.")
        # if not is_op_user:                              return await ctx.send("No permission.")
        # if not (is_trusted or is_adm or is_op_user):   return await ctx.send("No permission.")

        await ctx.send("🔧 **WIP Command** — rename this file and implement your logic!")

    # ── SLASH COMMAND ───────────────────────────────────────────
    @app_commands.command(name="wipcommand", description="WIP — rename and implement this command!")
    async def wip_slash(self, interaction: discord.Interaction):
        # ── Paste your access control block here ──
        stats    = load_stats()
        gid_str  = str(interaction.guild.id)
        uid_str  = str(interaction.user.id)
        trusted  = stats.get("trusted_users", {}).get(gid_str, [])

        is_trusted  = uid_str in trusted
        is_adm      = is_admin(interaction.user.id, interaction.guild)
        is_op_user  = is_op(interaction.user.id)

        # Uncomment the level you need:
        # if not is_trusted:                              return await interaction.response.send_message("No permission.", ephemeral=True)
        # if not is_adm:                                  return await interaction.response.send_message("No permission.", ephemeral=True)
        # if not is_op_user:                              return await interaction.response.send_message("No permission.", ephemeral=True)
        # if not (is_trusted or is_adm or is_op_user):   return await interaction.response.send_message("No permission.", ephemeral=True)

        await interaction.response.send_message("🔧 **WIP Command** — rename this file and implement your logic!")


async def setup(bot):
    await bot.add_cog(WipCommandCog(bot))
'''


class AtcmdCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addtemplatecommand", aliases=["atcmd"])
    async def addtemplatecommand(self, ctx):
        if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
            return

        if os.path.exists(WIP_FILE):
            return await ctx.send(
                "⚠️ **Already created!** Please check and edit the code. Thanks!\n"
                f"→ `{WIP_FILE}`"
            )

        try:
            with open(WIP_FILE, "w", encoding="utf-8") as f:
                f.write(TEMPLATE)
        except Exception as e:
            return await ctx.send(f"❌ Failed to create template: `{e}`")

        embed = discord.Embed(
            title="✅ Template Command Created!",
            description=(
                f"**File:** `{WIP_FILE}`\n\n"
                "**Next steps:**\n"
                "1️⃣ Rename the file to `cogs/yourcommand.py`\n"
                "2️⃣ Rename `WipCommandCog` → `YourCommandCog`\n"
                "3️⃣ Rename both commands from `wipcommand` → your name\n"
                "4️⃣ Uncomment the access control level you need\n"
                "5️⃣ The bot will **auto-load it on next restart** — no code changes needed!\n\n"
                "**Access levels included in template:**\n"
                "`Trusted` | `Admin` | `Op` | `Trusted OR Admin OR Op` | `Admin AND Op`"
            ),
            color=0x57F287
        )
        await ctx.send(embed=embed)
        await send_debug_msg(
            self.bot,
            f"📝 `.atcmd` | {ctx.author} (`{ctx.author.id}`) created `wipcommand.py` template | {ctx.guild.name}"
        )


async def setup(bot):
    await bot.add_cog(AtcmdCog(bot))
