import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import discord
from discord import app_commands
from discord.ext import commands

import functions
from editrespond import get_response

F = "values"


OWNER_ID = 1465295674768883889
COMMAND_DESCRIPTION = "only iamninjaau can access this command"
SKIP_DIRECTORIES = {".git", ".cache", ".local", ".agents", "__pycache__"}
SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|private[_-]?key|"
    r"client[_-]?secret|authorization|cookie|credential)",
    re.IGNORECASE,
)


def _owner_only(user):
    return user.id == OWNER_ID


def _json_files():
    """Find project JSON files without including internal tool directories."""
    files = []
    for path in Path(".").rglob("*.json"):
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def _redact_json(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY_PATTERN.search(str(key)) else _redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def _safe_json_bytes(path):
    """Return formatted JSON bytes with secret-like fields redacted."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return json.dumps(_redact_json(value), indent=2, ensure_ascii=False).encode("utf-8")


def _build_json_archive():
    archive_buffer = io.BytesIO()
    included = []
    skipped = []

    with zipfile.ZipFile(
        archive_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in _json_files():
            content = _safe_json_bytes(path)
            relative_name = path.as_posix()
            if content is None:
                skipped.append(relative_name)
                continue
            archive.writestr(relative_name, content)
            included.append(relative_name)

    archive_buffer.seek(0)
    return archive_buffer, included, skipped


def _safe_zip_json_name(raw_name):
    normalized = str(raw_name).replace("\\", "/")
    member = PurePosixPath(normalized)
    if member.is_absolute() or ".." in member.parts:
        return None
    if not member.name.lower().endswith(".json"):
        return None
    # Imports are intentionally flattened into the project root so an uploaded
    # folder cannot overwrite arbitrary directories.
    filename = member.name
    if not filename or filename.startswith("."):
        return None
    return filename


def _refresh_loaded_json_globals():
    """Refresh modules that imported persistent JSON globals at startup."""
    functions.server_config = functions.load_json(functions.CONFIG_FILE, dict)
    functions.leaderboard = functions.load_json(functions.LEADERBOARD_FILE, lambda: {"servers": {}})
    functions.roles_data = functions.load_json(functions.ROLES_FILE, lambda: {"servers": {}})
    functions.categories_data = functions.load_json(functions.CATEGORIES_FILE, lambda: {"servers": {}})
    functions.emojis = functions.load_json(
        functions.EMOJI_FILE,
        lambda: {"correct": {}, "misplaced": {}, "wrong": {}},
    )

    for module in list(sys.modules.values()):
        if module is None:
            continue
        for name in ("server_config", "leaderboard", "roles_data", "categories_data", "emojis"):
            if hasattr(module, name):
                setattr(module, name, getattr(functions, name))


class ValuesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="getvalues", description=COMMAND_DESCRIPTION)
    async def getvalues(self, interaction: discord.Interaction):
        if not _owner_only(interaction.user):
            return await interaction.response.send_message(
                get_response("values", "owner_only"),
                ephemeral=True,
            )

        try:
            archive, included, skipped = _build_json_archive()
            await interaction.user.send(
                content=(
                    f"JSON export complete: `{len(included)}` file(s)."
                    + (f" Skipped invalid JSON: `{len(skipped)}`." if skipped else "")
                ),
                file=discord.File(archive, filename="json_values.zip"),
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                get_response("values", "dm_failed"),
                ephemeral=True,
            )
        except (discord.HTTPException, OSError, zipfile.BadZipFile) as error:
            print(f"[getvalues] {error}")
            return await interaction.response.send_message(
                get_response("values", "export_failed"),
                ephemeral=True,
            )

        await interaction.response.send_message(
            get_response("values", "export_sent", count=len(included)),
            ephemeral=True,
        )

    @app_commands.command(name="importvalues", description=COMMAND_DESCRIPTION)
    @app_commands.describe(
        archive="Upload a ZIP containing the JSON files to import"
    )
    async def importvalues(
        self,
        interaction: discord.Interaction,
        archive: discord.Attachment,
    ):
        if not _owner_only(interaction.user):
            return await interaction.response.send_message(
                get_response("values", "owner_only"),
                ephemeral=True,
            )

        if not archive.filename.lower().endswith(".zip"):
            return await interaction.response.send_message(
                get_response("values", "not_zip"),
                ephemeral=True,
            )

        try:
            payload = await archive.read()
            imported = {}
            with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
                for member in source.infolist():
                    filename = _safe_zip_json_name(member.filename)
                    if filename is None or member.is_dir():
                        continue
                    if filename in imported:
                        raise ValueError(f"duplicate JSON filename: {filename}")
                    raw = source.read(member)
                    json.loads(raw.decode("utf-8"))
                    imported[filename] = raw
        except (discord.HTTPException, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            print(f"[importvalues] {error}")
            return await interaction.response.send_message(
                get_response("values", "import_failed"),
                ephemeral=True,
            )

        if not imported:
            return await interaction.response.send_message(
                get_response("values", "import_empty"),
                ephemeral=True,
            )

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                staged = Path(temp_dir)
                for filename, raw in imported.items():
                    destination = staged / filename
                    destination.write_bytes(raw)
                for filename in imported:
                    (Path(".") / filename).write_bytes((staged / filename).read_bytes())
            _refresh_loaded_json_globals()
        except OSError as error:
            print(f"[importvalues] {error}")
            return await interaction.response.send_message(
                get_response("values", "import_write_failed"),
                ephemeral=True,
            )

        await interaction.response.send_message(
            get_response("values", "import_done", count=len(imported)),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(ValuesCog(bot))