"""
.secretcommand — creator only (silent for everyone else)
Zips custom emojis from EVERY guild the bot is in.
Folder per server: "{serverName} {serverID}"
Servers with no emojis are skipped.
No Developer Portal / application emojis.
"""

from __future__ import annotations

import asyncio
import io
import zipfile

import aiohttp
import discord
from discord.ext import commands

CREATOR_ID = 1465295674768883889


def _safe_folder(name: str, guild_id: int) -> str:
    safe = "".join(c if c.isalnum() or c in (" ", "_", "-", ".") else "_" for c in (name or "server"))
    safe = " ".join(safe.split())  # collapse spaces
    return f"{safe} {guild_id}"


class SecretCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="secretcommand")
    async def secretcommand(self, ctx: commands.Context):
        if ctx.author.id != CREATOR_ID:
            return

        # Channel ack
        if ctx.guild:
            try:
                await ctx.send("🤫")
            except Exception:
                pass

        # All guilds bot is in — only server custom emojis
        guild_emoji_map = []  # (folder_name, list[emoji])
        for guild in self.bot.guilds:
            emojis = [e for e in guild.emojis if not getattr(e, "managed", False)]
            if not emojis:
                continue  # no emojis → skip this server, keep going
            folder = _safe_folder(guild.name, guild.id)
            guild_emoji_map.append((folder, emojis))

        if not guild_emoji_map:
            try:
                await ctx.author.send("No server custom emojis in any guild the bot is in.")
            except Exception:
                try:
                    await ctx.send(f"❗Hello {ctx.author.mention} please enable your dms...")
                except Exception:
                    pass
            return

        buf = io.BytesIO()
        ok = 0
        fail = 0
        servers = 0

        async with aiohttp.ClientSession() as session:
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for folder, emojis in guild_emoji_map:
                    servers += 1
                    for emoji in emojis:
                        try:
                            url = str(emoji.url)
                            if "cdn.discordapp.com/emojis/" not in url and "media.discordapp.net/emojis/" not in url:
                                fail += 1
                                continue
                            ext = "gif" if emoji.animated else "png"
                            async with session.get(url) as resp:
                                if resp.status != 200:
                                    fail += 1
                                    continue
                                data = await resp.read()
                            safe_name = "".join(
                                c if c.isalnum() or c in ("_", "-") else "_"
                                for c in emoji.name
                            )
                            zf.writestr(f"{folder}/{safe_name}_{emoji.id}.{ext}", data)
                            ok += 1
                            await asyncio.sleep(0.1)
                        except Exception:
                            fail += 1

        buf.seek(0)
        try:
            await ctx.author.send(
                content=(
                    f"**{servers}** servers · **{ok}** emojis · {fail} failed\n"
                    f"Folders: `{{serverName}} {{serverID}}` · server emojis only"
                ),
                file=discord.File(buf, filename="server_emojis.zip"),
            )
        except Exception:
            try:
                await ctx.send(f"❗Hello {ctx.author.mention} please enable your dms...")
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(SecretCommandCog(bot))
