import contextlib
import logging
from pathlib import Path

import aiofiles
import aiofiles.os
import aiohttp

from . import settings

logger = logging.getLogger(__name__)


async def add_map_file(name: str) -> str:
    map_file = (settings.mapfiles.path / name).with_suffix(".pk3").resolve()
    if await aiofiles.os.path.exists(str(map_file)):
        return f"map file [{map_file}] already exists on the server"
    map_url = f"{settings.mapfiles.downloads_url}/{map_file.name}"
    tmp_file = map_file.with_suffix(".tmp")
    try:
        await download_file(map_url, tmp_file)
    except aiohttp.ClientResponseError as exc:
        return f"failed to download map file [{map_url}]: {exc.status} - {exc.message}"
    else:
        logger.info("moving [%s] to [%s]", tmp_file, map_file)
        await aiofiles.os.rename(tmp_file, map_file)
        stats = await aiofiles.os.stat(map_file)
        return f"added file {map_file} (size {stats.st_size:,})"
    finally:
        with contextlib.suppress(FileNotFoundError):
            await aiofiles.os.unlink(tmp_file)


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
