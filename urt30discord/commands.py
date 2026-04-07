import asyncio
import datetime
import functools
import logging
from typing import Literal

import discord
import psutil

from . import __version__, mapfiles, settings
from .core import GUILD, discord_client

CMD_RESP_EXPIRY = 10.0
CMD_RESP_EXPIRY_DEFER = 60.0
EMBED_DESCR_CHAR_LIMIT = 4_096

logger = logging.getLogger(__name__)


@discord_client.tree.command(name="bot-info", guild=GUILD)
async def bot_info(interaction: discord.Interaction) -> None:
    """Information about the bot.

    Args:
        interaction: discord.Interaction
    """
    await interaction.response.defer(ephemeral=True, thinking=True)

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

    await interaction.followup.send(embed=embed)
    await asyncio.sleep(CMD_RESP_EXPIRY_DEFER)
    await interaction.delete_original_response()


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


@discord_client.tree.command(name="map-add", guild=GUILD)
async def map_add(interaction: discord.Interaction, name: str) -> None:
    """Adds a map file to the server.

    Args:
        interaction: discord.Interaction
        name: name of the map file (ex. ut4_casa_n1)
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await mapfiles.add_map_file(name)
    await interaction.followup.send(result)
    await asyncio.sleep(CMD_RESP_EXPIRY_DEFER)
    await interaction.delete_original_response()


@discord_client.tree.command(name="map-cycle-add", guild=GUILD)
async def map_cycle_add(
    interaction: discord.Interaction,
    map_name: str,
    pos: Literal["before", "after"],
    other_map: str | None = None,
) -> None:
    """Adds the map to the mapcycle.

    Args:
        interaction: discord.Interaction
        map_name: name of map to add to the map cycle
        pos: position to add the new map
        other_map: position relative to this map for insertion
    """
    await interaction.response.defer(ephemeral=True, thinking=True)

    if not await _map_exists_on_server(map_name):
        await interaction.followup.send(
            f"map `{map_name}` is not available on the server"
        )
        await asyncio.sleep(CMD_RESP_EXPIRY)
        await interaction.delete_original_response()
        return

    result = await mapfiles.map_cycle_add(map_name, pos, other_map)
    await interaction.followup.send(result)
    if updater := discord_client.embed_updaters.get("MapCycleUpdater"):
        await updater.update()
    await asyncio.sleep(CMD_RESP_EXPIRY_DEFER)
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
    if updater := discord_client.embed_updaters.get("GameInfoUpdater"):
        await updater.update()


@discord_client.tree.command(name="map-cycle-remove", guild=GUILD)
async def map_cycle_remove(interaction: discord.Interaction, map_name: str) -> None:
    """Removes the map to the mapcycle.

    Args:
        interaction: discord.Interaction
        map_name: name of map to remove from the map cycle
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await mapfiles.map_cycle_remove(map_name)
    await interaction.followup.send(result)
    if updater := discord_client.embed_updaters.get("MapCycleUpdater"):
        await updater.update()
    await asyncio.sleep(CMD_RESP_EXPIRY_DEFER)
    await interaction.delete_original_response()


@discord_client.tree.command(name="map-list", guild=GUILD)
async def map_list(interaction: discord.Interaction) -> None:
    """Lists maps available on the server.

    Args:
        interaction: discord.Interaction
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    all_maps = await discord_client.rcon.maps()
    # find the longest map name so we can pad the embed to this many chars
    # so all embeds are spaced the same
    padding = sorted(len(x) for x in all_maps)[-1]
    # Discord message limits (2,000 chars) are too restrictive for servers
    # with a large number of maps, so embeds are used instead. Embed
    # descriptions are limited to 4,096 characters. If the map list exceeds
    # that limit, then multiple embeds are created.
    embeds = []
    current_maps = ""
    for m in all_maps:
        if (len(current_maps) + len(m) + 10) > EMBED_DESCR_CHAR_LIMIT:
            embeds.append(
                discord.Embed(
                    colour=discord.Colour.dark_orange(),
                    description=f"```\n{current_maps}\n```",
                )
            )
            current_maps = f"{m:{padding}}\n"
            continue
        if current_maps:
            current_maps += f"{m}\n"
        else:
            # just pad the first map, so we don't waste our limit on padding
            current_maps += f"{m:{padding}}\n"
    if current_maps:
        embeds.append(
            discord.Embed(
                colour=discord.Colour.dark_orange(),
                description=f"```\n{current_maps}\n```",
            )
        )

    await interaction.followup.send(embeds=embeds)
    await asyncio.sleep(CMD_RESP_EXPIRY_DEFER)
    await interaction.delete_original_response()


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


@discord_client.tree.command(name="map-set-next", guild=GUILD)
async def map_set_next(interaction: discord.Interaction, map_name: str) -> None:
    """Set the next map.

    Args:
        interaction: discord.Interaction
        map_name: name of map to cycle to next
    """
    if await _map_exists_on_server(map_name):
        await discord_client.rcon.setcvar("g_nextmap", map_name)
        await interaction.response.send_message(
            f"next map set to `{map_name}`",
            ephemeral=True,
            delete_after=CMD_RESP_EXPIRY,
        )
        if updater := discord_client.embed_updaters.get("GameInfoUpdater"):
            await updater.update()
    else:
        await interaction.response.send_message(
            f"map `{map_name}` is not available on the server",
            ephemeral=True,
            delete_after=CMD_RESP_EXPIRY,
        )


@functools.cache
def _sys_boot_time() -> datetime.datetime:
    boot_time = psutil.boot_time()
    return datetime.datetime.fromtimestamp(boot_time, tz=datetime.UTC)


async def _map_exists_on_server(map_name: str) -> bool:
    all_maps = await discord_client.rcon.maps()
    needle = map_name.strip().lower()
    return any(m.lower() == needle for m in all_maps)
