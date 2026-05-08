from __future__ import annotations

from ipaddress import ip_address
import socket
from typing import Any
from urllib.parse import quote_plus, urlsplit

from .external_project_registry import resolve_external_project_provider_binding

EXTERNAL_PROJECT_CHANNEL_KEY = "external_project.manifest"
EXTERNAL_PROJECT_MANIFEST_KEY = "external_project_manifest"
EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION = "external_item.manifest.v1"
SUPPORTED_EXECUTION_MODES = {"rss_feed", "sitemap", "http_api"}

_CAPABILITY_KEYS = (
    "candidate_urls",
    "article_metadata",
    "article_body",
    "pdf_artifact",
)
_ACCEPTED_INPUT_KEYS = (
    "query_terms",
    "urls",
    "domains",
    "date_range",
    "max_items",
)
_DEFAULT_CAPABILITIES = {
    "candidate_urls": True,
    "article_metadata": False,
    "article_body": False,
    "pdf_artifact": False,
}
_DEFAULT_ACCEPTED_INPUTS = {
    "query_terms": True,
    "urls": False,
    "domains": False,
    "date_range": False,
    "max_items": True,
}
_BLOCKED_RUNTIME_HEADER_KEYS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-forwarded-for",
    "forwarded",
}


def has_external_project_manifest(extra: dict[str, Any] | None) -> bool:
    return isinstance(extra, dict) and isinstance(extra.get(EXTERNAL_PROJECT_MANIFEST_KEY), dict)


def is_external_project_item(item: dict[str, Any] | None) -> bool:
    payload = item if isinstance(item, dict) else {}
    if str(payload.get("channel_key") or "").strip().lower() == EXTERNAL_PROJECT_CHANNEL_KEY:
        return True
    return has_external_project_manifest(payload.get("extra") if isinstance(payload.get("extra"), dict) else None)


def validate_external_http_url(value: Any, *, field_name: str) -> str:
    return _normalize_remote_http_url(value, field_name=field_name)


def normalize_external_project_extra(
    extra: dict[str, Any] | None,
    *,
    item_key: str | None,
    display_name: str | None,
    channel_key: str | None,
) -> dict[str, Any]:
    normalized = dict(extra or {})
    has_manifest = isinstance(normalized.get(EXTERNAL_PROJECT_MANIFEST_KEY), dict)
    normalized_channel = str(channel_key or "").strip().lower()
    if normalized_channel == EXTERNAL_PROJECT_CHANNEL_KEY and not has_manifest:
        raise ValueError(f"{EXTERNAL_PROJECT_CHANNEL_KEY} requires extra.{EXTERNAL_PROJECT_MANIFEST_KEY}")
    if has_manifest:
        if normalized_channel and normalized_channel != EXTERNAL_PROJECT_CHANNEL_KEY:
            raise ValueError(
                f"extra.{EXTERNAL_PROJECT_MANIFEST_KEY} requires channel_key={EXTERNAL_PROJECT_CHANNEL_KEY}"
            )
        normalized[EXTERNAL_PROJECT_MANIFEST_KEY] = normalize_external_project_manifest(
            normalized.get(EXTERNAL_PROJECT_MANIFEST_KEY),
            item_key=item_key,
            display_name=display_name,
        )
    return normalized


def get_external_project_manifest(
    extra: dict[str, Any] | None,
    *,
    item_key: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(extra, dict):
        return None
    payload = extra.get(EXTERNAL_PROJECT_MANIFEST_KEY)
    if not isinstance(payload, dict):
        return None
    return normalize_external_project_manifest(payload, item_key=item_key, display_name=display_name)


def normalize_external_project_manifest(
    manifest: dict[str, Any] | None,
    *,
    item_key: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    payload = dict(manifest or {})
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION:
        raise ValueError(
            f"external project manifest contract_version must be {EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION}"
        )

    resolved_item_key = str(payload.get("item_key") or item_key or "").strip()
    if not resolved_item_key:
        raise ValueError("external project manifest item_key is required")
    if item_key and resolved_item_key != str(item_key).strip():
        raise ValueError("external project manifest item_key must match payload.item_key")

    resolved_display_name = str(payload.get("display_name") or display_name or "").strip()
    if not resolved_display_name:
        raise ValueError("external project manifest display_name is required")

    execution_mode = str(payload.get("execution_mode") or "").strip().lower()
    if execution_mode not in SUPPORTED_EXECUTION_MODES:
        raise ValueError(
            f"external project manifest execution_mode must be one of: {', '.join(sorted(SUPPORTED_EXECUTION_MODES))}"
        )

    normalized = {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": resolved_item_key,
        "display_name": resolved_display_name,
        "project_link": _normalize_remote_http_url(payload.get("project_link"), field_name="project_link"),
        "source_kind": _require_text(payload.get("source_kind"), field_name="source_kind"),
        "source_scope": _require_text(payload.get("source_scope"), field_name="source_scope"),
        "capabilities": _normalize_bool_map(
            payload.get("capabilities"),
            allowed_keys=_CAPABILITY_KEYS,
            defaults=_DEFAULT_CAPABILITIES,
        ),
        "accepted_inputs": _normalize_bool_map(
            payload.get("accepted_inputs"),
            allowed_keys=_ACCEPTED_INPUT_KEYS,
            defaults=_DEFAULT_ACCEPTED_INPUTS,
        ),
        "execution_mode": execution_mode,
        "runner_ref": _normalize_runner_ref(payload.get("runner_ref"), execution_mode=execution_mode),
        "normalization": _normalize_normalization(
            payload.get("normalization"),
            capabilities=payload.get("capabilities"),
        ),
        "limits": _normalize_limits(payload.get("limits")),
        "refresh_policy": _normalize_refresh_policy(payload.get("refresh_policy")),
        "provenance": _normalize_provenance(payload.get("provenance")),
    }
    runtime_config = payload.get("runtime_config") if isinstance(payload.get("runtime_config"), dict) else {}
    if isinstance(payload.get("runtime"), dict):
        runtime_config = {**runtime_config, **dict(payload.get("runtime") or {})}
    normalized["runtime_config"] = _normalize_runtime_config(runtime_config)
    normalized["provider_binding"] = resolve_external_project_provider_binding(normalized)

    if not any(bool(normalized["capabilities"].get(key)) for key in _CAPABILITY_KEYS):
        raise ValueError("external project manifest capabilities must declare at least one supported output")

    return normalized


def build_external_project_summary(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(manifest, dict):
        return None
    try:
        normalized = normalize_external_project_manifest(manifest)
    except Exception:
        return None
    return {
        "project_link": normalized.get("project_link"),
        "source_kind": normalized.get("source_kind"),
        "source_scope": normalized.get("source_scope"),
        "execution_mode": normalized.get("execution_mode"),
        "runner_ref": normalized.get("runner_ref"),
        "frontdoor_strategy": ((normalized.get("normalization") or {}).get("frontdoor_strategy")),
        "provider_binding": dict((normalized.get("provider_binding") or {})),
    }


def resolve_runner_url(
    manifest: dict[str, Any],
    *,
    query_terms: list[str] | None = None,
    domains: list[str] | None = None,
    max_items: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    runner_ref = str((manifest or {}).get("runner_ref") or "").strip()
    if runner_ref.startswith("rsshub://"):
        url = f"https://rsshub.app/{runner_ref[len('rsshub://'):].lstrip('/')}"
        return _normalize_remote_http_url(url, field_name="runner_ref")
    replacements = {
        "query": " ".join(query_terms or []).strip(),
        "query_csv": ",".join(query_terms or []),
        "query_plus": quote_plus(" ".join(query_terms or []).strip()),
        "domains_csv": ",".join(domains or []),
        "max_items": str(max_items or ""),
        "date_from": str(date_from or ""),
        "date_to": str(date_to or ""),
    }
    rendered = runner_ref
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return _normalize_remote_http_url(rendered, field_name="runner_ref")


def _normalize_runner_ref(value: Any, *, execution_mode: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("external project manifest runner_ref is required")
    if raw.startswith("rsshub://"):
        if execution_mode != "rss_feed":
            raise ValueError("rsshub:// runner_ref is only supported for rss_feed execution_mode")
        return raw
    return _normalize_remote_http_url(raw, field_name="runner_ref")


def _normalize_remote_http_url(value: Any, *, field_name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"{field_name} must use http or https")
    host = str(parts.hostname or "").strip().lower()
    if not host:
        raise ValueError(f"{field_name} host is required")
    _ensure_public_host(host, field_name=field_name)
    return raw


def _ensure_public_host(host: str, *, field_name: str) -> None:
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise ValueError(f"{field_name} cannot target localhost or local hosts")
    try:
        parsed = ip_address(host)
    except ValueError:
        _ensure_host_resolves_public(host, field_name=field_name)
        return
    if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved or parsed.is_multicast:
        raise ValueError(f"{field_name} cannot target private or non-routable hosts")


def _ensure_host_resolves_public(host: str, *, field_name: str) -> None:
    try:
        resolved = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    for row in resolved:
        sockaddr = row[4] if len(row) > 4 else None
        if not sockaddr:
            continue
        candidate = str(sockaddr[0] or "").strip()
        if not candidate:
            continue
        try:
            parsed = ip_address(candidate)
        except ValueError:
            continue
        if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved or parsed.is_multicast:
            raise ValueError(f"{field_name} cannot resolve to private or non-routable hosts")


def _require_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"external project manifest {field_name} is required")
    return text


def _normalize_bool_map(
    payload: Any,
    *,
    allowed_keys: tuple[str, ...],
    defaults: dict[str, bool],
) -> dict[str, bool]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    out = dict(defaults)
    for key in allowed_keys:
        if key in source:
            out[key] = bool(source.get(key))
    return out


def _normalize_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _normalize_limits(payload: Any) -> dict[str, int]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    return {
        "default_max_items": _normalize_int(source.get("default_max_items"), default=20, min_value=1, max_value=500),
        "max_items_cap": _normalize_int(source.get("max_items_cap"), default=100, min_value=1, max_value=2000),
        "request_timeout_ms": _normalize_int(source.get("request_timeout_ms"), default=30000, min_value=1000, max_value=120000),
    }


def _normalize_refresh_policy(payload: Any) -> dict[str, int]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    return {
        "manifest_ttl_minutes": _normalize_int(source.get("manifest_ttl_minutes"), default=60, min_value=1, max_value=10080),
        "probe_ttl_minutes": _normalize_int(source.get("probe_ttl_minutes"), default=1440, min_value=1, max_value=43200),
    }


def _normalize_provenance(payload: Any) -> dict[str, Any]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    source_refs = source.get("source_refs") if isinstance(source.get("source_refs"), list) else []
    return {
        "discovered_by": str(source.get("discovered_by") or "manual_registration").strip() or "manual_registration",
        "source_refs": [str(ref).strip() for ref in source_refs if str(ref or "").strip()],
    }


def _normalize_normalization(payload: Any, *, capabilities: Any) -> dict[str, str]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    capability_map = dict(capabilities or {}) if isinstance(capabilities, dict) else {}
    record_kind = str(source.get("record_kind") or "").strip().lower()
    if not record_kind:
        if capability_map.get("article_body"):
            record_kind = "document_candidate"
        elif capability_map.get("article_metadata"):
            record_kind = "article_metadata"
        else:
            record_kind = "candidate_url"
    frontdoor_strategy = str(source.get("frontdoor_strategy") or "").strip().lower()
    if not frontdoor_strategy:
        frontdoor_strategy = "records_allow_extract" if capability_map.get("article_body") else "records_only_defer"
    return {
        "record_kind": record_kind,
        "frontdoor_strategy": frontdoor_strategy,
    }


def _normalize_runtime_config(payload: Any) -> dict[str, Any]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    headers = source.get("headers") if isinstance(source.get("headers"), dict) else {}
    query_param_map = source.get("query_param_map") if isinstance(source.get("query_param_map"), dict) else {}
    record_mapping = source.get("record_mapping") if isinstance(source.get("record_mapping"), dict) else {}
    json_body = source.get("json_body") if isinstance(source.get("json_body"), dict) else {}
    normalized_headers: dict[str, str] = {}
    for key, value in headers.items():
        header_key = str(key).strip()
        if not header_key:
            continue
        if header_key.lower() in _BLOCKED_RUNTIME_HEADER_KEYS:
            raise ValueError(f"runtime_config.headers does not allow header: {header_key}")
        normalized_headers[header_key] = str(value)
    return {
        "method": str(source.get("method") or "GET").strip().upper() or "GET",
        "headers": normalized_headers,
        "query_param_map": {str(key): str(value) for key, value in query_param_map.items() if str(key).strip()},
        "records_path": str(source.get("records_path") or "").strip() or None,
        "record_mapping": {str(key): str(value) for key, value in record_mapping.items() if str(key).strip()},
        "json_body": json_body,
    }
