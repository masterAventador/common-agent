from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[4] / "alembic.ini"


def upgrade_database(database_url: str) -> None:
    config = Config(str(_alembic_config_path()))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def _alembic_config_path() -> Path:
    if ALEMBIC_CONFIG_PATH.is_file():
        return ALEMBIC_CONFIG_PATH
    runtime_path = Path.cwd() / "alembic.ini"
    if runtime_path.is_file():
        return runtime_path
    raise RuntimeError("alembic.ini is unavailable in source and runtime paths")
