import uvicorn

from common_agent.bootstrap import ApiSettings


def main() -> None:
    settings = ApiSettings.from_env()
    uvicorn.run(
        "common_agent.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
