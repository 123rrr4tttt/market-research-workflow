from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from typing import Literal, NoReturn, Protocol, TypeAlias, get_args

from mrw_functorial_kit.core.provider_port_failures import (
    source_library_crawler_provider_resolution_failures,
)

from ..crawlers.base import CrawlerProvider

CrawlerProviderResolutionCode = Literal[
    "resolver_not_configured",
    "provider_unavailable",
    "provider_unsupported",
]
_CRAWLER_PROVIDER_RESOLUTION_CODES = frozenset(get_args(CrawlerProviderResolutionCode))
_INVALID_RESOLUTION_FAILURE_LIFT = "crawler provider resolution failure lift context is inconsistent"

CrawlerPayloadValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | Sequence["CrawlerPayloadValue"]
    | Set["CrawlerPayloadValue"]
    | Mapping[str, "CrawlerPayloadValue"]
)
CrawlerPayload: TypeAlias = dict[str, CrawlerPayloadValue]


def normalize_crawler_provider_type(provider_type: str) -> str:
    return str(provider_type or "").strip().lower()


def _raise_programmer_defect(message: str) -> NoReturn:
    # kit:boundary owner=source_library.crawler_provider_resolution class=PROGRAMMER_DEFECT failure_family=none witness=test:test_crawler_resolution_programmer_defect
    raise ValueError(message)


def _raise_invalid_resolution_failure_lift() -> NoReturn:
    # kit:boundary owner=source_library.crawler_provider_resolution class=PROGRAMMER_DEFECT failure_family=none witness=test:test_unconfigured_crawler_resolver_fails_closed
    raise TypeError(_INVALID_RESOLUTION_FAILURE_LIFT)


def _raise_unconfigured_resolution(provider_type: str) -> NoReturn:
    failure = source_library_crawler_provider_resolution_failures.fail(
        "resolver_not_configured",
        "crawler provider resolver is not configured",
        {"provider_type": provider_type},
    )
    if not source_library_crawler_provider_resolution_failures.matches(failure):
        _raise_invalid_resolution_failure_lift()
    # kit:boundary owner=source_library.crawler_provider_resolution class=SHELL_BOUNDARY_EXCEPTION failure_family=source_library.crawler_provider_resolution.failure witness=test:test_unconfigured_crawler_resolver_fails_closed
    raise CrawlerProviderResolutionError(
        "resolver_not_configured",
        provider_type,
        "crawler provider resolver is not configured",
    )


class CrawlerProviderResolutionError(RuntimeError):
    def __init__(
        self,
        code: CrawlerProviderResolutionCode,
        provider_type: str,
        message: str,
    ) -> None:
        if code not in _CRAWLER_PROVIDER_RESOLUTION_CODES:
            _raise_programmer_defect(f"unknown crawler provider resolution code: {code}")
        self.code = code
        self.provider_type = normalize_crawler_provider_type(provider_type)
        super().__init__(message)


class CrawlerProviderResolver(Protocol):
    def resolve(
        self,
        provider_type: str,
        *,
        channel: Mapping[str, object],
        params: Mapping[str, object],
    ) -> CrawlerProvider: ...


@dataclass(frozen=True, slots=True)
class CrawlerOutputIngestRequest:
    provider_type: str
    project_key: str
    provider_project: str
    provider_job_id: str
    base_url: str | None
    wait_timeout_seconds: float
    poll_interval_seconds: float
    source_name: str
    doc_type: str
    enable_extraction: bool
    max_items: int


@dataclass(frozen=True, slots=True)
class CrawlerOutputIngestResult:
    status: str
    payload: CrawlerPayload

    def to_plain(self) -> CrawlerPayload:
        return {**self.payload, "status": self.status}


class CrawlerOutputIngestPort(Protocol):
    def ingest(self, request: CrawlerOutputIngestRequest) -> CrawlerOutputIngestResult: ...


_CRAWLER_PROVIDER_RESOLVER: CrawlerProviderResolver | None = None
_crawler_output_ingest_port: CrawlerOutputIngestPort | None = None


def set_crawler_provider_resolver(resolver: CrawlerProviderResolver | None) -> None:
    # Retain the historical private module slot because existing callers use it
    # to isolate resolver state in tests.  Indexed assignment avoids treating
    # the legacy uppercase name as a redefined constant.
    globals()["_CRAWLER_PROVIDER_RESOLVER"] = resolver


def set_crawler_output_ingest_port(port: CrawlerOutputIngestPort | None) -> None:
    global _crawler_output_ingest_port
    _crawler_output_ingest_port = port


def get_crawler_provider_resolver() -> CrawlerProviderResolver | None:
    return _CRAWLER_PROVIDER_RESOLVER


def get_crawler_output_ingest_port() -> CrawlerOutputIngestPort | None:
    return _crawler_output_ingest_port


def ingest_crawler_output(request: CrawlerOutputIngestRequest) -> CrawlerOutputIngestResult:
    port = _crawler_output_ingest_port
    if port is None:
        return CrawlerOutputIngestResult(
            status="failed",
            payload={"reason": "crawler output ingest port is not configured"},
        )
    return port.ingest(request)


def resolve_crawler_provider(
    provider_type: str,
    *,
    channel: Mapping[str, object],
    params: Mapping[str, object],
) -> CrawlerProvider:
    normalized_provider_type = normalize_crawler_provider_type(provider_type)
    resolver = _CRAWLER_PROVIDER_RESOLVER
    if resolver is None:
        _raise_unconfigured_resolution(normalized_provider_type)
    return resolver.resolve(
        normalized_provider_type,
        channel=channel,
        params=params,
    )


__all__ = [
    "CrawlerOutputIngestPort",
    "CrawlerOutputIngestRequest",
    "CrawlerOutputIngestResult",
    "CrawlerPayload",
    "CrawlerPayloadValue",
    "CrawlerProvider",
    "CrawlerProviderResolver",
    "CrawlerProviderResolutionCode",
    "CrawlerProviderResolutionError",
    "get_crawler_output_ingest_port",
    "get_crawler_provider_resolver",
    "ingest_crawler_output",
    "normalize_crawler_provider_type",
    "resolve_crawler_provider",
    "set_crawler_output_ingest_port",
    "set_crawler_provider_resolver",
]
