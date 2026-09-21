from __future__ import annotations

from typing import Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import source_library_contract_failures


EXTERNAL_PROJECT_PROVIDER_REGISTRY_VERSION = "external_project.provider_registry.v1"

_PROVIDER_BINDINGS: dict[str, dict[str, str]] = {
    "rss_feed": {
        "provider_key": "external_project.rss_feed",
        "provider_family": "feed_aggregator",
        "capability_family": "candidate_discovery",
        "adapter_ref": "source_library.adapters.external_project.rss_feed",
    },
    "sitemap": {
        "provider_key": "external_project.sitemap",
        "provider_family": "site_index",
        "capability_family": "candidate_discovery",
        "adapter_ref": "source_library.adapters.external_project.sitemap",
    },
    "http_api": {
        "provider_key": "external_project.http_api",
        "provider_family": "api_provider",
        "capability_family": "record_materialization",
        "adapter_ref": "source_library.adapters.external_project.http_api",
    },
    "article_extractor": {
        "provider_key": "external_project.article_extractor",
        "provider_family": "article_extraction_stack",
        "capability_family": "article_body_extraction",
        "adapter_ref": "source_library.adapters.external_project.article_extractor",
    },
    "python_library": {
        "provider_key": "external_project.python_library",
        "provider_family": "python_library_wrapper",
        "capability_family": "record_materialization",
        "adapter_ref": "source_library.adapters.external_project.python_library",
    },
    "cli_or_container": {
        "provider_key": "external_project.cli_or_container",
        "provider_family": "cli_or_container_wrapper",
        "capability_family": "bounded_external_tool",
        "adapter_ref": "source_library.adapters.external_project.cli_or_container",
    },
}

_FAILURE_WITNESS = "test:test_w01_source_export_failures"


def _provider_failure(code: str, message: str, *, site: str) -> Failure:
    return source_library_contract_failures.fail(
        code,
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": source_library_contract_failures.name,
            "operation": "source_library.external_project_registry",
            "owner": "source_library.external_project_registry",
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _FAILURE_WITNESS,
        },
    )


def _raise_provider_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not source_library_contract_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_library_contract_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != "ValueError"
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.external_project_registry.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_source_export_failures
        raise TypeError("external-project provider failure lift context is incomplete or inconsistent")
    # kit:boundary owner=source_library.external_project_registry.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_w01_source_export_failures
    raise ValueError(str(context["public_message"]))


def list_external_project_provider_bindings() -> list[dict[str, str]]:
    return [
        {
            "registry_version": EXTERNAL_PROJECT_PROVIDER_REGISTRY_VERSION,
            "execution_mode": execution_mode,
            **binding,
        }
        for execution_mode, binding in _PROVIDER_BINDINGS.items()
    ]


def resolve_external_project_provider_binding(manifest: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(manifest or {})
    execution_mode = str(payload.get("execution_mode") or "").strip().lower()
    binding = _PROVIDER_BINDINGS.get(execution_mode)
    if binding is None:
        _raise_provider_failure(
            _provider_failure(
                "external_project_execution_mode_unsupported",
                f"unsupported external project execution_mode: {execution_mode or '<missing>'}",
                site="resolve_external_project_provider_binding.execution_mode",
            )
        )

    capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    accepted_inputs = payload.get("accepted_inputs") if isinstance(payload.get("accepted_inputs"), dict) else {}
    normalization = payload.get("normalization") if isinstance(payload.get("normalization"), dict) else {}
    runtime_config = payload.get("runtime_config") if isinstance(payload.get("runtime_config"), dict) else {}
    return {
        "registry_version": EXTERNAL_PROJECT_PROVIDER_REGISTRY_VERSION,
        "execution_mode": execution_mode,
        **binding,
        "record_kind": str(normalization.get("record_kind") or "").strip().lower() or None,
        "frontdoor_strategy": str(normalization.get("frontdoor_strategy") or "").strip().lower() or None,
        "supports_article_body": bool(capabilities.get("article_body")),
        "supports_pdf_artifact": bool(capabilities.get("pdf_artifact")),
        "accepts_query_terms": bool(accepted_inputs.get("query_terms")),
        "accepts_domains": bool(accepted_inputs.get("domains")),
        "accepts_date_range": bool(accepted_inputs.get("date_range")),
        "accepts_urls": bool(accepted_inputs.get("urls")),
        "parser_capability": {
            "parser": str(runtime_config.get("parser") or "trafilatura_or_heuristic").strip().lower(),
            "article_body": bool(capabilities.get("article_body")) or execution_mode == "article_extractor",
            "fallback_states": [
                "article_body_extracted",
                "metadata_only_fallback",
                "fetch_error_fallback",
            ],
        },
    }
