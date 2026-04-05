#!/usr/bin/env bash
set -xe

if [[ -d .venv/bin ]]; then
    export PATH=.venv/bin:$PATH
fi

echo "CI is set to [${CI}]"
if [[ $CI != "true" ]]; then
    pre-commit run --all-files
fi

ty --version
ty check

export URT30DISCORD_CONFIG_FILE=./tests/test_config.toml

pytest
