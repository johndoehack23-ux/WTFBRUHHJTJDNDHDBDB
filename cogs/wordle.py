import discord
from discord.ext import commands
from discord import app_commands
import json
import random
from functions import *
from editrespond import r


def has_admin(user, guild):
    if not guild:
        return False
    if isinstance(user, discord.Member):
        return user.guild_permissions.administrator
    return False


def _normalize_channel_id(value):
    """Always return an int channel id (or None). Prevents str/int key mismatches."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_wordle_channels(guild_id) -> list:
    """List of channel-ID strings wordle is restricted to in this guild (set via .setwordle). Empty = no restriction."""
    stats = load_stats()
    return [str(c) for c in stats.get("wordle_channels", {}).get(str(guild_id), [])]


def is_wordle_channel_allowed(guild_id, channel_id) -> bool:
    allowed = get_wordle_channels(guild_id)
    if not allowed:
        return True
    return str(channel_id) in allowed


class WordleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_wordle_announcement(self, ctx_or_interaction, target_channel, content, *, ephemeral_fallback=False):
        """
        Send the game announcement.
        Works with both Context and Interaction.
        Returns True on success, False on failure (caller must clean up active_games).
        """
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)

        async def reply(msg, ephemeral=False):
            if is_interaction:
                if ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.followup.send(msg, ephemeral=ephemeral)
                else:
                    await ctx_or_interaction.response.send_message(msg, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(msg)

        try:
            await target_channel.send(content)
        except discord.Forbidden:
            target_name = getattr(target_channel, "mention", "the configured public channel")
            await reply(
                f"❌ I can’t send the Wordle announcement to {target_name}. "
                "Please give me permission to view and send messages there.",
                ephemeral=ephemeral_fallback,
            )
            return False
        except discord.HTTPException as error:
            print(f"[wordle announcement] {error}")
            await reply("❌ Discord rejected the Wordle announcement. Please try again.", ephemeral=ephemeral_fallback)
            return False

        # Confirm redirect only for prefix commands
        if not is_interaction:
            src_id = getattr(getattr(ctx_or_interaction, "channel", None), "id", None)
            if getattr(target_channel, "id", None) != src_id:
                target_name = getattr(target_channel, "mention", "the configured public channel")
                await reply(f"✅ Wordle started in {target_name}.")
        return True

    def _resolve_target(self, guild_id, preferred_channel, force_preferred=False):
        """
        Decide which channel the game lives in.
        Returns (target_id: int, resolved_channel).
        """
        gid = str(guild_id)
        configured = _normalize_channel_id(
            server_config.get(gid, {}).get("public")
        )

        if configured and not force_preferred:
            target_id = configured
            ch = self.bot.get_channel(target_id)
            if ch is None:
                ch = preferred_channel
                target_id = preferred_channel.id
            return target_id, ch

        return preferred_channel.id, preferred_channel

    def _can_start_game(self, user, guild, *, practice=False):
        """
        Returns (allowed: bool, error_message: str | None)
        Handles daily limits consistently for prefix + slash.
        """
        if practice:
            return True, None

        stats = load_stats()
        gid_str = str(guild.id)
        uid_str = str(user.id)
        trusted_pool = stats.get("trusted_users", {}).get(gid_str, [])
        is_user_trusted = uid_str in trusted_pool

        is_user_admin = is_admin(user.id, guild, check_global=True)
        can_bypass = is_user_admin or (is_infinite_wordle(user.id) and not is_user_trusted)

        if can_bypass:
            return True, None

        count = get_user_game_count(user.id)
        daily_limit = TRUSTED_DAILY_LIMIT if is_user_trusted else REGULAR_DAILY_LIMIT
        
        msg = r("lose", "max_guesses", daily_limit=daily_limit)

        if count >= daily_limit:
            return False, msg
        return True, None

    def _pick_secret_from_category(self, category: str, difficulty: str = "easy"):
        """Load a word from wordlecategories.json. Returns (word, error_msg)."""
        clean_cat = (category or "").lower().strip()
        clean_diff = (difficulty or "easy").lower().strip()

        try:
            with open("wordlecategories.json", "r", encoding="utf-8") as f:
                cats_data = json.load(f)
        except Exception:
            return None, "❌ Failed to load category configuration file."

        if clean_cat not in cats_data:
            available = ", ".join(f"`{c}`" for c in cats_data.keys()) or "none"
            return None, f"❌ Unknown category! Available: {available}"

        available_diffs = list(cats_data[clean_cat].keys())
        if clean_diff not in available_diffs:
            clean_diff = available_diffs[0] if available_diffs else "easy"

        word_pool = cats_data[clean_cat].get(clean_diff, [])
        if not word_pool:
            return None, f"❌ No words found for `{clean_cat} / {clean_diff}`."

        secret = random.choice(word_pool).lower().replace(" ", "").replace("-", "")
        return secret, None

    async def _start_game(
        self,
        *,
        user,
        guild,
        preferred_channel,
        secret_word: str,
        practice: bool = False,
        mode_label: str = "",
        force_preferred_channel: bool = False,
        ctx_or_interaction=None,
        respond_ephemeral: bool = False,
    ):
        """
        Shared start path used by both prefix and slash.
        Handles key normalization, already-running check, announcement, debug msg, and cleanup.
        """
        target_id, resolved_channel = self._resolve_target(
            guild.id, preferred_channel, force_preferred=force_preferred_channel
        )

        game_key = f"{target_id}_practice_{user.id}" if practice else target_id

        # Also check string form of the key in case old games used str keys
        if game_key in active_games or str(game_key) in active_games:
            msg = r("wordle", "already_running")
            if ctx_or_interaction is not None:
                if isinstance(ctx_or_interaction, discord.Interaction):
                    if not ctx_or_interaction.response.is_done():
                        await ctx_or_interaction.response.send_message(msg, ephemeral=True)
                    else:
                        await ctx_or_interaction.followup.send(msg, ephemeral=True)
                else:
                    await ctx_or_interaction.send(msg)
            return False

        active_games[game_key] = {
            "secret": secret_word,
            "length": len(secret_word),
            "guild_id": guild.id,
            "revealed_indices": [],
            "processing_win": False,
            "practice": practice,
            "author_id": user.id,
        }

        if not practice:
            increment_user_game_count(user.id)

        practice_label = " [PRACTICE MODE]" if practice else ""
        if practice:
            content = r("wordle", "start_practice", user_id=user.id, length=len(secret_word))
        else:
            content = r("wordle", "start", user_id=user.id, length=len(secret_word))
        if mode_label:
            content = content.replace("New Wordle", f"New Wordle{mode_label}", 1)

        announced = await self.send_wordle_announcement(
            ctx_or_interaction or preferred_channel,
            resolved_channel,
            content,
            ephemeral_fallback=respond_ephemeral,
        )

        if not announced:
            active_games.pop(game_key, None)
            return False

        if is_debug_mode():
            debug_ch = await get_debug_channel(self.bot)
            if debug_ch:
                try:
                    label = "[PRACTICE] " if practice else ""
                    dm = await debug_ch.send(
                        f"🔐 {label}`{secret_word}` | {guild.id} ({guild.name})"
                    )
                    if not practice:
                        active_games[game_key]["debug_msg_id"] = dm.id
                        active_games[game_key]["debug_msg_channel_id"] = debug_ch.id
                except Exception as e:
                    print(f"[wordle start debug send] {e}")

        return True
          # ──────────────────────────────────────────────────────────────
    # Prefix commands
    # ──────────────────────────────────────────────────────────────

    @commands.command(name="wordle")
    async def wordle_prefix(self, ctx, mode_or_option: str = None, category: str = None, difficulty: str = "easy"):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send(r("maintenance", "on"))

        # ── .wordle globalend ──
        if mode_or_option and mode_or_option.lower().strip() == "globalend":
            if not is_op(ctx.author.id):
                return await ctx.send("You do not have permission to use this command.")
            count = len(active_games)
            active_games.clear()
            await send_debug_msg(
                self.bot,
                f"⚡ `.wordle globalend` | {ctx.author} (`{ctx.author.id}`) ended ALL **{count}** game(s) globally | {ctx.guild.name}",
            )
            return await ctx.send(f"All active Wordle games ended globally ({count} game(s)).")

        # ── .wordle end ──
        if mode_or_option and mode_or_option.lower().strip() == "end":
            if not (is_admin(ctx.author.id, ctx.guild) or has_admin(ctx.author, ctx.guild)):
                return await ctx.send("Denied Access.")

            keys_to_end = [
                k for k, g in active_games.items()
                if isinstance(g, dict) and g.get("guild_id") == ctx.guild.id
            ]
            ended = 0
            for k in keys_to_end:
                if k not in active_games:
                    continue
                game = active_games[k]
                debug_msg_id = game.get("debug_msg_id")
                debug_ch_id = game.get("debug_msg_channel_id")
                if debug_msg_id and debug_ch_id:
                    try:
                        debug_ch = self.bot.get_channel(debug_ch_id) or await self.bot.fetch_channel(debug_ch_id)
                        dm = await debug_ch.fetch_message(debug_msg_id)
                        await dm.delete()
                    except Exception:
                        pass
                del active_games[k]
                ended += 1

            if ended:
                await send_debug_msg(
                    self.bot,
                    f"⚡ `.wordle end` | {ctx.author} (`{ctx.author.id}`) ended **{ended}** game(s) | {ctx.guild.name} (`{ctx.guild.id}`)",
                )
                return await ctx.send(f"Ended {ended} game(s) in this server.")
            return await ctx.send("No active game found in this server.")

        # ── .wordle edit <word> [serverID] — debug channel only ──
        if mode_or_option and mode_or_option.lower().strip() == "edit":
            if ctx.channel.id != get_debug_channel_id():
                return
            if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
                return

            if not category:
                return await ctx.send("❌ Usage: `.wordle edit <word> [serverID]`")

            word_clean = "".join(c for c in category.lower() if c.isalpha())
            if not word_clean:
                return await ctx.send("❌ Invalid word — alphabetic characters only.")

            if difficulty and difficulty.strip().isdigit():
                target_gid = int(difficulty.strip())
            else:
                target_gid = ctx.guild.id

            game_key_found = None
            for k, g in list(active_games.items()):
                if isinstance(g, dict) and g.get("guild_id") == target_gid and not g.get("practice"):
                    game_key_found = k
                    break

            if game_key_found is None:
                return await ctx.send(f"❌ No active game found for server `{target_gid}`.")

            old_word = active_games[game_key_found]["secret"]
            active_games[game_key_found]["secret"] = word_clean
            active_games[game_key_found]["length"] = len(word_clean)
            await ctx.send(f"✅ `{old_word}` → `{word_clean}` (length: {len(word_clean)})")

            debug_msg_id = active_games[game_key_found].get("debug_msg_id")
            debug_ch_id = active_games[game_key_found].get("debug_msg_channel_id")
            if debug_msg_id and debug_ch_id:
                try:
                    debug_ch = self.bot.get_channel(debug_ch_id)
                    if debug_ch:
                        dm = await debug_ch.fetch_message(debug_msg_id)
                        guild_obj = self.bot.get_guild(target_gid)
                        gname = guild_obj.name if guild_obj else str(target_gid)
                        await dm.edit(content=f"🔐 `{word_clean}` | {target_gid} ({gname}) *(edited)*")
                except Exception:
                    pass
            return

        # ── .wordle secrethelp [info] ──
        if mode_or_option and mode_or_option.lower().strip() == "secrethelp":
            stats = load_stats()
            gid_str = str(ctx.guild.id)
            uid_str = str(ctx.author.id)
            trusted_pool = stats.get("trusted_users", {}).get(gid_str, [])
            is_user_trusted = uid_str in trusted_pool
            is_user_admin = is_admin(ctx.author.id, ctx.guild)
            is_user_op = is_op(ctx.author.id)

            if not (is_user_trusted or is_user_admin or is_user_op):
                return

            pfx = stats.get("prefix", ".")
            show_info = category and category.lower().strip() == "info"

            everyone_can_see = ctx.channel.permissions_for(ctx.guild.default_role).view_channel
            public_warning = "\n⚠️ **This channel is PUBLIC** — @everyone can see this message!\n" if everyone_can_see else ""

            if is_user_op:
                level, level_color = "Op 🔵", 0x5865F2
            elif is_user_admin:
                level, level_color = "Admin 🔴", 0xED4245
            else:
                level, level_color = "Trusted 🟡", 0xFEE75C

            if not show_info:
                embed = discord.Embed(
                    title="🔐 Secret Help — Command Reference",
                    description=f"{public_warning}Your access level: **{level}**",
                    color=level_color,
                )
                embed.add_field(
                    name="🟡 Trusted",
                    value=(
                        f"`/say` — Send a message as the bot\n"
                        f"`/autoresponder` — Manage server autoresponders\n"
                        f"`{pfx}wordle mode <cat> <diff>` — Category wordle"
                    ),
                    inline=False,
                )
                if is_user_admin or is_user_op:
                    embed.add_field(
                        name="🔴 Admin",
                        value=(
                            f"`{pfx}wordle end` / `/wordle end` — End active wordle (this server)\n"
                            f"`{pfx}eg [server]` / `/endgame` — Force-end active game(s)\n"
                            f"`{pfx}hint` — Reveal a hint letter\n"
                            f"`{pfx}reveal` / `/reveal` — Reveal the secret word\n"
                            f"`{pfx}give trusted <@user>` — Grant trusted access\n"
                            f"`{pfx}give admin <@user>` — Grant admin access globally\n"
                            f"`{pfx}give iw <@user> add` — Give infinite wordle\n"
                            f"`{pfx}give rwordle <@user>` — Reset a user's daily limit\n"
                            f"`{pfx}access` — Reset ALL daily limits\n"
                            f"`{pfx}bllserver [ID]` — Blacklist/unblacklist server\n"
                            f"`{pfx}maintenance` / `/maintenance` — Toggle maintenance mode"
                        ),
                        inline=False,
                    )
                if is_user_op:
                    embed.add_field(
                        name="🔵 Op",
                        value=(
                            f"`{pfx}give op <@user>` — Grant Operator access globally\n"
                            f"`{pfx}give trusted <@user> global` — Trusted across all servers\n"
                            f"`{pfx}eg global` / `/endgame global` — End ALL games globally\n"
                            f"`{pfx}leave <serverID>` — Leave a specific server\n"
                            f"`{pfx}leave all` — Leave all servers\n"
                            f"`{pfx}leave server list` — List servers the bot is in\n"
                            f"`{pfx}debugtest <label>` — Test debug channel\n"
                            f"`{pfx}wordle edit <word> [guildID]` — Edit active game word (debug ch only)"
                        ),
                        inline=False,
                    )
                embed.set_footer(text=f"Use {pfx}wordle secrethelp info for detailed examples")
            else:
                embed = discord.Embed(
                    title="🔐 Secret Help — Detailed Info",
                    description=f"{public_warning}Your access level: **{level}**",
                    color=level_color,
                )
                embed.add_field(
                    name="🟡 /say",
                    value=(
                        "Send a message as the bot to any channel.\n"
                        "**Example:** `/say message:Hello! channel:#general`\n"
                        "• Add `user:@someone` to send as a webhook clone of that user\n"
                        "• Add `message_id:` to reply to a message\n"
                        "**Access:** Trusted, Admin, Op"
                    ),
                    inline=False,
                )
                embed.add_field(
                    name="🟡 /autoresponder",
                    value=(
                        "Create or manage automatic responses to messages.\n"
                        "**Example:** `/autoresponder action:add trigger:hello reply:Hi there!`\n"
                        "• Supports `contains`, `exact`, `startswith`, `endswith` match modes\n"
                        "• Global scope requires Admin+\n"
                        "**Access:** Trusted, Admin, Op"
                    ),
                    inline=False,
                )
                embed.add_field(
                    name=f"🟡 {pfx}wordle mode",
                    value=(
                        "Start a wordle from a specific word category.\n"
                        f"**Example:** `{pfx}wordle mode meme easy`\n"
                        "• Category and difficulty must exist in `wordlecategories.json`\n"
                        "**Access:** Trusted, Admin, Op"
                    ),
                    inline=False,
                )
                if is_user_admin or is_user_op:
                    embed.add_field(
                        name=f"🔴 {pfx}wordle end / /wordle end",
                        value=(
                            "Force-end the active wordle game in this server.\n"
                            f"**Example:** `{pfx}wordle end` or `/wordle word:end`\n"
                            "**Access:** Admin, Op (or Discord Administrator)"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name=f"🔴 {pfx}eg / /endgame",
                        value=(
                            "Force-end game(s) in the server.\n"
                            f"**Example:** `{pfx}eg server` or `/endgame scope:server`\n"
                            "• Use `global` scope (Op only) to end all games everywhere\n"
                            "**Access:** Admin, Op"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name=f"🔴 {pfx}hint / {pfx}reveal / /reveal",
                        value=(
                            f"`{pfx}hint` — Reveals a random letter from the current secret word\n"
                            f"`{pfx}reveal` / `/reveal` — Reveals the full secret word (also works in 1v1)\n"
                            "**Access:** Admin, Op"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name=f"🔴 {pfx}give",
                        value=(
                            "Manage user access levels.\n"
                            f"• `{pfx}give trusted <@user>` — Add/remove trusted in this server\n"
                            f"• `{pfx}give admin <@user>` — Add/remove global admin\n"
                            f"• `{pfx}give iw <@user> add/remove` — Infinite wordle toggle\n"
                            f"• `{pfx}give rwordle <@user>` — Reset daily wordle limit\n"
                            "**Access:** Admin+ (op required for `give op` and `trusted global`)"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name=f"🔴 {pfx}access / {pfx}bllserver / {pfx}maintenance",
                        value=(
                            f"`{pfx}access` — Reset ALL user wordle limits globally\n"
                            f"`{pfx}bllserver [serverID]` — Blacklist/unblacklist a server\n"
                            f"`{pfx}maintenance` / `/maintenance` — Toggle bot maintenance mode\n"
                            "**Access:** Admin, Op"
                        ),
                        inline=False,
                    )
                if is_user_op:
                    embed.add_field(
                        name=f"🔵 {pfx}give op / trusted global",
                        value=(
                            "Manage top-level permissions.\n"
                            f"• `{pfx}give op <@user>` — Grant/revoke Operator (top tier)\n"
                            f"• `{pfx}give trusted <@user> global` — Trusted in all servers\n"
                            "**Access:** Op only"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name=f"🔵 {pfx}leave",
                        value=(
                            "Manage which servers the bot is in.\n"
                            f"• `{pfx}leave <serverID>` — Leave a specific server\n"
                            f"• `{pfx}leave all` — Leave ALL servers\n"
                            f"• `{pfx}leave server list` — Paginated list of all servers\n"
                            "**Access:** Op only"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name=f"🔵 {pfx}debugtest / {pfx}wordle edit",
                        value=(
                            f"`{pfx}debugtest <label>` — Send a test message to the debug channel\n"
                            f"`{pfx}wordle edit <word> [guildID]` — Change active game's secret word (debug channel only)\n"
                            "**Access:** Op only"
                        ),
                        inline=False,
                    )
                embed.set_footer(text=f"Use {pfx}wordle secrethelp for the quick command list")

            await ctx.send(embed=embed)
            return

        # ── Wordle channel restriction (set via .setwordle) ──
        if not is_wordle_channel_allowed(ctx.guild.id, ctx.channel.id):
            allowed_channels = get_wordle_channels(ctx.guild.id)
            mentions = ", ".join(f"<#{c}>" for c in allowed_channels)
            return await ctx.send(f"❌ Wordle can only be played in: {mentions}")

        # ── Category mode ──
        secret_word = None
        mode_label = ""

        if mode_or_option and mode_or_option.lower().strip() == "mode":
            stats = load_stats()
            gid_str = str(ctx.guild.id)
            uid_str = str(ctx.author.id)
            trusted_pool = stats.get("trusted_users", {}).get(gid_str, [])
            is_user_trusted = uid_str in trusted_pool
            is_user_admin = is_admin(ctx.author.id, ctx.guild)
            is_user_op = is_op(ctx.author.id)

            if not (is_user_admin or is_user_op or is_user_trusted or has_admin(ctx.author, ctx.guild)):
                return await ctx.send("You do not have permission to use this command")

            if not category:
                return await ctx.send("😭🙏")

            secret_word, err = self._pick_secret_from_category(category, difficulty)
            if err:
                return await ctx.send(err)

            mode_label = f" [{category.title()} - {(difficulty or 'easy').title()}]"

        elif mode_or_option and mode_or_option.lower().strip() in ("easy", "hard", "extreme", "impossible"):
            return await ctx.send("❌ Invalid command! Please use .wordle")

        # Daily limit check
        allowed, limit_msg = self._can_start_game(ctx.author, ctx.guild, practice=False)
        if not allowed:
            return await ctx.send(limit_msg)

        if not secret_word:
            gid = str(ctx.guild.id)
            default_mode = server_config.get("default_modes", {}).get(gid)
            secret_word, _ = get_random_word(ctx.guild.id, default_mode)

        await self._start_game(
            user=ctx.author,
            guild=ctx.guild,
            preferred_channel=ctx.channel,
            secret_word=secret_word,
            practice=False,
            mode_label=mode_label,
            ctx_or_interaction=ctx,
        )
          # ──────────────────────────────────────────────────────────────
    # Slash command
    # ──────────────────────────────────────────────────────────────

    @app_commands.command(name="wordle", description="Play a game of wordle")
    @app_commands.describe(
        word='Enter a custom word, or "end" to end the current game.',
        practice="Practice Mode (does not count toward daily limit)",
    )
    async def wordle_slash(
        self,
        interaction: discord.Interaction,
        word: str = None,
        practice: bool = False,
    ):
        if is_server_blacklisted(interaction.guild.id):
            return await interaction.response.send_message(
                "This server is blacklisted.", ephemeral=True
            )

        if is_maintenance_mode() and not is_admin(interaction.user.id):
            return await interaction.response.send_message(
                r("maintenance", "on"), ephemeral=True
            )

        preferred = interaction.channel

        # ── word provided ──
        if word:
            word_clean = word.lower().strip()

            if word_clean == "globalend":
                if not is_admin(interaction.user.id, interaction.guild, check_global=True):
                    return await interaction.response.send_message(
                        "You do not have permission to use this command.", ephemeral=True
                    )
                count = len(active_games)
                active_games.clear()
                return await interaction.response.send_message(
                    f"Wordle ended ({count})", ephemeral=True
                )

            if word_clean == "end":
                if not (
                    is_admin(interaction.user.id, interaction.guild)
                    or has_admin(interaction.user, interaction.guild)
                ):
                    return await interaction.response.send_message(
                        "You do not have permission to use this command.", ephemeral=True
                    )

                keys_to_end = [
                    k for k, g in active_games.items()
                    if isinstance(g, dict) and g.get("guild_id") == interaction.guild.id
                ]
                ended = 0
                for k in keys_to_end:
                    if k not in active_games:
                        continue
                    game = active_games[k]
                    debug_msg_id = game.get("debug_msg_id")
                    debug_ch_id = game.get("debug_msg_channel_id")
                    if debug_msg_id and debug_ch_id:
                        try:
                            debug_ch = self.bot.get_channel(debug_ch_id) or await self.bot.fetch_channel(debug_ch_id)
                            dm = await debug_ch.fetch_message(debug_msg_id)
                            await dm.delete()
                        except Exception:
                            pass
                    del active_games[k]
                    ended += 1

                if ended:
                    await send_debug_msg(
                        self.bot,
                        f"⚡ `/wordle end` | {interaction.user} (`{interaction.user.id}`) ended **{ended}** game(s) | {interaction.guild.name}",
                    )
                    return await interaction.response.send_message(
                        f"Wordle ended ({ended} game(s))", ephemeral=False
                    )
                return await interaction.response.send_message(
                    "Wordle hasn't been started.", ephemeral=True
                )

            # Custom word
            if not is_wordle_channel_allowed(interaction.guild.id, interaction.channel.id):
                allowed_channels = get_wordle_channels(interaction.guild.id)
                mentions = ", ".join(f"<#{c}>" for c in allowed_channels)
                return await interaction.response.send_message(
                    f"❌ Wordle can only be played in: {mentions}", ephemeral=True
                )

            stats = load_stats()
            gid_str = str(interaction.guild.id)
            uid_str = str(interaction.user.id)
            trusted_pool = stats.get("trusted_users", {}).get(gid_str, [])
            is_user_trusted = uid_str in trusted_pool
            is_user_admin = is_admin(interaction.user.id, interaction.guild)
            is_user_op = is_op(interaction.user.id)
            is_guild_admin = has_admin(interaction.user, interaction.guild)

            if not (is_user_admin or is_user_op or is_user_trusted or is_guild_admin):
                return await interaction.response.send_message(
                    "You do not have permission to start a custom Wordle.", ephemeral=True
                )

            word_clean = "".join(c for c in word_clean if c.isalpha())
            if not word_clean:
                return await interaction.response.send_message(
                    "Custom words must only contain alphabetic letters.", ephemeral=True
                )

            ok = await self._start_game(
                user=interaction.user,
                guild=interaction.guild,
                preferred_channel=preferred,
                secret_word=word_clean,
                practice=practice,
                force_preferred_channel=True,
                ctx_or_interaction=interaction,
                respond_ephemeral=True,
            )
            if ok:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"Custom game loaded into {preferred.mention}!", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"Custom game loaded into {preferred.mention}!", ephemeral=True
                    )
            return

        # ── No custom word → normal start ──
        if not is_wordle_channel_allowed(interaction.guild.id, interaction.channel.id):
            allowed_channels = get_wordle_channels(interaction.guild.id)
            mentions = ", ".join(f"<#{c}>" for c in allowed_channels)
            return await interaction.response.send_message(
                f"❌ Wordle can only be played in: {mentions}", ephemeral=True
            )

        mode_label = ""
        secret_word = None

        allowed, limit_msg = self._can_start_game(
            interaction.user, interaction.guild, practice=practice
        )
        if not allowed:
            return await interaction.response.send_message(limit_msg, ephemeral=True)

        gid = str(interaction.guild.id)
        default_mode = server_config.get("default_modes", {}).get(gid)
        secret_word, _ = get_random_word(interaction.guild.id, default_mode)

        ok = await self._start_game(
            user=interaction.user,
            guild=interaction.guild,
            preferred_channel=preferred,
            secret_word=secret_word,
            practice=practice,
            mode_label=mode_label,
            force_preferred_channel=False,
            ctx_or_interaction=interaction,
            respond_ephemeral=True,
        )

        if ok:
            if not interaction.response.is_done():
                await interaction.response.send_message("Game started!", ephemeral=True)
            else:
                await interaction.followup.send("Game started!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WordleCog(bot))
