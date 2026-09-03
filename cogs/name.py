import discord
from discord.ext import commands
from functions import is_op


class NameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nick")
    async def nick(self, ctx, *, args: str = None):
        if not is_op(ctx.author.id):
            return await ctx.send("You do not have permission to use this command")

        scope = "server"
        text = None

        if args is not None and args.strip():
            parts = args.strip().rsplit(None, 1)  # split off last word
            if len(parts) == 2 and parts[1].lower() in ("server", "global"):
                text = parts[0].strip()
                scope = parts[1].lower()
            elif args.strip().lower() in ("server", "global"):
                # bare `.nick server` or `.nick global` → reset
                scope = args.strip().lower()
                text = None
            else:
                # no scope given → treat whole thing as nickname, default server
                text = args.strip()
                scope = "server"

        # Discord nickname limit is 32 characters
        if text is not None and len(text) > 32:
            return await ctx.send("❌ Name must be 32 characters or fewer.")

        if scope == "server":
            try:
                await ctx.guild.me.edit(nick=text)
                if text is None:
                    await ctx.send("✅ Bot nickname has been reset in this server.")
                else:
                    await ctx.send(f"✅ Bot nickname set to **{text}** in this server.")
            except discord.Forbidden:
                await ctx.send("❌ I don't have permission to change my own nickname in this server.")
            except Exception as e:
                await ctx.send(f"❌ Failed to change nickname: `{e}`")
            return

        # ── scope == "global" ──────────────────────────────────────────────
        # 1) Change actual bot username (+ display name if discord.py supports it)
        # 2) Change nickname in every server the bot is in

        account_msg = ""
        if text is not None:
            try:
                # Try username + global_name (newer discord.py)
                await self.bot.user.edit(username=text, global_name=text)
                account_msg = f"✅ Bot **username** & **display name** set to **{text}**\n"
            except TypeError:
                # Older discord.py — no global_name support, username only
                try:
                    await self.bot.user.edit(username=text)
                    account_msg = f"✅ Bot **username** set to **{text}**\n"
                except discord.HTTPException as e:
                    account_msg = f"❌ Failed to change username: `{e}`\n"
                except Exception as e:
                    account_msg = f"❌ Failed to change username: `{e}`\n"
            except discord.HTTPException as e:
                # Username taken / rate-limited / invalid — try display name only if supported
                try:
                    await self.bot.user.edit(global_name=text)
                    account_msg = (
                        f"⚠️ Could not change **username** (`{e}`)\n"
                        f"✅ Bot **display name** set to **{text}**\n"
                    )
                except TypeError:
                    account_msg = f"❌ Failed to change username: `{e}`\n"
                except Exception as e2:
                    account_msg = f"❌ Failed to change account name: `{e2}`\n"
            except Exception as e:
                account_msg = f"❌ Failed to change account name: `{e}`\n"
        else:
            # Reset display name if supported (username cannot be empty)
            try:
                await self.bot.user.edit(global_name=None)
                account_msg = "✅ Bot **display name** has been reset.\n"
            except TypeError:
                account_msg = "ℹ️ Display name reset not supported on this discord.py version.\n"
            except Exception as e:
                account_msg = f"❌ Failed to reset display name: `{e}`\n"

        # Change nickname in all guilds
        success = 0
        failed = 0
        for guild in self.bot.guilds:
            try:
                await guild.me.edit(nick=text)
                success += 1
            except (discord.Forbidden, discord.HTTPException, Exception):
                failed += 1

        if text is None:
            await ctx.send(
                f"{account_msg}"
                f"✅ Nicknames reset globally.\n"
                f"Succeeded: **{success}** | Failed: **{failed}**"
            )
        else:
            await ctx.send(
                f"{account_msg}"
                f"✅ Nicknames set to **{text}** globally.\n"
                f"Succeeded: **{success}** | Failed: **{failed}**"
            )


async def setup(bot):
    await bot.add_cog(NameCog(bot))
