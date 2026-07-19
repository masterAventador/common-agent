from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common_agent.domain.employee import (
    EMPLOYEE_DESCRIPTION_MAX_LENGTH,
    EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    EMPLOYEE_NAME_MAX_LENGTH,
    EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
)


class PersistenceBase(DeclarativeBase):
    pass


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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(EMPLOYEE_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(EMPLOYEE_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH), nullable=True
    )
    allowed_workflow_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
