from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypeGuard

from app.services.source_library.provider_ports import (
    CrawlerOutputIngestPort,
    CrawlerOutputIngestRequest,
    CrawlerOutputIngestResult,
    CrawlerPayload,
    CrawlerPayloadValue,
    CrawlerProvider,
    CrawlerProviderResolutionError,
    CrawlerProviderResolver,
    normalize_crawler_provider_type,
    set_crawler_output_ingest_port,
    set_crawler_provider_resolver,
)

_CRAWLER_PROVIDER_TIMEOUT_NUMERIC_ERROR = "crawler provider timeout must be numeric"


def _is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, dict)


def _payload_mapping_values(value: Mapping[object, object]) -> bool:
    return all(isinstance(key, str) and _is_crawler_payload_value(item) for key, item in value.items())


def _payload_iterable_values(value: Iterable[object]) -> bool:
    return all(_is_crawler_payload_value(item) for item in value)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, dict)


def _is_object_iterable(value: object) -> TypeGuard[Iterable[object]]:
    return isinstance(value, (list, tuple, set, frozenset))


def _is_crawler_payload_value(value: object) -> TypeGuard[CrawlerPayloadValue]:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if _is_object_mapping(value):
        return _payload_mapping_values(value)
    if _is_object_iterable(value):
        return _payload_iterable_values(value)
    return False


def _is_crawler_payload(value: object) -> TypeGuard[CrawlerPayload]:
    return _is_object_mapping(value) and _is_crawler_payload_value(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(_CRAWLER_PROVIDER_TIMEOUT_NUMERIC_ERROR)


class DefaultCrawlerProviderResolver:
    def resolve(
        self,
        provider_type: str,
        *,
        channel: Mapping[str, object],
        params: Mapping[object, object],
    ) -> CrawlerProvider:
        from ..services.crawlers.registry import get_provider, register_provider

        normalized = normalize_crawler_provider_type(provider_type)
        provider = get_provider(normalized)
        if provider is not None:
            return provider

        if normalized == "scrapy":
            try:
                from ..services.crawlers.providers.scrapy import ScrapyCrawlerProvider

                raw_provider_config = channel.get("provider_config")
                provider_config: Mapping[str, object] = (
                    raw_provider_config if _is_string_object_mapping(raw_provider_config) else {}
                )
                base_url = (
                    str(params.get("scrapyd_base_url") or "").strip()
                    or str(provider_config.get("scrapyd_base_url") or "").strip()
                    or str(provider_config.get("base_url") or "").strip()
                    or None
                )
                timeout_raw = params.get("scrapyd_timeout") or provider_config.get("timeout")
                timeout = _optional_float(timeout_raw)
                provider = ScrapyCrawlerProvider(base_url=base_url, timeout=timeout)
                register_provider(normalized, provider)
                return provider  # noqa: TRY300
            except Exception as exc:  # noqa: BLE001
                raise CrawlerProviderResolutionError(
                    "provider_unavailable",
                    normalized,
                    f"crawler provider '{normalized}' is unavailable: {exc}",
                ) from exc

        raise CrawlerProviderResolutionError(
            "provider_unsupported",
            normalized,
            f"unsupported crawler provider_type: {normalized}",
        )


class ScrapydCrawlerOutputIngestPort:
    def ingest(self, request: CrawlerOutputIngestRequest) -> CrawlerOutputIngestResult:
        if normalize_crawler_provider_type(request.provider_type) != "scrapy":
            return CrawlerOutputIngestResult(
                status="failed",
                payload={"reason": f"unsupported crawler output provider: {request.provider_type}"},
            )
        from ..services.crawlers.scrapyd_result_ingest import ingest_scrapyd_job_output

        raw_result = ingest_scrapyd_job_output(
            project_key=request.project_key,
            scrapy_project=request.provider_project,
            job_id=request.provider_job_id,
            base_url=request.base_url,
            wait_timeout_seconds=request.wait_timeout_seconds,
            poll_interval_seconds=request.poll_interval_seconds,
            source_name=request.source_name,
            material_type=request.material_type,
            enable_extraction=request.enable_extraction,
            max_items=request.max_items,
        )
        if not _is_crawler_payload(raw_result):
            return CrawlerOutputIngestResult(
                status="failed",
                payload={"reason": "crawler output ingest adapter returned a non-object result"},
            )
        return CrawlerOutputIngestResult(
            status=str(raw_result.get("status") or "failed"),
            payload={key: value for key, value in raw_result.items() if key != "status"},
        )


def configure_source_library_adapters() -> None:
    set_crawler_provider_resolver(DefaultCrawlerProviderResolver())
    set_crawler_output_ingest_port(ScrapydCrawlerOutputIngestPort())


__all__ = [
    "CrawlerProviderResolver",
    "CrawlerOutputIngestPort",
    "DefaultCrawlerProviderResolver",
    "ScrapydCrawlerOutputIngestPort",
    "configure_source_library_adapters",
]
