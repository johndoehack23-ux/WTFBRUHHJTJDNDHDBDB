import discord
from discord import app_commands
from discord.ext import commands

from functions import active_games, is_maintenance_mode, stats_col, MAINTENANCE_DOC_ID, is_op

CREATOR_ID = 1465295674768883889


def has_panel_access(user_id: int) -> bool:
    return user_id == CREATOR_ID or is_op(user_id)


def _parse_id_list(raw: str) -> list[str]:
    """Parse comma-separated channel IDs; strip whitespace and <#...>."""
    if raw is None:
        return []
    parts = []
    for piece in str(raw).replace(" ", ",").split(","):
        piece = piece.strip().replace("<#", "").replace(">", "")
        if piece:
            parts.append(piece)
    return parts


def _collect_guild_games():
    """
    Build {guild_id: [game_info, ...]} for non-practice active games.
    game_info: {channel_id, secret, revealed_indices, guild_id}
    """
    by_guild = {}
    for game_key, game in list(active_games.items()):
        if not isinstance(game, dict) or game.get("practice"):
            continue
        guild_id = game.get("guild_id")
        if not guild_id:
            continue
        try:
            channel_id = int(game_key)
        except (TypeError, ValueError):
            # practice keys look like "{id}_practice_{user}"
            continue
        entry = {
            "channel_id": channel_id,
            "secret": game.get("secret", "?"),
            "revealed_indices": game.get("revealed_indices") or [],
            "guild_id": int(guild_id),
        }
        by_guild.setdefault(int(guild_id), []).append(entry)
    return by_guild


def _playing_status(games: list) -> str:
    if not games:
        return "🔴"
    # Any revealed letter => someone is actively guessing
    if any(g.get("revealed_indices") for g in games):
        return "🟢"
    return "🟡"


# ───────────────────────── Announce ─────────────────────────


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


# ───────────────────────── View Wordle Playing ─────────────────────────


class EndGamesModal(discord.ui.Modal, title="serverID"):
    server_id_input = discord.ui.TextInput(
        label="serverID",
        placeholder="Paste the server ID…",
        required=True,
        max_length=30,
    )
    channel_ids_input = discord.ui.TextInput(
        label="channelID1, channelID2, …",
        placeholder="IDs, or . or 1 = all channels in that server",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )

        sid_raw = str(self.server_id_input.value).strip()
        if not sid_raw.isdigit():
            return await interaction.response.send_message(
                "❌ serverID must be a numeric ID.", ephemeral=True
            )
        target_gid = int(sid_raw)

        ch_raw = str(self.channel_ids_input.value).strip()
        end_all = ch_raw in {".", "1"}

        ended_channels = []
        keys_to_delete = []

        for game_key, game in list(active_games.items()):
            if not isinstance(game, dict) or game.get("practice"):
                continue
            if int(game.get("guild_id") or 0) != target_gid:
                continue
            try:
                channel_id = int(game_key)
            except (TypeError, ValueError):
                continue

            if end_all:
                keys_to_delete.append((game_key, channel_id))
            else:
                wanted = set(_parse_id_list(ch_raw))
                if str(channel_id) in wanted:
                    keys_to_delete.append((game_key, channel_id))

        if not keys_to_delete:
            return await interaction.response.send_message(
                f"❌ No matching active games found for server `{target_gid}`.",
                ephemeral=True,
            )

        bot = interaction.client
        for game_key, channel_id in keys_to_delete:
            active_games.pop(game_key, None)
            ended_channels.append(channel_id)
            channel = bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except Exception:
                    channel = None
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send("Wordle ended by: iamninjaau")
                except (discord.Forbidden, discord.HTTPException):
                    pass

        mentions = " ".join(f"<#{c}>" for c in ended_channels)
        await interaction.response.send_message(
            f"✅ Ended {len(ended_channels)} game(s) in server `{target_gid}`.\n{mentions}",
            ephemeral=True,
        )


class EditWordsModal(discord.ui.Modal, title="Edit Wordle words"):
    channel_ids_input = discord.ui.TextInput(
        label="channelID",
        placeholder="channelID1,channelID2,… (up to 5)",
        required=True,
        max_length=200,
    )
    words_input = discord.ui.TextInput(
        label="Word",
        placeholder="word,test,test,test123,test12  (one per channel, comma-separated)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )

        channel_ids = _parse_id_list(str(self.channel_ids_input.value))
        words_raw = [w.strip() for w in str(self.words_input.value).split(",")]
        words = ["".join(c for c in w.lower() if c.isalpha()) for w in words_raw if w.strip()]

        if not channel_ids:
            return await interaction.response.send_message(
                "❌ Provide at least one channel ID.", ephemeral=True
            )
        if len(words) != len(channel_ids):
            return await interaction.response.send_message(
                f"❌ Channel count ({len(channel_ids)}) must match word count ({len(words)}).\n"
                "Example: channelIDs `111,222` → words `apple,grape`",
                ephemeral=True,
            )
        if len(channel_ids) > 5:
            return await interaction.response.send_message(
                "❌ Max 5 channel IDs at once.", ephemeral=True
            )

        results = []
        for cid_str, word in zip(channel_ids, words):
            if not cid_str.isdigit():
                results.append(f"❌ `{cid_str}` — invalid channel ID")
                continue
            if not word:
                results.append(f"❌ <#{cid_str}> — empty/invalid word")
                continue

            # Game keys may be int or str
            game_key = None
            for k in (int(cid_str), cid_str):
                if k in active_games and isinstance(active_games[k], dict) and not active_games[k].get("practice"):
                    game_key = k
                    break

            if game_key is None:
                results.append(f"❌ <#{cid_str}> — no active game")
                continue

            old = active_games[game_key].get("secret", "?")
            active_games[game_key]["secret"] = word
            active_games[game_key]["length"] = len(word)
            results.append(f"✅ <#{cid_str}> `{old}` → `{word}`")

            # Update debug message if present
            debug_msg_id = active_games[game_key].get("debug_msg_id")
            debug_ch_id = active_games[game_key].get("debug_msg_channel_id")
            if debug_msg_id and debug_ch_id:
                try:
                    debug_ch = interaction.client.get_channel(debug_ch_id)
                    if debug_ch:
                        dm = await debug_ch.fetch_message(debug_msg_id)
                        gid = active_games[game_key].get("guild_id")
                        guild_obj = interaction.client.get_guild(gid) if gid else None
                        gname = guild_obj.name if guild_obj else str(gid)
                        await dm.edit(content=f"🔐 `{word}` | {gid} ({gname}) *(edited)*")
                except Exception:
                    pass

        await interaction.response.send_message("\n".join(results), ephemeral=True)


class WordlePlayingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="End", style=discord.ButtonStyle.danger, custom_id="panel_wordle_end")
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        await interaction.response.send_modal(EndGamesModal())

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.success, custom_id="panel_wordle_edit")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        await interaction.response.send_modal(EditWordsModal())

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.primary, custom_id="panel_wordle_hint")
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        # Yellow-ish: Discord has no true yellow; primary is blurple.
        # User asked yellow — secondary is grey, success green, danger red.
        # Using primary; message is plain text WIP as requested (not embed).
        await interaction.response.send_message("WIP", ephemeral=True)


# Discord has no pure yellow button style; map Hint to secondary + note,
# or use primary. User asked yellow — closest is often omitted.
# Re-bind Hint to a custom style: Discord only has primary/secondary/success/danger.
# We'll keep primary and accept it; alternatively secondary.
# Actually discord.ButtonStyle has no yellow. Keep primary for Hint.


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

    @discord.ui.button(
        label="View Wordle Playing",
        style=discord.ButtonStyle.secondary,
        custom_id="panel_view_wordle_playing",
    )
    async def view_wordle_playing(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return

        by_guild = _collect_guild_games()
        bot = interaction.client

        # Include all guilds the bot is in so 🔴 servers still show
        guild_ids = set(by_guild.keys()) | {g.id for g in bot.guilds}

        if not guild_ids:
            return await interaction.response.send_message(
                "❌ Bot is not in any servers.",
                ephemeral=True,
            )

        lines = []
        # Sort by name for readability
        guild_entries = []
        for gid in guild_ids:
            guild = bot.get_guild(gid)
            name = guild.name if guild else f"Unknown ({gid})"
            guild_entries.append((name.lower(), name, gid))
        guild_entries.sort()

        for _, name, gid in guild_entries:
            games = by_guild.get(gid, [])
            status = _playing_status(games)

            if not games:
                lines.append(
                    f"**{name}**\n"
                    f"Playing: {status} (noone playing)\n"
                    f"Word: —\n"
                    f"channel: —\n"
                    f"serverID: `{gid}`"
                )
            else:
                # One block per active channel under this server
                for g in games:
                    cid = g["channel_id"]
                    word = g["secret"]
                    st = "🟢 (playing)" if g.get("revealed_indices") else "🟡 (Playing but no players are guessing)"
                    lines.append(
                        f"**{name}**\n"
                        f"Playing: {st}\n"
                        f"Word: `{word}`\n"
                        f"channel: <#{cid}> (`{cid}`)\n"
                        f"serverID: `{gid}`"
                    )

        # Discord embed description max 4096 — paginate if needed
        description = "\n\n".join(lines)
        if len(description) > 4000:
            description = description[:3990] + "\n…"

        embed = discord.Embed(
            title="Wordle Players",
            description=description or "No servers found.",
            color=0x2f3136,
        )
        embed.set_footer(text="serverID & channelID are in `backticks` — tap to copy")

        await interaction.response.send_message(
            embed=embed,
            view=WordlePlayingView(),
            ephemeral=True,
        )

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
