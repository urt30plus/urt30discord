"""
Bot settings and configuration.
"""

import dataclasses
import logging
import os
import sys
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_CONFIG = PROJECT_ROOT / "etc" / "urt30discord.toml"
TRUE_VALUES = frozenset(["true", "1", "yes", "on", "enable"])


@dataclasses.dataclass(frozen=True)
class BotSettings:
    user: str
    token: str
    server_id: int
    channel_id: int
    log_level: str
    log_level_root: str
    log_level_discord: str

    def __post_init__(self) -> None:
        errors = []
        if not self.user:
            errors.append("user")
        if not self.token:
            errors.append("token")
        if not self.server_id:
            errors.append("server_id")
        if not self.channel_id:
            errors.append("channel_id")
        if errors:
            raise RuntimeError("bot_config_missing", errors)


@dataclasses.dataclass(frozen=True)
class RconSettings:
    host: str
    port: int
    password: str
    recv_timeout: float
    log_level: str

    def __post_init__(self) -> None:
        if not self.password:
            raise RuntimeError("rcon_config_missing", ["password"])


@dataclasses.dataclass(frozen=True)
class GameInfoSettings:
    enabled: bool
    log_level: str
    game_host: str
    embed_title: str
    delay: float
    delay_no_updates: float
    timeout: float


@dataclasses.dataclass(frozen=True)
class MapCycleSettings:
    enabled: bool
    log_level: str
    embed_title: str
    delay: float
    timeout: float
    file: str

    def __post_init__(self) -> None:
        if not self.file:
            raise RuntimeError("gameinfo_config_missing", ["file"])


with DEFAULT_CONFIG.open(mode="rb") as fp:
    _config = tomllib.load(fp)

if "URT30DISCORD_CONFIG_FILE" in os.environ:
    _custom_config_file = Path(os.environ["URT30DISCORD_CONFIG_FILE"])
elif len(sys.argv) > 1:
    _custom_config_file = Path(sys.argv[1])
else:
    _custom_config_file = None

if _custom_config_file:
    with _custom_config_file.open(mode="rb") as fp:
        _custom_config = tomllib.load(fp)
    _config |= _custom_config

bot = BotSettings(**_config["bot"])
rcon = RconSettings(**_config["rcon"])
gameinfo = GameInfoSettings(**_config["gameinfo"])
mapcycle = MapCycleSettings(**_config["mapcycle"])

if not (gameinfo.enabled or mapcycle.enabled):
    # TODO: better message
    raise RuntimeError("no_updaters_enabled")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s:%(funcName)s %(message)s"
)
logging.getLogger().setLevel(bot.log_level_root)
logging.getLogger("discord").setLevel(bot.log_level_discord)
logging.getLogger("urt30arcon").setLevel(rcon.log_level)
logging.getLogger("urt30discord").setLevel(bot.log_level)
logging.getLogger("urt30discord.gameinfo").setLevel(gameinfo.log_level)
logging.getLogger("urt30discord.mapcycle").setLevel(mapcycle.log_level)
