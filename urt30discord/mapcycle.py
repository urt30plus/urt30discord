import asyncio
import dataclasses
import datetime
import logging
import time
from typing import TYPE_CHECKING, Literal

import aiofiles
import aiofiles.os
import discord
from urt30arcon import GameType

from . import settings
from .core import DiscordClient, DiscordEmbedUpdater

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MapCycleEntry:
    map_name: str
    map_options: dict[str, str] | None = None


class MapCycleUpdater(DiscordEmbedUpdater):
    def __init__(
        self,
        client: DiscordClient,
        embed_title: str,
        mapcycle_file: Path,
    ) -> None:
        super().__init__(client, embed_title)
        self.mapcycle_file = mapcycle_file
        self.last_mtime = 0.0

    async def update(self) -> bool:
        if await self.file_not_changed():
            return False

        message, embed = await asyncio.gather(
            self.fetch_embed_message(),
            create_embed(self.mapcycle_file, self.embed_title),
        )
        return await self._update_or_create_if_needed(message, embed)

    def should_update_embed(
        self, message: discord.Message, embed: discord.Embed
    ) -> bool:
        curr_embed = message.embeds[0]
        curr_txt = curr_embed.description or ""
        new_txt = embed.description or ""
        return curr_txt.strip() != new_txt.strip()

    async def file_not_changed(self) -> bool:
        stats = await aiofiles.os.stat(self.mapcycle_file)
        if stats.st_mtime == self.last_mtime:
            return True

        if self.last_mtime:  # only if we previously stored the mtime
            old_time = datetime.datetime.fromtimestamp(self.last_mtime, tz=datetime.UTC)
            new_time = datetime.datetime.fromtimestamp(stats.st_mtime, tz=datetime.UTC)
            logger.info(
                "%s mtime changed: [%s]-->[%s]", self.mapcycle_file, old_time, new_time
            )

        self.last_mtime = stats.st_mtime
        return False


async def create_embed(mapcycle_file: Path, embed_title: str) -> discord.Embed:
    logger.debug("Creating map cycle embed from: %s", mapcycle_file)
    try:
        cycle = await load_map_cycle_file(mapcycle_file)
    except Exception:
        logger.exception("Failed to parse map cycle file: %s", mapcycle_file)
        cycle = []
    return create_mapcycle_embed(cycle, embed_title)


def create_mapcycle_embed(
    cycle: list[MapCycleEntry], embed_title: str
) -> discord.Embed:
    if cycle:
        descr = (
            "```\n"
            + "\n".join([
                f"{e.map_name:24} {map_mode(e.map_options):20}" for e in cycle
            ])
            + "```"
        )
        color = discord.Colour.blue()
    else:
        descr = "*Unable to retrieve map cycle*"
        color = discord.Colour.red()
    embed = discord.Embed(
        title=embed_title,
        description=descr,
        colour=color,
    )
    embed.add_field(
        name=f"{len(cycle)} maps",
        value=f"updated <t:{int(time.time())}>",
        inline=False,
    )

    return embed


def map_mode(map_opts: dict[str, str] | None) -> str:
    if not map_opts:
        return ""
    game_type = map_opts.get("g_gametype")
    # d3mod Gungame uses a g_gametype of FFA (0)
    if game_type == GameType.FFA.value and map_opts.get("mod_gungame", "0") == "1":
        result = GameType.GUNGAME.name + " d3mod"
    elif game_type == GameType.CTF.value and map_opts.get("mod_ctf", "0") == "1":
        result = GameType.CTF.name + " d3mod"
    elif (game_type := map_opts.get("g_gametype")) not in {
        GameType.CTF.value,
        GameType.TS.value,
    }:
        # show game type for non-standard modes
        result = GameType(game_type).name
    else:
        result = ""
    if map_opts.get("g_instagib") == "1":
        result += " Instagib" if result else "Instagib"

    return f"({result})" if result else ""


async def map_cycle_add(
    map_name: str, pos: Literal["before", "after"], other_map: str | None
) -> str:
    entries = await load_map_cycle_file(settings.mapcycle.file)

    map_to_add = map_name.strip().lower()
    if [x for x in entries if x.map_name.lower() == map_to_add]:
        return f"map file [{map_name}] already exists in the map cycle"

    new_entry = MapCycleEntry(map_name=map_to_add)
    new_entries = []
    if other_map:
        needle = other_map.strip().lower()
        for entry in entries:
            if entry.map_name.lower() == needle:
                if pos == "before":
                    new_entries.append(new_entry)
                    new_entries.append(entry)
                else:
                    new_entries.append(entry)
                    new_entries.append(new_entry)
            else:
                new_entries.append(entry)

    if not new_entries or len(new_entries) == len(entries):
        if pos == "before":
            new_entries = [new_entry, *entries]
        else:
            new_entries = [*entries, new_entry]

    await save_map_cycle_file(settings.mapcycle.file, new_entries)
    return f"map file [{map_name}] has been added to the map cycle"


async def map_cycle_remove(map_name: str) -> str:
    entries = await load_map_cycle_file(settings.mapcycle.file)
    map_to_remove = map_name.strip().lower()
    new_entries = [e for e in entries if e.map_name.lower() != map_to_remove]
    if len(new_entries) == len(entries):
        return f"map file [{map_name}] not found in map cycle"
    await save_map_cycle_file(settings.mapcycle.file, new_entries)
    return f"map file [{map_name}] has been removed from map cycle"


async def load_map_cycle_file(cycle_file: Path) -> list[MapCycleEntry]:
    data = await asyncio.to_thread(cycle_file.read_text, encoding="utf-8")
    return parse_map_entries(data)


async def save_map_cycle_file(cycle_file: Path, entries: list[MapCycleEntry]) -> None:
    async with aiofiles.open(cycle_file, mode="w", encoding="utf-8") as f:
        for entry in entries:
            await f.write(entry.map_name + "\n")
            if entry.map_options:
                await f.write("{\n")
                for k, v in entry.map_options.items():
                    await f.write(f'{k} "{v}"\n')
                await f.write("}\n")


def parse_map_entries(s: str) -> list[MapCycleEntry]:
    entries = []
    options: dict[str, str] | None = None
    for line in s.splitlines():
        if not (line := line.strip()) or line.startswith("//"):
            continue
        if line == "{":
            options = {}
        elif line == "}":
            if not entries and options is None:
                raise ValueError(s)
            entries[-1].map_options = options
            options = None
        elif options is not None:
            k, _, v = line.partition(" ")
            options[k.lower()] = v.strip().strip("\"'")
        else:
            entries.append(MapCycleEntry(map_name=line))
    return entries
