from __future__ import annotations

import asyncio

from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from tests.support.employees import delete_employees_from_database_url
from tests.support.http import authenticated_client, running_api, running_apis
from tests.support.settings import TEST_DATABASE_URL


def test_formal_startup_seeds_once_and_preserves_api_edits_after_restart() -> None:
    asyncio.run(
        delete_employees_from_database_url(
            TEST_DATABASE_URL,
            DEFAULT_KNOWLEDGE_ASSISTANT_ID,
        )
    )
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            seeded = client.get(f"/api/v1/employees/{DEFAULT_KNOWLEDGE_ASSISTANT_ID}")
            listed = client.get("/api/v1/employees")

            assert seeded.status_code == 200
            assert seeded.json()["name"] == "知识助理"
            assert seeded.json()["knowledge_base_id"] is None
            assert [
                item["id"]
                for item in listed.json()["items"]
                if item["id"] == str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)
            ] == [str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)]

            edited = client.put(
                f"/api/v1/employees/{DEFAULT_KNOWLEDGE_ASSISTANT_ID}",
                json={
                    "name": "用户编辑的知识助理",
                    "description": "用户编辑后的说明",
                    "system_prompt": "保留用户编辑后的系统指令。",
                    "knowledge_base_id": None,
                },
            )
            assert edited.status_code == 200
            created_at = edited.json()["created_at"]

        with (
            running_api(TEST_DATABASE_URL) as restarted_url,
            authenticated_client(base_url=restarted_url, timeout=5) as restarted_client,
        ):
            restored = restarted_client.get(f"/api/v1/employees/{DEFAULT_KNOWLEDGE_ASSISTANT_ID}")
            listed_again = restarted_client.get("/api/v1/employees")

            assert restored.status_code == 200
            assert restored.json()["name"] == "用户编辑的知识助理"
            assert restored.json()["description"] == "用户编辑后的说明"
            assert restored.json()["system_prompt"] == "保留用户编辑后的系统指令。"
            assert restored.json()["created_at"] == created_at
            assert [
                item["id"]
                for item in listed_again.json()["items"]
                if item["id"] == str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)
            ] == [str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)]
    finally:
        asyncio.run(
            delete_employees_from_database_url(
                TEST_DATABASE_URL,
                DEFAULT_KNOWLEDGE_ASSISTANT_ID,
            )
        )


def test_concurrent_formal_startups_converge_on_one_default_employee() -> None:
    asyncio.run(
        delete_employees_from_database_url(
            TEST_DATABASE_URL,
            DEFAULT_KNOWLEDGE_ASSISTANT_ID,
        )
    )
    try:
        with (
            running_apis(TEST_DATABASE_URL, count=2) as api_urls,
            authenticated_client(base_url=api_urls[0], timeout=5) as first_client,
            authenticated_client(base_url=api_urls[1], timeout=5) as second_client,
        ):
            responses = [
                first_client.get("/api/v1/employees"),
                second_client.get("/api/v1/employees"),
            ]

        assert all(response.status_code == 200 for response in responses)
        for response in responses:
            assert [
                item["id"]
                for item in response.json()["items"]
                if item["id"] == str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)
            ] == [str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)]
    finally:
        asyncio.run(
            delete_employees_from_database_url(
                TEST_DATABASE_URL,
                DEFAULT_KNOWLEDGE_ASSISTANT_ID,
            )
        )
