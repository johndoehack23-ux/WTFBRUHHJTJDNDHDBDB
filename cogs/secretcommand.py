"""
.secretcommand — creator only (silent for everyone else)
Downloads all custom emojis from the current server as images,
zips them, DMs the zip to the creator, and replies 🤫 in the channel.
"""

from __future__ import annotations

import asyncio
import io
import zipfile

import aiohttp
import discord
from discord.ext import commands

CREATOR_ID = 1465295674768883889


class SecretCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="secretcommand")
    async def secretcommand(self, ctx: commands.Context):
        # Silent for non-creator
        if ctx.author.id != CREATOR_ID:
            return

        if not ctx.guild:
            try:
                await ctx.author.send("Use this in a server with custom emojis.")
            except Exception:
                pass
            return

        emojis = list(ctx.guild.emojis)
        if not emojis:
            try:
                await ctx.author.send("No custom emojis in this server.")
            except Exception:
                pass
            try:
                await ctx.send("🤫")
            except Exception:
                pass
            return

        # Acknowledge in channel first
        try:
            await ctx.send("🤫")
        except Exception:
            pass

        buf = io.BytesIO()
        ok = 0
        fail = 0

        async with aiohttp.ClientSession() as session:
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for emoji in emojis:
                    try:
                        # Prefer animated gif / static png from CDN
                        url = str(emoji.url)
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
                        zf.writestr(f"{safe_name}_{emoji.id}.{ext}", data)
                        ok += 1
                        await asyncio.sleep(0.15)
                    except Exception:
                        fail += 1

        buf.seek(0)
        filename = f"emojis_{ctx.guild.id}.zip"

        try:
            await ctx.author.send(
                content=f"Emojis from **{ctx.guild.name}** (`{ctx.guild.id}`) · {ok} ok · {fail} failed",
                file=discord.File(buf, filename=filename),
            )
        except Exception:
            # Never send the zip in the channel — tell creator to open DMs
            try:
                await ctx.send(f"❗Hello {ctx.author.mention} please enable your dms...")
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(SecretCommandCog(bot))
