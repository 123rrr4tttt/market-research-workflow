from __future__ import annotations

import json
from typing import Any
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


_RUNNER_BY_PROVIDER_KEY = {
    "external_project.rss_feed": lambda *, manifest, params: _run_rss_feed_manifest(manifest=manifest, params=params),
    "external_project.sitemap": lambda *, manifest, params: _run_sitemap_manifest(manifest=manifest, params=params),
    "external_project.http_api": lambda *, manifest, params: _run_http_api_manifest(manifest=manifest, params=params),
    "external_project.article_extractor": lambda *, manifest, params: _run_article_extractor_manifest(manifest=manifest, params=params),
    "external_project.python_library": lambda *, manifest, params: _run_python_library_manifest(manifest=manifest, params=params),
    "external_project.cli_or_container": lambda *, manifest, params: _run_cli_or_container_manifest(manifest=manifest, params=params),
}

_PYTHON_LIBRARY_RUNNERS = {
    "source_library.fixture_records.v1": lambda *, manifest, params, runtime, runtime_config: _run_fixture_records(
        manifest=manifest,
        runtime=runtime,
        runtime_config=runtime_config,
        source="python_library",
    ),
}

_CLI_OR_CONTAINER_RUNNERS = {
    "source_library.fixture_json.v1": lambda *, manifest, params, runtime, runtime_config: _run_fixture_json_output(
        manifest=manifest,
        runtime=runtime,
        runtime_config=runtime_config,
    ),
}


def handle_external_project_manifest(params: dict[str, Any], project_key: str | None) -> dict[str, Any]:
    _ = project_key
    item = params.get("_source_library_item") if isinstance(params.get("_source_library_item"), dict) else {}
    manifest = get_external_project_manifest(
        item.get("extra") if isinstance(item.get("extra"), dict) else {},
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


def _run_rss_feed_manifest(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
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
        errors=execution.errors,
        diagnostics={
            "feed_url": feed_url,
            "pages_scanned": execution.pages_scanned,
            "used_term_fallback": execution.used_term_fallback,
            "probe": dict(execution.diagnostics or {}),
        },
    )


def _run_sitemap_manifest(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
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
        max_depth=int(params.get("max_depth") or 2),
        max_sitemaps=int(params.get("max_sitemaps") or 30),
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
        errors=execution.errors,
        diagnostics={
            "sitemap_url": sitemap_url,
            "pages_scanned": execution.pages_scanned,
            "used_term_fallback": execution.used_term_fallback,
            "probe": dict(execution.diagnostics or {}),
        },
    )


def _run_http_api_manifest(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = manifest.get("runtime_config") if isinstance(manifest.get("runtime_config"), dict) else {}
    method = str(runtime_config.get("method") or "GET").strip().upper() or "GET"
    request_headers = dict(runtime_config.get("headers") or {})
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
        payload = _render_json_template(runtime_config.get("json_body") or {}, runtime=runtime)
        response = default_http_client.post_json(
            url,
            json=payload,
            params=request_params,
            headers=request_headers,
            timeout=timeout_seconds,
        )
    else:
        response = default_http_client.get_json(
            url,
            params=request_params,
            headers=request_headers,
            timeout=timeout_seconds,
        )
    rows = _extract_http_api_rows(response, records_path=runtime_config.get("records_path"))
    record_mapping = runtime_config.get("record_mapping") if isinstance(runtime_config.get("record_mapping"), dict) else {}
    records = []
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


def _run_article_extractor_manifest(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = manifest.get("runtime_config") if isinstance(manifest.get("runtime_config"), dict) else {}
    request_headers = dict(runtime_config.get("headers") or {})
    timeout_seconds = float(runtime["request_timeout_ms"]) / 1000.0
    parser_capability = _build_parser_capability(manifest=manifest, runtime_config=runtime_config)

    target_urls = list(runtime.get("urls") or [])[: runtime["max_items"]]
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

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    fallback_states: list[dict[str, Any]] = []
    for index, url in enumerate(target_urls):
        try:
            html = default_http_client.get_text(
                url,
                headers=request_headers,
                timeout=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - runner diagnostics must preserve fallback state.
            state = {
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
        state = {
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


def _run_python_library_manifest(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = manifest.get("runtime_config") if isinstance(manifest.get("runtime_config"), dict) else {}
    runner_id = _resolve_registered_runner_id(
        manifest=manifest,
        runtime_config=runtime_config,
        allowed_scheme="python-library",
    )
    runner = _PYTHON_LIBRARY_RUNNERS.get(runner_id)
    if runner is None:
        raise ValueError(f"unsupported python_library runner_id: {runner_id or '<missing>'}")
    return runner(manifest=manifest, params=params, runtime=runtime, runtime_config=runtime_config)


def _run_cli_or_container_manifest(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    runtime = _resolve_runtime_inputs(manifest=manifest, params=params)
    runtime_config = manifest.get("runtime_config") if isinstance(manifest.get("runtime_config"), dict) else {}
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
    manifest: dict[str, Any],
    runtime: dict[str, Any],
    runtime_config: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    rows = runtime_config.get("fixture_records") if isinstance(runtime_config.get("fixture_records"), list) else []
    record_mapping = runtime_config.get("record_mapping") if isinstance(runtime_config.get("record_mapping"), dict) else {}
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
    manifest: dict[str, Any],
    runtime: dict[str, Any],
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    payload = _load_fixture_output_json(runtime_config.get("fixture_output_json"))
    rows = _extract_http_api_rows(payload, records_path=runtime_config.get("records_path"))
    record_mapping = runtime_config.get("record_mapping") if isinstance(runtime_config.get("record_mapping"), dict) else {}
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


def _resolve_runtime_inputs(*, manifest: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    accepted = manifest.get("accepted_inputs") if isinstance(manifest.get("accepted_inputs"), dict) else {}
    limits = manifest.get("limits") if isinstance(manifest.get("limits"), dict) else {}
    query_terms = _normalize_terms(params.get("query_terms")) if accepted.get("query_terms", True) else []
    urls = _normalize_runtime_urls(params.get("urls")) if accepted.get("urls") else []
    domains = _normalize_terms(params.get("domains")) if accepted.get("domains") else []
    requested_max_items = _to_optional_int(params.get("max_items")) if accepted.get("max_items", True) else None
    default_max_items = int(limits.get("default_max_items") or 20)
    max_items_cap = int(limits.get("max_items_cap") or 100)
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
        "request_timeout_ms": int(limits.get("request_timeout_ms") or 30000),
    }


def _build_probe_result(
    *,
    manifest: dict[str, Any],
    runtime: dict[str, Any],
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]] | list[str],
    diagnostics: dict[str, Any],
    status_override: str | None = None,
) -> dict[str, Any]:
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
            "frontdoor_strategy": ((manifest.get("normalization") or {}).get("frontdoor_strategy")),
            "provider_binding": dict((manifest.get("provider_binding") or {})),
            "accepted_inputs": dict(manifest.get("accepted_inputs") or {}),
            "runtime_inputs": runtime,
            "diagnostics": diagnostics,
        },
    }


def _build_record(
    *,
    manifest: dict[str, Any],
    url: str,
    title: str | None,
    summary: str | None,
    index: int,
    content_text: str | None = None,
    published_at: str | None = None,
    author: str | None = None,
    language: str | None = None,
    artifact_url: str | None = None,
    record_meta_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record_meta: dict[str, Any] = {
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
    row: Any,
    manifest: dict[str, Any],
    record_mapping: dict[str, str],
    index: int,
) -> dict[str, Any] | None:
    if isinstance(row, str):
        url = str(row).strip()
        if not url:
            return None
        return _build_record(manifest=manifest, url=url, title=None, summary=None, index=index)
    if not isinstance(row, dict):
        return None
    url = _extract_path_value(row, record_mapping.get("url") or "url")
    if not url:
        url = _extract_path_value(row, "link")
    title = _extract_path_value(row, record_mapping.get("title") or "title")
    summary = _extract_path_value(row, record_mapping.get("summary") or "summary")
    content_text = _extract_path_value(row, record_mapping.get("content_text") or "content")
    published_at = _extract_path_value(row, record_mapping.get("published_at") or "published_at")
    author = _extract_path_value(row, record_mapping.get("author") or "author")
    language = _extract_path_value(row, record_mapping.get("language") or "language")
    artifact_url = _extract_path_value(row, record_mapping.get("artifact_url") or "artifact_url")
    if not artifact_url:
        artifact_url = _extract_path_value(row, "pdf_url")
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
    rows: list[Any],
    manifest: dict[str, Any],
    record_mapping: dict[str, str],
    max_items: int,
) -> list[dict[str, Any]]:
    records = []
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
    manifest: dict[str, Any],
    runtime_config: dict[str, Any],
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


def _load_fixture_output_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        return json.loads(text)
    if isinstance(value, (dict, list)):
        return value
    return {}


def _build_http_api_params(*, runtime: dict[str, Any], runtime_config: dict[str, Any]) -> dict[str, Any]:
    query_param_map = runtime_config.get("query_param_map") if isinstance(runtime_config.get("query_param_map"), dict) else {}
    values = {
        "query_terms": " ".join(runtime.get("query_terms") or []),
        "domains": ",".join(runtime.get("domains") or []),
        "max_items": runtime.get("max_items"),
        "date_from": runtime.get("date_from"),
        "date_to": runtime.get("date_to"),
    }
    out: dict[str, Any] = {}
    for source_key, target_key in query_param_map.items():
        target = str(target_key or "").strip()
        value = values.get(str(source_key or "").strip())
        if not target or value in (None, "", []):
            continue
        out[target] = value
    return out


def _render_json_template(payload: dict[str, Any], *, runtime: dict[str, Any]) -> dict[str, Any]:
    rendered: dict[str, Any] = {}
    replacements = {
        "query": " ".join(runtime.get("query_terms") or []),
        "domains_csv": ",".join(runtime.get("domains") or []),
        "max_items": str(runtime.get("max_items") or ""),
        "date_from": str(runtime.get("date_from") or ""),
        "date_to": str(runtime.get("date_to") or ""),
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


def _extract_http_api_rows(payload: Any, *, records_path: str | None) -> list[Any]:
    if records_path:
        resolved = _extract_nested_value(payload, records_path)
        if isinstance(resolved, list):
            return list(resolved)
        return [resolved] if resolved not in (None, "") else []
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        for key in ("items", "records", "data", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return list(candidate)
        return [payload]
    return []


def _extract_path_value(payload: dict[str, Any], path: str) -> str:
    resolved = _extract_nested_value(payload, path)
    if resolved is None:
        return ""
    text = str(resolved).strip()
    return text


def _extract_nested_value(payload: Any, path: str) -> Any:
    current = payload
    for segment in [part for part in str(path or "").split(".") if part]:
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except Exception:
                return None
            continue
        return None
    return current


def _normalize_terms(value: Any) -> list[str]:
    if isinstance(value, str):
        terms = [value]
    elif isinstance(value, list):
        terms = [str(entry or "") for entry in value]
    else:
        terms = []
    out: list[str] = []
    for entry in terms:
        normalized = str(entry or "").strip()
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _normalize_runtime_urls(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []
    out: list[str] = []
    for entry in raw_values:
        raw = str(entry or "").strip()
        if not raw:
            continue
        normalized = validate_external_http_url(raw, field_name="runtime url")
        if normalized not in out:
            out.append(normalized)
    return out


def _build_parser_capability(*, manifest: dict[str, Any], runtime_config: dict[str, Any]) -> dict[str, Any]:
    capabilities = manifest.get("capabilities") if isinstance(manifest.get("capabilities"), dict) else {}
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


def _article_extraction_meta(*, state: dict[str, Any], parser_capability: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "external_project.article_body_extraction.v1",
        "parser_capability": dict(parser_capability),
        "state": str(state.get("state") or "").strip(),
        "extractor": str(state.get("extractor") or parser_capability.get("parser") or "").strip() or None,
        "confidence": str(state.get("confidence") or "").strip() or None,
        "content_chars": int(state.get("content_chars") or 0),
        "error": str(state.get("error") or "").strip() or None,
    }


def _normalize_date(value: Any) -> str | None:
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


def _to_optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _stringify_error(entry: Any) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        return str(entry.get("error") or entry.get("message") or entry).strip()
    return str(entry or "").strip()
