import discord
from discord.ext import commands
from discord import app_commands
from functions import *


class SayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="say", description="Send a message as the bot")
    @app_commands.describe(
        message="The message to send",
        channel="Target channel (defaults to current)",
        message_id="Message ID to reply to"
    )
    async def say_slash(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel = None,
        message_id: str = None
    ):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message("🛠️ Bot is under maintenance.", ephemeral=True)

        target_channel = channel if channel else interaction.channel
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
