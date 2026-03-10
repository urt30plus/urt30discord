import asyncio
import logging
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

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
        self._conf = settings.bot
        self._started_at = settings.bot.now()
        self._rcon: AsyncRconClient | None = None
        self._discord: DiscordClient | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        logger.info("%s running", self)
        logger.info("Python %s", sys.version)
        self._rcon = await AsyncRconClient.create_client(
            host=settings.rcon.host,
            port=settings.rcon.port,
            password=settings.rcon.password,
            recv_timeout=settings.rcon.recv_timeout,
        )
        logger.info(self._rcon)
        self._discord = DiscordClient(
            bot_user=settings.bot.user,
            server_name=settings.bot.server_name,
        )
        await self._discord.login(settings.bot.token)
        self._run_background_task(self._discord_update_mapcycle(self._discord))
        self._run_background_task(self._discord_update_gameinfo(self._discord))
        self._run_background_task(self._run_cleanup())

    @property
    def rcon(self) -> AsyncRconClient:
        if self._rcon is None:
            msg = "Rcon Client is not initialized"
            raise RuntimeError(msg)
        return self._rcon

    async def on_shutdown(self) -> None:
        if self._rcon:
            self._rcon.close()
        if self._discord:
            await self._discord.close()
        logger.info("%s stopped", self)

    async def _run_cleanup(self) -> None:
        fut: asyncio.Future[None] = asyncio.Future()
        try:
            await fut
        except asyncio.CancelledError:
            logger.info("Shutdown cleanup has been triggered")
            raise
        finally:
            await self.on_shutdown()

    async def _discord_update_gameinfo(self, api_client: DiscordClient) -> None:
        if not settings.gameinfo.enabled:
            logger.warning("Discord GameInfo Updates are not enabled")
            return
        updater = GameInfoUpdater(
            api_client=api_client,
            rcon_client=self.rcon,
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

    async def _discord_update_mapcycle(self, api_client: DiscordClient) -> None:
        if not settings.mapcycle.enabled:
            logger.warning("Discord Mapcycle Updates are not enabled")
            return
        if mapcycle_file := settings.mapcycle.file:
            mapcycle_file = Path(mapcycle_file)
        else:
            mapcycle_file = await self.rcon.mapcycle_file()
        if not mapcycle_file or not mapcycle_file.exists():
            logger.warning(
                "Discord Mapcycle Updates disabled, mapcycle file does not exist: %s",
                mapcycle_file,
            )
            return
        updater = MapCycleUpdater(
            api_client=api_client,
            rcon_client=self.rcon,
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

    def _run_background_task(self, coro: Coroutine[Any, None, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def __repr__(self) -> str:
        return f"Bot(v{settings.__version__}, started={self._started_at})"
