
import discord
from discord.ext import commands
from cogs.economy.eco_data import CREATOR_ID, get_cash, format_money, all_balances


class MoneyLBView(discord.ui.View):
    def __init__(self, owner_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id and interaction.user.id != CREATOR_ID:
            await interaction.response.send_message("Only the command user can use these buttons.", ephemeral=True)
            return False
        return True

    def _entries(self):
        return all_balances()

    def _build_embed(self, bot, user_id: int) -> discord.Embed:
        entries = self._entries()
        if not entries:
            desc = "username1's money: 0$"
            embed = discord.Embed(title="Leaderboard $", description=desc, color=0xFEE75C)
            embed.set_footer(text=f"Your rank: — | Your Money: {format_money(get_cash(user_id))}")
            return embed

        per = 10
        start = self.page * per
        chunk = entries[start:start + per]
        lines = []
        for i, (uid, cash) in enumerate(chunk, start=start + 1):
            u = bot.get_user(int(uid))
            name = u.name if u else f"user{uid}"
            lines.append(f"**{i}.** `{name}` money: **{format_money(cash)}**")
        if not lines:
            lines = ["username1's money: 0$"]

        embed = discord.Embed(title="Leaderboard $", description="\n".join(lines), color=0xFEE75C)
        rank = None
        for i, (uid, cash) in enumerate(entries, start=1):
            if int(uid) == int(user_id):
                rank = i
                break
        if int(user_id) == CREATOR_ID:
            rank_txt, my_cash_txt = "∞", "∞"
        else:
            rank_txt = str(rank) if rank else "—"
            my_cash_txt = format_money(get_cash(user_id))
        embed.set_footer(text=f"Your rank: {rank_txt} | Your Money: {my_cash_txt}")
        return embed

    async def _edit(self, interaction: discord.Interaction):
        embed = self._build_embed(interaction.client, interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="<<", style=discord.ButtonStyle.secondary)
    async def first_jump(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 10)
        await self._edit(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self._edit(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        entries = self._entries()
        max_page = max(0, (len(entries) - 1) // 10) if entries else 0
        self.page = min(max_page, self.page + 1)
        await self._edit(interaction)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.secondary)
    async def last_jump(self, interaction: discord.Interaction, button: discord.ui.Button):
        entries = self._entries()
        max_page = max(0, (len(entries) - 1) // 10) if entries else 0
        self.page = min(max_page, self.page + 10)
        await self._edit(interaction)

    @discord.ui.button(label="Search", style=discord.ButtonStyle.success)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MoneyRankSearchModal(self))


class MoneyRankSearchModal(discord.ui.Modal, title="Search rank"):
    def __init__(self, view: MoneyLBView):
        super().__init__()
        self.view_ref = view

    rank = discord.ui.TextInput(label="rank", placeholder="e.g. 72", required=True, max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rank = int(str(self.rank.value).strip())
        except ValueError:
            return await interaction.response.send_message("Rank must be a number.", ephemeral=True)
        if rank < 1:
            return await interaction.response.send_message("Rank must be >= 1.", ephemeral=True)

        entries = all_balances()
        start_rank = ((rank - 1) // 10) * 10 + 1
        end_rank = start_rank + 9
        lines = []
        for i in range(start_rank, end_rank + 1):
            if i > len(entries):
                break
            uid, cash = entries[i - 1]
            u = interaction.client.get_user(int(uid))
            name = u.name if u else f"user{uid}"
            mark = " ←" if i == rank else ""
            lines.append(f"**{i}.** `{name}` money: **{format_money(cash)}**{mark}")
        if not lines:
            lines = ["username1's money: 0$"]
        embed = discord.Embed(title="Leaderboard $", description="\n".join(lines), color=0xFEE75C)
        my_cash = get_cash(interaction.user.id)
        my_rank = None
        for i, (uid, _) in enumerate(entries, start=1):
            if int(uid) == interaction.user.id:
                my_rank = i
                break
        embed.set_footer(text=f"Your rank: {my_rank or '—'} | Your Money: {format_money(my_cash)}")
        self.view_ref.page = max(0, (start_rank - 1) // 10)
        await interaction.response.edit_message(embed=embed, view=self.view_ref)


class MoneyLeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def show(self, ctx: commands.Context):
        if ctx.author.id != CREATOR_ID:
            return
        view = MoneyLBView(ctx.author.id, page=0)
        embed = view._build_embed(self.bot, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="moneylb", aliases=["cashlb", "moneyleaderboard"])
    async def moneylb(self, ctx: commands.Context):
        await self.show(ctx)


async def setup(bot):
    await bot.add_cog(MoneyLeaderboardCog(bot))
    print("[economy.moneyleaderboard] loaded")
