import abc
import asyncio
import datetime
import functools
import logging

import discord
import psutil
from urt30arcon import AsyncRconClient

from . import __version__, mapfiles, settings

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
        self.rcon = AsyncRconClient(
            host=settings.rcon.private_ip,
            port=settings.rcon.port,
            password=settings.rcon.password,
            recv_timeout=settings.rcon.recv_timeout,
        )

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


@discord_client.tree.command(name="bot-stop", guild=GUILD)
async def bot_stop(interaction: discord.Interaction) -> None:
    """Stops the bot (and possibly restarts it).

    Args:
        interaction: discord.Interaction
    """
    await interaction.response.send_message(
        "stopping...",
        ephemeral=True,
        delete_after=1.5,
    )
    await asyncio.sleep(3.0)
    raise SystemExit(3)


@discord_client.tree.command(name="add-map-file", guild=GUILD)
async def add_map_file(interaction: discord.Interaction, name: str) -> None:
    """Adds a map file to the server.

    Args:
        interaction: discord.Interaction
        name: name of the map file (ex. ut4_casa_n1)
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await mapfiles.add_map_file(name)
    await interaction.followup.send(result)
    await asyncio.sleep(60.0)
    await interaction.delete_original_response()


@discord_client.tree.command(name="map-list", guild=GUILD)
async def map_list(interaction: discord.Interaction) -> None:
    """Lists maps available on the server.

    Args:
        interaction: discord.Interaction
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    all_maps = await discord_client.rcon.maps()
    result = "* " + "\n* ".join(all_maps)
    await interaction.followup.send(result)
    await asyncio.sleep(60.0)
    await interaction.delete_original_response()


@discord_client.tree.command(name="map-cycle-next", guild=GUILD)
async def map_cycle_next(interaction: discord.Interaction) -> None:
    """Cycle to the next map.

    Args:
        interaction: discord.Interaction
    """
    await discord_client.rcon.cycle_map()
    await interaction.response.send_message(
        "cycling to next map",
        ephemeral=True,
        delete_after=CMD_RESP_EXPIRY,
    )


@discord_client.tree.command(name="map-set-next", guild=GUILD)
async def map_set_next(interaction: discord.Interaction, map_name: str) -> None:
    """Set the next map.

    Args:
        interaction: discord.Interaction
        map_name: name of map to cycle to next
    """
    await discord_client.rcon.setcvar("g_nextmap", map_name)
    await interaction.response.send_message(
        f"next map set to `{map_name}`",
        ephemeral=True,
        delete_after=CMD_RESP_EXPIRY,
    )


@discord_client.tree.command(name="bot-info", guild=GUILD)
async def bot_info(interaction: discord.Interaction) -> None:
    """Information about the bot.

    Args:
        interaction: discord.Interaction
    """
    embed = discord.Embed(title="Bot Information")
    embed.colour = discord.Colour.green()
    embed.add_field(name="bot version", value=__version__, inline=False)
    embed.add_field(name="discord-py version", value=discord.__version__, inline=False)
    embed.add_field(name="bot user", value=discord_client.bot_user, inline=False)
    embed.add_field(
        name="updaters channel", value=discord_client.channel.name, inline=False
    )
    embed.add_field(name="rcon client", value=f"{discord_client.rcon!r}", inline=False)
    embed.add_field(
        name="asyncio.loop", value=f"{asyncio.get_running_loop()!r}", inline=False
    )
    embed.add_field(
        name="gameinfo updater enabled", value=settings.gameinfo.enabled, inline=False
    )
    embed.add_field(
        name="mapcycle updater enabled", value=settings.mapcycle.enabled, inline=False
    )
    embed.add_field(name="bot boot time", value=settings.STARTED_AT, inline=False)
    embed.add_field(name="system boot time", value=_sys_boot_time(), inline=False)
    async with asyncio.timeout(1.0):
        try:
            net_stats_udp = await _net_stats_udp()
        except TimeoutError:
            net_stats_udp = "timed out"
        except Exception as exc:
            net_stats_udp = f"failed: {exc!r}"
    embed.add_field(name="udp network stats", value=net_stats_udp, inline=False)
    embed.add_field(name="cpu stats", value=psutil.cpu_percent(), inline=False)
    embed.add_field(name="memory stats", value=psutil.virtual_memory(), inline=False)
    await interaction.response.send_message(
        embed=embed,
        ephemeral=True,
        delete_after=120.0,
    )


async def _net_stats_udp() -> str:
    proc = await asyncio.create_subprocess_exec(
        "/usr/bin/netstat",
        "-suna",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if stderr:
        logger.error(stderr)
    data = stdout.decode().splitlines()
    text = None
    for line in data:
        if (line := line.strip()) == "Udp:":
            text = []
        elif line == "UdpLite:":
            break
        elif text is not None:
            text.append(line)
    return "```" + "\n".join(text or []) + "```"


@functools.cache
def _sys_boot_time() -> datetime.datetime:
    boot_time = psutil.boot_time()
    return datetime.datetime.fromtimestamp(boot_time, tz=datetime.UTC)
