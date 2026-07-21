import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_PLATFORM_DATABASE_URL",
    (
        "mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/"
        "common_agent_test?charset=utf8mb4"
    ),
)
