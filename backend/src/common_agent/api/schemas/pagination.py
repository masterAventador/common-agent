from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CursorPageResponse[ItemResponse](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ItemResponse]
    next_cursor: str | None


__all__ = ["CursorPageResponse"]
