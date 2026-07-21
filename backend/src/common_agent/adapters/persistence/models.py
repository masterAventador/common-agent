from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common_agent.domain.conversation import (
    CITATION_CONTENT_MAX_LENGTH,
    CITATION_DOCUMENT_NAME_MAX_LENGTH,
    CITATION_REFERENCE_MAX_LENGTH,
    CONVERSATION_TITLE_MAX_LENGTH,
    MESSAGE_CONTENT_MAX_LENGTH,
    MESSAGE_ERROR_CODE_MAX_LENGTH,
)
from common_agent.domain.employee import (
    EMPLOYEE_DESCRIPTION_MAX_LENGTH,
    EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    EMPLOYEE_NAME_MAX_LENGTH,
    EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
)
from common_agent.domain.knowledge import (
    KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH,
    KNOWLEDGE_BASE_ID_MAX_LENGTH,
    KNOWLEDGE_BASE_NAME_MAX_LENGTH,
    KNOWLEDGE_DOCUMENT_ERROR_CODE_MAX_LENGTH,
    KNOWLEDGE_DOCUMENT_ID_MAX_LENGTH,
    KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH,
)
from common_agent.domain.model_configuration import (
    MODEL_DISPLAY_NAME_MAX_LENGTH,
    MODEL_IDENTIFIER_MAX_LENGTH,
)
from common_agent.domain.workflow import (
    WORKFLOW_DESCRIPTION_MAX_LENGTH,
    WORKFLOW_EDGE_ID_MAX_LENGTH,
    WORKFLOW_NAME_MAX_LENGTH,
    WORKFLOW_NODE_ID_MAX_LENGTH,
)
from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH,
    WORKFLOW_RUN_INPUT_MAX_LENGTH,
    WORKFLOW_RUN_OUTPUT_MAX_LENGTH,
)


class PersistenceBase(DeclarativeBase):
    pass


class OrganizationRow(PersistenceBase):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_organizations_id"),
        CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 100 AND name = TRIM(name)",
            name="ck_organizations_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class TenantRow(PersistenceBase):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_tenants_id"),
        CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 100 AND name = TRIM(name)",
            name="ck_tenants_name",
        ),
        UniqueConstraint("organization_id", "name", name="uq_tenants_organization_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE", name="fk_tenants_organization_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class TenantMembershipRow(PersistenceBase):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_tenant_memberships_role",
        ),
        Index("ix_tenant_memberships_user", "user_id", "tenant_id"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_tenant_memberships_tenant_id"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_tenant_memberships_user_id"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class AuthUserRow(PersistenceBase):
    __tablename__ = "auth_users"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_auth_users_id"),
        CheckConstraint(
            "CHAR_LENGTH(email) BETWEEN 3 AND 254 AND email = LOWER(TRIM(email))",
            name="ck_auth_users_email",
        ),
        CheckConstraint(
            "password_hash LIKE '$argon2id$%'",
            name="ck_auth_users_password_hash",
        ),
        CheckConstraint(
            "password_changed_at BETWEEN created_at AND updated_at",
            name="ck_auth_users_password_changed_at",
        ),
        CheckConstraint(
            "bootstrap_slot IS NULL OR bootstrap_slot = 'owner'",
            name="ck_auth_users_bootstrap_slot",
        ),
        UniqueConstraint("email", name="uq_auth_users_email"),
        UniqueConstraint("bootstrap_slot", name="uq_auth_users_bootstrap_slot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bootstrap_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class AuthSessionRow(PersistenceBase):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_auth_sessions_id"),
        CheckConstraint(
            "CHAR_LENGTH(user_id) = 36 AND user_id = TRIM(user_id)",
            name="ck_auth_sessions_user_id",
        ),
        CheckConstraint(
            "CHAR_LENGTH(token_digest) = 64",
            name="ck_auth_sessions_token_digest",
        ),
        CheckConstraint(
            "CHAR_LENGTH(csrf_token) = 43",
            name="ck_auth_sessions_csrf_token",
        ),
        CheckConstraint(
            "last_seen_at >= created_at AND idle_expires_at > last_seen_at "
            "AND absolute_expires_at >= idle_expires_at",
            name="ck_auth_sessions_lifetime",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_auth_sessions_revoked_at",
        ),
        UniqueConstraint("token_digest", name="uq_auth_sessions_token_digest"),
        Index(
            "ix_auth_sessions_user_active",
            "user_id",
            "revoked_at",
            "absolute_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_auth_sessions_user_id"),
        nullable=False,
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(43), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)


class AuthRecoveryCodeRow(PersistenceBase):
    __tablename__ = "auth_recovery_codes"
    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(code_digest) = 64",
            name="ck_auth_recovery_codes_digest",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="ck_auth_recovery_codes_consumed_at",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_auth_recovery_codes_user_id"),
        primary_key=True,
    )
    code_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)


class AuthLoginAttemptRow(PersistenceBase):
    __tablename__ = "auth_login_attempts"
    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(key_digest) = 64",
            name="ck_auth_login_attempts_key_digest",
        ),
        CheckConstraint(
            "failure_count >= 0 AND updated_at >= window_started_at",
            name="ck_auth_login_attempts_state",
        ),
        CheckConstraint(
            "locked_until IS NULL OR locked_until >= updated_at",
            name="ck_auth_login_attempts_locked_until",
        ),
        Index("ix_auth_login_attempts_locked_until", "locked_until"),
        Index("ix_auth_login_attempts_updated_at", "updated_at"),
    )

    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class AuditChainHeadRow(PersistenceBase):
    __tablename__ = "audit_chain_heads"
    __table_args__ = (
        CheckConstraint(
            "(scope_key = 'platform' AND tenant_id IS NULL) OR "
            "(scope_key = CONCAT('tenant:', tenant_id) AND tenant_id IS NOT NULL)",
            name="ck_audit_chain_heads_scope",
        ),
        CheckConstraint("event_count >= 0", name="ck_audit_chain_heads_count"),
        CheckConstraint(
            "CHAR_LENGTH(last_hash) = 64",
            name="ck_audit_chain_heads_last_hash",
        ),
        UniqueConstraint("tenant_id", name="uq_audit_chain_heads_tenant_id"),
    )

    scope_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class AuditEventRow(PersistenceBase):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(event_id) = 36", name="ck_audit_events_event_id"),
        CheckConstraint("sequence > 0", name="ck_audit_events_sequence"),
        CheckConstraint(
            "outcome IN ('started', 'succeeded', 'denied', 'failed')",
            name="ck_audit_events_outcome",
        ),
        CheckConstraint(
            "(resource_type IS NULL AND resource_id IS NULL) OR "
            "(resource_type IS NOT NULL AND resource_id IS NOT NULL)",
            name="ck_audit_events_resource",
        ),
        CheckConstraint(
            "(outcome IN ('started', 'succeeded') AND error_code IS NULL) OR "
            "(outcome IN ('denied', 'failed') AND error_code IS NOT NULL)",
            name="ck_audit_events_error",
        ),
        CheckConstraint(
            "CHAR_LENGTH(trace_id) = 32 AND CHAR_LENGTH(previous_hash) = 64 "
            "AND CHAR_LENGTH(event_hash) = 64",
            name="ck_audit_events_hashes",
        ),
        CheckConstraint(
            "retention_until > occurred_at",
            name="ck_audit_events_retention",
        ),
        UniqueConstraint("event_id", name="uq_audit_events_event_id"),
        UniqueConstraint("scope_key", "sequence", name="uq_audit_events_scope_sequence"),
        Index(
            "ix_audit_events_tenant_occurred",
            "tenant_id",
            "occurred_at",
            "sequence",
        ),
        Index(
            "ix_audit_events_tenant_actor_occurred",
            "tenant_id",
            "actor_user_id",
            "occurred_at",
        ),
        Index(
            "ix_audit_events_tenant_resource_occurred",
            "tenant_id",
            "resource_type",
            "resource_id",
            "occurred_at",
        ),
        Index("ix_audit_events_retention_until", "retention_until"),
    )

    storage_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scope_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "audit_chain_heads.scope_key",
            ondelete="RESTRICT",
            name="fk_audit_events_scope_key",
        ),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    retention_until: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DurableTaskRow(PersistenceBase):
    __tablename__ = "durable_tasks"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(task_id) = 36", name="ck_durable_tasks_task_id"),
        CheckConstraint(
            "kind IN ('conversation.reply', 'workflow.run')",
            name="ck_durable_tasks_kind",
        ),
        CheckConstraint(
            "state IN ('pending', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled')",
            name="ck_durable_tasks_state",
        ),
        CheckConstraint(
            "attempts >= 0 AND max_attempts BETWEEN 1 AND 100 AND attempts <= max_attempts",
            name="ck_durable_tasks_attempts",
        ),
        CheckConstraint(
            "(state = 'running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_until IS NOT NULL) OR (state <> 'running' AND lease_owner IS NULL "
            "AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_durable_tasks_lease",
        ),
        CheckConstraint(
            "(state IN ('failed', 'retry_wait') AND error_code IS NOT NULL) OR "
            "(state NOT IN ('failed', 'retry_wait') AND error_code IS NULL)",
            name="ck_durable_tasks_error",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_durable_tasks_tenant_key"),
        Index(
            "ix_durable_tasks_claim",
            "state",
            "available_at",
            "lease_until",
            "created_at",
        ),
        Index("ix_durable_tasks_tenant_aggregate", "tenant_id", "kind", "aggregate_id"),
        Index("ix_durable_tasks_updated", "updated_at"),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_durable_tasks_tenant_id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(191), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    stop_requested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class DurableEventStreamRow(PersistenceBase):
    __tablename__ = "durable_event_streams"
    __table_args__ = (
        CheckConstraint(
            "stream_kind IN ('conversation', 'workflow')",
            name="ck_durable_event_streams_kind",
        ),
        CheckConstraint(
            "next_sequence >= 1 AND event_count >= 0",
            name="ck_durable_event_streams_counters",
        ),
        Index("ix_durable_event_streams_updated", "updated_at"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
            name="fk_durable_event_streams_tenant_id",
        ),
        primary_key=True,
    )
    stream_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    stream_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    next_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class DurableEventRow(PersistenceBase):
    __tablename__ = "durable_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_durable_events_sequence"),
        CheckConstraint(
            "stream_kind IN ('conversation', 'workflow')",
            name="ck_durable_events_kind",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "stream_kind", "stream_id"],
            [
                "durable_event_streams.tenant_id",
                "durable_event_streams.stream_kind",
                "durable_event_streams.stream_id",
            ],
            name="fk_durable_events_stream",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "stream_kind",
            "stream_id",
            "sequence",
            name="uq_durable_events_stream_sequence",
        ),
        UniqueConstraint(
            "tenant_id",
            "stream_kind",
            "stream_id",
            "event_key",
            name="uq_durable_events_stream_key",
        ),
        Index(
            "ix_durable_events_stream_read",
            "tenant_id",
            "stream_kind",
            "stream_id",
            "sequence",
        ),
        Index("ix_durable_events_retention", "retention_until"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    stream_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    stream_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_key: Mapped[str] = mapped_column(String(191), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    retention_until: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class DemoKnowledgeBaseRow(PersistenceBase):
    __tablename__ = "demo_knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {KNOWLEDGE_BASE_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_demo_knowledge_bases_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {KNOWLEDGE_BASE_NAME_MAX_LENGTH} "
            "AND name = TRIM(name)",
            name="ck_demo_knowledge_bases_name",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(description) <= {KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH} "
            "AND description = TRIM(description)",
            name="ck_demo_knowledge_bases_description",
        ),
        UniqueConstraint("tenant_id", "name", name="uq_demo_knowledge_bases_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_demo_knowledge_bases_tenant_id"),
        Index("ix_demo_knowledge_bases_tenant_created", "tenant_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(KNOWLEDGE_BASE_ID_MAX_LENGTH), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_demo_knowledge_bases_tenant_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(KNOWLEDGE_BASE_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class DemoKnowledgeDocumentRow(PersistenceBase):
    __tablename__ = "demo_knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {KNOWLEDGE_DOCUMENT_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_demo_knowledge_documents_id",
        ),
        CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND "
            f"{KNOWLEDGE_BASE_ID_MAX_LENGTH} AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_demo_knowledge_documents_base_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH} "
            "AND name = TRIM(name)",
            name="ck_demo_knowledge_documents_name",
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 20971520",
            name="ck_demo_knowledge_documents_size",
        ),
        CheckConstraint(
            "parsing_status IN ('uploaded', 'parsing', 'completed', 'failed')",
            name="ck_demo_knowledge_documents_status",
        ),
        CheckConstraint(
            "(parsing_status = 'failed' AND error_code IS NOT NULL) OR "
            "(parsing_status != 'failed' AND error_code IS NULL)",
            name="ck_demo_knowledge_documents_error",
        ),
        CheckConstraint(
            "error_code IS NULL OR "
            f"(CHAR_LENGTH(error_code) BETWEEN 1 AND {KNOWLEDGE_DOCUMENT_ERROR_CODE_MAX_LENGTH} "
            "AND error_code = TRIM(error_code))",
            name="ck_demo_knowledge_documents_error_code",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["demo_knowledge_bases.tenant_id", "demo_knowledge_bases.id"],
            name="fk_demo_knowledge_documents_tenant_base",
            ondelete="CASCADE",
        ),
        Index(
            "ix_demo_knowledge_documents_tenant_base_created",
            "tenant_id",
            "knowledge_base_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(KNOWLEDGE_DOCUMENT_ID_MAX_LENGTH), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_demo_knowledge_documents_tenant_id"),
        nullable=False,
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(KNOWLEDGE_BASE_ID_MAX_LENGTH),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parsing_status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(
        String(KNOWLEDGE_DOCUMENT_ERROR_CODE_MAX_LENGTH), nullable=True
    )
    content: Mapped[str] = mapped_column(mysql.LONGTEXT(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class ModelConfigurationRow(PersistenceBase):
    __tablename__ = "model_configurations"
    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(id) = 36 AND id = TRIM(id)",
            name="ck_model_configurations_id",
        ),
        CheckConstraint(
            "CHAR_LENGTH(display_name) BETWEEN 1 AND "
            f"{MODEL_DISPLAY_NAME_MAX_LENGTH} AND display_name = TRIM(display_name)",
            name="ck_model_configurations_display_name",
        ),
        CheckConstraint(
            "provider = 'bailian'",
            name="ck_model_configurations_provider",
        ),
        CheckConstraint(
            "CHAR_LENGTH(model_identifier) BETWEEN 1 AND "
            f"{MODEL_IDENTIFIER_MAX_LENGTH} AND model_identifier = TRIM(model_identifier)",
            name="ck_model_configurations_identifier",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_model_configurations_timestamps",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_model_configurations_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "display_name",
            name="uq_model_configurations_tenant_name",
        ),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "model_identifier",
            name="uq_model_configurations_tenant_provider_identifier",
        ),
        Index(
            "ix_model_configurations_tenant_created",
            "tenant_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_model_configurations_tenant_enabled_created",
            "tenant_id",
            "enabled",
            "created_at",
            "id",
        ),
        Index(
            "ix_model_configurations_tenant_name_created",
            "tenant_id",
            "display_name",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
            name="fk_model_configurations_tenant_id",
        ),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(MODEL_DISPLAY_NAME_MAX_LENGTH), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    model_identifier: Mapped[str] = mapped_column(
        String(MODEL_IDENTIFIER_MAX_LENGTH), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class ModelConfigurationReferenceRow(PersistenceBase):
    __tablename__ = "model_configuration_references"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('employee', 'workflow', 'conversation')",
            name="ck_model_configuration_references_type",
        ),
        CheckConstraint(
            "CHAR_LENGTH(resource_id) BETWEEN 1 AND 128 AND resource_id = TRIM(resource_id)",
            name="ck_model_configuration_references_resource_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "model_configuration_id"],
            ["model_configurations.tenant_id", "model_configurations.id"],
            name="fk_model_configuration_references_configuration",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_model_configuration_references_resource",
            "tenant_id",
            "resource_type",
            "resource_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
            name="fk_model_configuration_references_tenant_id",
        ),
        primary_key=True,
    )
    model_configuration_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class EmployeeRow(PersistenceBase):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_employees_id"),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {EMPLOYEE_NAME_MAX_LENGTH} AND name = TRIM(name)",
            name="ck_employees_name",
        ),
        CheckConstraint(
            "CHAR_LENGTH(description) "
            f"<= {EMPLOYEE_DESCRIPTION_MAX_LENGTH} AND description = TRIM(description)",
            name="ck_employees_description",
        ),
        CheckConstraint(
            "CHAR_LENGTH(system_prompt) BETWEEN 1 AND "
            f"{EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH} AND system_prompt = TRIM(system_prompt)",
            name="ck_employees_system_prompt",
        ),
        CheckConstraint(
            "knowledge_base_id IS NULL OR "
            "(CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND "
            f"{EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH} "
            "AND knowledge_base_id = TRIM(knowledge_base_id))",
            name="ck_employees_knowledge_base_id",
        ),
        CheckConstraint(
            "JSON_TYPE(allowed_workflow_ids) = 'ARRAY'",
            name="ck_employees_allowed_workflow_ids",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_employees_timestamps"),
        ForeignKeyConstraint(
            ["tenant_id", "default_model_configuration_id"],
            ["model_configurations.tenant_id", "model_configurations.id"],
            name="fk_employees_tenant_default_model",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_employees_tenant_id"),
        Index(
            "ix_employees_tenant_default_model",
            "tenant_id",
            "default_model_configuration_id",
        ),
        Index("ix_employees_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_employees_tenant_name_created", "tenant_id", "name", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_employees_tenant_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(EMPLOYEE_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(EMPLOYEE_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    default_model_configuration_id: Mapped[str] = mapped_column(String(36), nullable=False)
    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH), nullable=True
    )
    allowed_workflow_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class ConversationRow(PersistenceBase):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_conversations_id"),
        CheckConstraint(
            "CHAR_LENGTH(employee_id) = 36 AND employee_id = TRIM(employee_id)",
            name="ck_conversations_employee_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(title) BETWEEN 1 AND {CONVERSATION_TITLE_MAX_LENGTH} "
            "AND title = TRIM(title)",
            name="ck_conversations_title",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_conversations_timestamps"),
        CheckConstraint(
            "(source = 'employee' AND employee_id IS NOT NULL "
            "AND model_configuration_id IS NULL) OR "
            "(source = 'generic' AND employee_id IS NULL "
            "AND model_configuration_id IS NOT NULL)",
            name="ck_conversations_source_references",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_conversations_tenant_employee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "model_configuration_id"],
            ["model_configurations.tenant_id", "model_configurations.id"],
            name="fk_conversations_tenant_model_configuration",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "employee_id",
            name="uq_conversations_tenant_id_employee",
        ),
        Index("ix_conversations_tenant_updated", "tenant_id", "updated_at", "id"),
        Index(
            "ix_conversations_tenant_source_updated",
            "tenant_id",
            "source",
            "updated_at",
            "id",
        ),
        Index(
            "ix_conversations_tenant_model_configuration",
            "tenant_id",
            "model_configuration_id",
        ),
        Index(
            "ix_conversations_tenant_employee_updated",
            "tenant_id",
            "employee_id",
            "updated_at",
            "id",
        ),
        Index("ix_conversations_tenant_title_updated", "tenant_id", "title", "updated_at", "id"),
        Index(
            "ix_conversations_tenant_employee_title_updated",
            "tenant_id",
            "employee_id",
            "title",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_conversations_tenant_id"),
        nullable=False,
    )
    employee_id: Mapped[str] = mapped_column(
        String(36),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    model_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(CONVERSATION_TITLE_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class MessageRow(PersistenceBase):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_messages_id"),
        CheckConstraint(
            "CHAR_LENGTH(conversation_id) = 36 AND conversation_id = TRIM(conversation_id)",
            name="ck_messages_conversation_id",
        ),
        CheckConstraint("sequence_number >= 1", name="ck_messages_sequence_number"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        CheckConstraint(
            "status IN ('pending', 'streaming', 'completed', 'failed', 'stopped')",
            name="ck_messages_status",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(content) <= {MESSAGE_CONTENT_MAX_LENGTH}",
            name="ck_messages_content_length",
        ),
        CheckConstraint(
            "error_code IS NULL OR "
            f"(CHAR_LENGTH(error_code) BETWEEN 1 AND {MESSAGE_ERROR_CODE_MAX_LENGTH} "
            "AND error_code = TRIM(error_code))",
            name="ck_messages_error_code",
        ),
        CheckConstraint(
            "(role = 'user' AND status = 'completed' "
            "AND CHAR_LENGTH(TRIM(content)) >= 1 AND error_code IS NULL) OR "
            "(role = 'assistant' AND ("
            "(status = 'pending' AND CHAR_LENGTH(content) = 0 AND error_code IS NULL) OR "
            "(status = 'streaming' AND error_code IS NULL) OR "
            "(status = 'completed' AND CHAR_LENGTH(TRIM(content)) >= 1 AND error_code IS NULL) OR "
            "(status = 'failed' AND error_code IS NOT NULL) OR "
            "(status = 'stopped' AND error_code IS NULL)))",
            name="ck_messages_role_state",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_messages_timestamps"),
        CheckConstraint(
            "(role = 'user' AND model_configuration_id IS NULL "
            "AND model_identifier IS NULL) OR "
            "(role = 'assistant' AND ((model_configuration_id IS NULL "
            "AND model_identifier IS NULL) OR (model_configuration_id IS NOT NULL "
            "AND model_identifier IS NOT NULL AND CHAR_LENGTH(model_identifier) BETWEEN 1 AND "
            f"{MODEL_IDENTIFIER_MAX_LENGTH} AND model_identifier = TRIM(model_identifier))))",
            name="ck_messages_model_selection",
        ),
        UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_messages_conversation_sequence",
        ),
        UniqueConstraint("conversation_id", "id", name="uq_messages_conversation_id"),
        Index("ix_messages_model_configuration", "model_configuration_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE", name="fk_messages_conversation_id"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(
        String(MESSAGE_ERROR_CODE_MAX_LENGTH), nullable=True
    )
    model_configuration_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "model_configurations.id",
            ondelete="RESTRICT",
            name="fk_messages_model_configuration_id",
        ),
        nullable=True,
    )
    model_identifier: Mapped[str | None] = mapped_column(
        String(MODEL_IDENTIFIER_MAX_LENGTH),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class MessageCitationRow(PersistenceBase):
    __tablename__ = "message_citations"
    __table_args__ = (
        CheckConstraint("position >= 1", name="ck_message_citations_position"),
        CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND "
            f"{CITATION_REFERENCE_MAX_LENGTH} AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_message_citations_knowledge_base_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(chunk_id) BETWEEN 1 AND {CITATION_REFERENCE_MAX_LENGTH} "
            "AND chunk_id = TRIM(chunk_id)",
            name="ck_message_citations_chunk_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(document_id) BETWEEN 1 AND {CITATION_REFERENCE_MAX_LENGTH} "
            "AND document_id = TRIM(document_id)",
            name="ck_message_citations_document_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(document_name) BETWEEN 1 AND {CITATION_DOCUMENT_NAME_MAX_LENGTH} "
            "AND document_name = TRIM(document_name)",
            name="ck_message_citations_document_name",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(TRIM(content)) BETWEEN 1 AND {CITATION_CONTENT_MAX_LENGTH}",
            name="ck_message_citations_content",
        ),
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_message_citations_score"),
    )

    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE", name="fk_message_citations_message_id"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(CITATION_REFERENCE_MAX_LENGTH), nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(String(CITATION_REFERENCE_MAX_LENGTH), nullable=False)
    document_id: Mapped[str] = mapped_column(String(CITATION_REFERENCE_MAX_LENGTH), nullable=False)
    document_name: Mapped[str] = mapped_column(
        String(CITATION_DOCUMENT_NAME_MAX_LENGTH), nullable=False
    )
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)


class WorkflowRow(PersistenceBase):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_workflows_id"),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {WORKFLOW_NAME_MAX_LENGTH} AND name = TRIM(name)",
            name="ck_workflows_name",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(description) <= {WORKFLOW_DESCRIPTION_MAX_LENGTH} "
            "AND description = TRIM(description)",
            name="ck_workflows_description",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_workflows_timestamps"),
        UniqueConstraint("tenant_id", "id", name="uq_workflows_tenant_id"),
        Index("ix_workflows_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_workflows_tenant_name_created", "tenant_id", "name", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_workflows_tenant_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(WORKFLOW_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(WORKFLOW_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class WorkflowNodeRow(PersistenceBase):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_workflow_nodes_id",
        ),
        CheckConstraint("ordinal >= 0", name="ck_workflow_nodes_ordinal"),
        CheckConstraint(
            "type IN ('start', 'ai_chat', 'knowledge_retrieval', 'end')",
            name="ck_workflow_nodes_type",
        ),
        CheckConstraint("JSON_TYPE(config) = 'OBJECT'", name="ck_workflow_nodes_config"),
        UniqueConstraint("workflow_id", "ordinal", name="uq_workflow_nodes_ordinal"),
    )

    workflow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflows.id", ondelete="CASCADE", name="fk_workflow_nodes_workflow_id"),
        primary_key=True,
    )
    id: Mapped[str] = mapped_column(String(WORKFLOW_NODE_ID_MAX_LENGTH), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    position_x: Mapped[float] = mapped_column(mysql.DOUBLE(asdecimal=False), nullable=False)
    position_y: Mapped[float] = mapped_column(mysql.DOUBLE(asdecimal=False), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class WorkflowEdgeRow(PersistenceBase):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {WORKFLOW_EDGE_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_workflow_edges_id",
        ),
        CheckConstraint("ordinal >= 0", name="ck_workflow_edges_ordinal"),
        CheckConstraint(
            f"CHAR_LENGTH(source) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND source = TRIM(source)",
            name="ck_workflow_edges_source",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(target) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND target = TRIM(target)",
            name="ck_workflow_edges_target",
        ),
        ForeignKeyConstraint(
            ["workflow_id", "source"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_edges_source",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workflow_id", "target"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_edges_target",
            ondelete="CASCADE",
        ),
        UniqueConstraint("workflow_id", "ordinal", name="uq_workflow_edges_ordinal"),
        UniqueConstraint(
            "workflow_id",
            "source",
            "target",
            name="uq_workflow_edges_connection",
        ),
    )

    workflow_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(WORKFLOW_EDGE_ID_MAX_LENGTH), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=False)
    target: Mapped[str] = mapped_column(String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=False)


class WorkflowRunRow(PersistenceBase):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_workflow_runs_id"),
        CheckConstraint(
            "`trigger` IN ('manual', 'employee')",
            name="ck_workflow_runs_trigger",
        ),
        CheckConstraint(
            "(`trigger` = 'manual' AND employee_id IS NULL "
            "AND conversation_id IS NULL AND assistant_message_id IS NULL) OR "
            "(`trigger` = 'employee' AND employee_id IS NOT NULL "
            "AND conversation_id IS NOT NULL AND assistant_message_id IS NOT NULL)",
            name="ck_workflow_runs_origin",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'stopped')",
            name="ck_workflow_runs_status",
        ),
        CheckConstraint(
            "current_node_id IS NULL OR "
            f"(CHAR_LENGTH(current_node_id) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND current_node_id = TRIM(current_node_id))",
            name="ck_workflow_runs_current_node_id",
        ),
        CheckConstraint("JSON_TYPE(completed_node_ids) = 'ARRAY'", name="ck_workflow_runs_nodes"),
        CheckConstraint(
            f"CHAR_LENGTH(TRIM(input)) BETWEEN 1 AND {WORKFLOW_RUN_INPUT_MAX_LENGTH}",
            name="ck_workflow_runs_input",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(output) <= {WORKFLOW_RUN_OUTPUT_MAX_LENGTH} "
            "AND (output = '' OR CHAR_LENGTH(TRIM(output)) >= 1)",
            name="ck_workflow_runs_output",
        ),
        CheckConstraint(
            "failed_node_id IS NULL OR "
            f"(CHAR_LENGTH(failed_node_id) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND failed_node_id = TRIM(failed_node_id))",
            name="ck_workflow_runs_failed_node_id",
        ),
        CheckConstraint(
            "error_code IS NULL OR "
            f"(CHAR_LENGTH(error_code) BETWEEN 1 AND {WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH} "
            "AND error_code = TRIM(error_code))",
            name="ck_workflow_runs_error_code",
        ),
        CheckConstraint(
            "updated_at >= created_at AND "
            "(started_at IS NULL OR started_at BETWEEN created_at AND updated_at) AND "
            "(finished_at IS NULL OR finished_at = updated_at)",
            name="ck_workflow_runs_timestamps",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL "
            "AND current_node_id IS NULL AND JSON_LENGTH(completed_node_ids) = 0 "
            "AND output = '' AND failed_node_id IS NULL AND error_code IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL "
            "AND output = '' AND failed_node_id IS NULL AND error_code IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "AND CHAR_LENGTH(TRIM(output)) >= 1 AND failed_node_id IS NULL "
            "AND error_code IS NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND output = '' "
            "AND error_code IS NOT NULL AND "
            "((failed_node_id IS NULL AND current_node_id IS NULL) "
            "OR failed_node_id = current_node_id)) OR "
            "(status = 'stopped' AND finished_at IS NOT NULL AND output = '' "
            "AND failed_node_id IS NULL AND error_code IS NULL)",
            name="ck_workflow_runs_state",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_id"],
            ["workflows.tenant_id", "workflows.id"],
            name="fk_workflow_runs_tenant_workflow",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id", "employee_id"],
            ["conversations.tenant_id", "conversations.id", "conversations.employee_id"],
            name="fk_workflow_runs_tenant_origin",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "assistant_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_workflow_runs_conversation_message",
            ondelete="CASCADE",
        ),
        Index(
            "ix_workflow_runs_tenant_workflow_created",
            "tenant_id",
            "workflow_id",
            "created_at",
        ),
        Index(
            "ix_workflow_runs_tenant_conversation_created",
            "tenant_id",
            "conversation_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_workflow_runs_tenant_conversation_input_created",
            "tenant_id",
            "conversation_id",
            "input",
            "created_at",
            "id",
            mysql_length={"input": 191},
        ),
        Index(
            "ix_workflow_runs_tenant_conversation_status_created",
            "tenant_id",
            "conversation_id",
            "status",
            "created_at",
            "id",
        ),
        Index("ix_workflow_runs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_workflow_runs_tenant_id"),
        nullable=False,
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assistant_message_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    output: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    current_node_id: Mapped[str | None] = mapped_column(
        String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=True
    )
    completed_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    failed_node_id: Mapped[str | None] = mapped_column(
        String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(
        String(WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class RagFlowKnowledgeBaseOwnershipRow(PersistenceBase):
    __tablename__ = "ragflow_knowledge_base_ownerships"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND {KNOWLEDGE_BASE_ID_MAX_LENGTH} "
            "AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_ragflow_knowledge_ownership_id",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            name="uq_ragflow_knowledge_ownership_external_id",
        ),
        Index(
            "ix_ragflow_knowledge_ownership_tenant",
            "tenant_id",
            "knowledge_base_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
            name="fk_ragflow_knowledge_ownership_tenant_id",
        ),
        primary_key=True,
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String(KNOWLEDGE_BASE_ID_MAX_LENGTH), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
