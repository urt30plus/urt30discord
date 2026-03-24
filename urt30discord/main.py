import asyncio
import logging
import sys
from pathlib import Path

from . import __version__, settings
from .core import DiscordEmbedUpdater, discord_client
from .gameinfo import GameInfoUpdater
from .mapcycle import MapCycleUpdater

logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("v%s - %s", __version__, sys.version)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(discord_client.start(settings.bot.token))

            if settings.mapcycle.enabled:
                if mapcycle_file := settings.mapcycle.file:
                    mapcycle_file = Path(mapcycle_file)
                else:
                    mapcycle_file = await discord_client.rcon.mapcycle_file()
                if not mapcycle_file or not mapcycle_file.exists():
                    logger.warning(
                        "mapcycle updates disabled, file does not exist: %s",
                        mapcycle_file,
                    )
                else:
                    updater = MapCycleUpdater(
                        client=discord_client,
                        embed_title=settings.mapcycle.embed_title,
                        mapcycle_file=mapcycle_file,
                    )
                    tg.create_task(
                        run_updater_task(
                            updater,
                            delay=settings.mapcycle.delay,
                            delay_no_updates=settings.mapcycle.delay,
                            timeout=settings.mapcycle.timeout,
                        )
                    )
            else:
                logger.warning("mapcycle updates are not enabled")

            if settings.gameinfo.enabled:
                updater = GameInfoUpdater(
                    client=discord_client,
                    embed_title=settings.gameinfo.embed_title,
                    game_host=settings.gameinfo.game_host,
                )
                if settings.mapcycle.enabled:
                    # delay on first start to allow mapcycle time to complete first
                    await asyncio.sleep(10.0)
                tg.create_task(
                    run_updater_task(
                        updater,
                        delay=settings.gameinfo.delay,
                        delay_no_updates=settings.gameinfo.delay_no_updates,
                        timeout=settings.gameinfo.timeout,
                    )
                )
            else:
                logger.warning("game updates are not enabled")
    finally:
        await discord_client.close()
        logger.info("shutdown complete")


async def run_updater_task(
    updater: DiscordEmbedUpdater, delay: float, delay_no_updates: float, timeout: float
) -> None:
    await discord_client.wait_until_ready()
    logger.info(
        "%r - delay=[%s], delay_no_updates=[%s], timeout=[%s]",
        updater,
        delay,
        delay_no_updates,
        timeout,
    )
    while True:
        try:
            was_updated = await updater.update()
        except Exception:
            logger.exception("%r updater failed", updater)
            was_updated = True  # use the shorter delay to retry

        await asyncio.sleep(delay if was_updated else delay_no_updates)
