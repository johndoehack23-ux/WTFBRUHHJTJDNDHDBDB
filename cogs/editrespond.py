import discord
from discord.ext import commands
from functions import *
from editrespond import (
    RESPOND_KEYS,
    DEFAULT_RESPONSES,
    get_responds,
    set_respond,
    delete_respond,
    reset_category_to_defaults,
)

CREATOR_ID = 1465295674768883889


class EditRespondCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _check(self, ctx) -> bool:
        return ctx.author.id == CREATOR_ID

    @commands.group(name="editrespond", invoke_without_command=True)
    async def editrespond(self, ctx, category: str = None):
        if not self._check(ctx):
            return await ctx.send("You do not have permission to use this command.")

        available = ", ".join(f"`{k}`" for k in RESPOND_KEYS)

        if not category:
            return await ctx.send(
                f"**Usage:**\n"
                f"`.editrespond <category>` — List all responses in that category\n"
                f"`.editrespond edit <category> <key> <new text>` — Edit a response\n"
                f"`.editrespond add <category> <key> <text>` — Add a new response\n"
                f"`.editrespond delete <category> <key>` — Delete a response\n"
                f"`.editrespond reset <category>` — Reset category back to defaults\n\n"
                f"**Categories:** {available}"
            )

        category = category.lower()
        if category not in RESPOND_KEYS:
            return await ctx.send(f"❌ Unknown category. Available: {available}")

        responds = get_responds(category)
        if not responds:
            return await ctx.send(f"📭 No responses found for `{category}`.")

        # Detect whether these are still the built-in defaults
        is_default = responds == DEFAULT_RESPONSES.get(category, {})
        header = f"📋 **{category.title()} responses**"
        if is_default:
            header += " *(using defaults — nothing custom saved yet)*"
        header += ":\n"

        lines = [f"**`{k}`** → {v}" for k, v in responds.items()]
        chunks = []
        current = header
        for line in lines:
            if len(current) + len(line) + 1 > 1900:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            chunks.append(current)

        for chunk in chunks:
            await ctx.send(chunk)

    @editrespond.command(name="edit")
    async def editrespond_edit(self, ctx, category: str = None, key: str = None, *, new_text: str = None):
        if not self._check(ctx):
            return await ctx.send("You do not have permission to use this command.")

        if not category or not key or not new_text:
            return await ctx.send("❌ Usage: `.editrespond edit <category> <key> <new text>`")

        category = category.lower()
        if category not in RESPOND_KEYS:
            return await ctx.send(f"❌ Unknown category. Available: {', '.join(RESPOND_KEYS)}")

        responds = get_responds(category)
        old_text = responds.get(key, "(new entry)")

        ok = set_respond(category, key, new_text)
        if not ok:
            return await ctx.send("❌ Failed to save. Check category name.")

        embed = discord.Embed(title=f"✅ Updated `{category}` → `{key}`", color=0x00ff00)
        embed.add_field(name="Before", value=old_text[:1024], inline=False)
        embed.add_field(name="After", value=new_text[:1024], inline=False)
        await ctx.send(embed=embed)

    @editrespond.command(name="add")
    async def editrespond_add(self, ctx, category: str = None, key: str = None, *, text: str = None):
        if not self._check(ctx):
            return await ctx.send("You do not have permission to use this command.")

        if not category or not key or not text:
            return await ctx.send("❌ Usage: `.editrespond add <category> <key> <text>`")

        category = category.lower()
        if category not in RESPOND_KEYS:
            return await ctx.send(f"❌ Unknown category. Available: {', '.join(RESPOND_KEYS)}")

        responds = get_responds(category)
        if key in responds:
            return await ctx.send(f"⚠️ `{key}` already exists in `{category}`. Use `.editrespond edit` to update it.")

        set_respond(category, key, text)
        await ctx.send(f"✅ Added `{key}` to `{category}` responses.")

    @editrespond.command(name="delete")
    async def editrespond_delete(self, ctx, category: str = None, key: str = None):
        if not self._check(ctx):
            return await ctx.send("You do not have permission to use this command.")

        if not category or not key:
            return await ctx.send("❌ Usage: `.editrespond delete <category> <key>`")

        category = category.lower()
        if category not in RESPOND_KEYS:
            return await ctx.send(f"❌ Unknown category. Available: {', '.join(RESPOND_KEYS)}")

        ok = delete_respond(category, key)
        if not ok:
            return await ctx.send(f"❌ `{key}` not found in `{category}` (or it was already using defaults).")

        await ctx.send(f"🗑️ Deleted `{key}` from `{category}` responses.\n*(If the category is now empty it will fall back to defaults)*")

    @editrespond.command(name="reset")
    async def editrespond_reset(self, ctx, category: str = None):
        if not self._check(ctx):
            return await ctx.send("You do not have permission to use this command.")

        if not category:
            return await ctx.send("❌ Usage: `.editrespond reset <category>`")

        category = category.lower()
        if category not in RESPOND_KEYS:
            return await ctx.send(f"❌ Unknown category. Available: {', '.join(RESPOND_KEYS)}")

        ok = reset_category_to_defaults(category)
        if not ok:
            return await ctx.send("❌ Failed to reset.")

        await ctx.send(f"♻️ `{category}` has been reset to the built-in defaults.")


async def setup(bot):
    await bot.add_cog(EditRespondCog(bot))
