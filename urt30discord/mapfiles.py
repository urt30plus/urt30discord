import contextlib
import dataclasses
import logging
import urllib.parse
from pathlib import Path
from typing import Literal

import aiofiles
import aiofiles.os
import aiohttp
import asyncssh

from . import settings

logger = logging.getLogger(__name__)

URTLI_DOWNLOAD_URL = "https://urt.li/q3ut4"


@dataclasses.dataclass
class MapCycleEntry:
    map_name: str
    map_options: dict[str, str] | None = None


async def add_map_file(name: str) -> str:
    map_file = (settings.mapfiles.path / name).with_suffix(".pk3").resolve()
    if await aiofiles.os.path.exists(str(map_file)):
        return f"map file [{map_file}] already exists on the server"
    map_url = f"{settings.mapfiles.downloads_url}/{map_file.name}"
    tmp_file = map_file.with_suffix(".tmp")
    results = []
    try:
        try:
            await download_file(map_url, tmp_file)
            results.append(f"downloaded from [{map_url}]")
        except aiohttp.ClientResponseError:
            if settings.mapfiles.downloads_url != URTLI_DOWNLOAD_URL:
                results.append(f"unable to download map file [{map_url}]")
                map_url = f"{URTLI_DOWNLOAD_URL}/{map_file.name}"
                await download_file(map_url, tmp_file)
                results.append(f"downloaded from [{map_url}]")
                try:
                    rv = await upload_map_file(tmp_file)
                except Exception as exc:
                    results.append(f"failed to upload map file [{map_url}]: {exc!r}")
                    raise
                else:
                    results.append(rv)
            else:
                raise
    except aiohttp.ClientResponseError as exc:
        results.append(
            f"failed to download map file [{map_url}]: {exc.status} - {exc.message}"
        )
    else:
        logger.info("moving [%s] to [%s]", tmp_file, map_file)
        await aiofiles.os.rename(tmp_file, map_file)
        stats = await aiofiles.os.stat(map_file)
        results.append(f"added file {map_file} (size {stats.st_size:,})")
    finally:
        with contextlib.suppress(FileNotFoundError):
            await aiofiles.os.unlink(tmp_file)

    return "* " + "\n* ".join(results)


async def download_file(url: str, path: Path) -> None:
    logger.info("attempting to download [%s] to [%s]", url, path)
    async with (
        aiofiles.open(path, "wb") as fp,
        aiohttp.ClientSession() as session,
        session.get(url) as r,
    ):
        r.raise_for_status()
        async for chunk in r.content.iter_chunked(1024 * 1024):
            await fp.write(chunk)


async def upload_map_file(map_file: Path) -> str:
    parts = urllib.parse.urlparse(settings.mapfiles.sftp_url)
    path = str(parts.path).strip("/")
    filename = map_file.with_suffix(".pk3").name
    target_file = f"{path}/{filename}"
    logger.info("attempting to upload [%s] to [%s]", map_file, target_file)
    async with (
        asyncssh.connect(
            host=parts.hostname,
            port=parts.port,
            username=parts.username,
            password=parts.password,
            known_hosts=None,
            connect_timeout=15.0,
            login_timeout=5.0,
        ) as conn,
        conn.start_sftp_client() as sftp,
    ):
        await sftp.put(map_file, remotepath=target_file)
    return (
        f"uploaded map file to [{parts.username}@{parts.hostname}"
        f":{parts.port or 22}{parts.path}]"
    )


async def map_cycle_add(
    map_name: str, pos: Literal["before", "after"], other_map: str | None
) -> str:
    entries = await load_map_cycle_file(settings.mapcycle.file)
    if [x for x in entries if x.map_name == map_name]:
        return f"map file [{map_name}] already exists in the map cycle"

    new_entry = MapCycleEntry(map_name=map_name)
    new_entries = []
    if other_map:
        for entry in entries:
            if entry.map_name == other_map:
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
    new_entries = [e for e in entries if e.map_name != map_name]
    if len(new_entries) == len(entries):
        return f"map file [{map_name}] not found in map cycle"
    await save_map_cycle_file(settings.mapcycle.file, new_entries)
    return f"map file [{map_name}] has been removed from map cycle"


async def load_map_cycle_file(cycle_file: Path) -> list[MapCycleEntry]:
    async with aiofiles.open(cycle_file, encoding="utf-8") as f:
        s = await f.read()
    return parse_map_entries(s)


async def save_map_cycle_file(cycle_file: Path, entries: list[MapCycleEntry]) -> None:
    async with aiofiles.open(cycle_file, mode="w", encoding="utf-8") as f:
        for entry in entries:
            await f.write(entry.map_name + "\n")
            if entry.map_options:
                await f.write("{\n")
                for k, v in entry.map_options.items():
                    await f.write(f"{k} {v}\n")
                await f.write("}\n")


def parse_map_entries(s: str) -> list[MapCycleEntry]:
    entries = []
    options: dict[str, str] | None = None
    for line in s.splitlines():
        if not (line := line.strip()):
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
            options[k] = v.strip()
        else:
            entries.append(MapCycleEntry(map_name=line))
    return entries
