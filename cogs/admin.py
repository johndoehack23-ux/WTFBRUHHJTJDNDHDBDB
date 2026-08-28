import discord
from discord.ext import commands
from discord import app_commands
import datetime
from functions import *


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_debug_admin_or_op(self, user_id):
        """Strict access check for .debugchannel: only globally listed admin/OP users."""
        uid = str(user_id)
        if uid in {"1465295674768883889", "1375782450118000681", "1469939898130895022"}:
            return True

        stats = load_stats()
        admin_users = stats.get("admin_users", [])
        op_users = stats.get("op_users", [])

        if isinstance(admin_users, dict):
            admin_users = list(admin_users.keys())
        if isinstance(op_users, dict):
            op_users = list(op_users.keys())

        return uid in {str(x) for x in admin_users} or uid in {str(x) for x in op_users}

    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Central debug hook: every recognized prefix command is logged."""
        if not getattr(ctx, "guild", None):
            return
        if not is_debug_mode():
            return

        command = getattr(ctx, "command", None)
        if command is None:
            return

        full_name = getattr(command, "qualified_name", None) or getattr(command, "name", "unknown")
        args = getattr(ctx, "message", None)
        content = getattr(args, "content", "") if args else ""
        await send_debug_msg(
            self.bot,
            f"📬 | {ctx.author} (`{ctx.author.id}`) | {ctx.channel.mention} | {ctx.guild.name} (`{ctx.guild.id}`) | `{content[:500]}`",
            guild_id=ctx.guild.id,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Central debug hook: every slash-command interaction is logged."""
        if not interaction.guild or not is_debug_mode():
            return

        if interaction.type != discord.InteractionType.application_command:
            return

        data = interaction.data or {}
        command_name = data.get("name")
        if not command_name:
            return

        options = data.get("options", [])
        option_text = ""

        def flatten_options(items):
            parts = []
            for item in items or []:
                name = item.get("name")
                if "options" in item:
                    parts.extend(flatten_options(item.get("options")))
                elif name is not None:
                    value = item.get("value", "")
                    parts.append(f"{name}={value}")
            return parts

        parts = flatten_options(options)
        if parts:
            option_text = " | " + ", ".join(parts)[:500]

        await send_debug_msg(
            self.bot,
            f"📬 | `/{command_name}`{option_text} | {interaction.user} (`{interaction.user.id}`) | #{getattr(interaction.channel, 'name', 'unknown')} | {interaction.guild.name} (`{interaction.guild.id}`)",
            guild_id=interaction.guild.id,
        )

    @commands.command(name="give")
    async def give(self, ctx, sub_action: str = None, user_input: str = None, value1: str = None, value2: str = None):
        if is_server_blacklisted(ctx.guild.id):
            return

        if is_maintenance_mode() and not is_admin(ctx.author.id, ctx.guild):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        # Master ID Bypass Override + Core Access Check
        is_master = ctx.author.id == 1465295674768883889
        if not (is_master or is_admin(ctx.author.id, ctx.guild, check_global=True) or is_op(ctx.author.id)):
            return await ctx.send("You do not have permission to use this command.")

        if not sub_action or not user_input:
            return await ctx.send("**Usage:** `.give <admin|trusted|op|infinitewordle|rwordle> <@user/userID/rall> [remove/delete]`")

        sub_action = sub_action.lower().strip()
        user_input_clean = user_input.lower().strip()

        # === INFINITE PLAYERS MANAGEMENT ===
        if sub_action in ["infinitewordle", "iwordle", "iw"]:
            # Wipe everyone globally shortcut
            if user_input_clean in ["rall", "dall", "removeall", "deleteall"]:
                data = load_wordle_limits()
                data["infinite"] = {}
                save_wordle_limits(data)
                return await ctx.send("Successfully removed infinite wordle for all users globally.")

            target_uid = user_input.replace("<@", "").replace("!", "").replace(">", "").strip()
            if not target_uid.isdigit():
                return await ctx.send("❌ Please provide a valid user mention, numerical User ID, or `rall` / `dall`.")

            if not value1 or value1.lower().strip() not in ["add", "remove", "delete"]:
                return await ctx.send("❌ Usage: `.give InfiniteWordle <userID/mention> <add/remove>`")

            uid_int = int(target_uid)
            is_remove_action = value1.lower().strip() in ["remove", "delete"]
            is_infinite = is_infinite_wordle(uid_int)

            if is_remove_action:
                if is_infinite:
                    toggle_infinite_wordle(uid_int)
                reset_user_wordle_limit(uid_int)
                await ctx.send(f"Successfully removed infinite wordle and reset limits for user ID `{target_uid}`.")
                await send_debug_msg(self.bot, f"🔑 `.give iw remove` | {ctx.author} (`{ctx.author.id}`) removed InfiniteWordle from `{target_uid}` | {ctx.guild.name}")
            else:
                if not is_infinite:
                    toggle_infinite_wordle(uid_int)
                await ctx.send(f"Infinite wordle enabled for user ID `{target_uid}`.")
                await send_debug_msg(self.bot, f"🔑 `.give iw add` | {ctx.author} (`{ctx.author.id}`) gave InfiniteWordle to `{target_uid}` | {ctx.guild.name}")
            return

        # === SPECIFIC USER WORDLE RESET MANAGEMENT ===
        if sub_action in ["resetwordle", "rwordle", "rw"]:
            target_uid = user_input.replace("<@", "").replace("!", "").replace(">", "").strip()
            if not target_uid.isdigit():
                return await ctx.send("❌ Please provide a valid user mention or numerical User ID.")

            uid_int = int(target_uid)
            
            # Run the limit reset
            did_reset = reset_user_wordle_limit(uid_int)
            if did_reset:
                is_remove_action = value1 and value1.lower().strip() in ["remove", "delete"]
                if is_remove_action:
                    await ctx.send(f"Successfully reset and removed limits for user ID `{target_uid}`.")
                else:
                    await ctx.send(f"Successfully reset daily wordle uses for user ID `{target_uid}`.")
                await send_debug_msg(self.bot, f"♻️ `.give rwordle` | {ctx.author} (`{ctx.author.id}`) reset wordle limits for `{target_uid}` | {ctx.guild.name}")
            else:
                await ctx.send("...")
            return

        # Extract standard numerical target ID for access lists
        target_uid = user_input.replace("<@", "").replace("!", "").replace(">", "").strip()
        if not target_uid.isdigit():
            return await ctx.send("❌ Please provide a valid user mention or numerical User ID.")

        is_remove_action = value1 and value1.lower().strip() in ["remove", "delete"]

        # === GLOBAL GROUPS MANAGEMENT (admin, op) ===
        if sub_action in ["admin", "op"]:
            # Strict division: Admins can't manage or touch OP features
            if sub_action == "op" and not (is_master or is_op(ctx.author.id)):
                return await ctx.send("You do not have permission to manage Operator privileges.")

            stats = load_stats()
            pool_key = f"{sub_action}_users"

            if pool_key not in stats or isinstance(stats[pool_key], dict):
                stats[pool_key] = []

            if "1465295674768883889" not in stats[pool_key]:
                stats[pool_key].append("1465295674768883889")

            user_pool = stats[pool_key]

            if is_remove_action:
                if target_uid == "1465295674768883889":
                    return await ctx.send("❌ Error: Total master root ID protection locked. Cannot remove creator.")

                if target_uid in user_pool:
                    user_pool.remove(target_uid)
                    save_stats(stats)
                    await ctx.send("Successfully removed")
                    await send_debug_msg(self.bot, f"🔑 `.give {sub_action} remove` | {ctx.author} (`{ctx.author.id}`) removed `{target_uid}` from **{sub_action}** list | {ctx.guild.name}")
                else:
                    await ctx.send(f"Not in the global {sub_action} list")
            else:
                if target_uid in user_pool:
                    user_pool.remove(target_uid)
                    save_stats(stats)
                    await ctx.send("Successfully removed")
                    await send_debug_msg(self.bot, f"🔑 `.give {sub_action} remove` | {ctx.author} (`{ctx.author.id}`) removed `{target_uid}` from **{sub_action}** list | {ctx.guild.name}")
                else:
                    user_pool.append(target_uid)
                    save_stats(stats)
                    await ctx.send(f"Successfully added as {sub_action} globally")
                    await send_debug_msg(self.bot, f"🔑 `.give {sub_action} add` | {ctx.author} (`{ctx.author.id}`) added `{target_uid}` as **{sub_action}** globally | {ctx.guild.name}")
            return

        # === SERVER-SPECIFIC OR GLOBAL MANAGEMENT (trusted) ===
        if sub_action == "trusted":
            # Parse scope and action from value1/value2
            # .give trusted userID [server/global] [remove]
            v1 = value1.lower().strip() if value1 else "server"
            v2 = value2.lower().strip() if value2 else None

            if v1 in ["remove", "delete"]:
                scope_trusted = "server"
                remove_trusted = True
            elif v1 in ["server", "global"]:
                scope_trusted = v1
                remove_trusted = v2 in ["remove", "delete"] if v2 else False
            else:
                scope_trusted = "server"
                remove_trusted = False

            # Global scope restricted to op only
            if scope_trusted == "global" and not (is_master or is_op(ctx.author.id)):
                return await ctx.send("You do not have permission to manage trusted users globally.")

            stats = load_stats()
            if "trusted_users" not in stats or isinstance(stats["trusted_users"], list):
                stats["trusted_users"] = {}

            if scope_trusted == "global":
                # Add/remove across ALL known servers
                if remove_trusted:
                    removed_from = []
                    for gid_k in stats["trusted_users"]:
                        pool = stats["trusted_users"][gid_k]
                        if target_uid in pool:
                            pool.remove(target_uid)
                            removed_from.append(gid_k)
                    save_stats(stats)
                    if removed_from:
                        await ctx.send(f"Successfully removed from trusted globally ({len(removed_from)} server(s)).")
                        await send_debug_msg(self.bot, f"🔑 `.give trusted global remove` | {ctx.author} (`{ctx.author.id}`) removed `{target_uid}` from trusted in {len(removed_from)} server(s)")
                    else:
                        await ctx.send("Not found in any trusted list globally.")
                else:
                    added_to = 0
                    for gid_k in stats["trusted_users"]:
                        pool = stats["trusted_users"][gid_k]
                        if target_uid not in pool:
                            pool.append(target_uid)
                            added_to += 1
                    # Also add to current server if not already tracked
                    gid_str = str(ctx.guild.id)
                    if gid_str not in stats["trusted_users"]:
                        stats["trusted_users"][gid_str] = [target_uid]
                        added_to += 1
                    elif target_uid not in stats["trusted_users"][gid_str]:
                        stats["trusted_users"][gid_str].append(target_uid)
                        added_to += 1
                    save_stats(stats)
                    await ctx.send(f"Successfully added as trusted globally ({added_to} server(s)).")
                    await send_debug_msg(self.bot, f"🔑 `.give trusted global add` | {ctx.author} (`{ctx.author.id}`) added `{target_uid}` as trusted in {added_to} server(s)")
            else:
                # Server scope (default)
                gid_str = str(ctx.guild.id)
                if gid_str not in stats["trusted_users"]:
                    stats["trusted_users"][gid_str] = []
                user_pool = stats["trusted_users"][gid_str]

                if remove_trusted:
                    if target_uid in user_pool:
                        user_pool.remove(target_uid)
                        save_stats(stats)
                        await ctx.send("Successfully removed from trusted (this server).")
                        await send_debug_msg(self.bot, f"🔑 `.give trusted server remove` | {ctx.author} (`{ctx.author.id}`) removed `{target_uid}` from trusted | {ctx.guild.name} (`{ctx.guild.id}`)")
                    else:
                        await ctx.send("Not in the trusted list for this server.")
                else:
                    if target_uid not in user_pool:
                        user_pool.append(target_uid)
                        save_stats(stats)
                        await ctx.send("Successfully added as trusted (this server).")
                        await send_debug_msg(self.bot, f"🔑 `.give trusted server add` | {ctx.author} (`{ctx.author.id}`) added `{target_uid}` as trusted | {ctx.guild.name} (`{ctx.guild.id}`)")
                    else:
                        await ctx.send("Already in the trusted list for this server.")
        else:
            await ctx.send("❌ Invalid action type! Choose `admin`, `op`, `trusted`, `infinitewordle`, or `rwordle`.")

    @commands.command(name="access")
    async def reset_wordle_limit_all(self, ctx):
        if not is_admin(ctx.author.id, ctx.guild):
            return await ctx.send("🔐 Denied Access.")

        data = load_wordle_limits()
        data["users"] = {}
        data["infinite"] = {} if "infinite" in data else {}
        data["last_reset"] = datetime.datetime.now().isoformat()
        save_wordle_limits(data)

        await ctx.send("✅ **ALL** Wordle limits have been reset globally.")
        await send_debug_msg(self.bot, f"♻️ `.access` | {ctx.author} (`{ctx.author.id}`) reset **ALL** wordle limits globally | {ctx.guild.name}")

    @commands.command(name="test", aliases=["maintenance"])
    async def maintenance_toggle(self, ctx):
        if not is_admin(ctx.author.id, ctx.guild):
            return await ctx.send("🔐 Denied Access")

        new_state = toggle_maintenance()
        status = "🔐 **ENABLED**" if new_state else "🔓 **DISABLED**"
        blocked = "Non-admins are now blocked." if new_state else ""
        await ctx.send(f"**Maintenance Mode:** {status}\n\n{blocked}")
        await send_debug_msg(self.bot, f"🔧 Maintenance | {ctx.author} (`{ctx.author.id}`) → **{'ON' if new_state else 'OFF'}** | {ctx.guild.name}")

    @commands.command(name="access1")
    async def reset_wordle_limit(self, ctx):
        if not is_admin(ctx.author.id, ctx.guild):
            return await ctx.send("❌ You can't access this command. Please contact the bot owner to get access.")

        data = load_wordle_limits()
        data["users"] = {}
        data["last_reset"] = datetime.datetime.now().isoformat()
        save_wordle_limits(data)

        await ctx.send("✅ **Wordle limits have been manually reset for all users.**")

    @commands.command(name="debugchannel", aliases=["debugch"])
    async def set_debug_channel_cmd(self, ctx, channel: str = None, scope: str = "server"):
        # .debugchannel is intentionally stricter than normal admin checks:
        # only users explicitly listed in global admin_users/op_users (plus root IDs) may use it.
        if not self._is_debug_admin_or_op(ctx.author.id):
            return await ctx.send("You do not have permission to use this command.")

        if not channel:
            return await ctx.send(
                "❌ Usage: `.debugchannel <#channel|channelID> [server/global]`\n"
                "• Default scope is `server` (only this server's logs)\n"
                "• Use `global` to receive logs from **all** servers (op only)"
            )

        # Accept <#id>, raw id, or channel name
        raw = channel.replace("<#", "").replace(">", "").strip()
        target_channel = None

        if raw.isdigit():
            target_channel = ctx.guild.get_channel(int(raw)) or self.bot.get_channel(int(raw))
            if target_channel is None:
                try:
                    target_channel = await self.bot.fetch_channel(int(raw))
                except Exception:
                    target_channel = None
        else:
            # Try name match in current guild
            name_lower = raw.lower().lstrip("#")
            target_channel = discord.utils.get(ctx.guild.text_channels, name=name_lower)

        if target_channel is None:
            return await ctx.send("❌ Could not find that channel. Use a mention (`#channel`) or a numeric channel ID.")

        scope = (scope or "server").lower().strip()
        if scope not in ("server", "global"):
            scope = "server"

        if scope == "global" and not is_op(ctx.author.id):
            return await ctx.send("You do not have permission to set the global debug channel.")

        guild_id = ctx.guild.id if scope == "server" else None
        set_debug_channel(target_channel.id, guild_id=guild_id)

        scope_label = f"server ({ctx.guild.name})" if scope == "server" else "global (all servers)"
        await ctx.send(
            f"✅ Debug channel set to {target_channel.mention} for **{scope_label}**.\n"
            f"{'Only this server' if scope == 'server' else 'All servers'}' command logs will go there."
        )
        # Send this confirmation using the newly configured routing.
        await send_debug_msg(
            self.bot,
            f"🔧 `.debugchannel` | {ctx.author} (`{ctx.author.id}`) set debug channel to {target_channel.mention} [{scope_label}] | {ctx.guild.name} (`{ctx.guild.id}`)",
            guild_id=ctx.guild.id
        )

    @commands.command(name="debug")
    async def debug_toggle(self, ctx, state: str = None):
        if not is_admin(ctx.author.id, ctx.guild):
            return await ctx.send("🔐 Denied Access.")

        if not state or state.lower().strip() not in ["on", "off", "true", "false"]:
            current = "on" if is_debug_mode() else "off"
            return await ctx.send(f"Debug mode is currently **{current}**. Usage: `+debug on/off`")

        enabled = state.lower().strip() in ["on", "true"]
        set_debug_mode(enabled)
        status = "**ON** ✅" if enabled else "**OFF** ❌"
        await ctx.send(f"Debug mode set to {status}. Messages will {'be sent' if enabled else 'NOT be sent'} to the debug channel.")

    @commands.command(name="bllserver", aliases=["bll"])
    async def admin_blacklist(self, ctx, server_id: str = None, action: str = None):
        if is_maintenance_mode() and not is_admin(ctx.author.id, ctx.guild):
            return await ctx.send("🛠️ **Bot is under maintenance.**")

        if not is_admin(ctx.author.id, ctx.guild, check_global=True) and ctx.author.id != 1465295674768883889:
            return await ctx.send("You do not have permission to use this command.")

        if not server_id:
            return await ctx.send("❌ Usage: `.bllserver <serverID | all> [remove]`")

        if "blacklisted_servers" not in server_config:
            server_config["blacklisted_servers"] = []

        blacklist_pool = server_config["blacklisted_servers"]
        input_clean = server_id.strip().lower()

        if input_clean == "all" or (action and action.strip().lower() == "all"):
            if not blacklist_pool:
                return await ctx.send("ℹ️ The blacklist is already completely empty.")
            server_config["blacklisted_servers"] = []
            save_json(CONFIG_FILE, server_config)
            return await ctx.send("🔓 Successfully **wiped the blacklist**. All servers are now unbanished globally.")

        target_sid = server_id.strip()
        action_clean = action.lower().strip() if action else None

        if not target_sid.isdigit():
            return await ctx.send("❌ Invalid syntax! Server ID must be a numerical value.")

        try:
            discovered_guild = await self.bot.fetch_guild(int(target_sid))
            server_name_display = f"**{discovered_guild.name}** "
        except discord.NotFound:
            return await ctx.send(f"❌ **Verification Failed:** `{target_sid}` is not a real or valid Discord server ID!")
        except discord.HTTPException:
            server_name_display = ""

        if action_clean == "remove":
            if target_sid in blacklist_pool:
                blacklist_pool.remove(target_sid)
                save_json(CONFIG_FILE, server_config)
                return await ctx.send(f"🔓 Server {server_name_display}(`{target_sid}`) has been successfully **removed** from the blacklist.")
            else:
                return await ctx.send(f"❌ Server {server_name_display}(`{target_sid}`) was not found in the blacklist pool.")

        if target_sid in blacklist_pool:
            blacklist_pool.remove(target_sid)
            status_msg = f"🔓 Server {server_name_display}(`{target_sid}`) was already blacklisted. **Removed** from blacklist."
        else:
            blacklist_pool.append(target_sid)
            status_msg = f"🚫 Server {server_name_display}(`{target_sid}`) has been **added** to the blacklist."

        save_json(CONFIG_FILE, server_config)
        await ctx.send(status_msg)
        await send_debug_msg(self.bot, f"🚫 `.bllserver` | {ctx.author} (`{ctx.author.id}`) | {status_msg.replace('**', '')}")

    @app_commands.command(name="ophelp", description="···")
    async def admin_help(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id, interaction.guild):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=False)

        embed = discord.Embed(
            title="💫 Admin / Whitelisted Commands 💫", 
            description="**Slash Commands** (`/`) and **Prefix Commands** (`.`)",
            color=0x2f3136
        )

        embed.add_field(
            name="🔹 Slash Commands",
            value=(
                "/wordle <customwords/globalend>\n"
                "/reveal\n"
                "/adminhelp\n"
                "/difficulty <mode>\n"
                "/hint\n"
                "/autoresponder\n"
                "/deleteautoresponder\n"
                "/say\n"
                "/rlb\n\n\n"
                "/ophelp"
            ),
            inline=False
        )

        embed.add_field(
            name="🔹 Prefix Commands",
            value=(
                ".mode <1v1/end>\n"
                ".wordle <end>\n"
                ".bllserver <serverID/all> <add/remove>\n"
                ".give <admin/trusted/op/infinitewordle> <userID/mention> [remove/delete]\n"
                ".difficulty <mode>\n"
                ".reveal\n"
                ".test\n"
                ".eg <server/global>\n"
                ".rlb\n"
                ".streak"
            ),
            inline=False
        )

        embed.set_footer(text="Only admins can see this • /ophelp")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="maintenance", description="Toggle maintenance mode (admin only)")
    async def maintenance_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id, interaction.guild):
            return await interaction.response.send_message("🔐 Denied Access", ephemeral=True)

        new_state = toggle_maintenance()
        status = "🔐 **ENABLED**" if new_state else "🔓 **DISABLED**"
        blocked = "Non-admins are now blocked." if new_state else ""
        await interaction.response.send_message(f"**Maintenance Mode:** {status}\n\n{blocked}", ephemeral=True)
        await send_debug_msg(self.bot, f"🔧 /maintenance | {interaction.user} (`{interaction.user.id}`) → **{'ON' if new_state else 'OFF'}** | {interaction.guild.name}")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))