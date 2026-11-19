from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol, TypeGuard, TypedDict
from urllib.parse import urlsplit

from ...http.client import default_http_client
from ...resource_pool.article_extraction_service import extract_article_content_from_html
from ...resource_pool.search_template_service import execute_feed_probe, execute_sitemap_probe
from ..external_project import (
    build_external_project_summary,
    get_external_project_manifest,
    resolve_runner_url,
    validate_external_http_url,
)
from ..external_project_registry import resolve_external_project_provider_binding



class ManifestRunner(Protocol):
    def __call__(self, *, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]: ...


class RegisteredRunner(Protocol):
    def __call__(
        self,
        *,
        manifest: dict[str, object],
        params: Mapping[object, object],
        runtime: RuntimeInputs,
        runtime_config: dict[str, object],
    ) -> dict[str, object]: ...


class RuntimeInputs(TypedDict):
    query_terms: list[str]
    urls: list[str]
    domains: list[str]
    max_items: int
    date_from: str | None
    date_to: str | None
    request_timeout_ms: int


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _object(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _string_map(value: object) -> dict[str, str]:
    source = _object(value)
    return {str(key): str(item) for key, item in source.items()}


def _nullable_str(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def handle_external_project_manifest(params: Mapping[object, object], project_key: str | None) -> dict[str, object]:
    _ = project_key
    item = _object(params.get("_source_library_item"))
    # V2 declares parameter bindings that legacy runners do not consume. Reject
    # before normalization (DNS) or dispatch, even if callers enable the item.
    from ..external_integration import INTEGRATION_MANIFEST_VERSION
    raw_manifest = _object(_object(item.get("extra")).get("external_project_manifest"))
    if raw_manifest.get("contract_version") == INTEGRATION_MANIFEST_VERSION or "integration" in raw_manifest:
        raise ValueError("integration_runtime_not_connected: integration specifications cannot execute yet")
    manifest = get_external_project_manifest(
        _object(item.get("extra")),
        item_key=str(item.get("item_key") or "").strip() or None,
        display_name=str(item.get("name") or "").strip() or None,
    )
    if manifest is None:
        raise ValueError("external project item requires a normalized external project manifest")

    provider_binding = resolve_external_project_provider_binding(manifest)
    execution_mode = str(provider_binding.get("execution_mode") or "").strip().lower()
    provider_key = str(provider_binding.get("provider_key") or "").strip()
    runner = _RUNNER_BY_PROVIDER_KEY.get(provider_key)
    if runner is None:
        raise ValueError(f"external project registry does not define a runtime runner for {provider_key or execution_mode}")
    result = runner(manifest=manifest, params=params)

    result.setdefault("provider", "external_project")
    result.setdefault("project_link", manifest.get("project_link"))
    result.setdefault("source_kind", manifest.get("source_kind"))
    result.setdefault("execution_mode", execution_mode)
    result.setdefault("runner_ref", manifest.get("runner_ref"))
    result.setdefault("manifest_summary", build_external_project_summary(manifest))
    result.setdefault("provider_binding", provider_binding)
    return result


def _run_rss_feed_manifest(*, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    feed_url = resolve_runner_url(
        manifest,
        query_terms=runtime["query_terms"],
        domains=runtime["domains"],
        max_items=runtime["max_items"],
        date_from=runtime["date_from"],
        date_to=runtime["date_to"],
    )
    execution = execute_feed_probe(
        feed_url=feed_url,
        query_terms=runtime["query_terms"],
        probe_timeout=float(runtime["request_timeout_ms"]) / 1000.0,
        allow_term_fallback=bool(params.get("allow_term_fallback", True)),
    )
    records = [
        _build_record(
            manifest=manifest,
            url=str(candidate.url or "").strip(),
            title=str(candidate.title or "").strip() or None,
            summary=str(candidate.text or "").strip() or None,
            index=index,
        )
        for index, candidate in enumerate(execution.selected_candidates[: runtime["max_items"]])
        if str(candidate.url or "").strip()
    ]
    return _build_probe_result(
        manifest=manifest,
        runtime=runtime,
        records=records,
        errors=[dict(entry) for entry in execution.errors],
        diagnostics={
            "feed_url": feed_url,
            "pages_scanned": execution.pages_scanned,
            "used_term_fallback": execution.used_term_fallback,
            "probe": _object(execution.diagnostics),
        },
    )


def _run_sitemap_manifest(*, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    sitemap_url = resolve_runner_url(
        manifest,
        query_terms=runtime["query_terms"],
        domains=runtime["domains"],
        max_items=runtime["max_items"],
        date_from=runtime["date_from"],
        date_to=runtime["date_to"],
    )
    execution = execute_sitemap_probe(
        sitemap_url=sitemap_url,
        query_terms=runtime["query_terms"],
        probe_timeout=float(runtime["request_timeout_ms"]) / 1000.0,
        max_depth=_to_optional_int(params.get("max_depth")) or 2,
        max_sitemaps=_to_optional_int(params.get("max_sitemaps")) or 30,
        allow_term_fallback=bool(params.get("allow_term_fallback", True)),
    )
    records = [
        _build_record(
            manifest=manifest,
            url=str(candidate.url or "").strip(),
            title=str(candidate.title or "").strip() or None,
            summary=str(candidate.text or "").strip() or None,
            index=index,
        )
        for index, candidate in enumerate(execution.selected_candidates[: runtime["max_items"]])
        if str(candidate.url or "").strip()
    ]
    return _build_probe_result(
        manifest=manifest,
        runtime=runtime,
        records=records,
        errors=[dict(entry) for entry in execution.errors],
        diagnostics={
            "sitemap_url": sitemap_url,
            "pages_scanned": execution.pages_scanned,
            "used_term_fallback": execution.used_term_fallback,
            "probe": _object(execution.diagnostics),
        },
    )


def _run_http_api_manifest(*, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = _object(manifest.get("runtime_config"))
    method = str(runtime_config.get("method") or "GET").strip().upper() or "GET"
    request_headers = _string_map(runtime_config.get("headers"))
    url = resolve_runner_url(
        manifest,
        query_terms=runtime["query_terms"],
        domains=runtime["domains"],
        max_items=runtime["max_items"],
        date_from=runtime["date_from"],
        date_to=runtime["date_to"],
    )
    request_params = _build_http_api_params(runtime=runtime, runtime_config=runtime_config)
    timeout_seconds = float(runtime["request_timeout_ms"]) / 1000.0
    if method == "POST":
        payload = _render_json_template(_object(runtime_config.get("json_body")), runtime=runtime)
        response: object = default_http_client.post_json(
            url,
            json=payload,
            params=request_params,
            headers=request_headers,
            timeout=timeout_seconds,
        )
    else:
        response: object = default_http_client.get_json(
            url,
            params=request_params,
            headers=request_headers,
            timeout=timeout_seconds,
        )
    rows = _extract_http_api_rows(response, records_path=_nullable_str(runtime_config.get("records_path")))
    record_mapping = _string_map(runtime_config.get("record_mapping"))
    records: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if len(records) >= runtime["max_items"]:
            break
        normalized = _build_http_api_record(
            row=row,
            manifest=manifest,
            record_mapping=record_mapping,
            index=index,
        )
        if normalized:
            records.append(normalized)
    return _build_probe_result(
        manifest=manifest,
        runtime=runtime,
        records=records,
        errors=[],
        diagnostics={
            "endpoint": url,
            "method": method,
            "records_path": runtime_config.get("records_path"),
            "records_total": len(rows),
        },
    )


def _run_article_extractor_manifest(*, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = _object(manifest.get("runtime_config"))
    request_headers = _string_map(runtime_config.get("headers"))
    timeout_seconds = float(runtime["request_timeout_ms"]) / 1000.0
    parser_capability = _build_parser_capability(manifest=manifest, runtime_config=runtime_config)

    target_urls = runtime["urls"][: runtime["max_items"]]
    if not target_urls:
        target_urls = [
            resolve_runner_url(
                manifest,
                query_terms=runtime["query_terms"],
                domains=runtime["domains"],
                max_items=runtime["max_items"],
                date_from=runtime["date_from"],
                date_to=runtime["date_to"],
            )
        ]

    records: list[dict[str, object]] = []
    errors: list[object] = []
    fallback_states: list[dict[str, object]] = []
    for index, url in enumerate(target_urls):
        try:
            html = default_http_client.get_text(
                url,
                headers=request_headers,
                timeout=timeout_seconds,
                follow_redirects=True,
            )
        except Exception as exc:  # noqa: BLE001 - runner diagnostics must preserve fallback state.
            state: dict[str, object] = {
                "url": url,
                "state": "fetch_error_fallback",
                "error": str(exc),
            }
            fallback_states.append(state)
            errors.append({"url": url, "error": str(exc), "fallback_state": state["state"]})
            records.append(
                _build_record(
                    manifest=manifest,
                    url=url,
                    title=None,
                    summary=None,
                    index=index,
                    record_meta_extra={"article_extraction": _article_extraction_meta(state=state, parser_capability=parser_capability)},
                )
            )
            continue

        extraction = extract_article_content_from_html(html=html, url=url, title=None)
        content_text = str(getattr(extraction, "content", "") or "").strip()
        state_name = "article_body_extracted" if content_text else "metadata_only_fallback"
        state: dict[str, object] = {
            "url": url,
            "state": state_name,
            "extractor": str(getattr(extraction, "extractor", "") or parser_capability["parser"]),
            "confidence": str(getattr(extraction, "confidence", "") or "unknown"),
            "content_chars": len(content_text),
        }
        fallback_states.append(state)
        records.append(
            _build_record(
                manifest=manifest,
                url=url,
                title=str(getattr(extraction, "title", "") or "").strip() or None,
                summary=content_text[:800] if content_text else None,
                content_text=content_text or None,
                index=index,
                record_meta_extra={"article_extraction": _article_extraction_meta(state=state, parser_capability=parser_capability)},
            )
        )

    extracted_count = sum(1 for state in fallback_states if state.get("state") == "article_body_extracted")
    status_override = "ok" if extracted_count == len(target_urls) and not errors else ("error" if not records else "partial")
    return _build_probe_result(
        manifest=manifest,
        runtime=runtime,
        records=records,
        errors=errors,
        diagnostics={
            "target_urls": target_urls,
            "parser_capability": parser_capability,
            "fallback_states": fallback_states,
            "article_body_extracted": extracted_count,
            "records_total": len(records),
        },
        status_override=status_override,
    )


def _run_python_library_manifest(*, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = _object(manifest.get("runtime_config"))
    runner_id = _resolve_registered_runner_id(
        manifest=manifest,
        runtime_config=runtime_config,
        allowed_scheme="python-library",
    )
    runner = _PYTHON_LIBRARY_RUNNERS.get(runner_id)
    if runner is None:
        raise ValueError(f"unsupported python_library runner_id: {runner_id or '<missing>'}")
    return runner(manifest=manifest, params=params, runtime=runtime, runtime_config=runtime_config)


def _run_cli_or_container_manifest(*, manifest: dict[str, object], params: Mapping[object, object]) -> dict[str, object]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = _object(manifest.get("runtime_config"))
    runner_id = _resolve_registered_runner_id(
        manifest=manifest,
        runtime_config=runtime_config,
        allowed_scheme=("cli", "container"),
    )
    runner = _CLI_OR_CONTAINER_RUNNERS.get(runner_id)
    if runner is None:
        raise ValueError(f"unsupported cli_or_container runner_id: {runner_id or '<missing>'}")
    return runner(manifest=manifest, params=params, runtime=runtime, runtime_config=runtime_config)


def _run_fixture_records(
    *,
    manifest: dict[str, object],
    runtime: RuntimeInputs,
    runtime_config: dict[str, object],
    source: str,
) -> dict[str, object]:
    rows = _object_list(runtime_config.get("fixture_records"))
    record_mapping = _string_map(runtime_config.get("record_mapping"))
    records = _build_mapped_records(
        rows=rows,
        manifest=manifest,
        record_mapping=record_mapping,
        max_items=runtime["max_items"],
    )
    return _build_probe_result(
        manifest=manifest,
        runtime=runtime,
        records=records,
        errors=[] if records else [{"error": "registered python_library runner returned no records"}],
        diagnostics={
            "runner_contract": "external_project.python_library_runner.v1",
            "runner_id": _resolve_registered_runner_id(
                manifest=manifest,
                runtime_config=runtime_config,
                allowed_scheme="python-library",
            ),
            "runner_source": source,
            "records_total": len(rows),
        },
    )


def _run_fixture_json_output(
    *,
    manifest: dict[str, object],
    runtime: RuntimeInputs,
    runtime_config: dict[str, object],
) -> dict[str, object]:
    payload = _load_fixture_output_json(runtime_config.get("fixture_output_json"))
    rows = _extract_http_api_rows(payload, records_path=_nullable_str(runtime_config.get("records_path")))
    record_mapping = _string_map(runtime_config.get("record_mapping"))
    records = _build_mapped_records(
        rows=rows,
        manifest=manifest,
        record_mapping=record_mapping,
        max_items=runtime["max_items"],
    )
    return _build_probe_result(
        manifest=manifest,
        runtime=runtime,
        records=records,
        errors=[] if records else [{"error": "registered cli_or_container runner returned no records"}],
        diagnostics={
            "runner_contract": "external_project.cli_or_container_runner.v1",
            "runner_id": _resolve_registered_runner_id(
                manifest=manifest,
                runtime_config=runtime_config,
                allowed_scheme=("cli", "container"),
            ),
            "execution_policy": "predeclared_wrapper_no_arbitrary_shell",
            "records_total": len(rows),
        },
    )


_RUNNER_BY_PROVIDER_KEY: dict[str, ManifestRunner] = {
    "external_project.rss_feed": _run_rss_feed_manifest,
    "external_project.sitemap": _run_sitemap_manifest,
    "external_project.http_api": _run_http_api_manifest,
    "external_project.article_extractor": _run_article_extractor_manifest,
    "external_project.python_library": _run_python_library_manifest,
    "external_project.cli_or_container": _run_cli_or_container_manifest,
}


def _run_python_fixture_runner(
    *,
    manifest: dict[str, object],
    params: Mapping[object, object],
    runtime: RuntimeInputs,
    runtime_config: dict[str, object],
) -> dict[str, object]:
    return _run_fixture_records(
        manifest=manifest,
        runtime=runtime,
        runtime_config=runtime_config,
        source="python_library",
    )


def _run_cli_fixture_runner(
    *,
    manifest: dict[str, object],
    params: Mapping[object, object],
    runtime: RuntimeInputs,
    runtime_config: dict[str, object],
) -> dict[str, object]:
    return _run_fixture_json_output(
        manifest=manifest,
        runtime=runtime,
        runtime_config=runtime_config,
    )


_PYTHON_LIBRARY_RUNNERS: dict[str, RegisteredRunner] = {
    "source_library.fixture_records.v1": _run_python_fixture_runner,
}

_CLI_OR_CONTAINER_RUNNERS: dict[str, RegisteredRunner] = {
    "source_library.fixture_json.v1": _run_cli_fixture_runner,
}


def _resolve_runtime_inputs(*, manifest: dict[str, object], params: Mapping[object, object]) -> RuntimeInputs:
    accepted = _object(manifest.get("accepted_inputs"))
    limits = _object(manifest.get("limits"))
    query_terms = _normalize_terms(params.get("query_terms")) if accepted.get("query_terms", True) else []
    urls = _normalize_runtime_urls(params.get("urls")) if accepted.get("urls") else []
    domains = _normalize_terms(params.get("domains")) if accepted.get("domains") else []
    requested_max_items = _to_optional_int(params.get("max_items")) if accepted.get("max_items", True) else None
    default_max_items = _to_optional_int(limits.get("default_max_items")) or 20
    max_items_cap = _to_optional_int(limits.get("max_items_cap")) or 100
    max_items = requested_max_items if requested_max_items is not None else default_max_items
    max_items = max(1, min(max_items, max_items_cap))

    date_from = None
    date_to = None
    if accepted.get("date_range"):
        date_from = _normalize_date(params.get("date_from") or params.get("start_time"))
        date_to = _normalize_date(params.get("date_to") or params.get("end_time"))
    return {
        "query_terms": query_terms,
        "urls": urls,
        "domains": domains,
        "max_items": max_items,
        "date_from": date_from,
        "date_to": date_to,
        "request_timeout_ms": _to_optional_int(limits.get("request_timeout_ms")) or 30000,
    }


def _build_probe_result(
    *,
    manifest: dict[str, object],
    runtime: RuntimeInputs,
    records: list[dict[str, object]],
    errors: list[object],
    diagnostics: dict[str, object],
    status_override: str | None = None,
) -> dict[str, object]:
    messages = [_stringify_error(entry) for entry in errors]
    candidates = [str(record.get("url") or "").strip() for record in records if str(record.get("url") or "").strip()]
    result_status = status_override or ("partial" if records and messages else ("ok" if records else ("error" if messages else "partial")))
    return {
        "status": result_status,
        "inserted": len(records),
        "updated": 0,
        "skipped": 0,
        "records": records,
        "candidates": candidates,
        "errors": [message for message in messages if message],
        "error_details": list(errors or []),
        "runtime_diagnostics": {
            "source_kind": manifest.get("source_kind"),
            "source_scope": manifest.get("source_scope"),
            "frontdoor_strategy": _object(manifest.get("normalization")).get("frontdoor_strategy"),
            "provider_binding": _object(manifest.get("provider_binding")),
            "accepted_inputs": _object(manifest.get("accepted_inputs")),
            "runtime_inputs": runtime,
            "diagnostics": diagnostics,
        },
    }


def _build_record(
    *,
    manifest: dict[str, object],
    url: str,
    title: str | None,
    summary: str | None,
    index: int,
    content_text: str | None = None,
    published_at: str | None = None,
    author: str | None = None,
    language: str | None = None,
    artifact_url: str | None = None,
    record_meta_extra: dict[str, object] | None = None,
) -> dict[str, object]:
    record_meta: dict[str, object] = {
        "origin": "external_project_manifest",
        "external_project": build_external_project_summary(manifest) or {},
    }
    if isinstance(record_meta_extra, dict):
        record_meta.update({str(key): value for key, value in record_meta_extra.items() if value not in (None, "", [], {})})
    if artifact_url:
        record_meta["artifact_ref"] = {
            "artifact_source": "external_project",
            "artifact_role": "project_artifact",
            "source_locator": artifact_url,
        }
    return {
        "record_id": f"external:{manifest.get('item_key')}:{index}",
        "url": url,
        "title": title,
        "content_text": content_text,
        "summary": summary,
        "published_at": published_at,
        "author": author,
        "language": language,
        "source_label": str(manifest.get("display_name") or "external_project"),
        "record_meta": record_meta,
        "raw_ref": {
            "source": "external_project",
            "runner_ref": manifest.get("runner_ref"),
            "project_link": manifest.get("project_link"),
        },
    }


def _build_http_api_record(
    *,
    row: object,
    manifest: dict[str, object],
    record_mapping: dict[str, str],
    index: int,
) -> dict[str, object] | None:
    if isinstance(row, str):
        url = str(row).strip()
        if not url:
            return None
        return _build_record(manifest=manifest, url=url, title=None, summary=None, index=index)
    if not _is_object(row):
        return None
    object_row = dict(row)
    url = _extract_path_value(object_row, record_mapping.get("url") or "url")
    if not url:
        url = _extract_path_value(object_row, "link")
    title = _extract_path_value(object_row, record_mapping.get("title") or "title")
    summary = _extract_path_value(object_row, record_mapping.get("summary") or "summary")
    content_text = _extract_path_value(object_row, record_mapping.get("content_text") or "content")
    published_at = _extract_path_value(object_row, record_mapping.get("published_at") or "published_at")
    author = _extract_path_value(object_row, record_mapping.get("author") or "author")
    language = _extract_path_value(object_row, record_mapping.get("language") or "language")
    artifact_url = _extract_path_value(object_row, record_mapping.get("artifact_url") or "artifact_url")
    if not artifact_url:
        artifact_url = _extract_path_value(object_row, "pdf_url")
    if not url and not title and not content_text:
        return None
    return _build_record(
        manifest=manifest,
        url=url or "",
        title=title or None,
        summary=summary or None,
        content_text=content_text or None,
        published_at=published_at or None,
        author=author or None,
        language=language or None,
        artifact_url=artifact_url or None,
        index=index,
    )


def _build_mapped_records(
    *,
    rows: list[object],
    manifest: dict[str, object],
    record_mapping: dict[str, str],
    max_items: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if len(records) >= max_items:
            break
        normalized = _build_http_api_record(
            row=row,
            manifest=manifest,
            record_mapping=record_mapping,
            index=index,
        )
        if normalized:
            records.append(normalized)
    return records


def _resolve_registered_runner_id(
    *,
    manifest: dict[str, object],
    runtime_config: dict[str, object],
    allowed_scheme: str | tuple[str, ...],
) -> str:
    configured = str(runtime_config.get("runner_id") or "").strip()
    if configured:
        return configured
    runner_ref = str(manifest.get("runner_ref") or "").strip()
    parts = urlsplit(runner_ref)
    allowed_schemes = {allowed_scheme} if isinstance(allowed_scheme, str) else set(allowed_scheme)
    if parts.scheme not in allowed_schemes:
        raise ValueError(f"runner_ref scheme must be one of: {', '.join(sorted(allowed_schemes))}")
    runner_id = "/".join(part for part in [parts.netloc, parts.path.lstrip("/")] if part).strip()
    return runner_id


def _load_fixture_output_json(value: object) -> object:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        decoded: object = json.loads(text)
        return decoded
    if _is_object(value) or _is_object_list(value):
        return value
    return {}


def _build_http_api_params(*, runtime: RuntimeInputs, runtime_config: dict[str, object]) -> dict[str, object]:
    query_param_map = _string_map(runtime_config.get("query_param_map"))
    values: dict[str, object] = {
        "query_terms": " ".join(runtime["query_terms"]),
        "domains": ",".join(runtime["domains"]),
        "max_items": runtime["max_items"],
        "date_from": runtime["date_from"],
        "date_to": runtime["date_to"],
    }
    out: dict[str, object] = {}
    for source_key, target_key in query_param_map.items():
        target = str(target_key or "").strip()
        value = values.get(str(source_key or "").strip())
        if not target or value in (None, "", []):
            continue
        out[target] = value
    return out


def _render_json_template(payload: dict[str, object], *, runtime: RuntimeInputs) -> dict[str, object]:
    rendered: dict[str, object] = {}
    replacements = {
        "query": " ".join(runtime["query_terms"]),
        "domains_csv": ",".join(runtime["domains"]),
        "max_items": str(runtime["max_items"]),
        "date_from": str(runtime["date_from"] or ""),
        "date_to": str(runtime["date_to"] or ""),
    }
    for key, value in payload.items():
        if isinstance(value, str):
            current = value
            for placeholder, replacement in replacements.items():
                current = current.replace(f"{{{{{placeholder}}}}}", replacement)
            rendered[str(key)] = current
        else:
            rendered[str(key)] = value
    return rendered


def _extract_http_api_rows(payload: object, *, records_path: str | None) -> list[object]:
    if records_path:
        resolved = _extract_nested_value(payload, records_path)
        if _is_object_list(resolved):
            return list(resolved)
        return [resolved] if resolved not in (None, "") else []
    if _is_object_list(payload):
        return list(payload)
    if _is_object(payload):
        for key in ("items", "records", "data", "results"):
            candidate = payload.get(key)
            if _is_object_list(candidate):
                return list(candidate)
        return [payload]
    return []


def _extract_path_value(payload: dict[str, object], path: str) -> str:
    resolved = _extract_nested_value(payload, path)
    if resolved is None:
        return ""
    text = str(resolved).strip()
    return text


def _extract_nested_value(payload: object, path: str) -> object:
    current = payload
    for segment in [part for part in str(path or "").split(".") if part]:
        if _is_object(current):
            current = current.get(segment)
            continue
        if _is_object_list(current):
            items = _object_list(current)
            try:
                index = int(segment)
                current = items[index] if -len(items) <= index < len(items) else None
            except Exception:
                return None
            continue
        return None
    return current


def _normalize_terms(value: object) -> list[str]:
    if isinstance(value, str):
        terms = [value]
    else:
        terms = [str(entry or "") for entry in _object_list(value)]
    out: list[str] = []
    for entry in terms:
        normalized = str(entry or "").strip()
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _normalize_runtime_urls(value: object) -> list[str]:
    raw_values = [value] if isinstance(value, str) else _object_list(value)
    out: list[str] = []
    for entry in raw_values:
        raw = str(entry or "").strip()
        if not raw:
            continue
        normalized = validate_external_http_url(raw, field_name="runtime url")
        if normalized not in out:
            out.append(normalized)
    return out


def _build_parser_capability(*, manifest: dict[str, object], runtime_config: dict[str, object]) -> dict[str, object]:
    capabilities = _object(manifest.get("capabilities"))
    return {
        "contract_version": "external_project.article_extraction_runner.v1",
        "parser": str(runtime_config.get("parser") or "trafilatura_or_heuristic").strip().lower(),
        "article_body": bool(capabilities.get("article_body")),
        "fallback_states": [
            "article_body_extracted",
            "metadata_only_fallback",
            "fetch_error_fallback",
        ],
    }


def _article_extraction_meta(*, state: dict[str, object], parser_capability: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "external_project.article_body_extraction.v1",
        "parser_capability": dict(parser_capability),
        "state": str(state.get("state") or "").strip(),
        "extractor": str(state.get("extractor") or parser_capability.get("parser") or "").strip() or None,
        "confidence": str(state.get("confidence") or "").strip() or None,
        "content_chars": _to_optional_int(state.get("content_chars")) or 0,
        "error": str(state.get("error") or "").strip() or None,
    }


def _normalize_date(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) != 3:
        return None
    if not all(part.isdigit() for part in parts):
        return None
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        return None
    return raw


def _to_optional_int(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        if not isinstance(value, int | float | str):
            return None
        return int(value)
    except Exception:
        return None


def _stringify_error(entry: object) -> str:
    if isinstance(entry, str):
        return entry.strip()
    payload = _object(entry)
    if payload:
        return str(payload.get("error") or payload.get("message") or entry).strip()
    return str(entry or "").strip()
