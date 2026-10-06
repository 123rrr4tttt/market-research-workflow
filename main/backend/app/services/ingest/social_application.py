from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, TypeGuard, TypedDict

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

from .social import collect_policy_and_regulation, collect_user_social_sentiment


class SocialExtractionStats(TypedDict):
    enabled: bool
    ok: int
    empty: int
    fallback: int


class SocialCollectResult(TypedDict):
    inserted: int
    skipped: int
    links: list[str]
    doc_type: str
    extraction_stats: SocialExtractionStats


_SOCIAL_RESULT_WITNESS = (
    "test:test_social_collect_result_parser_classifies_all_malformed_branches"
)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _social_collect_result_failure(
    message: str,
    *,
    path: str,
    expected_type: str,
    actual_value: object,
) -> Failure:
    return ingest_operation_failures.fail(
        "social_collect_result_invalid",
        message,
        {
            "owner": "ingest.social_application.result_parser",
            "operation": "parse_social_collect_result",
            "path": path,
            "expected_type": expected_type,
            "actual_type": type(actual_value).__name__,
            "public_exception": "TypeError",
            "public_message": message,
            "witness": _SOCIAL_RESULT_WITNESS,
        },
    )


def _mapping(value: object, *, path: str) -> dict[str, object] | Failure:
    if not _is_object_dict(value):
        return _social_collect_result_failure(
            f"{path} must be an object",
            path=path,
            expected_type="object",
            actual_value=value,
        )
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return _social_collect_result_failure(
                f"{path} keys must be strings",
                path=path,
                expected_type="string keys",
                actual_value=key,
            )
        result[key] = item
    return result


def _integer(value: object, *, path: str) -> int | Failure:
    if isinstance(value, bool) or not isinstance(value, int):
        return _social_collect_result_failure(
            f"{path} must be an integer",
            path=path,
            expected_type="integer",
            actual_value=value,
        )
    return value


def _boolean(value: object, *, path: str) -> bool | Failure:
    if not isinstance(value, bool):
        return _social_collect_result_failure(
            f"{path} must be a boolean",
            path=path,
            expected_type="boolean",
            actual_value=value,
        )
    return value


def _string(value: object, *, path: str) -> str | Failure:
    if not isinstance(value, str):
        return _social_collect_result_failure(
            f"{path} must be a string",
            path=path,
            expected_type="string",
            actual_value=value,
        )
    return value


def _string_list(value: object, *, path: str) -> list[str] | Failure:
    if not _is_object_list(value):
        return _social_collect_result_failure(
            f"{path} must be a list",
            path=path,
            expected_type="list",
            actual_value=value,
        )
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            item_path = f"{path}[{index}]"
            return _social_collect_result_failure(
                f"{item_path} must be a string",
                path=item_path,
                expected_type="string",
                actual_value=item,
            )
        result.append(item)
    return result


def try_parse_social_collect_result(value: object) -> SocialCollectResult | Failure:
    result = _mapping(value, path="social collect result")
    if isinstance(result, Failure):
        return result
    stats = _mapping(result.get("extraction_stats"), path="social collect result.extraction_stats")
    if isinstance(stats, Failure):
        return stats

    inserted = _integer(result.get("inserted"), path="social collect result.inserted")
    if isinstance(inserted, Failure):
        return inserted
    skipped = _integer(result.get("skipped"), path="social collect result.skipped")
    if isinstance(skipped, Failure):
        return skipped
    links = _string_list(result.get("links"), path="social collect result.links")
    if isinstance(links, Failure):
        return links
    doc_type = _string(result.get("doc_type"), path="social collect result.doc_type")
    if isinstance(doc_type, Failure):
        return doc_type
    enabled = _boolean(stats.get("enabled"), path="social collect result.extraction_stats.enabled")
    if isinstance(enabled, Failure):
        return enabled
    ok = _integer(stats.get("ok"), path="social collect result.extraction_stats.ok")
    if isinstance(ok, Failure):
        return ok
    empty = _integer(stats.get("empty"), path="social collect result.extraction_stats.empty")
    if isinstance(empty, Failure):
        return empty
    fallback = _integer(stats.get("fallback"), path="social collect result.extraction_stats.fallback")
    if isinstance(fallback, Failure):
        return fallback

    return SocialCollectResult(
        inserted=inserted,
        skipped=skipped,
        links=links,
        doc_type=doc_type,
        extraction_stats=SocialExtractionStats(
            enabled=enabled,
            ok=ok,
            empty=empty,
            fallback=fallback,
        ),
    )


def _raise_social_collect_result_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    public_message = str(context.get("public_message") or failure.message)
    cause = TypeError(failure.message)
    # kit:boundary owner=ingest.social_application.result_parser class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_social_collect_result_parser_preserves_type_error_abi_and_cause
    raise TypeError(public_message) from cause


def _social_collect_result(value: object) -> SocialCollectResult:
    parsed = try_parse_social_collect_result(value)
    if isinstance(parsed, Failure):
        _raise_social_collect_result_failure(parsed)
    return parsed


@dataclass(slots=True)
class SocialIngestApplicationService:
    def collect_data_api(
        self,
        *,
        keywords: list[str],
        platforms: list[str] | None = None,
        limit: int = 20,
        enable_extraction: bool = True,
        enable_subreddit_discovery: bool = True,
        base_subreddits: list[str] | None = None,
    ) -> SocialCollectResult:
        result = collect_user_social_sentiment(
            keywords=keywords,
            platforms=platforms,
            limit=limit,
            enable_extraction=enable_extraction,
            enable_subreddit_discovery=enable_subreddit_discovery,
            base_subreddits=base_subreddits,
        )
        return _social_collect_result(result)

    def collect_policy_regulation(
        self,
        *,
        keywords: list[str],
        limit: int = 20,
        enable_extraction: bool = True,
        provider: str = "google",
        start_offset: int | None = None,
        days_back: int | None = None,
        language: str = "en",
        project_key: str | None = None,
    ) -> dict[str, object]:
        return collect_policy_and_regulation(
            keywords=keywords,
            limit=limit,
            enable_extraction=enable_extraction,
            provider=provider,
            start_offset=start_offset,
            days_back=days_back,
            language=language,
            project_key=project_key,
        )
