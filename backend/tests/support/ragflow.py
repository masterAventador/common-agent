from __future__ import annotations

import httpx

_TEST_EMAIL = "common-agent@local.test"
# RAGFlow 官方 SDK 测试夹具提供的 RSA 密文, 对应仅限 loopback 测试账号的密码 123。
_TEST_PASSWORD = (
    "ctAseGvejiaSWWZ88T/m4FQVOpQyUvP+x7sXtdv3feqZACiQleuewkUi35E16wSd5C5QcnkkcV9cYc8T"
    "KPTRZlxappDuirxghxoOvFcJxFU4ixLsDfN33jCHRoDUW81IH9zjij/vaw8IbVyb6vuwg6MX6inOEBRRzVbRYxXO"
    "u1wkWY6SsI8X70oF9aeLFp/PzQpjoe/YbSqpTq8qqrmHzn9vO+yvyYyvmDsphXeX8f7fp9c7vUsfOCkM+gHY3Pad"
    "G+QHa7KI7mzTKgUTZImK6BZtfRBATDTthEUbbaTewY4H0MnWiCeeDhcbeQao6cFy1To8pE3RpmxnGnS8BsBn8w=="
)


async def provision_api_key(base_url: str) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0, trust_env=False) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "email": _TEST_EMAIL,
                "nickname": "common-agent",
                "password": _TEST_PASSWORD,
            },
        )
        registration.raise_for_status()
        registration_payload = registration.json()
        if registration_payload["code"] != 0:
            assert "already registered" in registration_payload["message"]

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
        )
        login.raise_for_status()
        assert login.json()["code"] == 0
        authorization = login.headers["Authorization"]

        tokens = await client.get(
            "/api/v1/system/tokens",
            headers={"Authorization": authorization},
        )
        tokens.raise_for_status()
        tokens_payload = tokens.json()
        assert tokens_payload["code"] == 0
        if tokens_payload["data"]:
            return str(tokens_payload["data"][0]["token"])

        created = await client.post(
            "/api/v1/system/tokens",
            headers={"Authorization": authorization},
        )
        created.raise_for_status()
        created_payload = created.json()
        assert created_payload["code"] == 0
        return str(created_payload["data"]["token"])


async def delete_dataset(base_url: str, api_key: str, dataset_id: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0, trust_env=False) as client:
        response = await client.request(
            "DELETE",
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"ids": [dataset_id]},
        )
        response.raise_for_status()
        payload = response.json()
        assert payload["code"] == 0


async def delete_datasets_named(base_url: str, api_key: str, name: str) -> int:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0, trust_env=False) as client:
        response = await client.get(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"page": 1, "page_size": 100, "orderby": "create_time", "desc": "true"},
        )
        response.raise_for_status()
        payload = response.json()
        assert payload["code"] == 0
        dataset_ids = [str(item["id"]) for item in payload["data"] if item["name"] == name]

    for dataset_id in dataset_ids:
        await delete_dataset(base_url, api_key, dataset_id)
    return len(dataset_ids)


async def cancel_document_parsing(
    base_url: str,
    api_key: str,
    dataset_id: str,
    document_id: str,
) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0, trust_env=False) as client:
        response = await client.request(
            "DELETE",
            f"/api/v1/datasets/{dataset_id}/chunks",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"document_ids": [document_id]},
        )
        response.raise_for_status()
        payload = response.json()
        assert payload["code"] == 0
