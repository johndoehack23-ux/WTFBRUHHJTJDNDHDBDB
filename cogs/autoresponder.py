import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class AutoresponderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="autoresponder", description="Create or manage an autoresponder.")
    @app_commands.describe(
        action="add | edit | list",
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
        if not is_admin(interaction.user.id, interaction.guild) and not interaction.permissions.administrator:
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        action = action.lower().strip()
        guild_id = str(interaction.guild.id)
        channel_id = str(channel.id) if channel else None

        if action in ["removeall", "global_removeall"]:
            if action == "global_removeall":
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                if remove_all_auto_responses(global_all=True):
                    await interaction.response.send_message("🗑️ **ALL auto responders deleted globally.**", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Failed global reset operation.", ephemeral=True)
            else:
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                if remove_all_auto_responses(guild_id=guild_id):
                    await interaction.response.send_message("🗑️ **All auto responders for this server deleted.**", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Failed server reset operation.", ephemeral=True)
            return

        if global_server and not is_admin(interaction.user.id, interaction.guild, check_global=True):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

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

        elif action == "edit":
            if not trigger:
                return await interaction.response.send_message("❌ Need current trigger to locate the dataset entry.", ephemeral=True)

            all_responses = get_all_auto_responses()
            if trigger.lower().strip() in all_responses:
                if all_responses[trigger.lower().strip()].get("global") and not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

            edit_auto_response(trigger, new_trigger, reply, matchmode, react, channel_id, cooldown, global_server)
            await interaction.response.send_message(f"✅ Updated autoresponder setup: `{trigger}`", ephemeral=True)

        elif action == "list":
            data = get_all_auto_responses()
            if not data:
                return await interaction.response.send_message("No auto responders set.", ephemeral=True)

            embed = discord.Embed(title="Auto Responders Configuration", color=0x2f3136)
            for t, d in data.items():
                is_item_global = d.get("global", False)
                item_guild = str(d.get("guild_id", guild_id))

                if is_item_global or item_guild == guild_id:
                    ch = f"#{interaction.client.get_channel(int(d.get('channel'))).name}" if d.get("channel") and interaction.client.get_channel(int(d.get("channel"))) else "All Channels"
                    cd = f"{d.get('cooldown')}s" if d.get("cooldown") else "None"
                    global_tag = " 🌐 [Global]" if is_item_global else ""

                    embed.add_field(
                        name=f"`{t}`{global_tag}",
                        value=f"Reply: {d.get('response')[:100]}...\nChannel: {ch}\nCooldown: {cd}",
                        inline=False
                    )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            await interaction.response.send_message("Use: `add | edit | list` (Use `/deleteautoresponder` to remove entries)", ephemeral=True)

    @app_commands.command(name="deleteautoresponder", description="Delete an autoresponder trigger")
    @app_commands.describe(
        trigger="The trigger word/phrase to remove",
        delete_all_globally="Delete this trigger globally across ALL servers (Admin only)"
    )
    async def deleteautoresponder(
        self,
        interaction: discord.Interaction,
        trigger: str,
        delete_all_globally: bool = False
    ):
        if not is_admin(interaction.user.id, interaction.guild) and not interaction.permissions.administrator:
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        target_trigger = trigger.lower().strip()
        guild_id = str(interaction.guild.id)
        all_responses = get_all_auto_responses()

        if target_trigger not in all_responses:
            return await interaction.response.send_message(f"❌ Autoresponder for `{trigger}` not found.", ephemeral=True)

        is_item_global = all_responses[target_trigger].get("global", False)
        item_guild = all_responses[target_trigger].get("guild_id")

        if delete_all_globally:
            if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
            remove_auto_response(target_trigger)
            return await interaction.response.send_message(f"🗑️ Global Autoresponder `{trigger}` has been deleted across all servers.", ephemeral=True)

        else:
            if is_item_global:
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                remove_auto_response(target_trigger)
                return await interaction.response.send_message(f"🗑️ Global Autoresponder `{trigger}` completely removed.", ephemeral=True)
            else:
                if item_guild and item_guild != guild_id:
                    return await interaction.response.send_message(f"❌ Autoresponder for `{trigger}` not found on this server.", ephemeral=True)
                if not is_admin(interaction.user.id, interaction.guild):
                    return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)
                remove_auto_response(target_trigger)
                return await interaction.response.send_message(f"🗑️ Local Autoresponder `{trigger}` successfully removed.", ephemeral=True)


    @commands.command(name="showresponders")
    async def showresponders(self, ctx):
        data = get_all_auto_responses()
        guild_id = str(ctx.guild.id)

        names = [
            t for t, d in data.items()
            if d.get("global") or str(d.get("guild_id", "")) == guild_id
        ]

        embed = discord.Embed(title="**Responders**", color=0x2f3136)

        if not names:
            embed.description = "No autoresponders set for this server."
        else:
            embed.description = "\n".join(f"`{name}`" for name in names)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AutoresponderCog(bot))
