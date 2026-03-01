from __future__ import annotations

import os
from typing import Any, Dict

from ...project_customization import get_project_customization
from .handler_registry import get

_REGISTERED = False
_CRAWLER_PROVIDER_TYPES = {"scrapy", "crawlee", "meltano"}


def _ensure_handlers_registered() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    from . import adapters  # noqa: F401 - trigger handler registration (lazy to avoid circular import)
    _REGISTERED = True


def resolve_credential(cred_name: str, project_key: str | None) -> str | None:
    normalized = (project_key or "").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in normalized)
    if normalized:
        project_scoped = f"PROJECT_{normalized}_{cred_name}"
        value = os.getenv(project_scoped)
        if value:
            return value
    return os.getenv(cred_name)


def validate_params(params: Dict[str, Any], param_schema: Dict[str, Any]) -> None:
    required = param_schema.get("required", [])
    if not isinstance(required, list):
        return
    missing = [key for key in required if key not in params]
    if missing:
        raise ValueError(f"missing required params: {missing}")


def _iter_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(v) for v in value if v is not None]
    else:
        return []
    return [v.strip() for v in raw_values if str(v).strip()]


def _normalize_identity(value: str | None) -> str:
    return str(value or "").strip().lower()


def _extract_gray_rollout_allowlist(execution_policy: Dict[str, Any]) -> tuple[bool, set[str], set[str]]:
    def _collect_values(
        container: Dict[str, Any],
        *,
        names: tuple[str, ...],
    ) -> tuple[bool, set[str]]:
        configured = False
        values: set[str] = set()
        for name in names:
            if name in container:
                configured = True
                for raw in _iter_string_values(container.get(name)):
                    values.add(_normalize_identity(raw))
        return configured, values

    rollout_nodes: list[Dict[str, Any]] = []
    if isinstance(execution_policy, dict):
        rollout_nodes.append(execution_policy)
        for key in ("gray_release", "gray_rollout", "rollout", "crawler_gray_release", "crawler_rollout"):
            value = execution_policy.get(key)
            if isinstance(value, dict):
                rollout_nodes.append(value)

    project_keys: set[str] = set()
    item_keys: set[str] = set()
    configured = False

    project_fields = ("projects", "project_keys", "project_key_allowlist", "allow_projects")
    item_fields = ("items", "item_keys", "item_key_allowlist", "allow_items")

    for node in rollout_nodes:
        node_configured, node_projects = _collect_values(node, names=project_fields)
        configured = configured or node_configured
        project_keys.update(node_projects)

        node_configured, node_items = _collect_values(node, names=item_fields)
        configured = configured or node_configured
        item_keys.update(node_items)

        allowlist = node.get("allowlist")
        if isinstance(allowlist, dict):
            configured = True
            _, nested_projects = _collect_values(allowlist, names=project_fields)
            _, nested_items = _collect_values(allowlist, names=item_fields)
            project_keys.update(nested_projects)
            item_keys.update(nested_items)

    return configured, project_keys, item_keys


def _is_crawler_rollout_allowed(
    *,
    execution_policy: Dict[str, Any],
    project_key: str | None,
    item_key: str | None,
) -> bool:
    configured, project_allowlist, item_allowlist = _extract_gray_rollout_allowlist(execution_policy)
    if not configured:
        # Backward-compatible default: no rollout policy means keep crawler path.
        return True

    if "*" in project_allowlist or "*" in item_allowlist:
        return True

    normalized_project = _normalize_identity(project_key)
    normalized_item = _normalize_identity(item_key)
    return (normalized_project in project_allowlist) or (normalized_item in item_allowlist)


def _run_via_crawler_provider_registry(
    *,
    channel: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None,
    provider_type: str,
) -> Dict[str, Any]:
    from .. import crawlers as _crawlers  # noqa: F401 - trigger builtin crawler provider registration
    from ..crawlers.base import CrawlerDispatchRequest
    from ..crawlers.registry import get_provider
    from ..crawlers.scrapyd_result_ingest import ingest_scrapyd_job_output

    provider = get_provider(provider_type)
    if provider is None:
        raise ValueError(f"unsupported crawler provider_type: {provider_type}")

    provider_config = channel.get("provider_config")
    if not isinstance(provider_config, dict):
        provider_config = {}
    execution_policy = channel.get("execution_policy")
    if not isinstance(execution_policy, dict):
        execution_policy = {}

    spider = str(params.get("spider") or params.get("spider_name") or provider_config.get("spider") or "").strip()
    project = str(
        params.get("scrapy_project")
        or params.get("project")
        or provider_config.get("project")
        or project_key
        or ""
    ).strip()
    if not project:
        raise ValueError(f"{provider_type} channel requires project/project_key")
    if not spider:
        raise ValueError(f"{provider_type} channel requires spider/spider_name")

    dispatch = provider.dispatch(
        CrawlerDispatchRequest(
            provider=provider_type,
            project=project,
            spider=spider,
            arguments=dict(params.get("arguments") or {}),
            settings=dict(params.get("settings") or {}),
            version=params.get("version"),
            priority=params.get("priority"),
            job_id=params.get("job_id"),
        )
    )
    ok_status = {"ok", "queued", "scheduled", "running", "accepted"}
    status = str(dispatch.provider_status or "").strip().lower()
    errors: list[str] = [] if status in ok_status else [f"crawler provider status: {status or 'unknown'}"]
    inserted = 0
    updated = 0
    skipped = 0
    output_ingest: dict[str, Any] | None = None
    if (
        provider_type == "scrapy"
        and project_key
        and dispatch.provider_job_id
        and bool(params.get("auto_ingest_crawler_output", True))
        and status in ok_status
    ):
        try:
            output_ingest = ingest_scrapyd_job_output(
                project_key=str(project_key),
                scrapy_project=project,
                job_id=str(dispatch.provider_job_id),
                base_url=str(params.get("scrapyd_base_url") or "") or None,
                wait_timeout_seconds=float(params.get("crawler_ingest_wait_timeout_seconds") or 8.0),
                poll_interval_seconds=float(params.get("crawler_ingest_poll_interval_seconds") or 0.8),
                source_name=str(params.get("crawler_output_source_name") or "") or None,
                doc_type=str(params.get("crawler_output_doc_type") or "news"),
                enable_extraction=bool(params.get("crawler_output_enable_extraction", False)),
                max_items=int(params.get("crawler_output_max_items") or 100),
            )
            if isinstance(output_ingest, dict):
                import_result = output_ingest.get("import_result")
                if isinstance(import_result, dict):
                    inserted = int(import_result.get("inserted") or 0)
                    updated = int(import_result.get("updated") or 0)
                    skipped = int(import_result.get("skipped") or 0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"crawler output ingest failed: {exc}")

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "provider_job_id": dispatch.provider_job_id,
        "provider_type": dispatch.provider_type,
        "provider_status": dispatch.provider_status,
        "attempt_count": dispatch.attempt_count,
        "execution_policy": execution_policy,
        "provider_config": provider_config,
        "output_ingest": output_ingest,
    }


def run_channel(
    *,
    channel: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None = None,
    item_key: str | None = None,
) -> Dict[str, Any]:
    _ensure_handlers_registered()
    credential_refs = channel.get("credential_refs") or []
    if isinstance(credential_refs, list):
        missing_creds = [
            c for c in credential_refs if isinstance(c, str) and resolve_credential(c, project_key) is None
        ]
        if missing_creds:
            raise ValueError(f"missing credentials for channel {channel.get('channel_key')}: {missing_creds}")

    validate_params(params=params, param_schema=channel.get("param_schema") or {})

    provider_type = str(channel.get("provider_type") or "native").strip().lower()
    if provider_type in _CRAWLER_PROVIDER_TYPES:
        execution_policy = channel.get("execution_policy")
        if not isinstance(execution_policy, dict):
            execution_policy = {}
        if _is_crawler_rollout_allowed(
            execution_policy=execution_policy,
            project_key=project_key,
            item_key=item_key,
        ):
            return _run_via_crawler_provider_registry(
                channel=channel,
                params=params,
                project_key=project_key,
                provider_type=provider_type,
            )

    provider = str(channel.get("provider", "")).strip().lower()
    kind = str(channel.get("kind", "")).strip().lower()

    customization = get_project_customization(project_key)
    project_handlers = customization.get_channel_handlers()
    handler = project_handlers.get((provider, kind)) if project_handlers else None
    if handler is not None:
        return handler(channel, params, project_key)

    handler = get(provider, kind)
    if handler is None:
        raise ValueError(f"unsupported channel provider/kind: {provider}/{kind}")
    if provider == "policy" and not str(params.get("state") or "").strip():
        raise ValueError("policy channel requires params.state")
    if provider == "market":
        keywords = params.get("keywords") or params.get("query_terms")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError("market channel requires params.keywords or params.query_terms")
    if provider == "google_news":
        keywords = params.get("keywords")
        if isinstance(keywords, str):
            keywords = [keywords]
            params = {**params, "keywords": keywords}
        if not isinstance(keywords, list) or not keywords:
            raise ValueError("google_news requires params.keywords list")
    return handler(params, project_key)


__all__ = ["run_channel", "resolve_credential", "validate_params"]
