import discord
from discord.ext import commands
from discord import app_commands
from functions import load_stats, is_maintenance_mode, is_admin
from editrespond import r


def _prefix(guild):
    stats = load_stats()
    prefix = stats.get("prefix", ".")
    if guild:
        sp = (stats.get("server_prefixes") or {}).get(str(guild.id))
        if sp:
            prefix = sp
    return prefix


def _color(key: str, default: int) -> int:
    raw = (r("help", key) or "").strip()
    try:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        if raw.startswith("#"):
            return int(raw[1:], 16)
        return int(raw)
    except Exception:
        return default


def build_help_embed(guild):
    p = _prefix(guild)
    body = r("help", "body")
    # help-only: inject prefix without breaking other editrespond categories
    body = body.replace("{prefix}", p)
    return discord.Embed(
        title=r("help", "title"),
        description=body,
        color=_color("color", 0x2f3136),
    )


def build_server_owner_embed():
    return discord.Embed(
        title=r("help", "server_owner_title"),
        description=r("help", "server_owner_body"),
        color=_color("server_owner_color", 0xFEE75C),
    )


class HelpView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=180)
        self.guild = guild

    @discord.ui.button(label="server-owner", style=discord.ButtonStyle.success)
    async def server_owner_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_server_owner_embed(),
            ephemeral=True,
        )

    @discord.ui.button(label="🔧 Administrator", style=discord.ButtonStyle.secondary)
    async def admin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=r("help", "admin_title"),
            description=r("help", "admin_body"),
            color=_color("admin_color", 0x2f3136),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_prefix(self, ctx):
        if is_maintenance_mode() and not is_admin(ctx.author.id):
            return await ctx.send("Maintenance mode is on.")
        await ctx.send(embed=build_help_embed(ctx.guild), view=HelpView(ctx.guild))

    @app_commands.command(name="help", description="Show the bot's command list")
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_help_embed(interaction.guild),
            view=HelpView(interaction.guild),
        )


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
