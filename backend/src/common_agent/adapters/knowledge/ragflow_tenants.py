from __future__ import annotations

import asyncio
import base64
from typing import cast

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from common_agent.adapters.knowledge.ragflow_models import (
    LOCAL_RAGFLOW_LEGACY_ENCRYPTED_PASSWORD,
    RagFlowModelConfigurationError,
    RagFlowModelConfigurator,
)
from common_agent.knowledge.ragflow_identity import ProvisionedRagFlowIdentity

_RAGFLOW_PUBLIC_KEY = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArq9XTUSeYr2+N1h3Afl/
z8Dse/2yD0ZGrKwx+EEEcdsBLca9Ynmx3nIB5obmLlSfmskLpBo0UACBmB5rEjBp2
Q2f3AG3Hjd4B+gNCG6BDaawuDlgANIhGnaTLrIqWrrcm4EMzJOnAOI1fgzJRsOOUE
faS318Eq9OVO3apEyCCt0lOQK6PuksduOjVxtltDav+guVAA068NrPYmRNabVKRNL
JpL8w4D44sfth5RvZ3q9t+6RTArpEtc5sh5ChzvqPOzKGMXW83C95TxmXqpbK6ol
N4RevSfVjEAgCydH6HN6OhtOQEcnrU97r9H0iZOWwbw3pVrZiUkuRD1R56Wzs2wID
AQAB
-----END PUBLIC KEY-----"""


def encrypt_ragflow_password(password: str) -> str:
    normalized = password.strip()
    if not normalized:
        raise RagFlowModelConfigurationError("account_password")
    public_key = cast(rsa.RSAPublicKey, serialization.load_pem_public_key(_RAGFLOW_PUBLIC_KEY))
    encrypted = public_key.encrypt(
        base64.b64encode(normalized.encode()),
        padding.PKCS1v15(),
    )
    return base64.b64encode(encrypted).decode()


class RagFlowTenantProvisioner:
    def __init__(
        self,
        *,
        base_url: str,
        expected_version: str,
        bailian_api_key: str,
        bailian_base_url: str,
        timeout_seconds: float,
        ca_bundle_path: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._expected_version = expected_version
        self._bailian_api_key = bailian_api_key.strip()
        self._bailian_base_url = bailian_base_url
        self._timeout_seconds = timeout_seconds
        self._ca_bundle_path = ca_bundle_path

    async def provision(
        self,
        *,
        account_email: str,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity:
        encrypted_password = encrypt_ragflow_password(account_password)
        return await asyncio.to_thread(
            self._provision,
            account_email,
            encrypted_password,
        )

    async def adopt(
        self,
        api_key: str,
        *,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity:
        return await asyncio.to_thread(
            self._adopt,
            api_key.strip(),
            account_password,
        )

    def _provision(
        self,
        account_email: str,
        encrypted_password: str,
    ) -> ProvisionedRagFlowIdentity:
        with self._client() as client:
            configurator = RagFlowModelConfigurator(
                client=client,
                account_email=account_email,
                encrypted_password=encrypted_password,
            )
            return self._finalize(configurator)

    def _adopt(
        self,
        api_key: str,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity:
        if not api_key:
            raise RagFlowModelConfigurationError("token_invalid")
        new_encrypted_password = encrypt_ragflow_password(account_password)
        with self._client() as client:
            configurator = RagFlowModelConfigurator(
                client=client,
                authorization=f"Bearer {api_key}",
            )
            _, account_email = configurator.profile()
            if not self._password_is_current(
                client,
                account_email=account_email,
                encrypted_password=new_encrypted_password,
            ):
                configurator.change_password(
                    current_encrypted_password=(
                        LOCAL_RAGFLOW_LEGACY_ENCRYPTED_PASSWORD
                    ),
                    new_encrypted_password=new_encrypted_password,
                )
            return self._finalize(configurator, current_api_key=api_key)

    @staticmethod
    def _password_is_current(
        client: httpx.Client,
        *,
        account_email: str,
        encrypted_password: str,
    ) -> bool:
        try:
            RagFlowModelConfigurator(
                client=client,
                account_email=account_email,
                encrypted_password=encrypted_password,
            ).authorization()
        except RagFlowModelConfigurationError:
            return False
        return True

    def _finalize(
        self,
        configurator: RagFlowModelConfigurator,
        *,
        current_api_key: str | None = None,
    ) -> ProvisionedRagFlowIdentity:
        self._verify_version(configurator)
        ragflow_tenant_id, account_email = configurator.profile()
        configurator.apply(
            api_key=self._bailian_api_key,
            provider_base_url=self._bailian_base_url,
        )
        api_key = configurator.ensure_api_token_value(current_api_key)
        return ProvisionedRagFlowIdentity(
            account_email=account_email,
            ragflow_tenant_id=ragflow_tenant_id,
            api_key=api_key,
        )

    def _verify_version(self, configurator: RagFlowModelConfigurator) -> None:
        if configurator.version() != self._expected_version:
            raise RagFlowModelConfigurationError("version")

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout_seconds),
            verify=self._ca_bundle_path or True,
            trust_env=False,
        )


__all__ = ["RagFlowTenantProvisioner", "encrypt_ragflow_password"]
