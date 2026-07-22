import importlib
from pathlib import Path
from unittest.mock import Mock

from pytest import MonkeyPatch

import common_agent.adapters.persistence.migrations as migrations


def test_tenant_resource_migration_index_definitions_have_stable_shape() -> None:
    migration = importlib.import_module("migrations.versions.20260721_0014_tenant_resources")

    assert all(len(definition) == 4 for definition in migration._LEGACY_INDEXES)
    assert all(len(definition) == 4 for definition in migration._TENANT_INDEXES)


def test_upgrade_database_uses_runtime_alembic_config_after_wheel_install(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runtime_config = tmp_path / "alembic.ini"
    runtime_config.write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        migrations,
        "ALEMBIC_CONFIG_PATH",
        tmp_path / "installed-wheel" / "alembic.ini",
    )
    upgrade = Mock()
    monkeypatch.setattr("common_agent.adapters.persistence.migrations.command.upgrade", upgrade)

    migrations.upgrade_database("mysql+aiomysql://user:secret@db:3306/common_agent")

    config = upgrade.call_args.args[0]
    assert config.config_file_name == str(runtime_config)
    assert config.attributes["database_url"].endswith("/common_agent")
    assert config.attributes["configure_logger"] is False
    assert upgrade.call_args.args[1] == "head"
