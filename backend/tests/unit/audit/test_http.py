from common_agent.api.app import create_app


def test_observability_wraps_the_fail_closed_audit_middleware() -> None:
    app = create_app()

    middleware_order = [
        getattr(middleware.kwargs.get("dispatch"), "__name__", None)
        for middleware in app.user_middleware
    ]

    assert middleware_order[:3] == [
        "observe_http_request",
        "audit_http_request",
        "enforce_request_security",
    ]
