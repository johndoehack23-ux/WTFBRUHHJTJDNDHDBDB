import discord
from discord import app_commands
from discord.ext import commands

from functions import get_tester_role_id, active_games, active_1v1_matches, is_maintenance_mode, stats_col, MAINTENANCE_DOC_ID, is_op

CREATOR_ID = 1465295674768883889


TESTER_ROLE_ID = 1545319674814791701
TESTER_SERVER_ID = 1545272798451343360


def has_panel_access(user_id: int, member: discord.Member | None = None, bot=None) -> bool:
    # Panel is creator / op only — no tester role
    return user_id == CREATOR_ID or is_op(user_id)


def is_tester_only(user_id: int, member: discord.Member | None = None, bot=None) -> bool:
    """True if user is tester but not creator/op."""
    if user_id == CREATOR_ID or is_op(user_id):
        return False
    if member is not None and any(getattr(r, "id", 0) == get_tester_role_id() for r in getattr(member, "roles", [])):
        return True
    if bot is not None:
        home = bot.get_guild(TESTER_SERVER_ID)
        if home:
            m = home.get_member(user_id)
            if m and any(r.id == get_tester_role_id() for r in m.roles):
                return True
    return False


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
    """Build {guild_id: [game_info, ...]} for wordle + 1v1 mode games."""
    by_guild = {}
    by_channel = {}

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
        entry = by_channel.get(channel_id)
        if not entry:
            entry = {
                "channel_id": channel_id,
                "secret": None,
                "mode_secret": None,
                "revealed_indices": [],
                "guild_id": int(guild_id),
                "kinds": [],
            }
            by_channel[channel_id] = entry
        entry["secret"] = game.get("secret", "?")
        entry["revealed_indices"] = game.get("revealed_indices") or []
        entry["guild_id"] = int(guild_id)
        if "wordle" not in entry["kinds"]:
            entry["kinds"].append("wordle")

    for channel_id, match in list(active_1v1_matches.items()):
        if not isinstance(match, dict):
            continue
        guild_id = match.get("guild_id")
        if not guild_id:
            continue
        try:
            cid = int(channel_id)
        except (TypeError, ValueError):
            continue
        entry = by_channel.get(cid)
        if not entry:
            entry = {
                "channel_id": cid,
                "secret": None,
                "mode_secret": None,
                "revealed_indices": [],
                "guild_id": int(guild_id),
                "kinds": [],
            }
            by_channel[cid] = entry
        entry["mode_secret"] = match.get("secret")
        entry["guild_id"] = int(guild_id)
        if "mode" not in entry["kinds"]:
            entry["kinds"].append("mode")

    for entry in by_channel.values():
        by_guild.setdefault(int(entry["guild_id"]), []).append(entry)
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
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        await interaction.response.send_modal(AnnounceModal())


class MaintenanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _set_state(self, interaction: discord.Interaction, enabled: bool):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
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
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
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
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
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
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        await interaction.response.send_modal(EndGamesModal())

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.success, custom_id="panel_wordle_edit")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message(
                "❌ Only the bot creator or an operator can use this.", ephemeral=True
            )
        await interaction.response.send_modal(EditWordsModal())

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.primary, custom_id="panel_wordle_hint")
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
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



# ───────────────────────── Fake Streak (client-side) ─────────────────────────

def _get_fake_map(_ignored=None) -> dict:
    """Flat map: target_user_id -> streak. Only that user sees it on .lb."""
    from functions import load_stats
    stats = load_stats()
    raw = stats.get("fake_streaks") or {}
    out = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if isinstance(v, dict):
            # migrate old nested format
            for tid, st in v.items():
                if str(tid).isdigit():
                    try:
                        out[str(tid)] = int(st)
                    except (TypeError, ValueError):
                        pass
        elif str(k).isdigit():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                pass
    return out


def _save_fake_map(_ignored, data: dict):
    from functions import load_stats, save_stats
    stats = load_stats()
    # Always store flat: targetId -> streak
    stats["fake_streaks"] = {str(k): int(v) for k, v in data.items() if str(k).isdigit()}
    save_stats(stats)


class FakeStreakSetModal(discord.ui.Modal, title="Set Fake Streaks"):
    def __init__(self):
        super().__init__()
        self.ids_input = discord.ui.TextInput(
            label="userID1, userID2, userID3",
            placeholder="userID1,userID2,... up to 6",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.streaks_input = discord.ui.TextInput(
            label="streak1, streak2, streak3",
            placeholder="streak1,streak2,... matching order (up to 6)",
            required=True,
            max_length=100,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.ids_input)
        self.add_item(self.streaks_input)

    async def on_submit(self, interaction: discord.Interaction):
        ids = [x.strip().replace("<@", "").replace("!", "").replace(">", "") for x in str(self.ids_input.value).split(",")]
        streaks = [x.strip() for x in str(self.streaks_input.value).split(",")]
        ids = [i for i in ids if i]
        streaks = [s for s in streaks if s]
        if not ids or len(ids) > 6 or len(streaks) > 6:
            return await interaction.response.send_message("Provide 1-6 userIDs and matching streaks.", ephemeral=True)
        if len(ids) != len(streaks):
            return await interaction.response.send_message("userID count must match streak count.", ephemeral=True)
        data = _get_fake_map(interaction.user.id)
        for uid, st in zip(ids, streaks):
            if not uid.isdigit():
                return await interaction.response.send_message(f"Invalid userID: {uid}", ephemeral=True)
            try:
                n = int(st)
            except ValueError:
                return await interaction.response.send_message(f"Invalid streak: {st}", ephemeral=True)
            data[uid] = n
        _save_fake_map(interaction.user.id, data)
        await interaction.response.send_message(
            f"Fake streaks set for {len(ids)} target user(s). **Only those users** see the fake when they run `.lb` — not you, not anyone else.",
            ephemeral=True,
        )


class FakeStreakRemoveModal(discord.ui.Modal, title="Remove Fake Streaks"):
    def __init__(self):
        super().__init__()
        self.ids_input = discord.ui.TextInput(
            label="userID1, userID2, userID3",
            placeholder="userID1,userID2,... up to 6",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.ids_input)

    async def on_submit(self, interaction: discord.Interaction):
        ids = [x.strip().replace("<@", "").replace("!", "").replace(">", "") for x in str(self.ids_input.value).split(",")]
        ids = [i for i in ids if i and i.isdigit()]
        if not ids or len(ids) > 6:
            return await interaction.response.send_message("Provide 1-6 numeric userIDs.", ephemeral=True)
        data = _get_fake_map(interaction.user.id)
        removed = 0
        for uid in ids:
            if uid in data:
                del data[uid]
                removed += 1
        _save_fake_map(interaction.user.id, data)
        await interaction.response.send_message(f"Removed {removed} target fake streak(s).", ephemeral=True)


class FakeStreakView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Streak", style=discord.ButtonStyle.danger, custom_id="fake_streak_set")
    async def streak_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message("No access.", ephemeral=True)
        await interaction.response.send_modal(FakeStreakSetModal())

    @discord.ui.button(label="Show list", style=discord.ButtonStyle.secondary, custom_id="fake_streak_list")
    async def list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message("No access.", ephemeral=True)
        data = _get_fake_map(interaction.user.id)
        if not data:
            return await interaction.response.send_message("No fake streaks set.", ephemeral=True)
        lines = [f"• <@{uid}> (`{uid}`): **{st}**" for uid, st in data.items()]
        await interaction.response.send_message("**Fake streak targets** (only they see it on `.lb`):\n" + "\n".join(lines), ephemeral=True)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, custom_id="fake_streak_remove")
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message("No access.", ephemeral=True)
        await interaction.response.send_modal(FakeStreakRemoveModal())

    @discord.ui.button(label="Removeall", style=discord.ButtonStyle.danger, custom_id="fake_streak_removeall")
    async def removeall_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, interaction.user if isinstance(interaction.user, discord.Member) else None, interaction.client):
            return await interaction.response.send_message("No access.", ephemeral=True)
        _save_fake_map(interaction.user.id, {})
        await interaction.response.send_message("All fake streak data removed.", ephemeral=True)



class GuideButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        names = [
            ("Announce", "Use **Announce** to post a global wordle announcement when others are playing."),
            ("Maintenance", "Toggle bot maintenance ON/OFF so non-admins are blocked."),
            ("View Wordle Playing", "Lists all servers/channels with active Wordle games. End / Edit / Hint from there."),
            ("Leaderboard", "Fake Streak / Fake Player / Hecker Mode tools."),
            ("Guide", "You are here — panel button tutorials."),
        ]
        for label, text in names:
            b = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
            async def _cb(interaction: discord.Interaction, lab=label, desc=text):
                embed = discord.Embed(title=f"{lab} WIP", description=desc, color=0x2f3136)
                await interaction.response.edit_message(embed=embed, view=self)
            b.callback = _cb
            self.add_item(b)



# ───────────────────────── Leaderboard tools ─────────────────────────
MAX_FAKE_USERNAME = 30
MAX_FAKE_STREAK = 10 ** 15  # 1 quadrillion
HECKER_USER_COUNT = 99999
HECKER_DURATION_SEC = 60


def _load_fake_players() -> list:
    doc = stats_col.find_one({"_id": "fake_players"}) or {}
    raw = doc.get("entries") or []
    return list(raw) if isinstance(raw, list) else []


def _save_fake_players(entries: list):
    stats_col.replace_one(
        {"_id": "fake_players"},
        {"_id": "fake_players", "entries": entries},
        upsert=True,
    )


def _set_hecker_mode(seconds: int = HECKER_DURATION_SEC):
    import time as _time
    until = _time.time() + seconds
    stats_col.replace_one(
        {"_id": "hecker_mode"},
        {"_id": "hecker_mode", "until": until},
        upsert=True,
    )
    return until


def is_hecker_mode_active() -> bool:
    import time as _time
    doc = stats_col.find_one({"_id": "hecker_mode"}) or {}
    until = float(doc.get("until") or 0)
    return _time.time() < until


class FakePlayerAddModal(discord.ui.Modal, title="Add Fake Player"):
    username = discord.ui.TextInput(label="username", max_length=MAX_FAKE_USERNAME, required=True)
    streak = discord.ui.TextInput(label="Streak", placeholder="1 to 1000000000000000", required=True)
    server_field = discord.ui.TextInput(
        label="ServerName/ServerID",
        placeholder="Custom name OR numeric serverID",
        required=True,
        max_length=100,
    )
    visibility = discord.ui.TextInput(
        label="everyone/userID",
        placeholder="everyone OR a userID",
        required=True,
        max_length=30,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != CREATOR_ID:
            return await interaction.response.send_message("Creator only.", ephemeral=True)

        uname = str(self.username.value or "").strip()
        if not uname or len(uname) > MAX_FAKE_USERNAME:
            return await interaction.response.send_message(
                f"Username required, max {MAX_FAKE_USERNAME} characters.", ephemeral=True
            )

        try:
            streak_val = int(str(self.streak.value).replace(",", "").strip())
        except ValueError:
            return await interaction.response.send_message("Streak must be a number.", ephemeral=True)
        if streak_val < 0 or streak_val > MAX_FAKE_STREAK:
            return await interaction.response.send_message(
                f"Streak max is {MAX_FAKE_STREAK} (1 quadrillion).", ephemeral=True
            )

        server_raw = str(self.server_field.value or "").strip()
        if not server_raw:
            return await interaction.response.send_message("ServerName/ServerID required.", ephemeral=True)

        server_id = None
        server_name = server_raw
        if server_raw.isdigit():
            server_id = server_raw
            g = interaction.client.get_guild(int(server_raw))
            server_name = g.name if g else f"Server {server_raw}"

        vis = str(self.visibility.value or "").strip().lower()
        if vis == "everyone":
            visibility = "everyone"
        elif vis.isdigit():
            visibility = vis
        else:
            return await interaction.response.send_message(
                "Visibility must be `everyone` or a numeric userID.", ephemeral=True
            )

        entries = _load_fake_players()
        # Block duplicate usernames (case-insensitive)
        for e in entries:
            if str(e.get("username", "")).strip().lower() == uname.lower():
                return await interaction.response.send_message(
                    f"Username **{uname}** already exists. Cannot add duplicate.",
                    ephemeral=True,
                )

        entries.append({
            "username": uname,
            "streak": streak_val,
            "server_name": server_name,
            "server_id": server_id,
            "visibility": visibility,
        })
        _save_fake_players(entries)
        where = f"server `{server_id}`" if server_id else f"custom name **{server_name}**"
        await interaction.response.send_message(
            f"Fake player **{uname}** streak **{streak_val}** added ({where}, vis: {visibility}).",
            ephemeral=True,
        )


class FakePlayerDeleteModal(discord.ui.Modal, title="Delete Fake Player"):
    username = discord.ui.TextInput(
        label="username",
        placeholder="Exact username to remove",
        max_length=MAX_FAKE_USERNAME,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != CREATOR_ID:
            return await interaction.response.send_message("Creator only.", ephemeral=True)

        uname = str(self.username.value or "").strip()
        if not uname:
            return await interaction.response.send_message("Username required.", ephemeral=True)

        entries = _load_fake_players()
        before = len(entries)
        entries = [
            e for e in entries
            if str(e.get("username", "")).strip().lower() != uname.lower()
        ]
        if len(entries) == before:
            return await interaction.response.send_message(
                f"No fake player named **{uname}**.", ephemeral=True
            )
        _save_fake_players(entries)
        await interaction.response.send_message(
            f"Removed fake player **{uname}**.", ephemeral=True
        )


class FakePlayerMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _creator_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != CREATOR_ID:
            await interaction.response.send_message("Creator only.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Add", style=discord.ButtonStyle.success)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._creator_only(interaction):
            return
        await interaction.response.send_modal(FakePlayerAddModal())

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._creator_only(interaction):
            return
        await interaction.response.send_modal(FakePlayerDeleteModal())

    @discord.ui.button(label="Delete all Fake Player", style=discord.ButtonStyle.danger)
    async def delete_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._creator_only(interaction):
            return
        entries = _load_fake_players()
        count = len(entries)
        _save_fake_players([])
        await interaction.response.send_message(
            f"Deleted **{count}** fake player(s).", ephemeral=True
        )


class LeaderboardToolsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _creator_only(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != CREATOR_ID:
            await interaction.response.send_message("Creator only.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="😂 Fake Streak", style=discord.ButtonStyle.danger, custom_id="lbtools_fake_streak")
    async def fake_streak(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_panel_access(interaction.user.id, None, interaction.client):
            return await interaction.response.send_message("No access.", ephemeral=True)
        embed = discord.Embed(
            title="Fake Streak 🤩",
            description="Welcome! This is fake streak i am lazy to put description here ahhhhh",
            color=0x2f3136,
        )
        await interaction.response.send_message(embed=embed, view=FakeStreakView(), ephemeral=True)

    @discord.ui.button(label="Fake Player", style=discord.ButtonStyle.primary, custom_id="lbtools_fake_player")
    async def fake_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._creator_only(interaction):
            return
        embed = discord.Embed(
            title="Fake Player",
            description="WIP",
            color=0x2f3136,
        )
        await interaction.response.send_message(
            embed=embed, view=FakePlayerMenuView(), ephemeral=True
        )

    @discord.ui.button(label="💻 Hecker Mode", style=discord.ButtonStyle.danger, custom_id="lbtools_hecker")
    async def hecker_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._creator_only(interaction):
            return
        until = _set_hecker_mode(HECKER_DURATION_SEC)
        await interaction.response.send_message(
            f"💻 Hecker Mode ON for **{HECKER_DURATION_SEC}s** — everyone sees {HECKER_USER_COUNT} hackers on `.lb` (data not deleted).",
            ephemeral=True,
        )


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not has_panel_access(interaction.user.id, member, interaction.client):
            await interaction.response.send_message(
                "❌ No access.", ephemeral=True
            )
            return False
        return True

    def _tester_only_user(self, interaction: discord.Interaction) -> bool:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        return is_tester_only(interaction.user.id, member, interaction.client)

    @discord.ui.button(label="📢 Announce", style=discord.ButtonStyle.secondary, custom_id="panel_announce")
    async def announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        if self._tester_only_user(interaction):
            return await interaction.response.send_message("Testers can only use View Wordle Playing and Guide.", ephemeral=True)

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
        if self._tester_only_user(interaction):
            return await interaction.response.send_message("Testers can only use View Wordle Playing and Guide.", ephemeral=True)

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
        label="👁️ View Wordle Playing",
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
                    word = g.get("secret")
                    mode_word = g.get("mode_secret")
                    kinds = g.get("kinds") or []
                    st = "🟢 (playing)" if g.get("revealed_indices") else "🟡 (Playing but no players are guessing)"
                    if "mode" in kinds and "wordle" not in kinds:
                        st = "🟢 (1v1 mode)" if mode_word else "🟡 (1v1 mode, no word yet)"
                    word_line = f"Word: `{word}`" if word else "Word: —"
                    if mode_word:
                        mode_line = f"Mode: `{mode_word}`"
                    elif "mode" in kinds:
                        mode_line = "Mode: `Not started yet`"
                    else:
                        mode_line = "Mode: —"
                    lines.append(
                        "\n".join([
                            f"**{name}**",
                            f"Playing: {st}",
                            word_line,
                            mode_line,
                            f"channel: <#{cid}> (`{cid}`)",
                            f"serverID: `{gid}`",
                        ])
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

    @discord.ui.button(label="🔧 Leaderboard", style=discord.ButtonStyle.secondary, custom_id="panel_leaderboard_tools")
    async def leaderboard_tools_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        embed = discord.Embed(
            title="WIP",
            description="WIP",
            color=0x2f3136,
        )
        await interaction.response.send_message(embed=embed, view=LeaderboardToolsView(), ephemeral=True)

    @discord.ui.button(label="Guide / Tutorial", style=discord.ButtonStyle.secondary, custom_id="panel_guide")
    async def guide_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_only(interaction):
            return
        embed = discord.Embed(
            title="WIP",
            description=(
                "Tutorial: how to use panel buttons.\n\n"
                "Click a button below to see a short guide for that feature.\n"
                "• **Announce** — global wordle announcements\n"
                "• **Maintenance** — turn maintenance on/off\n"
                "• **View Wordle Playing** — manage live games\n"
                "• **Leaderboard** — Fake Streak, Fake Player, Hecker Mode\n"
                "• **Guide** — this menu"
            ),
            color=0x2f3136,
        )
        # real newlines
        embed.description = embed.description.replace("\\n", "\n") if False else (
            "Tutorial: how to use panel buttons.\n\n"
            "Click a button below to see a short guide for that feature.\n"
            "• **Announce** — global wordle announcements\n"
            "• **Maintenance** — turn maintenance on/off\n"
            "• **View Wordle Playing** — manage live games\n"
            "• **Leaderboard** — Fake Streak, Fake Player, Hecker Mode\n"
            "• **Guide** — this menu"
        )
        embed.description = "\n".join([
            "Tutorial: how to use panel buttons.",
            "",
            "Click a button below to see a short guide for that feature.",
            "• **Announce** — global wordle announcements",
            "• **Maintenance** — turn maintenance on/off",
            "• **View Wordle Playing** — manage live games",
            "• **Leaderboard** — Fake Streak, Fake Player, Hecker Mode",
            "• **Guide** — this menu",
        ])
        await interaction.response.send_message(embed=embed, view=GuideButtonView(), ephemeral=True)


class PanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="panel", description="Open the bot owner panel")
    async def panel(self, interaction: discord.Interaction):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not has_panel_access(interaction.user.id, member, interaction.client):
            return await interaction.response.send_message(
                "❌ No access.",
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
