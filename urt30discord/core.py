import abc
import logging
from typing import Any

import discord
from urt30arcon import AsyncRconClient

logger = logging.getLogger(__name__)


class DiscordClientError(Exception):
    pass


class DiscordClient(discord.Client):
    def __init__(
        self,
        bot_user: str,
        server_name: str,
        **kwargs: Any,
    ) -> None:
        if "intents" not in kwargs:
            kwargs["intents"] = discord.Intents.all()
        super().__init__(**kwargs)
        self.bot_user = bot_user
        self.server_name = server_name
        self._guild: discord.Guild | None = None
        self._channel_cache: dict[str, discord.TextChannel] = {}

    async def login(self, token: str) -> None:
        await super().login(token)
        async for guild in super().fetch_guilds():
            if guild.name == self.server_name:
                self._guild = guild
                break
        else:
            msg = f"Discord Server not found: {self.server_name}"
            raise DiscordClientError(msg)

    async def fetch_embed_message(
        self,
        channel_name: str,
        embed_title: str,
        limit: int = 10,
    ) -> tuple[discord.TextChannel, discord.Message | None]:
        if not (channel := self._channel_cache.get(channel_name)):
            channel = await self._channel_by_name(channel_name)
            self._channel_cache[channel_name] = channel

        async for msg in channel.history(limit=limit):
            author = msg.author
            author_user = f"{author.name}#{author.discriminator}"
            if author.bot and author_user == self.bot_user:
                for embed in msg.embeds:
                    if embed.title == embed_title:
                        return channel, msg

        return channel, None

    async def _channel_by_name(self, name: str) -> discord.TextChannel:
        logger.debug("Looking for channel named [%s]", name)
        if self._guild is None:
            msg = f"Discord Guild not found: {name}"
            raise DiscordClientError(msg)

        for ch in await self._guild.fetch_channels():
            if ch.name == name:
                logger.debug("Found channel: %s [%s]", ch.name, ch.id)
                if isinstance(ch, discord.TextChannel):
                    return ch
                msg = f"Discord Invalid Channel Type: {ch}"
                raise DiscordClientError(msg)

        msg = f"Discord Channel Not Found: {name}"
        raise DiscordClientError(msg)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__qualname__}("
            f"bot_user={self.bot_user!r}, server={self.server_name!r})"
        )


class DiscordEmbedUpdater(abc.ABC):
    def __init__(
        self,
        api_client: DiscordClient,
        rcon_client: AsyncRconClient,
        channel_name: str,
        embed_title: str,
    ) -> None:
        self.api_client = api_client
        self.rcon_client = rcon_client
        self.channel_name = channel_name
        self.embed_title = embed_title
        self._channel: discord.TextChannel | None = None

    async def fetch_embed_message(self) -> discord.Message | None:
        channel, message = await self.api_client.fetch_embed_message(
            self.channel_name, self.embed_title
        )
        self._channel = channel
        return message

    async def new_message(self, embed: discord.Embed) -> discord.Message:
        if self._channel is None:
            msg = f"Discord Channel has not be fetched for: {self.channel_name}"
            raise DiscordClientError(msg)
        return await self._channel.send(embed=embed)

    @abc.abstractmethod
    async def update(self) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def should_update_embed(
        self, message: discord.Message, embed: discord.Embed
    ) -> bool:
        raise NotImplementedError

    async def _update_or_create_if_needed(
        self, message: discord.Message | None, embed: discord.Embed
    ) -> bool:
        if message:
            if self.should_update_embed(message, embed):
                logger.debug("Updating existing embed: %s", self.embed_title)
                await message.edit(embed=embed)
            else:
                return False
        else:
            logger.info(
                "Sending new message embed to channel %s: %s",
                self.channel_name,
                self.embed_title,
            )
            await self.new_message(embed=embed)

        return True

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__qualname__}(channel_name={self.channel_name!r}, "
            f"embed_title={self.embed_title!r})"
        )
