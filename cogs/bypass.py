import discord
from discord.ext import commands
from discord import app_commands
from functions import *

CREATOR_ID = 1465295674768883889


class BypassCog(commands.Cog):
    """
    Slash-only, creator-only toggle:
      /bypass  -> flips creator_bypass_enabled on/off in MongoDB.
    When ON, the creatorID skips selfpromo/media channel restrictions
    (cogs/selfpromo.py, cogs/media.py). When OFF, the creator is treated
    like anyone else there (still subject to the admin/op bypass, same as always).
    Anyone other than the creator gets NO response at all.
    """

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bypass", description="Toggle creator bypass for selfpromo/media restrictions")
    async def bypass(self, interaction: discord.Interaction):
        if interaction.user.id != CREATOR_ID:
            # Silent for everyone except the creator — we deliberately do NOT
            # call interaction.response here. Note: Discord itself will still
            # show the user a generic "This interaction failed" indicator if
            # nothing acknowledges the interaction within a few seconds — that's
            # a Discord-side behavior for slash commands, not something any bot
            # code can suppress. No actual reply/content is ever sent though.
            await send_debug_msg(
                self.bot,
                f"🚫 `/bypass` blocked | {interaction.user} (`{interaction.user.id}`) is not the creator | "
                f"{interaction.guild.name if interaction.guild else 'DM'}"
            )
            return

        new_state = not is_creator_bypass_enabled()
        set_creator_bypass(new_state)

        status = "🟢 ON" if new_state else "🔴 OFF"
        await interaction.response.send_message(f"✅ Creator bypass is now **{status}**.", ephemeral=True)
        await send_debug_msg(
            self.bot,
            f"🔁 `/bypass` | {interaction.user} (`{interaction.user.id}`) set creator bypass to {status} | "
            f"{interaction.guild.name if interaction.guild else 'DM'}"
        )


async def setup(bot):
    await bot.add_cog(BypassCog(bot))
