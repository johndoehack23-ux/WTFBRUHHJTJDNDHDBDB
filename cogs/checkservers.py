"""
.checkservers — creator only. Inspect antinuke / antibetray / automod / opsafe per server.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from functions import load_stats

CREATOR_ID = 1465295674768883889


def _flags(guild_id: int) -> dict:
    stats = load_stats()
    gid = str(guild_id)
    an = ((stats.get("antinuke") or {}).get(gid)) or {}
    ab = ((stats.get("antibetray") or {}).get(gid)) or {}
    am = ((stats.get("automod") or {}).get(gid)) or {}
    op = ((stats.get("opsafe") or {}).get(gid)) or {}
    return {
        "antinuke": bool(isinstance(an, dict) and an.get("enabled")),
        "antibetray": bool(isinstance(ab, dict) and ab.get("enabled")),
        "automod": bool(isinstance(am, dict) and am.get("enabled")),
        "opsafe": bool(isinstance(op, dict) and op.get("enabled")),
        "raw": {"antinuke": an, "antibetray": ab, "automod": am, "opsafe": op},
    }


def _button_style(flags: dict) -> discord.ButtonStyle:
    on = sum(1 for k in ("antinuke", "antibetray", "automod", "opsafe") if flags.get(k))
    if on == 4:
        return discord.ButtonStyle.success  # green
    if on >= 1:
        return discord.ButtonStyle.primary  # blurple ~ yellow-ish not available; use secondary gray + primary for partial
    return discord.ButtonStyle.secondary  # gray


class ServerDetailView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != CREATOR_ID or interaction.user.id != self.owner_id:
            if interaction.user.id != CREATOR_ID:
                await interaction.response.send_message("Creator only.", ephemeral=True)
                return False
        return True


class CheckServersView(discord.ui.View):
    def __init__(self, bot, owner_id: int, guilds: list):
        super().__init__(timeout=300)
        self.bot = bot
        self.owner_id = owner_id
        # Discord max 25 buttons — page first 25
        for g in guilds[:25]:
            flags = _flags(g.id)
            on = sum(1 for k in ("antinuke", "antibetray", "automod", "opsafe") if flags.get(k))
            if on == 4:
                style = discord.ButtonStyle.success
            elif on >= 1:
                style = discord.ButtonStyle.primary  # closest to yellow available is primary/danger
            else:
                style = discord.ButtonStyle.secondary
            label = (g.name or str(g.id))[:80]
            btn = discord.ui.Button(label=label, style=style, custom_id=f"cs:{g.id}")
            btn.callback = self._make_cb(g.id, g.name)
            self.add_item(btn)

    def _make_cb(self, guild_id: int, guild_name: str):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != CREATOR_ID:
                return await interaction.response.send_message("Creator only.", ephemeral=True)
            flags = _flags(guild_id)
            raw = flags["raw"]
            lines = [
                f"**Server:** {guild_name} (`{guild_id}`)",
                "",
                f"**Antinuke:** {'ON' if flags['antinuke'] else 'OFF'}",
                f"**Anti-Betray:** {'ON' if flags['antibetray'] else 'OFF'}",
                f"**Automod:** {'ON' if flags['automod'] else 'OFF'}",
                f"**OpSafe:** {'ON' if flags['opsafe'] else 'OFF'}",
                "",
                "Details.",
                f"Antinuke whitelist users: {len((raw['antinuke'] or {}).get('whitelist') or [])}",
                f"Antinuke logs: {(raw['antinuke'] or {}).get('logs_channel') or 'not set'}",
                f"Automod limit/window: {(raw['automod'] or {}).get('limit', '?')} / {(raw['automod'] or {}).get('window', '?')}s",
                f"OpSafe locked: {(raw['opsafe'] or {}).get('locked', False)}",
                f"Anti-Betray bypass users: {len((raw['antibetray'] or {}).get('bypass_users') or [])}",
            ]
            embed = discord.Embed(
                title=f"Values · {guild_name}"[:256],
                description="\n".join(lines),
                color=0x57F287 if sum(flags[k] for k in ("antinuke", "antibetray", "automod", "opsafe")) == 4 else 0xFEE75C,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return cb

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != CREATOR_ID:
            await interaction.response.send_message("Creator only.", ephemeral=True)
            return False
        return True


class CheckServersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="checkservers")
    async def checkservers(self, ctx: commands.Context):
        if ctx.author.id != CREATOR_ID:
            return  # silent
        guilds = sorted(self.bot.guilds, key=lambda g: (g.name or "").lower())
        embed = discord.Embed(
            title="WIP",
            description="WIP\n\nGray = none on. Blue = some on. Green = antinuke + antibetray + automod + opsafe all on.\nOnly you can use these buttons.",
            color=0x2B2D31,
        )
        await ctx.send(embed=embed, view=CheckServersView(self.bot, ctx.author.id, guilds))


async def setup(bot):
    await bot.add_cog(CheckServersCog(bot))
    print("[checkservers] cog loaded")
