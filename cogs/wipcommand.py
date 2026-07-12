import discord
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
