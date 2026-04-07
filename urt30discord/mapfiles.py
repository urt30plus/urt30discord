import contextlib
import logging
import urllib.parse
from typing import TYPE_CHECKING

import aiofiles
import aiofiles.os
import aiohttp
import asyncssh

from . import settings

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

URTLI_DOWNLOAD_URL = "https://urt.li/q3ut4"


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
