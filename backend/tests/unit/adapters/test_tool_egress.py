from __future__ import annotations

import asyncio
from ipaddress import ip_network

import pytest

from common_agent.adapters.security.tool_egress import (
    OutboundAccessPolicy,
    OutboundSecurityError,
)


class StaticResolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses
        self.calls = 0

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        del host, port
        self.calls += 1
        return self.addresses


def test_exact_allowed_host_is_resolved_on_every_connection() -> None:
    resolver = StaticResolver("203.0.113.10")
    policy = OutboundAccessPolicy(
        allowed_hosts=("mcp.example.com",),
        allowed_cidrs=(ip_network("203.0.113.0/24"),),
        http_allowed_hosts=(),
        allow_loopback=False,
        resolver=resolver,
    )

    first = asyncio.run(policy.resolve("https", "mcp.example.com", 443))
    second = asyncio.run(policy.resolve("https", "mcp.example.com", 443))

    assert first == second == ("203.0.113.10",)
    assert resolver.calls == 2


def test_private_business_address_requires_explicit_cidr_permission() -> None:
    denied = OutboundAccessPolicy(
        allowed_hosts=("business.internal",),
        allowed_cidrs=(),
        http_allowed_hosts=("business.internal",),
        allow_loopback=False,
        resolver=StaticResolver("10.10.0.8"),
    )
    allowed = OutboundAccessPolicy(
        allowed_hosts=("business.internal",),
        allowed_cidrs=(ip_network("10.10.0.0/16"),),
        http_allowed_hosts=("business.internal",),
        allow_loopback=False,
        resolver=StaticResolver("10.10.0.8"),
    )

    with pytest.raises(OutboundSecurityError, match="不允许"):
        asyncio.run(denied.resolve("http", "business.internal", 8080))
    assert asyncio.run(allowed.resolve("http", "business.internal", 8080)) == ("10.10.0.8",)


@pytest.mark.parametrize(
    ("address", "cidr"),
    [
        ("169.254.169.254", "169.254.0.0/16"),
        ("100.100.100.200", "100.64.0.0/10"),
        ("fd00:ec2::254", "fd00::/8"),
    ],
)
def test_metadata_and_link_local_are_never_allowlisted(address: str, cidr: str) -> None:
    policy = OutboundAccessPolicy(
        allowed_hosts=("metadata.internal",),
        allowed_cidrs=(ip_network(cidr),),
        http_allowed_hosts=("metadata.internal",),
        allow_loopback=False,
        resolver=StaticResolver(address),
    )

    with pytest.raises(OutboundSecurityError, match="不允许"):
        asyncio.run(policy.resolve("http", "metadata.internal", 80))


def test_loopback_requires_both_cidr_and_explicit_switch() -> None:
    resolver = StaticResolver("127.0.0.1")
    policy = OutboundAccessPolicy(
        allowed_hosts=("localhost",),
        allowed_cidrs=(ip_network("127.0.0.0/8"),),
        http_allowed_hosts=("localhost",),
        allow_loopback=False,
        resolver=resolver,
    )

    with pytest.raises(OutboundSecurityError, match="不允许"):
        asyncio.run(policy.resolve("http", "localhost", 8080))


def test_plain_http_requires_exact_host_permission() -> None:
    policy = OutboundAccessPolicy(
        allowed_hosts=("mcp.example.com",),
        allowed_cidrs=(ip_network("203.0.113.0/24"),),
        http_allowed_hosts=(),
        allow_loopback=False,
        resolver=StaticResolver("203.0.113.10"),
    )

    with pytest.raises(OutboundSecurityError, match="HTTPS"):
        asyncio.run(policy.resolve("http", "mcp.example.com", 80))
