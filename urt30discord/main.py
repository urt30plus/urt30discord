import asyncio
import logging
import sys
from asyncio import CancelledError
from pathlib import Path

from urt30arcon import AsyncRconClient

from . import __version__, settings
from .core import discord_client
from .gameinfo import GameInfoUpdater
from .mapcycle import MapCycleUpdater

logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("v%s - %s", __version__, sys.version)
    rcon_client = await AsyncRconClient.create_client(
        host=settings.rcon.host,
        port=settings.rcon.port,
        password=settings.rcon.password,
        recv_timeout=settings.rcon.recv_timeout,
    )
    logger.info(rcon_client)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(discord_client.start(settings.bot.token))
            if settings.mapcycle.enabled:
                tg.create_task(update_mapcycle(rcon_client))
            else:
                logger.warning("mapcycle updates are not enabled")

            if settings.gameinfo.enabled:
                tg.create_task(update_gameinfo(rcon_client))
            else:
                logger.warning("game updates are not enabled")
    finally:
        logger.info("cleanup has been triggered")
        await asyncio.shield(discord_client.close())
        rcon_client.close()
        logger.info("shutdown complete")


async def update_gameinfo(rcon_client: AsyncRconClient) -> None:
    await discord_client.wait_until_ready()
    updater = GameInfoUpdater(
        discord_client=discord_client,
        rcon_client=rcon_client,
        embed_title=settings.gameinfo.embed_title,
        game_host=settings.gameinfo.game_host,
    )
    delay = settings.gameinfo.delay
    delay_no_updates = settings.gameinfo.delay_no_updates
    timeout = settings.gameinfo.timeout
    logger.info(
        "%r - delay=[%s], delay_no_updates=[%s], timeout=[%s]",
        updater,
        delay,
        delay_no_updates,
        timeout,
    )
    # delay on first start to allow mapcycle time to complete first
    await asyncio.sleep(15.0)
    while True:
        try:
            was_updated = await updater.update()
        except Exception:
            logger.exception("game update failed")
            was_updated = True  # use the shorter delay to retry

        await asyncio.sleep(delay if was_updated else delay_no_updates)


async def update_mapcycle(rcon_client: AsyncRconClient) -> None:
    await discord_client.wait_until_ready()
    if mapcycle_file := settings.mapcycle.file:
        mapcycle_file = Path(mapcycle_file)
    else:
        mapcycle_file = await rcon_client.mapcycle_file()
    if not mapcycle_file or not mapcycle_file.exists():
        logger.warning(
            "mapcycle updates disabled, file does not exist: %s",
            mapcycle_file,
        )
        return
    updater = MapCycleUpdater(
        discord_client=discord_client,
        rcon_client=rcon_client,
        embed_title=settings.mapcycle.embed_title,
        mapcycle_file=mapcycle_file,
    )
    delay = settings.mapcycle.delay
    timeout = settings.mapcycle.timeout
    logger.info(
        "%r - delay=[%s], timeout=[%s], file=[%s]",
        updater,
        delay,
        timeout,
        mapcycle_file,
    )
    while True:
        try:
            await updater.update()
        except Exception:
            logger.exception("mapcycle update failed")
        await asyncio.sleep(delay)
