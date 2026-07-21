import pytest

from common_agent.bootstrap import AuditSettings, ConfigurationError


def test_audit_settings_defaults_and_bounds() -> None:
    assert AuditSettings.from_mapping({}) == AuditSettings(
        retention_days=365,
        maximum_events_per_scope=1_000_000,
    )

    with pytest.raises(ConfigurationError, match="RETENTION_DAYS"):
        AuditSettings.from_mapping({"COMMON_AGENT_AUDIT_RETENTION_DAYS": "29"})
    with pytest.raises(ConfigurationError, match="MAX_EVENTS_PER_SCOPE"):
        AuditSettings.from_mapping({"COMMON_AGENT_AUDIT_MAX_EVENTS_PER_SCOPE": "10000001"})
