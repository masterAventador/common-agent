from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from common_agent.adapters.backup.archive import (
    BackupArchiveError,
    inspect_archive,
    main,
    pack_directory,
    restore_archive,
)


def _write_key(path: Path, value: bytes = b"a" * 32) -> None:
    path.write_text(value.hex() + "\n", encoding="ascii")
    path.chmod(0o600)


def _source_tree(root: Path) -> None:
    (root / "platform").mkdir(parents=True)
    (root / "ragflow").mkdir()
    (root / "config").mkdir()
    (root / "platform/mysql.sql").write_text(
        "INSERT INTO employees VALUES ('recovery-marker');\n",
        encoding="utf-8",
    )
    (root / "platform/ragflow-external-references.json").write_text(
        '[{"tenant_id":"tenant-recovery","knowledge_base_id":"kb-recovery"}]\n',
        encoding="utf-8",
    )
    (root / "ragflow/minio-data.tar").write_bytes(b"uploaded-object-recovery-marker")
    (root / "config/deployment.env").write_text(
        "COMMON_AGENT_INTEGRATION_MODE=real\n",
        encoding="utf-8",
    )


def _metadata() -> dict[str, object]:
    return {
        "archive_id": "common-agent-20260721T120000Z",
        "created_at": "2026-07-21T12:00:00Z",
        "source_revision": "f743a64ef77ddca19143eaaf16e758330838ecdb",
        "policy": {
            "rpo_hours": 24,
            "rto_minutes": 120,
            "retention_days": 30,
            "minimum_generations": 7,
        },
    }


def test_encrypted_archive_round_trip_has_authenticated_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_tree(source)
    key_file = tmp_path / "backup.key"
    _write_key(key_file)
    archive = tmp_path / "backup.cab"

    manifest = pack_directory(source, archive, key_file, metadata=_metadata())

    assert archive.read_bytes().startswith(b"COMMON_AGENT_BACKUP\0")
    assert b"recovery-marker" not in archive.read_bytes()
    assert manifest["format_version"] == 1
    assert manifest["encryption"] == "AES-256-GCM"
    assert manifest["metadata"] == _metadata()
    assert {item["path"] for item in manifest["files"]} == {
        "config/deployment.env",
        "platform/mysql.sql",
        "platform/ragflow-external-references.json",
        "ragflow/minio-data.tar",
    }

    assert inspect_archive(archive, key_file) == manifest
    destination = tmp_path / "restored"
    restored_manifest = restore_archive(archive, destination, key_file)

    assert restored_manifest == manifest
    assert (
        (destination / "platform/mysql.sql")
        .read_text(encoding="utf-8")
        .endswith("recovery-marker');\n")
    )
    assert not (destination / "manifest.json").exists()


@pytest.mark.parametrize("failure", ["wrong-key", "tamper"])
def test_archive_authentication_fails_closed_without_extracting(
    tmp_path: Path,
    failure: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_tree(source)
    key_file = tmp_path / "backup.key"
    _write_key(key_file)
    archive = tmp_path / "backup.cab"
    pack_directory(source, archive, key_file, metadata=_metadata())

    if failure == "wrong-key":
        _write_key(key_file, b"b" * 32)
    else:
        payload = bytearray(archive.read_bytes())
        payload[-24] ^= 1
        archive.write_bytes(payload)

    destination = tmp_path / "restored"
    with pytest.raises(BackupArchiveError, match="authentication failed"):
        restore_archive(archive, destination, key_file)

    assert not destination.exists()


def test_pack_rejects_unsafe_source_and_key_permissions(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "plain.txt").write_text("payload", encoding="utf-8")
    key_file = tmp_path / "backup.key"
    _write_key(key_file)
    key_file.chmod(0o644)

    with pytest.raises(BackupArchiveError, match="0600"):
        pack_directory(source, tmp_path / "permissions.cab", key_file, metadata=_metadata())

    key_file.chmod(0o600)
    os.symlink(source / "plain.txt", source / "linked.txt")
    with pytest.raises(BackupArchiveError, match="symbolic links"):
        pack_directory(source, tmp_path / "symlink.cab", key_file, metadata=_metadata())


def test_restore_requires_an_empty_new_destination_and_valid_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_tree(source)
    key_file = tmp_path / "backup.key"
    _write_key(key_file)
    archive = tmp_path / "backup.cab"
    pack_directory(source, archive, key_file, metadata=_metadata())

    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(BackupArchiveError, match="empty new destination"):
        restore_archive(archive, destination, key_file)
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"

    unpacked = tmp_path / "unpacked"
    restore_archive(archive, unpacked, key_file)
    serialized = json.dumps(inspect_archive(archive, key_file), sort_keys=True)
    assert "BAILIAN_API_KEY" not in serialized


def test_archive_cli_packs_inspects_and_restores(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_tree(source)
    key_file = tmp_path / "backup.key"
    _write_key(key_file)
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text(json.dumps(_metadata()), encoding="utf-8")
    archive = tmp_path / "backup.cab"

    assert (
        main(
            [
                "pack",
                "--source",
                str(source),
                "--output",
                str(archive),
                "--key-file",
                str(key_file),
                "--metadata-file",
                str(metadata_file),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["format_version"] == 1
    assert main(["inspect", "--input", str(archive), "--key-file", str(key_file)]) == 0
    assert json.loads(capsys.readouterr().out)["encryption"] == "AES-256-GCM"
    destination = tmp_path / "restored"
    assert (
        main(
            [
                "restore",
                "--input",
                str(archive),
                "--destination",
                str(destination),
                "--key-file",
                str(key_file),
            ]
        )
        == 0
    )
    assert (destination / "ragflow/minio-data.tar").read_bytes().endswith(b"recovery-marker")


def test_invalid_inputs_fail_closed_with_stable_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_file = tmp_path / "backup.key"
    _write_key(key_file)
    empty_source = tmp_path / "empty"
    empty_source.mkdir()
    with pytest.raises(BackupArchiveError, match="at least one file"):
        pack_directory(empty_source, tmp_path / "empty.cab", key_file, metadata=_metadata())

    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.txt").write_text("payload", encoding="utf-8")
    existing = tmp_path / "existing.cab"
    existing.write_bytes(b"keep")
    with pytest.raises(BackupArchiveError, match="already exists"):
        pack_directory(source, existing, key_file, metadata=_metadata())
    with pytest.raises(BackupArchiveError, match="JSON serializable"):
        pack_directory(
            source,
            tmp_path / "metadata.cab",
            key_file,
            metadata={"invalid": object()},
        )

    unsupported = tmp_path / "unsupported.cab"
    unsupported.write_bytes(b"not-a-common-agent-backup")
    with pytest.raises(BackupArchiveError, match="format is not supported"):
        inspect_archive(unsupported, key_file)
    assert main(["inspect", "--input", str(unsupported), "--key-file", str(key_file)]) == 1
    assert "backup_archive_error" in capsys.readouterr().err
