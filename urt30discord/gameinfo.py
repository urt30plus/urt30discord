import asyncio
import logging
import operator
import time
from typing import NamedTuple

import discord
from urt30arcon import AsyncRconClient, Game, Player

from . import DiscordClient, DiscordEmbedUpdater

logger = logging.getLogger(__name__)

# max embed field length is roughly 48 for most mobile and desktop viewports
# found through trial and error
SIZE_MAX_LEN = 48

# padding between the player name and the KDA
PLAYER_NAME_PADDING = 6

# for player name we have to take into account the KDA/Ping display and
# a magic number for spacing for it to fit comfortably
SIZE_PLAYER_NAME = SIZE_MAX_LEN - len(" [K../D./A.] 123ms") - PLAYER_NAME_PADDING

# spacer used for showing a team with no players
EMBED_NO_PLAYERS = "```\n" + " " * SIZE_MAX_LEN + "\n```"

SORT_KEY_NAME = operator.attrgetter("clean_name")


class NextMapCache(NamedTuple):
    name: str | None
    expires: float


class GameInfoUpdater(DiscordEmbedUpdater):
    def __init__(
        self,
        api_client: DiscordClient,
        rcon_client: AsyncRconClient,
        channel_name: str,
        embed_title: str,
        game_host: str | None = None,
    ) -> None:
        super().__init__(api_client, rcon_client, channel_name, embed_title)
        self._last_game: Game | None = None
        self._next_map = NextMapCache(None, -1.0)
        self._game_host = game_host

    async def update(self) -> bool:
        message, game = await asyncio.gather(
            self.fetch_embed_message(),
            self.fetch_game_info(),
        )

        if message and same_map_and_specs(game, self._last_game):
            result = False
        else:
            next_map = await self.fetch_next_map(game)
            embed = create_server_embed(
                game, next_map, self.embed_title, self._game_host, self.rcon_client.port
            )
            result = await self._update_or_create_if_needed(message, embed)

        if game:
            self._last_game = game

        return result

    async def fetch_game_info(self) -> Game | None:
        for _ in range(3):
            try:
                return await self.rcon_client.game_info()
            except LookupError:
                continue
            except Exception:
                logger.exception("Failed to fetch game info")
                break
        return None

    async def fetch_next_map(self, game: Game | None) -> str | None:
        now = time.monotonic()
        if (
            self.is_same_map_as_last(game)
            and self._next_map.name
            and self._next_map.expires > now
        ):
            return self._next_map.name
        if next_map := await self.rcon_client.next_map():
            if next_map != self._next_map.name:
                logger.info("Updating next map from %s to %s", self._next_map, next_map)
            self._next_map = NextMapCache(next_map, now + 30.0)
            return next_map
        return self._next_map.name

    def is_same_map_as_last(self, game: Game | None) -> bool:
        return (
            self._last_game is not None
            and game is not None
            and self._last_game.map_name == game.map_name
        )

    def should_update_embed(
        self, message: discord.Message, embed: discord.Embed
    ) -> bool:
        current_embed = message.embeds[0]
        # embed fields indicate that either players are connected or there was an
        # error getting server info, in either case we want to continue updating
        if current_embed.fields or embed.fields:
            return True
        curr_txt = current_embed.description or ""
        new_txt = embed.description or ""
        # ignore the last line that has the updated timestamp embedded, at this
        # point the messages are `no players online` and we only want to update
        # if the map has changed
        return (
            new_txt.rsplit("\n", maxsplit=1)[0] != curr_txt.rsplit("\n", maxsplit=1)[0]
        )


def format_player(p: Player) -> str:
    ping = f"{p.ping:3}ms" if p.ping > 0 else "  0ms"
    player_name = p.clean_name[:SIZE_PLAYER_NAME].ljust(SIZE_PLAYER_NAME)
    return f"{player_name} [{p.kills:3}/{p.deaths:2}/{p.assists:2}] {ping}"


def sort_key_kda(p: Player) -> tuple[int, int, int, str]:
    return p.kills, p.deaths * -1, p.assists, p.name


def player_score_display(players: list[Player]) -> str | None:
    if not players:
        return None

    kda_sort = sorted(players, key=sort_key_kda, reverse=True)
    return "```\n" + "\n".join([format_player(p) for p in kda_sort]) + "\n```"


def add_player_fields(embed: discord.Embed, server: Game) -> None:
    team_r = player_score_display(server.team_red)
    team_b = player_score_display(server.team_blue)
    if team_r or team_b:
        embed.add_field(
            name=f"Red ({server.score_red})",
            value=team_r or EMBED_NO_PLAYERS,
            inline=False,
        )
        embed.add_field(
            name=f"Blue ({server.score_blue})",
            value=team_b or EMBED_NO_PLAYERS,
            inline=False,
        )
    elif team_free := player_score_display(server.team_free):
        embed.add_field(name="Players", value=team_free, inline=False)

    if server.spectators:
        specs = sorted(server.spectators, key=SORT_KEY_NAME)
        value = "```\n" + "\n".join(p.clean_name for p in specs) + "\n```"
        embed.add_field(name="Spectators", value=value, inline=False)


def add_mapinfo_field(embed: discord.Embed, game: Game) -> None:
    player_count = len(game.players)
    info = f"{game.time} / Total:{player_count:2}"
    if (spec_count := len(game.spectators)) != player_count:
        if (free_count := len(game.team_free)) > 0:
            if spec_count:
                info += f"  F:{free_count:2}"
        else:
            info += f"  R:{len(game.team_red):2}  B:{len(game.team_blue):2}"
        if spec_count:
            info += f"  S:{spec_count:2}"
    info = f"```\n{info}\n```"
    embed.add_field(name="Game Time / Player Counts", value=info, inline=False)


def create_server_embed(
    game: Game | None,
    next_map: str | None,
    title: str,
    game_host: str | None = None,
    game_port: int | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title)

    last_updated = f"updated <t:{int(time.time())}:R>"

    if game_host:
        if not game_port:
            game_port = 27960
        connect_info = f"```/connect {game_host}:{game_port}```"
    else:
        connect_info = ""

    if game:
        embed.description = f"```\n{game.map_name}\n```"
        if game.players:
            embed.colour = discord.Colour.green()
            if next_map:
                embed.add_field(
                    name="Next Map", value=f"```{next_map}```", inline=False
                )
            add_mapinfo_field(embed, game)
            add_player_fields(embed, game)
            embed.add_field(name="", value=connect_info, inline=False)
            embed.add_field(name="", value=last_updated, inline=False)
        else:
            embed.colour = discord.Colour.light_grey()
            # do not add a field to make updating based on description only
            if next_map:
                embed.description += (
                    f"\n**Next Map**\n```{next_map:{len(EMBED_NO_PLAYERS)}}```"
                )
            embed.description += "\n*No players online*\n"
            embed.description += f"\n{connect_info}"
            embed.description += f"\n{last_updated}"
    else:
        embed.colour = discord.Colour.red()
        embed.description = "*Unable to retrieve server information*"
        # add last updated as a field to trigger updating
        embed.add_field(name="", value=last_updated, inline=False)

    return embed


def same_map_and_specs(s1: Game | None, s2: Game | None) -> bool:
    """
    Used to determine if both game instances reference the same map and
    have the same spectators with no current players. In case we can skip
    updating the embedded message.
    """
    return (
        s1 is not None
        and s2 is not None
        and s1.map_name == s2.map_name
        and len(s1.players) == len(s2.players)
        and len(s1.spectators) == len(s1.players)
        and len(s2.spectators) == len(s2.players)
        and sorted(s1.spectators, key=SORT_KEY_NAME)
        == sorted(s2.spectators, key=SORT_KEY_NAME)
    )
