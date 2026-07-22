from __future__ import annotations

import asyncio
import socket
import ssl
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
)
from typing import Any, Protocol

import httpcore
import httpx

IpAddress = IPv4Address | IPv6Address
IpNetwork = IPv4Network | IPv6Network
_METADATA_ADDRESSES: frozenset[IpAddress] = frozenset(
    {
        ip_address("100.100.100.200"),
        ip_address("169.254.169.254"),
        ip_address("fd00:ec2::254"),
    }
)


class OutboundSecurityError(RuntimeError):
    code: str
    retryable: bool
    request_may_have_been_sent: bool

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        request_may_have_been_sent: bool = False,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.request_may_have_been_sent = request_may_have_been_sent
        super().__init__(message)


class AddressResolver(Protocol):
    async def resolve(self, host: str, port: int) -> tuple[str, ...]: ...


class SystemAddressResolver:
    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except socket.gaierror:
            raise OutboundSecurityError(
                "tool_egress_dns_failed",
                "MCP 出站目标暂时无法解析",
                retryable=True,
            ) from None
        return tuple(dict.fromkeys(record[4][0] for record in records))


class OutboundAccessPolicy:
    def __init__(
        self,
        *,
        allowed_hosts: Sequence[str],
        allowed_cidrs: Sequence[IpNetwork],
        http_allowed_hosts: Sequence[str],
        allow_loopback: bool,
        resolver: AddressResolver | None = None,
    ) -> None:
        self._allowed_hosts = _host_set(allowed_hosts)
        self._allowed_cidrs = tuple(allowed_cidrs)
        self._http_allowed_hosts = _host_set(http_allowed_hosts)
        if not self._http_allowed_hosts.issubset(self._allowed_hosts):
            raise ValueError("HTTP 放行主机必须同时存在于 MCP 出站主机许可中")
        self._allow_loopback = allow_loopback
        self._resolver = resolver or SystemAddressResolver()

    async def resolve(self, scheme: str, host: str, port: int) -> tuple[str, ...]:
        normalized_host = _host(host)
        if scheme not in {"http", "https"}:
            raise OutboundSecurityError("tool_egress_scheme_blocked", "MCP 出站协议不允许")
        if scheme == "http" and normalized_host not in self._http_allowed_hosts:
            raise OutboundSecurityError(
                "tool_egress_plaintext_blocked",
                "该 MCP 出站目标必须使用 HTTPS",
            )
        if not 1 <= port <= 65535:
            raise OutboundSecurityError("tool_egress_port_blocked", "MCP 出站端口不允许")
        raw_addresses = await self._resolver.resolve(normalized_host, port)
        if not raw_addresses:
            raise OutboundSecurityError(
                "tool_egress_dns_failed",
                "MCP 出站目标暂时无法解析",
                retryable=True,
            )
        authorized: list[str] = []
        for raw in raw_addresses:
            try:
                address = _effective_ip(ip_address(raw))
            except ValueError:
                raise OutboundSecurityError(
                    "tool_egress_dns_failed",
                    "MCP 出站目标暂时无法解析",
                    retryable=True,
                ) from None
            if not self._permitted(normalized_host, address):
                raise OutboundSecurityError(
                    "tool_egress_address_blocked",
                    "MCP 出站目标地址不允许",
                )
            authorized.append(str(address))
        return tuple(dict.fromkeys(authorized))

    def _permitted(self, host: str, address: IpAddress) -> bool:
        in_allowed_cidr = any(address in network for network in self._allowed_cidrs)
        host_allowed = host in self._allowed_hosts
        if (
            address in _METADATA_ADDRESSES
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
        ):
            return False
        if address.is_loopback:
            return self._allow_loopback and in_allowed_cidr and host_allowed
        if address.is_private or address.is_reserved:
            return in_allowed_cidr and (host_allowed or _is_ip_literal(host))
        return host_allowed or in_allowed_cidr


@dataclass(frozen=True, slots=True)
class OutboundHttpResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class _Origin:
    scheme: str
    host: str
    port: int


class _GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, policy: OutboundAccessPolicy, origin: _Origin) -> None:
        self._policy = policy
        self._origin = origin
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        if _host(host) != self._origin.host or port != self._origin.port:
            raise OutboundSecurityError(
                "tool_egress_origin_blocked",
                "MCP 出站目标来源不允许",
            )
        addresses = await self._policy.resolve(self._origin.scheme, self._origin.host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as error:  # Try the next already-authorized address.
                last_error = error
        if last_error is None:
            raise OutboundSecurityError(
                "tool_egress_dns_failed",
                "MCP 出站目标暂时无法解析",
                retryable=True,
            )
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        raise OutboundSecurityError(
            "tool_egress_unix_socket_blocked",
            "MCP 出站不允许 Unix Socket",
        )

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _CoreResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: AsyncIterable[bytes], maximum_bytes: int) -> None:
        self._stream = stream
        self._maximum_bytes = maximum_bytes

    async def __aiter__(self) -> AsyncIterator[bytes]:
        consumed = 0
        async for chunk in self._stream:
            consumed += len(chunk)
            if consumed > self._maximum_bytes:
                raise OutboundSecurityError(
                    "tool_egress_response_too_large",
                    "MCP 出站响应过大",
                    request_may_have_been_sent=True,
                )
            yield chunk

    async def aclose(self) -> None:
        closer = getattr(self._stream, "aclose", None)
        if closer is not None:
            await closer()


class _PinnedAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        *,
        policy: OutboundAccessPolicy,
        origin: _Origin,
        ssl_context: ssl.SSLContext,
        maximum_connections: int,
        maximum_response_bytes: int,
    ) -> None:
        self._origin = origin
        self._maximum_response_bytes = maximum_response_bytes
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=maximum_connections,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=_GuardedNetworkBackend(policy, origin),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if _origin(str(request.url), endpoint=False) != self._origin:
            raise OutboundSecurityError(
                "tool_egress_origin_blocked",
                "MCP 出站目标来源不允许",
            )
        if not isinstance(request.stream, httpx.AsyncByteStream):
            raise RuntimeError("MCP 出站请求体必须是异步字节流")
        response = await self._pool.handle_async_request(
            httpcore.Request(
                method=request.method,
                url=httpcore.URL(
                    scheme=request.url.raw_scheme,
                    host=request.url.raw_host,
                    port=request.url.port,
                    target=request.url.raw_path,
                ),
                headers=request.headers.raw,
                content=request.stream,
                extensions=request.extensions,
            )
        )
        if not isinstance(response.stream, AsyncIterable):
            raise RuntimeError("MCP 出站响应体必须是异步字节流")
        if 300 <= response.status < 400:
            closer = getattr(response.stream, "aclose", None)
            if closer is not None:
                await closer()
            raise OutboundSecurityError(
                "tool_egress_redirect_blocked",
                "MCP 出站响应重定向被阻止",
                request_may_have_been_sent=True,
            )
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(response.stream, self._maximum_response_bytes),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


class SafeOutboundHttpClient:
    """HTTP client with a fixed origin and a DNS policy enforced at every TCP connect."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        policy: OutboundAccessPolicy,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        call_timeout_seconds: float,
        maximum_response_bytes: int,
        maximum_concurrency: int,
        ssl_context: ssl.SSLContext | None = None,
        concurrency_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        origin = _origin(endpoint_url, endpoint=True)
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("MCP 出站连接和读取超时必须大于零")
        if call_timeout_seconds < max(connect_timeout_seconds, read_timeout_seconds):
            raise ValueError("MCP 出站总超时不能短于连接或读取超时")
        if maximum_response_bytes <= 0 or maximum_concurrency <= 0:
            raise ValueError("MCP 出站响应和并发限制必须大于零")
        self._origin = origin
        self._policy = policy
        self._call_timeout_seconds = call_timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes
        self._semaphore = concurrency_semaphore or asyncio.Semaphore(maximum_concurrency)
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=read_timeout_seconds,
            pool=connect_timeout_seconds,
        )
        self._closed = False

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
    ) -> OutboundHttpResponse:
        if self._closed:
            raise RuntimeError("MCP 出站客户端已经关闭")
        target_origin = _origin(url, endpoint=False)
        if target_origin != self._origin:
            raise OutboundSecurityError(
                "tool_egress_origin_blocked",
                "MCP 出站目标来源不允许",
            )
        normalized_method = method.strip().upper()
        if not normalized_method.isalpha():
            raise OutboundSecurityError(
                "tool_egress_method_blocked",
                "MCP 出站请求方法不允许",
            )
        safe_headers = _request_headers(headers or {})
        try:
            async with asyncio.timeout(self._call_timeout_seconds):
                async with self._semaphore:
                    transport = _PinnedAsyncTransport(
                        policy=self._policy,
                        origin=self._origin,
                        ssl_context=self._ssl_context,
                        maximum_connections=1,
                        maximum_response_bytes=self._maximum_response_bytes,
                    )
                    async with httpx.AsyncClient(
                        transport=transport,
                        follow_redirects=False,
                        timeout=self._timeout,
                    ) as client, client.stream(
                        normalized_method,
                        url,
                        headers=safe_headers,
                        content=content,
                    ) as response:
                        if 300 <= response.status_code < 400:
                            raise OutboundSecurityError(
                                "tool_egress_redirect_blocked",
                                "MCP 出站响应重定向被阻止",
                                request_may_have_been_sent=True,
                            )
                        declared_length = response.headers.get("content-length")
                        if declared_length is not None:
                            try:
                                if int(declared_length) > self._maximum_response_bytes:
                                    raise OutboundSecurityError(
                                        "tool_egress_response_too_large",
                                        "MCP 出站响应过大",
                                        request_may_have_been_sent=True,
                                    )
                            except ValueError:
                                pass
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self._maximum_response_bytes:
                                raise OutboundSecurityError(
                                    "tool_egress_response_too_large",
                                    "MCP 出站响应过大",
                                    request_may_have_been_sent=True,
                                )
                        return OutboundHttpResponse(
                            status_code=response.status_code,
                            headers=tuple(response.headers.multi_items()),
                            body=bytes(body),
                        )
        except OutboundSecurityError:
            raise
        except (TimeoutError, httpcore.TimeoutException):
            raise OutboundSecurityError(
                "tool_egress_timeout",
                "MCP 出站调用超时",
                retryable=True,
                request_may_have_been_sent=True,
            ) from None
        except (httpcore.NetworkError, httpcore.ProtocolError):
            raise OutboundSecurityError(
                "tool_egress_unavailable",
                "MCP 出站目标暂时不可用",
                retryable=True,
                request_may_have_been_sent=True,
            ) from None

    @asynccontextmanager
    async def stream_client(
        self,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[httpx.AsyncClient]:
        """Yield a cookie-isolated official-MCP-compatible client for one bounded session."""
        if self._closed:
            raise RuntimeError("MCP 出站客户端已经关闭")
        safe_headers = _request_headers(headers or {})
        try:
            async with asyncio.timeout(self._call_timeout_seconds), self._semaphore:
                transport = _PinnedAsyncTransport(
                    policy=self._policy,
                    origin=self._origin,
                    ssl_context=self._ssl_context,
                    maximum_connections=1,
                    maximum_response_bytes=self._maximum_response_bytes,
                )
                client: httpx.AsyncClient

                async def clear_response_cookies(response: httpx.Response) -> None:
                    del response
                    client.cookies.clear()

                async with httpx.AsyncClient(
                    transport=transport,
                    follow_redirects=False,
                    timeout=self._timeout,
                    headers=safe_headers,
                    trust_env=False,
                    event_hooks={"response": [clear_response_cookies]},
                ) as client:
                    yield client
        except OutboundSecurityError:
            raise
        except (TimeoutError, httpcore.TimeoutException, httpx.TimeoutException):
            raise OutboundSecurityError(
                "tool_egress_timeout",
                "MCP 出站调用超时",
                retryable=True,
                request_may_have_been_sent=True,
            ) from None
        except (httpcore.NetworkError, httpcore.ProtocolError, httpx.NetworkError):
            raise OutboundSecurityError(
                "tool_egress_unavailable",
                "MCP 出站目标暂时不可用",
                retryable=True,
                request_may_have_been_sent=True,
            ) from None

    async def aclose(self) -> None:
        self._closed = True


def _host_set(values: Sequence[str]) -> frozenset[str]:
    return frozenset(_host(value) for value in values)


def _host(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("MCP 出站主机许可不合法")
    normalized = value.strip().lower().removeprefix("[").removesuffix("]").rstrip(".")
    if not normalized or any(character.isspace() for character in normalized):
        raise ValueError("MCP 出站主机许可不合法")
    if "*" in normalized or "/" in normalized or "://" in normalized:
        raise ValueError("MCP 出站主机许可只接受精确主机名或 IP")
    return normalized


def _effective_ip(address: IpAddress) -> IpAddress:
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_ip_literal(host: str) -> bool:
    try:
        ip_address(host)
    except ValueError:
        return False
    return True


def _origin(url: str, *, endpoint: bool) -> _Origin:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        raise OutboundSecurityError("tool_egress_url_invalid", "MCP 出站 URL 不合法") from None
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise OutboundSecurityError("tool_egress_url_invalid", "MCP 出站 URL 不合法")
    if parsed.username or parsed.password or parsed.fragment:
        raise OutboundSecurityError("tool_egress_url_invalid", "MCP 出站 URL 不合法")
    if endpoint and parsed.query:
        raise OutboundSecurityError("tool_egress_url_invalid", "MCP 出站端点不能包含查询参数")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return _Origin(scheme=parsed.scheme, host=_host(parsed.host), port=port)


def _request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    protected = {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    normalized: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.lower()
        if lowered in protected or lowered.startswith("proxy-"):
            raise OutboundSecurityError(
                "tool_egress_header_blocked",
                "MCP 出站请求包含受保护的 Header",
            )
        if "\r" in value or "\n" in value:
            raise OutboundSecurityError(
                "tool_egress_header_blocked",
                "MCP 出站请求 Header 不合法",
            )
        normalized[name] = value
    return normalized


__all__ = [
    "AddressResolver",
    "IpNetwork",
    "OutboundAccessPolicy",
    "OutboundHttpResponse",
    "OutboundSecurityError",
    "SafeOutboundHttpClient",
    "SystemAddressResolver",
]
