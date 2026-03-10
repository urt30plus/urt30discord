# |30+| UrT Discord Bot

## Status

The Discord updaters that post mapcycle and player updates to our `#mapcycle`
channel in our Discord.

## Requirements

- Urban Terror 4.3.4
- Requires Python 3.14

## Configuration

The bot uses a TOML configuration file that can be passed
as the first argument to the program. See `etc/urt30discord.toml`
for the settings.

## Running

The project uses the [uv](https://docs.astral.sh/uv/) tool for
dependency management.

### Run the module

    uv run -m urt30discord

To set up as a `systemd` service, see the sample `etc/systemd/urt30discord.service` file.

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
