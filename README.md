# |30+| UrT Discord Bot

## Status

Discord updaters that post mapcycle and game updates to our `#mapcycle`
channel in our Discord.

## Requirements

- Urban Terror 4.3.4
- [uv](https://docs.astral.sh/uv/)

## Configuration

The bot uses a TOML configuration file that can be passed
as the first argument to the program or by setting an OS
environment variable named `URT30DISCORD_CONFIG_FILE` to
the full path to the config file.

See below for an example file. Those commented as required
must be provided in the config file. The other values are
defaults and only need to be provided if you want to override
those values.

```toml
[bot]
user = "mybot#1234"  # required
token = "xxxx"  # required
server_id = 123456789  # required
channel_id = 987654321  # required
log_level = "INFO"
log_level_root = "WARNING"
log_level_discord = "ERROR"

[rcon]
log_level = "INFO"
host = "127.0.0.1"
port = 27960
password = "supersekret"  # required
recv_timeout = 0.25

[gameinfo]
enabled = true
log_level = "INFO"
game_host = "game.urt-30plus.org"  # required
embed_title = "Current Map"
delay = 5.0
delay_no_updates = 60.0
timeout = 5.0

[mapcycle]
enabled = true
log_level = "INFO"
embed_title = "Map Cycle"
delay = 3600.0
timeout = 30.0
file = '/full/path/to/mapcycle.txt'  # required
```

## Running

The project uses the [uv](https://docs.astral.sh/uv/) tool for
dependency management.

### Run the module

    uv run -m urt30discord

To set up as a `systemd` service, see the sample service file below.

```systemd
[Unit]
Description=UrT 4.3 Discord Bot
After=urt43.service
StartLimitIntervalSec=120
StartLimitBurst=20

[Install]
WantedBy=multi-user.target

[Service]
Type=exec
CPUAffinity=1-2
Environment=UV_COMPILE_BYTECODE=1 UV_NO_DEV=1 UV_FROZEN=1 PYTHONUNBUFFERED=1
WorkingDirectory=%h/urt30discord
ExecStartPre=-git pull
ExecStartPre=-%h/.local/bin/uv sync
ExecStart=%h/urt30discord/.venv/bin/python -m urt30discord %h/.config/urt30discord.toml
Restart=on-failure
RestartSec=5
```

## Developing

### Installation

The following will create a `.venv` directory and install both the
runtime and development dependencies:

    uv sync --upgrade

### Install pre-commit

Recommend installing as a tool:

    uv tool install pre-commit

### Install the pre-commit hooks

    pre-commit install

### Set the appropriate Environment Variables

Create a `.env` file in the project root with the appropriate settings

### Run the checks

    bash run_checks.sh

### Reloading

To run the bot and have it reload when changes are made, use the following
command:

    watchfiles urt30discord.__main__.main
