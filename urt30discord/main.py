import asyncio
import logging
import sys
from asyncio import CancelledError
from pathlib import Path

from urt30arcon import AsyncRconClient

from . import (
    DiscordClient,
    GameInfoUpdater,
    MapCycleUpdater,
    settings,
)

logger = logging.getLogger(__name__)


class Bot:
    def __init__(self) -> None:
        self._started_at = settings.bot.now()

    async def run(self) -> None:
        logger.info("%s running", self)
        logger.info("Python %s", sys.version)
        rcon_client = await AsyncRconClient.create_client(
            host=settings.rcon.host,
            port=settings.rcon.port,
            password=settings.rcon.password,
            recv_timeout=settings.rcon.recv_timeout,
        )
        logger.info(rcon_client)
        discord_client = DiscordClient(
            bot_user=settings.bot.user,
            server_name=settings.bot.server_name,
        )
        await discord_client.login(settings.bot.token)
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(
                    self._discord_update_mapcycle(rcon_client, discord_client)
                )
                tg.create_task(
                    self._discord_update_gameinfo(rcon_client, discord_client)
                )
        except Exception, CancelledError:
            logger.info("Shutdown cleanup has been triggered")
            await discord_client.close()
            rcon_client.close()

    async def _discord_update_gameinfo(
        self, rcon_client: AsyncRconClient, api_client: DiscordClient
    ) -> None:
        if not settings.gameinfo.enabled:
            logger.warning("Discord GameInfo Updates are not enabled")
            return
        updater = GameInfoUpdater(
            api_client=api_client,
            rcon_client=rcon_client,
            channel_name=settings.gameinfo.channel_name,
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
                logger.exception("GameInfo update failed")
                was_updated = True  # use the shorter delay to retry

            await asyncio.sleep(delay if was_updated else delay_no_updates)

    async def _discord_update_mapcycle(
        self, rcon_client: AsyncRconClient, api_client: DiscordClient
    ) -> None:
        if not settings.mapcycle.enabled:
            logger.warning("Discord Mapcycle Updates are not enabled")
            return
        if mapcycle_file := settings.mapcycle.file:
            mapcycle_file = Path(mapcycle_file)
        else:
            mapcycle_file = await rcon_client.mapcycle_file()
        if not mapcycle_file or not mapcycle_file.exists():
            logger.warning(
                "Discord Mapcycle Updates disabled, mapcycle file does not exist: %s",
                mapcycle_file,
            )
            return
        updater = MapCycleUpdater(
            api_client=api_client,
            rcon_client=rcon_client,
            channel_name=settings.mapcycle.channel_name,
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
                logger.exception("Mapcycle update failed")
            await asyncio.sleep(delay)

    def __repr__(self) -> str:
        return f"Bot(v{settings.__version__}, started={self._started_at})"
