from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[4] / "alembic.ini"


def upgrade_database(database_url: str) -> None:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
