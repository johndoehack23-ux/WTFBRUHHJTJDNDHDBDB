import discord
from discord.ext import commands
from functions import *

# Maps the category keyword -> (stats.json key, is_per_guild_dict, friendly title)
CATEGORY_MAP = {
    "trusted": ("trusted_users", True, "🤝 Trusted Users"),
    "admin": ("admin_users", False, "🛡️ Admin Users"),
    "op": ("op_users", False, "⚙️ Op Users"),
    "allowed": ("allowed_servers", False, "✅ Allowed Servers"),
    "invited": ("invited_users", False, "📨 Invited Users"),
    "say": ("user_say_list", False, "💬 Say-Command Users"),
    "apps": ("user_apps", False, "📱 User Apps"),
    "allowedusers": ("allowed_users", False, "🟢 Allowed Users"),
}


class ShowValuesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _build_embed(self, listed: str):
        listed = listed.lower().strip()

        if listed not in CATEGORY_MAP:
            available = ", ".join(f"`{k}`" for k in CATEGORY_MAP)
            return discord.Embed(
                title="❌ Unknown category",
                description=f"Available categories: {available}",
                color=0xff4d4d
            )

        key, is_per_guild, title = CATEGORY_MAP[listed]
        stats = load_stats()
        value = stats.get(key, {} if is_per_guild else [])

        embed = discord.Embed(title=title, color=0x2f3136)

        if is_per_guild:
            # Per-server dict: {guild_id: [user_ids]}
            if not value:
                embed.description = "No entries found for any server."
                return embed

            for gid, user_ids in value.items():
                guild_obj = self.bot.get_guild(int(gid)) if str(gid).isdigit() else None
                server_name = guild_obj.name if guild_obj else f"Unknown Server (`{gid}`)"

                if user_ids:
                    lines = [f"<@{uid}> (`{uid}`)" for uid in user_ids]
                else:
                    lines = ["*None*"]

                embed.add_field(name=f"🏡 {server_name}", value="\n".join(lines), inline=False)
        else:
            # Flat global list
            if not value:
                embed.description = "No entries found."
                return embed

            lines = [f"<@{uid}> (`{uid}`)" for uid in value if uid]
            embed.description = "\n".join(lines) if lines else "No entries found."
            embed.set_footer(text="Scope: Global Value")

        return embed

    @commands.command(name="showvalues")
    async def showvalues(self, ctx, listed: str = None):
        if not (is_admin(ctx.author.id, ctx.guild) or is_op(ctx.author.id)):
            return await ctx.send("You do not have permission to use this command.")

        if not listed:
            available = ", ".join(f"`{k}`" for k in CATEGORY_MAP)
            return await ctx.send(f"Usage: `.showvalues <listed>`\nAvailable: {available}")

        embed = await self._build_embed(listed)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ShowValuesCog(bot))
