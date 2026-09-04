import discord
from discord import app_commands
from discord.ext import commands

from functions import active_games, is_maintenance_mode, stats_col, MAINTENANCE_DOC_ID, is_op

CREATOR_ID = 1465295674768883889


def has_panel_access(user_id: int) -> bool:
    return user_id == CREATOR_ID or is_op(user_id)


class AnnounceModal(discord.ui.Modal, title="Announce a message!"):
    announcement_title = discord.ui.TextInput(
        label="Title",
        placeholder="Enter the announcement title...",
        required=True,
        max_length=256,
    )

    announcement_description = discord.ui.TextInput(
        label="Description",
        placeholder="Enter the announcement description...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        channels = []
        seen = set()

        # active_games uses the Wordle channel ID as the normal game key.
        # Only non-practice games count as people currently playing Wordle.
        for game_key, game in list(active_games.items()):
            if not isinstance(game, dict) or game.get("practice"):
                continue

            guild_id = game.get("guild_id")
            if not guild_id:
                continue

            try:
                channel_id = int(game_key)
            except (TypeError, ValueError):
                continue

            if channel_id in seen:
                continue

            channel = interaction.client.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await interaction.client.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

            if not isinstance(channel, discord.TextChannel):
                continue

            seen.add(channel_id)
            channels.append(channel)

        if not channels:
            return await interaction.response.send_message(
                "❌ There are currently no active Wordle games. You can only announce when others are playing Wordle.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title=str(self.announcement_title),
            description=str(self.announcement_description),
        )
        embed.set_footer(text="Submitted by the owner of the bot (iamninjaau)")

        sent = 0
        failed = 0
        for channel in channels:
            try:
                await channel.send(embed=embed)
                sent += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1

        result = f"✅ Announcement sent to {sent} active Wordle channel(s)."
        if failed:
            result += f"\n⚠️ Failed to send to {failed} channel(s)."

        await interaction.response.send_message(result, ephemeral=True)


class AnnouncementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="Announce a message!",
        style=discord.ButtonStyle.danger,
        custom_id="panel_announce_message",
    )
    async def announce_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        await interaction.response.send_modal(AnnounceModal())


class MaintenanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _set_state(self, interaction: discord.Interaction, enabled: bool):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )

        try:
            stats_col.replace_one(
                {"_id": MAINTENANCE_DOC_ID},
                {"_id": MAINTENANCE_DOC_ID, "enabled": enabled},
                upsert=True,
            )
        except Exception as error:
            print(f"[panel maintenance] failed: {error}")
            return await interaction.response.send_message(
                "❌ Failed to update maintenance mode.", ephemeral=True
            )

        state = "ON" if enabled else "OFF"
        await interaction.response.send_message(
            f"✅ Maintenance mode is now **{state}**.", ephemeral=True
        )

    @discord.ui.button(label="ON", style=discord.ButtonStyle.success, custom_id="panel_maintenance_on")
    async def maintenance_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_state(interaction, True)

    @discord.ui.button(label="OFF", style=discord.ButtonStyle.danger, custom_id="panel_maintenance_off")
    async def maintenance_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_state(interaction, False)


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if not has_panel_access(interaction.user.id):
            await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="📢 Announce", style=discord.ButtonStyle.secondary, custom_id="panel_announce")
    async def announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return

        embed = discord.Embed(
            title="📢 Wordle Announcement",
            description="Welcome! You can ONLY announce when there's others playing the wordle game!\n\n-# NOTE: ⚠️ This will be global ⚠️",
        )
        await interaction.response.send_message(
            embed=embed,
            view=AnnouncementView(),
            ephemeral=True,
        )

    @discord.ui.button(label="🚧 Toggle Maintenance", style=discord.ButtonStyle.secondary, custom_id="panel_maintenance")
    async def maintenance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return

        embed = discord.Embed(
            title="Toggle Maintenance (WIP)",
            description="Enable or Disable a maintenance!",
        )
        await interaction.response.send_message(
            embed=embed,
            view=MaintenanceView(),
            ephemeral=True,
        )

    @discord.ui.button(label="🔜 Test", style=discord.ButtonStyle.secondary, custom_id="panel_test_1")
    async def test_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_message("This button is WIP!", ephemeral=True)

    @discord.ui.button(label="🔜 Test", style=discord.ButtonStyle.secondary, custom_id="panel_test_2")
    async def test_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_message("This button is WIP!", ephemeral=True)

    @discord.ui.button(label="🔜 Test", style=discord.ButtonStyle.secondary, custom_id="panel_test_3")
    async def test_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        await interaction.response.send_message("This button is WIP!", ephemeral=True)


class PanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="panel", description="Open the bot owner panel")
    async def panel(self, interaction: discord.Interaction):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this command.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="Bot Panel",
            description="Test Message",
        )

        await interaction.response.send_message(
            embed=embed,
            view=PanelView(),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(PanelCog(bot))
