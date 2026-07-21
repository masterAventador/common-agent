#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_VERSIONED_SECRET = REPOSITORY_ROOT / "backend/.env.demo"
LIVE_CREDENTIAL_PATTERN = re.compile(rb"(?<![A-Za-z0-9])sk-(?:ws-)?[A-Za-z0-9._-]{32,}")
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
TRUSTED_LOCAL_SECRET_ROOT = REPOSITORY_ROOT / ".local/secrets"
LOCAL_ARTIFACT_SUFFIXES = {".html", ".js", ".json", ".jsonl", ".log", ".map", ".trace"}


def _git(*arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _fingerprints(payload: bytes) -> set[str]:
    return {
        hashlib.sha256(match.group(0)).hexdigest()
        for match in LIVE_CREDENTIAL_PATTERN.finditer(payload)
    }


def _source_files() -> tuple[Path, ...]:
    return tuple(
        REPOSITORY_ROOT / raw_path.decode("utf-8")
        for raw_path in _git(
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ).split(b"\0")
        if raw_path
    )


def _artifact_files() -> tuple[Path, ...]:
    roots = (
        REPOSITORY_ROOT / ".local",
        REPOSITORY_ROOT / "backend/dist",
        REPOSITORY_ROOT / "frontend/dist",
        REPOSITORY_ROOT / "frontend/playwright-report",
        REPOSITORY_ROOT / "frontend/test-results",
    )
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            if root.name == ".local" and candidate.suffix.lower() not in LOCAL_ARTIFACT_SUFFIXES:
                continue
            try:
                candidate.relative_to(TRUSTED_LOCAL_SECRET_ROOT)
            except ValueError:
                pass
            else:
                continue
            try:
                if candidate.stat().st_size <= MAX_ARTIFACT_BYTES:
                    files.append(candidate)
            except OSError:
                continue
    return tuple(files)


def _scan_files(paths: tuple[Path, ...], *, category: str) -> list[str]:
    failures: list[str] = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            contains_credential = _file_contains_credential(path)
        except (OSError, tarfile.TarError, zipfile.BadZipFile):
            failures.append(f"{category}:unreadable")
            continue
        if contains_credential:
            failures.append(f"{category}:{path.relative_to(REPOSITORY_ROOT)}")
    return failures


def _file_contains_credential(path: Path) -> bool:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return any(
                member.file_size <= MAX_ARTIFACT_BYTES
                and bool(_fingerprints(archive.read(member)))
                for member in archive.infolist()
                if not member.is_dir()
            )
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or member.size > MAX_ARTIFACT_BYTES:
                    continue
                extracted = archive.extractfile(member)
                if extracted is not None and _fingerprints(extracted.read()):
                    return True
        return False
    return bool(_fingerprints(path.read_bytes()))


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        _self_test()
        print("Secret 扫描器自校验通过")
        return 0
    if sys.argv[1:]:
        print("用法: scripts/scan-secrets.py [--self-test]", file=sys.stderr)
        return 2

    source_files = _source_files()
    artifact_files = _artifact_files()
    try:
        authorized_fingerprints = _fingerprints(AUTHORIZED_VERSIONED_SECRET.read_bytes())
    except OSError:
        authorized_fingerprints = set()
    failures = [] if len(authorized_fingerprints) == 1 else ["authorized-source:invalid"]
    failures.extend(
        _scan_files(
            tuple(path for path in source_files if path != AUTHORIZED_VERSIONED_SECRET),
            category="source",
        )
    )
    failures.extend(_scan_files(artifact_files, category="artifact"))

    history_fingerprints = _fingerprints(
        _git(
            "log",
            "-p",
            "--all",
            "--full-history",
            "--no-ext-diff",
            "--",
            ".",
            ":!third_party/ragflow",
        )
    )
    unknown_history = history_fingerprints - authorized_fingerprints
    failures.extend(
        f"history:unauthorized:{fingerprint}" for fingerprint in sorted(unknown_history)
    )

    if failures:
        print("Secret 治理扫描失败：", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        "Secret 治理扫描通过："
        f"sources={len(source_files)}, "
        f"artifacts={len(artifact_files)}, "
        f"authorized_history_fingerprints={len(history_fingerprints)}"
    )
    return 0


def _self_test() -> None:
    synthetic_secret = b"sk-ws-" + b"A" * 64
    synthetic_fingerprint = hashlib.sha256(synthetic_secret).hexdigest()
    assert _fingerprints(b"prefix " + synthetic_secret + b" suffix") == {
        synthetic_fingerprint
    }
    assert not _fingerprints(b"sk-invalid-test-fixture")

    with tempfile.TemporaryDirectory(prefix="common-agent-secret-scan-") as raw_root:
        root = Path(raw_root)
        plain = root / "plain.txt"
        plain.write_bytes(synthetic_secret)
        assert _file_contains_credential(plain)

        wheel = root / "fixture.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("package/config.txt", synthetic_secret)
        assert _file_contains_credential(wheel)

        payload = root / "payload.txt"
        payload.write_bytes(synthetic_secret)
        source_archive = root / "fixture.tar.gz"
        with tarfile.open(source_archive, "w:gz") as archive:
            archive.add(payload, arcname="package/config.txt")
        assert _file_contains_credential(source_archive)


if __name__ == "__main__":
    raise SystemExit(main())
