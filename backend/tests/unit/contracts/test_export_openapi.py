from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from common_agent.contracts.export_openapi import export_openapi, main


def test_openapi_export_writes_deterministic_api_contract(tmp_path: Path) -> None:
    output = tmp_path / "contracts" / "openapi.json"

    export_openapi(output)

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.")
    assert "/api/v1/managed-mcp-sources" in document["paths"]
    assert output.read_bytes().endswith(b"\n")


def test_openapi_export_cli_uses_requested_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "openapi.json"
    monkeypatch.setattr(sys, "argv", ["export-openapi", "--output", str(output)])

    main()

    assert output.is_file()
