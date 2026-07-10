import discord
from discord.ext import commands
from discord import app_commands
from functions import *
import json
import os

STATS_FILE = "stats.json"

def get_server_trusted_users(guild_id: str) -> list:
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("trusted_users", {}).get(str(guild_id), [])
    except Exception:
        return []

class SayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="say", description="Send a message as the bot")
    @app_commands.describe(
        message="The message to send",
        channel="Target channel (defaults to current)",
        message_id="Message ID to reply to",
        user="The user to impersonate via webhook"
    )
    async def say_slash(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel = None,
        message_id: str = None,
        user: discord.Member = None
    ):
        trusted_list = get_server_trusted_users(str(interaction.guild.id))
        is_server_trusted = str(interaction.user.id) in trusted_list
        is_bot_admin = is_admin(interaction.user.id)
        
        if not is_server_trusted and not is_bot_admin: 
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        if is_maintenance_mode() and not is_bot_admin:
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        # CHECK: Block using both a webhook user and a message ID reply together
        if user and message_id:
            return await interaction.response.send_message("Discord bots does not support replying with webhook.", ephemeral=True)

        target_channel = channel if channel else interaction.channel

        if user:
            if not target_channel.permissions_for(interaction.guild.me).manage_webhooks:
                return await interaction.response.send_message('Bot doesn\'t have permission called: "Manage Webhooks".', ephemeral=False)

            try:
                stats_data = {}
                if os.path.exists(STATS_FILE):
                    with open(STATS_FILE, "r", encoding="utf-8") as f:
                        stats_data = json.load(f)
                
                if "user_say_list" not in stats_data:
                    stats_data["user_say_list"] = []
                
                user_id_str = str(user.id)
                if user_id_str not in stats_data["user_say_list"]:
                    stats_data["user_say_list"].append(user_id_str)
                    with open(STATS_FILE, "w", encoding="utf-8") as f:
                        json.dump(stats_data, f, indent=4)
            except:
                pass

            try:
                webhooks = await target_channel.webhooks()
                webhook = discord.utils.get(webhooks, name="SayWebhook")
                if not webhook:
                    webhook = await target_channel.create_webhook(name="SayWebhook")
                
                avatar_url = user.display_avatar.url if user.display_avatar else None
                await webhook.send(content=message, username=user.display_name, avatar_url=avatar_url)
                return await interaction.response.send_message(f"✅ Message sent via webhook as {user.mention}!", ephemeral=True)
            except Exception as e:
                return await interaction.response.send_message(f"❌ Failed to deliver webhook payload: {e}", ephemeral=True)

        target_message = None
        resolved_msg_id = None

        if message_id:
            resolved_msg_id = message_id.strip()
        elif interaction.data.get("resolved", {}).get("messages"):
            resolved_msg_id = list(interaction.data["resolved"]["messages"].keys())[0]

        if resolved_msg_id:
            try:
                target_message = await target_channel.fetch_message(int(resolved_msg_id))
            except Exception:
                try:
                    target_message = await interaction.channel.fetch_message(int(resolved_msg_id))
                    target_channel = interaction.channel
                except Exception:
                    return await interaction.response.send_message("❌ **Error:** Could not locate that Message ID.", ephemeral=True)

        try:
            if target_message:
                await target_message.reply(message)
                await interaction.response.send_message(f"✅ Successfully replied to message `{target_message.id}` in {target_channel.mention}!", ephemeral=True)
            else:
                await target_channel.send(message)
                await interaction.response.send_message(f"✅ Message successfully sent to {target_channel.mention}!", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to deliver message payload: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SayCog(bot))