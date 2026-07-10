import discord
from discord.ext import commands
import asyncio
import random
from functions import is_op


class LeaveConfirmationView(discord.ui.View):
    def __init__(self, cog, ctx, target_mode, guild_obj=None):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.target_mode = target_mode 
        self.guild_obj = guild_obj      

        #whatbro = [
            #discord.ButtonStyle.danger,
            #discord.ButtonStyle.secondary,
            #discord.ButtonStyle.primary
        #]
        #chosen_style = random.choice(whatbro)

        self.yes_button = discord.ui.Button(
            label="Yes", 
            style=discord.ButtonStyle.success, 
            emoji="✅"
        )
        self.yes_button.callback = self.on_yes_click
        self.add_item(self.yes_button)

        self.no_button = discord.ui.Button(
            label="No", 
            style=discord.ButtonStyle.danger,
            emoji="❌"
        )
        self.no_button.callback = self.on_no_click
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                f"❌ <@{interaction.user.id}>, you cannot interact with this confirmation. Only the command executor can run this!"
            )
            return True
        return True

    async def on_yes_click(self, interaction: discord.Interaction):
        # Disable elements instantly to prevent double-clicks
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        if self.target_mode == "all":
            await self.cog.execute_leave_all(self.ctx)
        else:
            await self.cog.execute_leave_single(self.ctx, self.guild_obj)

    async def on_no_click(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="🛸 Cancelled", 
            description="The request has been cancelled.", 
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


class LeaveServerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.MAIN_SERVER_ID = 1503365316065890364  # Protected main server

    @commands.command(name="leave")
    async def leave_prefix(self, ctx, target: str = None):

        if not is_op:
            await ctx.send("...")
            return

        if not target:
            await ctx.send("❌ Usage: `.leave <serverID | all>`")
            return

        target = target.strip().lower()

        # === CONFIRMATION PROMPT FOR ALL ===
        if target == "all":
            embed = discord.Embed(
                title="⚠️ This will leave ALL server ⚠️",
                description="Are you sure you wanted to leave ALL server?",
                color=discord.Color.dark_red()
            )
            view = LeaveConfirmationView(self, ctx, "all")
            await ctx.send(embed=embed, view=view)
            return

        # === CONFIRMATION PROMPT FOR SINGLE ===
        try:
            guild_id = int(target)
        except ValueError:
            await ctx.send("❌ Invalid server ID. Use a number or `all`.")
            return

        if guild_id == self.MAIN_SERVER_ID:
            await ctx.send("🗣️🔥")
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send("❌ I am not in a server with that ID.")
            return

        embed = discord.Embed(
            title="⚠️ This will leave a server ⚠️",
            description=f"Are you sure you wanted to leave the {guild.name} ({guild.id})",
            color=discord.Color.orange()
        )
        view = LeaveConfirmationView(self, ctx, "single", guild_obj=guild)
        await ctx.send(embed=embed, view=view)

    # === CORE EXECUTION LOGIC ===

    async def execute_leave_all(self, ctx):
        await ctx.send("https://cdn.discordapp.com/attachments/1496929056468373778/1519946593430671411/bcG5Q.jpg?ex=6a3f6813&is=6a3e1693&hm=c9bb123df48917a906ff45a0918f166c36a0be5ae000d9043e92bb5965431556&")

        for guild in list(self.bot.guilds):
            if guild.id != self.MAIN_SERVER_ID:
                try:
                    await guild.leave()
                    print(f"✅ Left server: {guild.name} ({guild.id})")
                except Exception as e:
                    print(f"❌ Failed to leave {guild.name}: {e}")

        await ctx.send(f"✅ Successfully left **{left_count}** servers.")

    async def execute_leave_single(self, ctx, guild):
        try:
            await guild.leave()
            await ctx.send(f"✅ Successfully left server: **{guild.name}** (`{guild.id}`)")
            print(f"✅ Left server via command: {guild.name} ({guild.id})")
        except Exception as e:
            await ctx.send(f"❌ Failed to leave server: {e}")


async def setup(bot):
    await bot.add_cog(LeaveServerCog(bot))