import abc
import logging

import discord
import discord.app_commands
from urt30arcon import AsyncRconClient

from . import settings

logger = logging.getLogger(__name__)

GUILD = discord.Object(id=settings.bot.server_id)


class DiscordClientError(Exception):
    pass


class DiscordClient(discord.Client):
    def __init__(
        self,
        bot_user: str,
        channel_id: int,
    ) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = discord.app_commands.CommandTree(self)
        self.bot_user = bot_user
        self.channel_id = channel_id
        self._channel: discord.TextChannel | None = None
        self.rcon = AsyncRconClient(
            host=settings.rcon.private_ip,
            port=settings.rcon.port,
            password=settings.rcon.password,
            recv_timeout=settings.rcon.recv_timeout,
        )
        self.embed_updaters: dict[str, DiscordEmbedUpdater] = {}

    @property
    def channel(self) -> discord.TextChannel:
        if self._channel is None:
            msg = f"Discord Channel has not be fetched: {self.channel_id}"
            raise DiscordClientError(msg)
        return self._channel

    async def setup_hook(self) -> None:
        channel = await self.fetch_channel(self.channel_id)
        if isinstance(channel, discord.TextChannel):
            self._channel = channel
        else:
            msg = f"Discord Channel not a TextChannel: {channel!r}"
            raise DiscordClientError(msg)
        logger.info("Logged on as: %s", self.user)

        # import our commands so they are registered with this client
        from . import commands  # noqa: F401, PLC0415

        self.tree.copy_global_to(guild=GUILD)
        await self.tree.sync(guild=GUILD)

    async def fetch_embed_message(
        self,
        embed_title: str,
        limit: int = 10,
    ) -> tuple[discord.TextChannel, discord.Message | None]:
        async for msg in self.channel.history(limit=limit):
            author = msg.author
            author_user = f"{author.name}#{author.discriminator}"
            if author.bot and author_user == self.bot_user:
                for embed in msg.embeds:
                    if embed.title == embed_title:
                        return self.channel, msg

        return self.channel, None

    async def close(self) -> None:
        await super().close()
        self.rcon.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}(bot_user={self.bot_user!r})"


class DiscordEmbedUpdater(abc.ABC):
    def __init__(self, client: DiscordClient, embed_title: str) -> None:
        self.client = client
        self.embed_title = embed_title
        client.embed_updaters[self.__class__.__name__] = self

    async def fetch_embed_message(self) -> discord.Message | None:
        _, message = await self.client.fetch_embed_message(self.embed_title)
        return message

    async def new_message(self, embed: discord.Embed) -> discord.Message:
        return await self.client.channel.send(embed=embed)

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
                self.client.channel.name,
                self.embed_title,
            )
            await self.new_message(embed=embed)

        return True

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__qualname__}"
            f"(channel_name={self.client.channel.name!r}, "
            f"embed_title={self.embed_title!r})"
        )


discord_client = DiscordClient(
    bot_user=settings.bot.user, channel_id=settings.bot.channel_id
)
