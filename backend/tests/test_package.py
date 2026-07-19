from importlib.metadata import version

import common_agent


def test_package_exports_distribution_version() -> None:
    assert common_agent.__version__ == version("common-agent-backend")
