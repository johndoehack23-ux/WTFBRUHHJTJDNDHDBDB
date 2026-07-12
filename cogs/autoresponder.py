import discord
from discord.ext import commands
from discord import app_commands
import json
from functions import *

STATS_FILE = "stats.json"

def get_server_trusted_users(guild_id: str) -> list:
    """Helper to safely fetch trusted users for a specific guild directly from stats.json"""
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("trusted_users", {}).get(str(guild_id), [])
    except Exception:
        return []

class AutoresponderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="autoresponder", description="Create or manage an autoresponder.")
    @app_commands.describe(
        action="add | edit",
        trigger="When the bot will respond to",
        new_trigger="Edit trigger",
        reply="Bot's reply",
        matchmode="contains | exact | startswith | endswith",
        react="The emoji the bot will react with [WIP]",
        channel="Target channel",
        cooldown="Cooldown duration",
        global_server="Apply globally across all servers"
    )
    async def autoresponder(
        self,
        interaction: discord.Interaction,
        action: str,
        trigger: str = None,
        new_trigger: str = None,
        reply: str = None,
        matchmode: str = "contains",
        react: str = None,
        channel: discord.TextChannel = None,
        cooldown: str = None,
        global_server: bool = False
    ):
        trusted_list = get_server_trusted_users(str(interaction.guild.id))
        is_server_trusted = str(interaction.user.id) in trusted_list
        is_bot_admin = is_admin(interaction.user.id, interaction.guild)

        if not is_bot_admin and not is_server_trusted and not interaction.permissions.administrator:
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        action = action.lower().strip()
        guild_id = str(interaction.guild.id)
        channel_id = str(channel.id) if channel else None

        if action in ["removeall", "global_removeall"]:
            if action == "global_removeall":
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
                if remove_all_auto_responses(global_all=True):
                    await interaction.response.send_message("🗑️ **ALL auto responders deleted globally.**", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Failed global reset operation.", ephemeral=True)
            else:
                if remove_all_auto_responses(guild_id=guild_id):
                    await interaction.response.send_message("🗑️ **All auto responders for this server deleted.**", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Failed server reset operation.", ephemeral=True)
            return

        if global_server and not is_admin(interaction.user.id, interaction.guild, check_global=True):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        if action == "add":
            if not trigger or not reply:
                return await interaction.response.send_message("❌ Need `trigger` + `reply`", ephemeral=True)

            is_global = global_server if is_admin(interaction.user.id, interaction.guild, check_global=True) else False

            add_auto_response(
                trigger=trigger,
                reply=reply,
                matchmode=matchmode,
                react=react,
                channel=channel_id,
                cooldown=cooldown,
                global_server=is_global,
                guild_id=interaction.guild.id
            )
            global_label = " 🌐 [GLOBAL]" if is_global else ""
            await interaction.response.send_message(f"✅ Autoresponder added{global_label} for: `{trigger}`", ephemeral=True)
            await send_debug_msg(self.bot, f"🤖 `/autoresponder add`{global_label} | {interaction.user} (`{interaction.user.id}`) added trigger `{trigger}` → `{reply}` | {interaction.guild.name}")

        elif action == "edit":
            if not trigger:
                return await interaction.response.send_message("❌ Need current trigger to locate the dataset entry.", ephemeral=True)

            all_responses = get_all_auto_responses()
            if trigger.lower().strip() in all_responses:
                if all_responses[trigger.lower().strip()].get("global") and not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

            edit_auto_response(trigger, new_trigger, reply, matchmode, react, channel_id, cooldown, global_server)
            await interaction.response.send_message(f"✅ Updated autoresponder setup: `{trigger}`", ephemeral=True)
            await send_debug_msg(self.bot, f"🤖 `/autoresponder edit` | {interaction.user} (`{interaction.user.id}`) edited trigger `{trigger}` | {interaction.guild.name}")

        else:
            await interaction.response.send_message("Use: `add | edit` (To view list, use `.showresponders`)", ephemeral=True)

    @app_commands.command(name="deleteautoresponder", description="Deletes an autoresponder trigger")
    @app_commands.describe(
        trigger="The trigger of the autoresponder to delete"
    )
    async def deleteautoresponder(
        self,
        interaction: discord.Interaction,
        trigger: str
    ):
        trusted_list = get_server_trusted_users(str(interaction.guild.id))
        is_server_trusted = str(interaction.user.id) in trusted_list
        is_bot_admin = is_admin(interaction.user.id, interaction.guild)

        if not is_bot_admin and not is_server_trusted and not interaction.permissions.administrator:
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        if is_maintenance_mode() and not is_bot_admin:
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        target_trigger = trigger.lower().strip()
        guild_id = str(interaction.guild.id)
        all_responses = get_all_auto_responses()

        local_triggers = [
            t for t, d in all_responses.items()
            if not d.get("global") and str(d.get("guild_id", "")) == guild_id
        ]
        local_list_str = "\n".join([f"• `{lt}`" for lt in local_triggers]) if local_triggers else "No active server autoresponders found."

        if target_trigger not in all_responses:
            embed = discord.Embed(title="❌ Trigger Not Found", color=0xff4d4d)
            embed.add_field(name="Current Server Autoresponders:", value=local_list_str, inline=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        is_item_global = all_responses[target_trigger].get("global", False)
        item_guild = all_responses[target_trigger].get("guild_id")

        if is_item_global:
            if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            remove_auto_response(target_trigger)
            await interaction.response.send_message(f"🗑️ Global Autoresponder `{trigger}` completely removed.", ephemeral=True)
            await send_debug_msg(self.bot, f"🗑️ `/deleteautoresponder` 🌐 [GLOBAL] | {interaction.user} (`{interaction.user.id}`) deleted trigger `{trigger}` | {interaction.guild.name}")
            return
        else:
            if item_guild and str(item_guild) != guild_id:
                embed = discord.Embed(title=f"❌ Autoresponder for `{trigger}` not found on this server.", color=0xff4d4d)
                embed.add_field(name="Current Server Autoresponders:", value=local_list_str, inline=False)
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            remove_auto_response(target_trigger)
            await interaction.response.send_message(f"🗑️ Local Autoresponder `{trigger}` successfully removed.", ephemeral=True)
            await send_debug_msg(self.bot, f"🗑️ `/deleteautoresponder` | {interaction.user} (`{interaction.user.id}`) deleted trigger `{trigger}` | {interaction.guild.name}")
            return

    @commands.command(name="showresponders")
    async def showresponders(self, ctx, scope: str = "server"):
        trusted_list = get_server_trusted_users(str(ctx.guild.id))
        is_server_trusted = str(ctx.author.id) in trusted_list
        is_bot_admin = is_admin(ctx.author.id)

        if not is_bot_admin and not is_server_trusted:
            return await ctx.send("❌ You do not have permission to use this command.")

        data = get_all_auto_responses()
        guild_id = str(ctx.guild.id)
        scope = scope.lower().strip()

        if scope not in ("global", "server"):
            return await ctx.send("❌ Usage: `.showresponders global` or `.showresponders server` (default: server)")

        embed = discord.Embed(title="🤖 **Autoresponders Configuration**", color=0x2f3136)

        if scope == "global":
            lines = []
            for trigger, content in data.items():
                if content.get("global"):
                    lines.append(f"• `{trigger}` | `[Global]`")
                else:
                    g_id = content.get("guild_id")
                    server_name = "Unknown Server"
                    if g_id:
                        guild_obj = self.bot.get_guild(int(g_id))
                        if guild_obj:
                            server_name = guild_obj.name
                    lines.append(f"• `{trigger}` | `{server_name}`")

            embed.set_footer(text="Scope: Global Overview")
            embed.description = "\n".join(lines) if lines else "No autoresponders found across any servers."
        
        else:  # server scope
            local_responders = []
            global_responders = []

            for trigger, content in data.items():
                if content.get("global"):
                    global_responders.append(f"• `{trigger}`")
                elif str(content.get("guild_id", "")) == guild_id:
                    local_responders.append(f"• `{trigger}`")

            embed.set_footer(text=f"Server: {ctx.guild.name}")
            
            local_value = "\n".join(local_responders) if local_responders else "No local server responders set."
            global_value = "\n".join(global_responders) if global_responders else "No global responders active."

            embed.add_field(name="🏡 Local Server Responders", value=local_value, inline=False)
            embed.add_field(name="🌐 Global Responders", value=global_value, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="deleteallautoresponders")
    async def deleteallautoresponders(self, ctx, scope: str = "server"):
        trusted_list = get_server_trusted_users(str(ctx.guild.id))
        is_server_trusted = str(ctx.author.id) in trusted_list
        is_bot_admin = is_admin(ctx.author.id)

        if not is_bot_admin and not is_server_trusted:
            return await ctx.send("❌ You do not have permission to use this command.")

        scope = scope.lower().strip()
        if scope not in ("global", "server"):
            return await ctx.send("❌ Usage: `.deleteallautoresponders server` or `.deleteallautoresponders global` (default: server)")

        if scope == "global":
            if not is_admin(ctx.author.id, ctx.guild, check_global=True):
                return await ctx.send("❌ You do not have permission to execute global wipes.")
            
            if remove_all_auto_responses(global_all=True):
                await ctx.send("🗑️ **ALL auto responders deleted globally across every server.**")
            else:
                await ctx.send("❌ Failed global reset operation.")
        
        else:  # server wipe
            if remove_all_auto_responses(guild_id=str(ctx.guild.id)):
                await ctx.send(f"🗑️ **All local auto responders for {ctx.guild.name} have been deleted.**")
            else:
                await ctx.send("❌ Failed server reset operation.")


async def setup(bot):
    await bot.add_cog(AutoresponderCog(bot))