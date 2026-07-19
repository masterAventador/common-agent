from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import UploadFile

from common_agent.api.routers.knowledge import _read_upload


def test_upload_reader_closes_framework_file_after_reading() -> None:
    upload = UploadFile(file=BytesIO(b"knowledge"), filename="knowledge.txt")

    content = asyncio.run(_read_upload(upload))

    assert content == b"knowledge"
    assert upload.file.closed is True
