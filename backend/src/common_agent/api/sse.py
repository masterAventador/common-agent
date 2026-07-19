from common_agent.api.errors import AppError


def resume_sequence(after_sequence: int, last_event_id: str | None) -> int:
    if after_sequence or last_event_id is None:
        return after_sequence
    try:
        parsed = int(last_event_id)
    except ValueError:
        raise AppError("validation_error", "请求参数不合法", 422, False) from None
    if parsed < 0:
        raise AppError("validation_error", "请求参数不合法", 422, False)
    return parsed
