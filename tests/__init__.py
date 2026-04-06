import os
from pathlib import Path

TEST_CONFIG = Path(__file__).parent / "test_config.toml"

os.environ["URT30DISCORD_CONFIG_FILE"] = str(TEST_CONFIG)
