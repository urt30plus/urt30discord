"""
Bot settings and configuration.
"""

import datetime
import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, DirectoryPath, Field, FilePath, HttpUrl

type DiscordUser = Annotated[str, Field(pattern=r"^.*#\d+$")]
type Snowflake = Annotated[int, Field(gt=0)]

PACKAGE_ROOT = Path(__file__).parent
PROJECT_ROOT = PACKAGE_ROOT.parent


class BotSettings(BaseModel, frozen=True):
    user: DiscordUser
    token: Annotated[str, Field(repr=False)]
    server_id: Snowflake
    channel_id: Snowflake
    log_level: str = "INFO"
    log_level_root: str = "WARNING"
    log_level_discord: str = "ERROR"


class RconSettings(BaseModel, frozen=True):
    public_ip_or_dns: str
    private_ip: str = "127.0.0.1"
    port: Annotated[int, Field(ge=0, le=65535)] = 27960
    password: Annotated[str, Field(repr=False)]
    recv_timeout: float = 0.25
    log_level: str = "INFO"


class BaseUpdaterSettings(BaseModel, frozen=True):
    enabled: bool = True
    log_level: str = "INFO"
    embed_title: str = "Embed Title"
    delay: float = 5.0
    delay_no_updates: float = 60.0
    timeout: float = 5.0


class GameInfoSettings(BaseUpdaterSettings, frozen=True):
    embed_title: str = "Current Map"


class MapCycleSettings(BaseUpdaterSettings, frozen=True):
    embed_title: str = "Map Cycle"
    delay: float = 300.0
    delay_no_updates: float = 3600.0
    timeout: float = 30.0
    file: FilePath


class MapFilesSettings(BaseModel, frozen=True):
    path: DirectoryPath
    downloads_url: HttpUrl
    sftp_url: str | None = None


if "URT30DISCORD_CONFIG_FILE" in os.environ:
    _config_file = Path(os.environ["URT30DISCORD_CONFIG_FILE"])
elif len(sys.argv) > 1:
    _config_file = Path(sys.argv[1])
else:
    raise RuntimeError("missing_config_file")

with _config_file.open(mode="rb") as fp:
    _config = tomllib.load(fp)


bot = BotSettings(**_config["bot"])
rcon = RconSettings(**_config["rcon"])
gameinfo = GameInfoSettings(**_config["gameinfo"])
mapcycle = MapCycleSettings(**_config["mapcycle"])
mapfiles = MapFilesSettings(**_config["mapfiles"])

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s:%(funcName)s %(message)s"
)
logging.getLogger().setLevel(bot.log_level_root)
logging.getLogger("discord").setLevel(bot.log_level_discord)
logging.getLogger("urt30arcon").setLevel(rcon.log_level)
logging.getLogger("urt30discord").setLevel(bot.log_level)
logging.getLogger("urt30discord.gameinfo").setLevel(gameinfo.log_level)
logging.getLogger("urt30discord.mapcycle").setLevel(mapcycle.log_level)

STARTED_AT = datetime.datetime.now(tz=datetime.UTC)
