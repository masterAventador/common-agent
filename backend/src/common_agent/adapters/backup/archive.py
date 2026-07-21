from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import stat
import struct
import sys
import tarfile
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Literal, TypedDict, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_MAGIC = b"COMMON_AGENT_BACKUP\0"
_HEADER_LENGTH = struct.Struct(">I")
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024
_MANIFEST_NAME = "manifest.json"
_FORMAT_VERSION = 1
_ENCRYPTION = "AES-256-GCM"


class BackupArchiveError(RuntimeError):
    """Raised when a backup cannot be safely packed, authenticated, or restored."""


class ManifestFile(TypedDict):
    path: str
    size_bytes: int
    sha256: str


class BackupManifest(TypedDict):
    format_version: Literal[1]
    encryption: Literal["AES-256-GCM"]
    metadata: dict[str, object]
    files: list[ManifestFile]


def pack_directory(
    source: Path,
    output: Path,
    key_file: Path,
    *,
    metadata: Mapping[str, object],
) -> BackupManifest:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir() or source.is_symlink():
        raise BackupArchiveError("backup source must be a regular directory")
    if output.exists():
        raise BackupArchiveError("backup output already exists")
    if not output.parent.is_dir():
        raise BackupArchiveError("backup output parent must exist")

    key = _read_key(key_file)
    files = _source_files(source)
    normalized_metadata = _normalize_metadata(metadata)
    manifest: BackupManifest = {
        "format_version": 1,
        "encryption": "AES-256-GCM",
        "metadata": normalized_metadata,
        "files": [
            {
                "path": path.relative_to(source).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in files
        ],
    }

    plain_path = _temporary_path(output.parent, ".tar.gz")
    encrypted_path = _temporary_path(output.parent, ".cab")
    try:
        _write_plain_archive(source, files, manifest, plain_path)
        _encrypt_file(plain_path, encrypted_path, key)
        os.chmod(encrypted_path, 0o600)
        os.replace(encrypted_path, output)
    finally:
        plain_path.unlink(missing_ok=True)
        encrypted_path.unlink(missing_ok=True)
    return manifest


def inspect_archive(archive: Path, key_file: Path) -> BackupManifest:
    archive = archive.resolve()
    key = _read_key(key_file)
    with _decrypted_archive(archive, key) as plain_path:
        return _validate_plain_archive(plain_path)


def restore_archive(archive: Path, destination: Path, key_file: Path) -> BackupManifest:
    archive = archive.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise BackupArchiveError("restore requires an empty new destination")
    if not destination.parent.is_dir():
        raise BackupArchiveError("restore destination parent must exist")

    key = _read_key(key_file)
    with _decrypted_archive(archive, key) as plain_path:
        manifest = _validate_plain_archive(plain_path)
        temporary_destination = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            with tarfile.open(plain_path, "r:gz") as bundle:
                for member in bundle.getmembers():
                    if member.name == _MANIFEST_NAME:
                        continue
                    relative = _safe_member_path(member)
                    target = temporary_destination.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    extracted = bundle.extractfile(member)
                    if extracted is None:
                        raise BackupArchiveError("backup contains an unreadable file")
                    with target.open("xb") as output_file:
                        while chunk := extracted.read(_CHUNK_BYTES):
                            output_file.write(chunk)
                    target.chmod(0o600)
            os.replace(temporary_destination, destination)
        finally:
            _remove_empty_tree(temporary_destination)
        return manifest


def _source_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for candidate in sorted(source.rglob("*")):
        if candidate.is_symlink():
            raise BackupArchiveError("backup source must not contain symbolic links")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise BackupArchiveError("backup source must contain only regular files")
        relative = candidate.relative_to(source)
        if relative.as_posix() == _MANIFEST_NAME:
            raise BackupArchiveError("backup source must not provide manifest.json")
        files.append(candidate)
    if not files:
        raise BackupArchiveError("backup source must contain at least one file")
    return files


def _normalize_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    try:
        serialized = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(serialized)
    except (TypeError, ValueError) as error:
        raise BackupArchiveError("backup metadata must be JSON serializable") from error
    if not isinstance(decoded, dict):
        raise BackupArchiveError("backup metadata must be an object")
    return cast(dict[str, object], decoded)


def _write_plain_archive(
    source: Path,
    files: list[Path],
    manifest: BackupManifest,
    output: Path,
) -> None:
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        for path in files:
            relative = path.relative_to(source).as_posix()
            info = bundle.gettarinfo(str(path), arcname=relative)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o600
            with path.open("rb") as source_file:
                bundle.addfile(info, source_file)
        manifest_info = tarfile.TarInfo(_MANIFEST_NAME)
        manifest_info.size = len(manifest_bytes)
        manifest_info.mode = 0o600
        manifest_info.mtime = 0
        bundle.addfile(manifest_info, io.BytesIO(manifest_bytes))


def _encrypt_file(source: Path, destination: Path, key: bytes) -> None:
    nonce = os.urandom(12)
    header = json.dumps(
        {
            "algorithm": _ENCRYPTION,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "version": _FORMAT_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    prefix = _MAGIC + _HEADER_LENGTH.pack(len(header)) + header
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    with source.open("rb") as source_file, destination.open("xb") as output_file:
        output_file.write(prefix)
        while chunk := source_file.read(_CHUNK_BYTES):
            output_file.write(encryptor.update(chunk))
        output_file.write(encryptor.finalize())
        output_file.write(encryptor.tag)
        output_file.flush()
        os.fsync(output_file.fileno())


@contextmanager
def _decrypted_archive(archive: Path, key: bytes) -> Iterator[Path]:
    if not archive.is_file() or archive.is_symlink():
        raise BackupArchiveError("backup archive must be a regular file")
    plain_path = _temporary_path(archive.parent, ".tar.gz")
    try:
        with archive.open("rb") as source_file:
            magic = source_file.read(len(_MAGIC))
            if magic != _MAGIC:
                raise BackupArchiveError("backup format is not supported")
            raw_header_length = source_file.read(_HEADER_LENGTH.size)
            if len(raw_header_length) != _HEADER_LENGTH.size:
                raise BackupArchiveError("backup header is truncated")
            header_length = _HEADER_LENGTH.unpack(raw_header_length)[0]
            if not 1 <= header_length <= 4096:
                raise BackupArchiveError("backup header is invalid")
            header_bytes = source_file.read(header_length)
            if len(header_bytes) != header_length:
                raise BackupArchiveError("backup header is truncated")
            nonce = _parse_header(header_bytes)
            ciphertext_start = source_file.tell()
            ciphertext_bytes = archive.stat().st_size - ciphertext_start - _TAG_BYTES
            if ciphertext_bytes < 1:
                raise BackupArchiveError("backup payload is truncated")
            source_file.seek(-_TAG_BYTES, os.SEEK_END)
            tag = source_file.read(_TAG_BYTES)
            source_file.seek(ciphertext_start)
            prefix = magic + raw_header_length + header_bytes
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(prefix)
            remaining = ciphertext_bytes
            try:
                with plain_path.open("xb") as output_file:
                    while remaining:
                        chunk = source_file.read(min(_CHUNK_BYTES, remaining))
                        if not chunk:
                            raise BackupArchiveError("backup payload is truncated")
                        remaining -= len(chunk)
                        output_file.write(decryptor.update(chunk))
                    output_file.write(decryptor.finalize())
            except InvalidTag as error:
                raise BackupArchiveError("backup authentication failed") from error
        yield plain_path
    finally:
        plain_path.unlink(missing_ok=True)


def _parse_header(header_bytes: bytes) -> bytes:
    try:
        header = json.loads(header_bytes)
        if not isinstance(header, dict):
            raise ValueError
        if header.get("version") != _FORMAT_VERSION or header.get("algorithm") != _ENCRYPTION:
            raise ValueError
        nonce = base64.b64decode(header["nonce"], validate=True)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise BackupArchiveError("backup header is invalid") from error
    if len(nonce) != 12:
        raise BackupArchiveError("backup header is invalid")
    return nonce


def _validate_plain_archive(path: Path) -> BackupManifest:
    try:
        with tarfile.open(path, "r:gz") as bundle:
            members = bundle.getmembers()
            names: set[str] = set()
            for member in members:
                _safe_member_path(member)
                if member.name in names:
                    raise BackupArchiveError("backup contains duplicate paths")
                names.add(member.name)
            if _MANIFEST_NAME not in names:
                raise BackupArchiveError("backup manifest is missing")
            manifest_file = bundle.extractfile(_MANIFEST_NAME)
            if manifest_file is None:
                raise BackupArchiveError("backup manifest is unreadable")
            manifest = _parse_manifest(manifest_file.read())
            expected_paths = {item["path"] for item in manifest["files"]}
            if names != expected_paths | {_MANIFEST_NAME}:
                raise BackupArchiveError("backup manifest does not match archive paths")
            expected = {item["path"]: item for item in manifest["files"]}
            for member in members:
                if member.name == _MANIFEST_NAME:
                    continue
                if member.size != expected[member.name]["size_bytes"]:
                    raise BackupArchiveError("backup file size does not match manifest")
                extracted = bundle.extractfile(member)
                if extracted is None:
                    raise BackupArchiveError("backup contains an unreadable file")
                digest = hashlib.sha256()
                while chunk := extracted.read(_CHUNK_BYTES):
                    digest.update(chunk)
                if digest.hexdigest() != expected[member.name]["sha256"]:
                    raise BackupArchiveError("backup checksum does not match manifest")
            return manifest
    except (tarfile.TarError, OSError) as error:
        raise BackupArchiveError("backup payload is not a valid archive") from error


def _parse_manifest(payload: bytes) -> BackupManifest:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupArchiveError("backup manifest is invalid") from error
    if not isinstance(raw, dict):
        raise BackupArchiveError("backup manifest is invalid")
    if raw.get("format_version") != 1 or raw.get("encryption") != _ENCRYPTION:
        raise BackupArchiveError("backup manifest version is not supported")
    metadata = raw.get("metadata")
    files = raw.get("files")
    if not isinstance(metadata, dict) or not isinstance(files, list) or not files:
        raise BackupArchiveError("backup manifest is invalid")
    validated_files: list[ManifestFile] = []
    for item in files:
        if not isinstance(item, dict):
            raise BackupArchiveError("backup manifest is invalid")
        path = item.get("path")
        size_bytes = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise BackupArchiveError("backup manifest is invalid")
        _safe_relative_path(path)
        validated_files.append({"path": path, "size_bytes": size_bytes, "sha256": digest})
    return {
        "format_version": 1,
        "encryption": "AES-256-GCM",
        "metadata": cast(dict[str, object], metadata),
        "files": validated_files,
    }


def _safe_member_path(member: tarfile.TarInfo) -> PurePosixPath:
    if not member.isfile():
        raise BackupArchiveError("backup archive may contain only regular files")
    return _safe_relative_path(member.name)


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise BackupArchiveError("backup contains an unsafe path")
    return path


def _read_key(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise BackupArchiveError("backup key must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise BackupArchiveError("backup key file permissions must be 0600")
    try:
        key = bytes.fromhex(path.read_text(encoding="ascii").strip())
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise BackupArchiveError("backup key must contain 64 hexadecimal characters") from error
    if len(key) != 32:
        raise BackupArchiveError("backup key must contain 64 hexadecimal characters")
    return key


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        while chunk := source_file.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_path(parent: Path, suffix: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=".common-agent-backup.", suffix=suffix, dir=parent
    )
    os.close(descriptor)
    path = Path(raw_path)
    path.unlink()
    return path


def _remove_empty_tree(root: Path) -> None:
    if not root.exists():
        return
    for candidate in sorted(root.rglob("*"), reverse=True):
        if candidate.is_file():
            candidate.unlink()
        elif candidate.is_dir():
            candidate.rmdir()
    root.rmdir()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Common Agent authenticated backup archive")
    subparsers = parser.add_subparsers(dest="action", required=True)
    pack = subparsers.add_parser("pack")
    pack.add_argument("--source", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--key-file", type=Path, required=True)
    pack.add_argument("--metadata-file", type=Path, required=True)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--key-file", type=Path, required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--key-file", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    values = parser.parse_args(arguments)
    try:
        if values.action == "pack":
            metadata = json.loads(values.metadata_file.read_text(encoding="utf-8"))
            manifest = pack_directory(
                values.source,
                values.output,
                values.key_file,
                metadata=metadata,
            )
        elif values.action == "inspect":
            manifest = inspect_archive(values.input, values.key_file)
        else:
            manifest = restore_archive(values.input, values.destination, values.key_file)
    except (BackupArchiveError, OSError, json.JSONDecodeError) as error:
        print(f"backup_archive_error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
