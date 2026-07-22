from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile

from common_agent.api.routers.tools import _read_openapi_upload
from common_agent.api.schemas.tools import ManagedHttpOpenApiDraftResponse
from common_agent.tools.openapi_import import OPENAPI_MAX_FILE_BYTES, OpenApiDocumentError


def test_openapi_upload_reader_closes_framework_file_after_bounded_read() -> None:
    upload = UploadFile(file=BytesIO(b'{"openapi":"3.0.3"}'), filename="openapi.json")

    content = asyncio.run(_read_openapi_upload(upload))

    assert content == b'{"openapi":"3.0.3"}'
    assert upload.file.closed is True


def test_openapi_upload_reader_rejects_oversize_and_still_closes_file() -> None:
    upload = UploadFile(
        file=BytesIO(b"x" * (OPENAPI_MAX_FILE_BYTES + 1)),
        filename="large.yaml",
    )

    with pytest.raises(OpenApiDocumentError) as captured:
        asyncio.run(_read_openapi_upload(upload))

    assert captured.value.code == "openapi_file_too_large"
    assert upload.file.closed is True


def test_openapi_preview_response_keeps_missing_description_editable() -> None:
    draft = ManagedHttpOpenApiDraftResponse(
        operation_key="GET /orders/{order_id}",
        remote_name="orders.get",
        display_name="orders.get",
        description="",
        input_schema={"type": "object", "properties": {}},
        method="GET",
        path_template="/orders/{order_id}",
        parameter_bindings=[],
        timeout_seconds=30,
        response_json_pointer=None,
        enabled=True,
        issues=["能力缺少说明"],
    )

    assert draft.description == ""
    assert draft.issues == ["能力缺少说明"]
