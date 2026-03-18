import abc
import asyncio
import logging

import discord
from urt30arcon import AsyncRconClient

from . import settings

logger = logging.getLogger(__name__)

GUILD = discord.Object(id=settings.bot.server_id)
CMD_RESP_EXPIRY = 10.0


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
        self.bot_running = asyncio.Event()

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
        self.tree.copy_global_to(guild=GUILD)
        await self.tree.sync(guild=GUILD)
        self.bot_running.set()

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

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}(bot_user={self.bot_user!r})"


class DiscordEmbedUpdater(abc.ABC):
    def __init__(
        self,
        discord_client: DiscordClient,
        rcon_client: AsyncRconClient,
        embed_title: str,
    ) -> None:
        self.discord_client = discord_client
        self.rcon_client = rcon_client
        self.embed_title = embed_title

    async def fetch_embed_message(self) -> discord.Message | None:
        _, message = await self.discord_client.fetch_embed_message(self.embed_title)
        return message

    async def new_message(self, embed: discord.Embed) -> discord.Message:
        return await self.discord_client.channel.send(embed=embed)

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
                self.discord_client.channel.name,
                self.embed_title,
            )
            await self.new_message(embed=embed)

        return True

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__qualname__}"
            f"(channel_name={self.discord_client.channel.name!r}, "
            f"embed_title={self.embed_title!r})"
        )


discord_client = DiscordClient(
    bot_user=settings.bot.user, channel_id=settings.bot.channel_id
)


@discord_client.tree.command(name="bot-restart", guild=GUILD)
async def bot_restart(interaction: discord.Interaction) -> None:
    """Restart the Bot.

    Args:
        interaction: discord.Interaction
    """
    await interaction.response.send_message(
        "not implemented yet",
        ephemeral=True,
        delete_after=CMD_RESP_EXPIRY,
    )
