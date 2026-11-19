"""Search contract discovery and persistence for site entries."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping
import copy
import threading
import time
from typing import Any, NoReturn, TypeGuard

from functorial_kit import Failure

from mrw_functorial_kit.core.provider_port_failures import resource_pool_contract_failures

from .http_port import (
    HttpFetchError,
    SameOriginHttpTargetPolicy,
    fetch_html as fetch_html_through_port,
    http_fetch_target_policy_supported,
    scoped_http_target_policy,
)
from .search_template_service import (
    SearchTemplateExecutionResult,
    execute_feed_probe,
    execute_search_template,
    execute_sitemap_probe,
    normalize_search_template_placeholders,
)
from .site_entry_discovery import extract_homepage_query_contract_clues, extract_opensearch_templates
from .site_entries import get_site_entry_by_url, upsert_site_entry
from .url_utils import domain_from_url, normalize_url

_DEFAULT_TEMPLATE_PATHS = (
    "/search?q={{q}}",
    "/search?query={{q}}",
    "/?s={{q}}",
)

_DEFAULT_QUERY_SUFFIXES = (
    "",
    "news",
    "blog",
    "release",
    "announcement",
    "pricing",
)

_QUERY_DISCOVERY_ORIGINS = frozenset(
    {"evidence_form", "known_template", "agent_proposal", "heuristic_path"}
)
_QUERY_DISCOVERY_REQUIRED_TOOLS = (
    "source.discovery.plan",
    "source.web.search",
    "ingest.source_library.run",
)
_QUERY_DISCOVERY_BLOCKING_REASONS = frozenset({"unsafe_target", "unsafe_target_policy_unavailable"})

@dataclass(frozen=True)
class _QueryDiscoveryIntegerSpec:
    default: int
    minimum: int
    maximum: int

    def json_schema(self) -> dict[str, object]:
        return {
            "type": "integer",
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class _QueryDiscoveryNumberSpec:
    default: float
    minimum: float
    maximum: float

    def json_schema(self) -> dict[str, object]:
        return {
            "type": "number",
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


_QUERY_DISCOVERY_MAX_REQUESTS_SPEC = _QueryDiscoveryIntegerSpec(default=4, minimum=0, maximum=12)
_QUERY_DISCOVERY_MAX_TEMPLATES_SPEC = _QueryDiscoveryIntegerSpec(default=3, minimum=0, maximum=6)
_QUERY_DISCOVERY_TIMEOUT_SPEC = _QueryDiscoveryNumberSpec(default=15.0, minimum=0.0, maximum=60.0)
_QUERY_DISCOVERY_NUMERIC_SPECS: dict[str, _QueryDiscoveryIntegerSpec | _QueryDiscoveryNumberSpec] = {
    "query_discovery_max_requests": _QUERY_DISCOVERY_MAX_REQUESTS_SPEC,
    "query_discovery_max_templates": _QUERY_DISCOVERY_MAX_TEMPLATES_SPEC,
    "query_discovery_timeout_seconds": _QUERY_DISCOVERY_TIMEOUT_SPEC,
}

_QUERY_DISCOVERY_PARAMETER_SCHEMA: dict[str, object] = {
    "agent_search_templates": {
        "type": "array",
        "maxItems": 6,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["template", "evidence_url", "reason"],
            "properties": {
                "template": {"type": "string", "minLength": 1},
                "evidence_url": {"type": "string", "minLength": 1},
                "reason": {"type": "string", "minLength": 1},
            },
        },
    },
}


_RESOURCE_POOL_FAILURE_WITNESS = "test:test_resource_pool_failure_preserves_public_errors"
_RESOURCE_POOL_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _contract_failure(code: str, message: str, *, operation: str, site: str) -> Failure:
    return resource_pool_contract_failures.fail(
        code,
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": resource_pool_contract_failures.name,
            "operation": operation,
            "owner": site,
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _RESOURCE_POOL_FAILURE_WITNESS,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    context = failure.context or {}
    if (
        not resource_pool_contract_failures.matches(failure)
        or _RESOURCE_POOL_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=resource_pool.search_contract_discovery.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_resource_pool_failure_preserves_public_errors
        raise TypeError("resource pool failure lift context is incomplete or inconsistent")
    # kit:boundary owner=resource_pool.search_contract_discovery.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=resource_pool.contract.failure witness=test:test_resource_pool_failure_preserves_public_errors
    raise exception_type(str(context["public_message"]))


def _optional_number(value: object) -> int | float | str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    return value



@dataclass(frozen=True)
class SearchContractProbeRow:
    template: str
    query_text: str
    candidate_count: int
    selected_count: int
    search_service: str
    score: float


@dataclass(frozen=True)
class SearchContractDiscoveryResult:
    site_url: str
    domain: str
    entry_type: str
    templates_tried: list[str]
    suffixes_tried: list[str]
    best_template: str | None
    best_suffix: str | None
    best_score: float
    probe_rows: list[SearchContractProbeRow]
    persisted_entry: dict[str, Any] | None


@dataclass
class QueryDiscoveryBudget:
    """Thread-safe bounded budget for transient query-contract exploration.

    The budget covers only discovery requests and template attempts made by
    ``resolve_query_contract``; it is not a claim over all ordinary fetch,
    search, or ingest execution budgets.
    """

    max_requests: int
    max_templates: int
    timeout_seconds: float
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = self.clock()
        self._used_requests = 0
        self._used_templates_by_source: dict[str, int] = {}
        self._last_denial_reason: str | None = None

    @staticmethod
    def _clamp_int(value: object, spec: _QueryDiscoveryIntegerSpec) -> int:
        default, minimum, maximum = spec.default, spec.minimum, spec.maximum
        normalized = _optional_number(value)
        try:
            parsed = int(normalized) if normalized is not None else default
        except (TypeError, ValueError, OverflowError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _clamp_float(value: object, spec: _QueryDiscoveryNumberSpec) -> float:
        default, minimum, maximum = spec.default, spec.minimum, spec.maximum
        normalized = _optional_number(value)
        try:
            parsed = float(normalized) if normalized is not None else default
        except (TypeError, ValueError, OverflowError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    @classmethod
    def from_params(cls, params: Mapping[str, object]) -> "QueryDiscoveryBudget":
        return cls(
            max_requests=cls._clamp_int(
                params.get("query_discovery_max_requests"),
                _QUERY_DISCOVERY_MAX_REQUESTS_SPEC,
            ),
            max_templates=cls._clamp_int(
                params.get("query_discovery_max_templates"),
                _QUERY_DISCOVERY_MAX_TEMPLATES_SPEC,
            ),
            timeout_seconds=cls._clamp_float(
                params.get("query_discovery_timeout_seconds"),
                _QUERY_DISCOVERY_TIMEOUT_SPEC,
            ),
        )

    @property
    def deadline_exceeded(self) -> bool:
        return self.clock() - self._started_at >= self.timeout_seconds

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.timeout_seconds - (self.clock() - self._started_at))

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.clock() - self._started_at)

    @property
    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            used_requests = self._used_requests
            used_templates_by_source = dict(self._used_templates_by_source)
            last_denial_reason = self._last_denial_reason
        used_templates = sum(used_templates_by_source.values())
        least_remaining_templates = self.max_templates - max(
            used_templates_by_source.values(),
            default=0,
        )
        return {
            "max_requests": self.max_requests,
            "used_requests": used_requests,
            "remaining_requests": max(0, self.max_requests - used_requests),
            "max_templates": self.max_templates,
            "used_templates": used_templates,
            "remaining_templates": max(0, least_remaining_templates),
            "used_templates_by_source": used_templates_by_source,
            "remaining_templates_by_source": {
                source_key: max(0, self.max_templates - used)
                for source_key, used in used_templates_by_source.items()
            },
            "timeout_seconds": self.timeout_seconds,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "remaining_seconds": round(self.remaining_seconds, 6),
            "deadline_exceeded": self.deadline_exceeded,
            "last_denial_reason": last_denial_reason,
        }

    def remaining(self) -> dict[str, object]:
        diagnostics = self.diagnostics
        return {
            "remaining_requests": diagnostics["remaining_requests"],
            "remaining_templates": diagnostics["remaining_templates"],
            "remaining_templates_by_source": diagnostics["remaining_templates_by_source"],
            "remaining_seconds": diagnostics["remaining_seconds"],
        }

    def _deny(self, reason: str) -> tuple[bool, str]:
        with self._lock:
            self._last_denial_reason = reason
        return False, reason

    def record_denial(self, reason: str) -> None:
        with self._lock:
            self._last_denial_reason = reason

    def try_acquire_request(self, url: str) -> tuple[bool, str | None]:
        if self.max_requests <= 0:
            return self._deny("discovery_disabled")
        if self.deadline_exceeded:
            return self._deny("deadline_exceeded")
        with self._lock:
            if self._used_requests >= self.max_requests:
                self._last_denial_reason = "request_budget_exhausted"
                return False, "request_budget_exhausted"
            if self.deadline_exceeded:
                self._last_denial_reason = "deadline_exceeded"
                return False, "deadline_exceeded"
            self._used_requests += 1
            self._last_denial_reason = None
            return True, None

    def try_acquire_template(
        self,
        template: str,
        *,
        source_key: str = "default",
    ) -> tuple[bool, str | None]:
        _ = str(template or "").strip()
        source = str(source_key or "default").strip() or "default"
        if self.max_templates <= 0:
            return self._deny("discovery_disabled")
        if self.deadline_exceeded:
            return self._deny("deadline_exceeded")
        with self._lock:
            source_used = self._used_templates_by_source.get(source, 0)
            if source_used >= self.max_templates:
                self._last_denial_reason = "request_budget_exhausted"
                return False, "request_budget_exhausted"
            if self.deadline_exceeded:
                self._last_denial_reason = "deadline_exceeded"
                return False, "deadline_exceeded"
            self._used_templates_by_source[source] = source_used + 1
            self._last_denial_reason = None
            return True, None


@dataclass(frozen=True, slots=True)
class QueryContractCandidate:
    entry_type: str
    template: str
    origin: str
    evidence_url: str
    reason: str


@dataclass(frozen=True, slots=True)
class QueryContractResolution:
    status: str
    entry: dict[str, object] | None
    diagnostics: dict[str, object]
    exploration_request: dict[str, object] | None
    execution: SearchTemplateExecutionResult | None = None


def query_discovery_parameter_schema() -> dict[str, object]:
    """Return the authoritative JSON-Schema-shaped query-discovery parameters."""

    schema: dict[str, object] = {}
    for key, spec in _QUERY_DISCOVERY_NUMERIC_SPECS.items():
        schema[key] = spec.json_schema()
    for key, value in _QUERY_DISCOVERY_PARAMETER_SCHEMA.items():
        schema[key] = copy.deepcopy(value)
    return schema


def _candidate_templates(site_url: str, template: str | None) -> list[str]:
    out: list[str] = []
    normalized_template = normalize_search_template_placeholders(template)
    if normalized_template and "{{q}}" in normalized_template:
        out.append(normalized_template)
    normalized_site = normalize_url(site_url) or str(site_url or "").strip()
    if normalized_site:
        if "{{q}}" in normalized_site and normalized_site not in out:
            out.append(normalized_site)
        if "?" not in normalized_site:
            for path in _DEFAULT_TEMPLATE_PATHS:
                candidate = f"{normalized_site.rstrip('/')}{path}"
                if candidate not in out:
                    out.append(candidate)
    return out


def _query_variants(query_terms: list[str], suffixes: list[str]) -> list[tuple[str, str]]:
    base = " ".join([term for term in query_terms if str(term or "").strip()]).strip()
    if not base:
        _raise_contract_failure(
            _contract_failure(
                "query_terms_required",
                "query_terms is required",
                operation="discover_search_contract",
                site="resource_pool.search_contract_discovery._query_variants",
            )
        )
    variants: list[tuple[str, str]] = []
    for suffix in suffixes:
        normalized_suffix = str(suffix or "").strip()
        query_text = f"{base} {normalized_suffix}".strip()
        variants.append((query_text, normalized_suffix))
    return variants


def discover_search_contract(
    *,
    scope: str,
    project_key: str | None,
    site_url: str,
    query_terms: list[str] | str,
    suffixes: list[str] | None = None,
    max_pages: int = 1,
    probe_timeout: float = 6.0,
    persist: bool = True,
) -> SearchContractDiscoveryResult:
    terms = query_terms if isinstance(query_terms, list) else [str(query_terms or "").strip()]
    entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=site_url) or {
        "site_url": site_url,
        "entry_type": "search_template",
        "template": None,
        "extra": {},
        "capabilities": {},
    }
    normalized_site_url = normalize_url(str(entry.get("site_url") or site_url).strip()) or str(site_url or "").strip()
    domain = str(entry.get("domain") or domain_from_url(normalized_site_url) or "").strip().lower()
    templates = _candidate_templates(normalized_site_url, str(entry.get("template") or "").strip() or None)
    suffix_rows = _query_variants(terms, list(suffixes or _DEFAULT_QUERY_SUFFIXES))
    rows: list[SearchContractProbeRow] = []
    best_template: str | None = None
    best_suffix: str | None = None
    best_score = -1.0

    for template in templates:
        for query_text, suffix in suffix_rows:
            execution = execute_search_template(
                template=template,
                query_terms=[query_text],
                params={"max_pages": max(1, int(max_pages)), "enable_search_service_fallback": True},
                probe_timeout=float(probe_timeout or 6.0),
                allow_term_fallback=False,
                entry_domain=domain or None,
            )
            selected_count = len(execution.selected_candidates or [])
            candidate_count = len(execution.raw_candidates or [])
            score = float(selected_count * 10 + candidate_count)
            rows.append(
                SearchContractProbeRow(
                    template=template,
                    query_text=query_text,
                    candidate_count=candidate_count,
                    selected_count=selected_count,
                    search_service=str(execution.diagnostics.get("search_service") or "basic"),
                    score=score,
                )
            )
            if selected_count > 0 and score > best_score:
                best_score = score
                best_template = template
                best_suffix = suffix or None

    persisted_entry = None
    if persist and best_template:
        existing_extra = dict(entry.get("extra") or {})
        existing_extra["search_contract_profile"] = {
            "service": "search_contract_discovery",
            "best_template": best_template,
            "best_suffix": best_suffix,
            "best_score": best_score,
            "templates_tried": templates,
            "suffixes_tried": [suffix for _, suffix in suffix_rows],
            "probe_rows": [
                {
                    "template": row.template,
                    "query_text": row.query_text,
                    "candidate_count": row.candidate_count,
                    "selected_count": row.selected_count,
                    "search_service": row.search_service,
                    "score": row.score,
                }
                for row in rows
            ],
        }
        persisted_entry = upsert_site_entry(
            scope=scope,
            project_key=project_key,
            site_url=normalized_site_url,
            entry_type=str(entry.get("entry_type") or "search_template").strip() or "search_template",
            template=best_template,
            domain=domain or None,
            capabilities=dict(entry.get("capabilities") or {}),
            source=str(entry.get("source") or "search_contract_discovery"),
            source_ref={
                **dict(entry.get("source_ref") or {}),
                "service": "search_contract_discovery",
                "best_suffix": best_suffix,
            },
            tags=list(entry.get("tags") or []),
            enabled=bool(entry.get("enabled", True)),
            extra=existing_extra,
        )

    return SearchContractDiscoveryResult(
        site_url=normalized_site_url,
        domain=domain,
        entry_type=str(entry.get("entry_type") or "search_template"),
        templates_tried=templates,
        suffixes_tried=[suffix for _, suffix in suffix_rows],
        best_template=best_template,
        best_suffix=best_suffix,
        best_score=max(best_score, 0.0),
        probe_rows=rows,
        persisted_entry=persisted_entry,
    )


def _query_terms(query_terms: list[str]) -> list[str]:
    return [str(term or "").strip() for term in query_terms if str(term or "").strip()]


def _query_text(query_terms: list[str]) -> str:
    return " ".join(_query_terms(query_terms)).strip()


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _string_object_view(value: object) -> dict[str, object]:
    return dict(value) if _is_string_object_dict(value) else {}


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _agent_search_templates(params: Mapping[str, object]) -> list[dict[str, str]]:
    raw = params.get("agent_search_templates")
    if not _is_object_list(raw):
        return []
    out: list[dict[str, str]] = []
    for value in raw[:6]:
        if not _is_string_object_dict(value):
            continue
        raw_template = value.get("template")
        raw_evidence_url = value.get("evidence_url")
        raw_reason = value.get("reason")
        if (
            not isinstance(raw_template, str)
            or not isinstance(raw_evidence_url, str)
            or not isinstance(raw_reason, str)
        ):
            continue
        row = {
            "template": raw_template.strip(),
            "evidence_url": raw_evidence_url.strip(),
            "reason": raw_reason.strip(),
        }
        if row not in out:
            out.append(row)
    return out


def _append_query_candidate(
    candidates: list[QueryContractCandidate],
    seen: set[tuple[str, str]],
    *,
    entry_type: str,
    template: str,
    origin: str,
    evidence_url: str,
    reason: str,
) -> None:
    if origin not in _QUERY_DISCOVERY_ORIGINS:
        return
    normalized = normalize_search_template_placeholders(template)
    target = normalized if entry_type == "search_template" else str(template or "").strip()
    if not target:
        return
    if entry_type == "search_template" and "{{q}}" not in target:
        return
    key = (entry_type, target)
    if key in seen:
        return
    seen.add(key)
    candidates.append(
        QueryContractCandidate(
            entry_type=entry_type,
            template=target,
            origin=origin,
            evidence_url=str(evidence_url or "").strip(),
            reason=str(reason or "").strip(),
        )
    )


def _same_origin_url(url: str, allowed_origin: str) -> bool:
    origin = SameOriginHttpTargetPolicy.canonical_origin(url)
    return isinstance(origin, str) and origin == allowed_origin


def _query_candidate_entry(
    entry: dict[str, object],
    candidate: QueryContractCandidate,
    execution: SearchTemplateExecutionResult,
) -> dict[str, object]:
    source_entry = dict(entry)
    keyword_mode = "search" if candidate.entry_type == "search_template" else "filter"
    source_entry["site_url"] = candidate.template
    source_entry["entry_type"] = candidate.entry_type
    source_entry["template"] = candidate.template if candidate.entry_type == "search_template" else None
    capabilities = _string_object_view(source_entry.get("capabilities"))
    capabilities.update({"supports_query_terms": True, "keyword_mode": keyword_mode})
    source_entry["capabilities"] = capabilities
    extra = _string_object_view(source_entry.get("extra"))
    extra["query_contract_resolution"] = {
        "contract_version": "resource_pool.query_contract_resolution.v1",
        "transient": True,
        "origin": candidate.origin,
        "evidence_url": candidate.evidence_url,
        "reason": candidate.reason,
        "selected_candidates": [str(item.url) for item in execution.selected_candidates],
        "used_term_fallback": execution.used_term_fallback,
        "search_urls": list(execution.search_urls),
    }
    source_entry["extra"] = extra
    return source_entry


def _execute_query_candidate(
    candidate: QueryContractCandidate,
    *,
    query_text: str,
    params: dict[str, object],
    probe_timeout: float,
    entry_domain: str,
) -> SearchTemplateExecutionResult:
    execution_params: dict[str, object] = dict(params)
    execution_params.update(
        {
            "page": 1,
            "max_pages": 1,
            "search_service": "basic",
            "enable_search_service_fallback": False,
            "enable_external_search_fallback": False,
        }
    )
    object_execution_params: dict[object, object] = {
        key: value for key, value in execution_params.items()
    }
    if candidate.entry_type == "search_template":
        return execute_search_template(
            template=candidate.template,
            query_terms=[query_text],
            params=object_execution_params,
            probe_timeout=max(0.001, float(probe_timeout)),
            allow_term_fallback=False,
            entry_domain=entry_domain,
        )
    if candidate.entry_type == "rss":
        return execute_feed_probe(
            feed_url=candidate.template,
            query_terms=[query_text],
            probe_timeout=max(0.001, float(probe_timeout)),
            allow_term_fallback=False,
            params=object_execution_params,
        )
    try:
        max_depth = max(0, min(2, _optional_int(execution_params.get("sitemap_max_depth")) or 1))
        max_sitemaps = max(1, min(10, _optional_int(execution_params.get("sitemap_max_sitemaps")) or 3))
    except (TypeError, ValueError):
        max_depth, max_sitemaps = 1, 3
    return execute_sitemap_probe(
        sitemap_url=candidate.template,
        query_terms=[query_text],
        probe_timeout=max(0.001, float(probe_timeout)),
        max_depth=max_depth,
        max_sitemaps=max_sitemaps,
        allow_term_fallback=False,
        params=execution_params,
    )


def _execution_reason_codes(execution: SearchTemplateExecutionResult) -> list[str]:
    if execution.selected_candidates and not execution.used_term_fallback:
        return ["verified_query_results"]
    if execution.raw_candidates and not execution.selected_candidates:
        return ["interaction_required"]
    reasons: list[str] = []
    for row in execution.errors:
        message = str(row.get("error") or "")
        reason = str(row.get("reason_code") or row.get("http_reason") or "")
        if reason == "target_policy_unavailable":
            reasons.append("unsafe_target_policy_unavailable")
        elif reason in {"unsafe_target", "request_budget_exhausted", "deadline_exceeded", "discovery_disabled"}:
            reasons.append(reason)
        elif row.get("http_status") in {401, 403} or " 401" in message or " 403" in message or "401" in message or "403" in message:
            reasons.append("authentication_required")
        elif row.get("error_class") in {"transport_failure", "unexpected_failure"} or "HttpFetchError" in message:
            reasons.append("http_error")
    return list(dict.fromkeys(reasons)) or ["probe_no_results"]


def _http_discovery_reason(error: HttpFetchError) -> str:
    reason = error.reason_code or error.reason.value
    if reason == "target_policy_unavailable":
        return "unsafe_target_policy_unavailable"
    if reason in {"unsafe_target", "request_budget_exhausted", "deadline_exceeded", "discovery_disabled"}:
        return reason
    if error.status_code in {401, 403} or "401" in str(error) or "403" in str(error):
        return "authentication_required"
    return "http_error"


def _exploration_request(
    *,
    project_key: str,
    entry: dict[str, object],
    query_terms: list[str],
    attempts: list[dict[str, object]],
    budget: QueryDiscoveryBudget,
) -> dict[str, object]:
    return {
        "status": "requested",
        "project_key": project_key,
        "source": {
            "site_url": str(entry.get("site_url") or "").strip(),
            "entry_type": str(entry.get("entry_type") or "").strip(),
        },
        "query_terms": _query_terms(query_terms),
        "attempts": attempts,
        "remaining_budget": budget.remaining(),
        "next_step": "Use the Cell-bound project agent to inspect the source and return evidence-backed query templates.",
        "required_tools": list(_QUERY_DISCOVERY_REQUIRED_TOOLS),
        "unmounted_tools": ["search-contract"],
        "agent_channel": "existing Cell relay",
    }


def resolve_query_contract(
    *,
    project_key: str,
    entry: dict[str, object],
    query_terms: list[str],
    probe_timeout: float,
    params: dict[str, object],
    budget: QueryDiscoveryBudget | None = None,
) -> QueryContractResolution:
    """Resolve a transient query contract without persistence or Agent calls."""

    terms = _query_terms(query_terms)
    query_text = _query_text(terms)
    params = dict(params or {})
    active_budget = budget or QueryDiscoveryBudget.from_params(params)
    attempts: list[dict[str, object]] = []
    reason_codes: list[str] = []

    if not project_key.strip():
        return QueryContractResolution(
            status="blocked",
            entry=None,
            diagnostics={"reason_codes": ["no_candidate_interface"], "project_key_required": True},
            exploration_request=None,
        )
    if not query_text:
        return QueryContractResolution(
            status="unresolved",
            entry=None,
            diagnostics={"reason_codes": ["no_candidate_interface"], "query_terms_required": True},
            exploration_request=None,
        )

    source_site_url = normalize_url(str(entry.get("site_url") or "").strip()) or ""
    allowed_origin = SameOriginHttpTargetPolicy.canonical_origin(source_site_url)
    if isinstance(allowed_origin, Failure):
        return QueryContractResolution(
            status="blocked",
            entry=None,
            diagnostics={"reason_codes": ["unsafe_target"], "invalid_entry_url": True},
            exploration_request=None,
        )
    homepage_url = f"{allowed_origin}/"

    if not http_fetch_target_policy_supported():
        return QueryContractResolution(
            status="blocked",
            entry=None,
            diagnostics={
                "reason_codes": ["unsafe_target_policy_unavailable"],
                "budget": active_budget.diagnostics,
            },
            exploration_request=None,
        )

    policy = SameOriginHttpTargetPolicy(allowed_origin=allowed_origin, budget=active_budget)
    entry_domain = str(entry.get("domain") or domain_from_url(source_site_url) or "").strip().lower()
    candidates: list[QueryContractCandidate] = []
    seen: set[tuple[str, str]] = set()
    source_key = source_site_url or allowed_origin

    with scoped_http_target_policy(policy):
        if active_budget.max_requests <= 0 or active_budget.max_templates <= 0:
            reason_codes.append("discovery_disabled")
        else:
            try:
                homepage_html, homepage_response = fetch_html_through_port(
                    homepage_url,
                    timeout=min(max(0.001, float(probe_timeout or 6.0)), max(0.001, active_budget.remaining_seconds)),
                    retries=1,
                )
                attempts.append(
                    {
                        "phase": "homepage_evidence",
                        "target": homepage_url,
                        "status": "fetched",
                        "http_status": homepage_response.status_code,
                    }
                )
                for clue in extract_homepage_query_contract_clues(homepage_html, base_url=homepage_url):
                    if _QUERY_DISCOVERY_BLOCKING_REASONS.intersection(reason_codes):
                        break
                    if clue["kind"] == "opensearch":
                        try:
                            description, description_response = fetch_html_through_port(
                                clue["value"],
                                timeout=min(max(0.001, float(probe_timeout or 6.0)), max(0.001, active_budget.remaining_seconds)),
                                retries=1,
                            )
                            attempts.append(
                                {
                                    "phase": "opensearch_description",
                                    "target": clue["value"],
                                    "status": "fetched",
                                    "http_status": description_response.status_code,
                                }
                            )
                            for template in extract_opensearch_templates(description, base_url=homepage_url):
                                _append_query_candidate(
                                    candidates,
                                    seen,
                                    entry_type="search_template",
                                    template=template,
                                    origin="evidence_form",
                                    evidence_url=clue["value"],
                                    reason="homepage OpenSearch description",
                                )
                        except HttpFetchError as exc:
                            reason = _http_discovery_reason(exc)
                            attempts.append(
                                {
                                    "phase": "opensearch_description",
                                    "target": clue["value"],
                                    "status": "failed",
                                    "error": str(exc),
                                    "reason_code": reason,
                                }
                            )
                            reason_codes.append(reason)
                    else:
                        _append_query_candidate(
                            candidates,
                            seen,
                            entry_type=clue["kind"],
                            template=clue["value"],
                            origin="evidence_form",
                            evidence_url=homepage_url,
                            reason=clue["evidence"],
                        )
            except HttpFetchError as exc:
                message = str(exc)
                reason = str(getattr(exc, "reason_code", "") or exc.reason.value)
                if reason in {"request_budget_exhausted", "deadline_exceeded", "discovery_disabled"}:
                    reason_codes.append(reason)
                elif reason in {"unsafe_target", "target_policy_unavailable"}:
                    reason_codes.append(_http_discovery_reason(exc))
                else:
                    if " 401" in message or " 403" in message or "401" in message or "403" in message:
                        reason_codes.append("authentication_required")
                    else:
                        reason_codes.append("http_error")
                attempts.append(
                    {
                        "phase": "homepage_evidence",
                        "target": homepage_url,
                        "status": "failed",
                        "error": message,
                        "reason_code": reason or "http_error",
                    }
                )

        explicit_type = str(entry.get("entry_type") or "").strip().lower()
        explicit_template = str(entry.get("template") or "").strip()
        if explicit_type in {"rss", "sitemap"}:
            explicit_template = str(entry.get("site_url") or "").strip()
        if explicit_template:
            _append_query_candidate(
                candidates,
                seen,
                entry_type="search_template" if explicit_type != "rss" and explicit_type != "sitemap" else explicit_type,
                template=explicit_template,
                origin="known_template",
                evidence_url=str(entry.get("site_url") or "").strip(),
                reason="entry template",
            )
        extra = _string_object_view(entry.get("extra"))
        profile = _string_object_view(extra.get("search_contract_profile"))
        profile_template = str(profile.get("best_template") or "").strip()
        if profile_template:
            _append_query_candidate(
                candidates,
                seen,
                entry_type="search_template",
                template=profile_template,
                origin="known_template",
                evidence_url=str(entry.get("site_url") or "").strip(),
                reason="entry search_contract_profile",
            )

        for proposal in _agent_search_templates(params):
            if not _same_origin_url(proposal["template"], allowed_origin):
                attempts.append(
                    {
                        "phase": "agent_proposal",
                        "target": proposal["template"],
                        "status": "skipped",
                        "reason_code": "proposal_not_for_source",
                    }
                )
                continue
            if not _same_origin_url(proposal["evidence_url"], allowed_origin):
                attempts.append(
                    {
                        "phase": "agent_evidence",
                        "target": proposal["evidence_url"],
                        "status": "rejected_without_fetch",
                        "reason_code": "unsafe_target",
                    }
                )
                reason_codes.append("unsafe_target")
                continue
            _append_query_candidate(
                candidates,
                seen,
                entry_type="search_template",
                template=proposal["template"],
                origin="agent_proposal",
                evidence_url=proposal["evidence_url"],
                reason=proposal["reason"] or "Agent evidence proposal",
            )

        for path in _DEFAULT_TEMPLATE_PATHS:
            _append_query_candidate(
                candidates,
                seen,
                entry_type="search_template",
                template=f"{allowed_origin}{path}",
                origin="heuristic_path",
                evidence_url=homepage_url,
                reason="bounded conventional query path",
            )

        selected_execution: SearchTemplateExecutionResult | None = None
        selected_candidate: QueryContractCandidate | None = None
        selected_entry: dict[str, object] | None = None

        for candidate in candidates:
            if _QUERY_DISCOVERY_BLOCKING_REASONS.intersection(reason_codes):
                break
            acquired, denial_reason = active_budget.try_acquire_template(
                candidate.template,
                source_key=source_key,
            )
            if not acquired:
                reason_codes.append(denial_reason or "request_budget_exhausted")
                attempts.append(
                    {
                        "phase": "query_probe",
                        "target": candidate.template,
                        "origin": candidate.origin,
                        "status": "not_run",
                        "reason_code": denial_reason,
                    }
                )
                continue
            remaining_seconds = active_budget.remaining_seconds
            if remaining_seconds <= 0:
                reason_codes.append("deadline_exceeded")
                attempts.append(
                    {
                        "phase": "query_probe",
                        "target": candidate.template,
                        "origin": candidate.origin,
                        "status": "not_run",
                        "reason_code": "deadline_exceeded",
                    }
                )
                continue
            try:
                execution = _execute_query_candidate(
                    candidate,
                    query_text=query_text,
                    params=params,
                    probe_timeout=min(float(probe_timeout or 6.0), remaining_seconds),
                    entry_domain=entry_domain,
                )
            except Exception as exc:  # noqa: BLE001 - preserve the original consumer failure in diagnostics
                reason_code = str(getattr(exc, "reason_code", ""))
                reason = reason_code or (
                    exc.reason.value
                    if isinstance(exc, HttpFetchError)
                    else None
                )
                if reason in {"request_budget_exhausted", "deadline_exceeded", "discovery_disabled"}:
                    reason_codes.append(reason)
                elif reason in {"unsafe_target", "target_policy_unavailable"}:
                    reason_codes.append(
                        _http_discovery_reason(exc) if isinstance(exc, HttpFetchError) else reason
                    )
                else:
                    reason_codes.append("http_error")
                attempts.append(
                    {
                        "phase": "query_probe",
                        "target": candidate.template,
                        "origin": candidate.origin,
                        "status": "failed",
                        "error": str(exc),
                        "reason_code": reason or "http_error",
                    }
                )
                continue

            attempt_reasons = _execution_reason_codes(execution)
            reason_codes.extend(attempt_reasons)
            attempts.append(
                {
                    "phase": "query_probe",
                    "target": candidate.template,
                    "origin": candidate.origin,
                    "status": "verified" if attempt_reasons == ["verified_query_results"] else "no_positive_results",
                    "reason_codes": attempt_reasons,
                    "raw_candidates": len(execution.raw_candidates),
                    "selected_candidates": len(execution.selected_candidates),
                    "used_term_fallback": execution.used_term_fallback,
                    "errors": list(execution.errors),
                }
            )
            if attempt_reasons == ["verified_query_results"]:
                selected_execution = execution
                selected_candidate = candidate
                selected_entry = _query_candidate_entry(entry, candidate, execution)
                break

    reason_codes = list(dict.fromkeys(reason_codes))
    if not reason_codes:
        reason_codes = ["no_candidate_interface"] if not candidates else ["probe_no_results"]
    budget_denied = any(
        reason in {"request_budget_exhausted", "deadline_exceeded", "discovery_disabled"}
        for reason in reason_codes
    )
    unsafe = bool(_QUERY_DISCOVERY_BLOCKING_REASONS.intersection(reason_codes))

    diagnostics: dict[str, object] = {
        "reason_codes": reason_codes,
        "candidate_origins": [candidate.origin for candidate in candidates],
        "attempts": attempts,
        "budget": active_budget.diagnostics,
        "params_contract": {
            "query_discovery_max_requests": active_budget.max_requests,
            "query_discovery_max_templates": active_budget.max_templates,
            "query_discovery_timeout_seconds": active_budget.timeout_seconds,
            "agent_search_templates": _agent_search_templates(params),
        },
        "suffix_fanout": False,
        "persisted": False,
        "agent_invoked": False,
        "site_material_claim": "not_assessed",
        "http_target_policy": {
            "scope": "same_origin",
            "checks": ["http_https", "no_userinfo", "public_dns_before_each_request", "per_hop_redirect"],
            "dns_rebinding_boundary": "DNS is checked before each request, but requests resolve again; IP pinning is not implemented",
        },
    }

    if selected_execution is not None and selected_candidate is not None and selected_entry is not None:
        return QueryContractResolution(
            status="verified",
            entry=selected_entry,
            diagnostics=diagnostics,
            exploration_request=None,
            execution=selected_execution,
        )
    if budget_denied and not unsafe and "verified_query_results" not in reason_codes:
        return QueryContractResolution(
            status="budget_exhausted",
            entry=None,
            diagnostics=diagnostics,
            exploration_request=_exploration_request(
                project_key=project_key,
                entry=entry,
                query_terms=terms,
                attempts=attempts,
                budget=active_budget,
            ),
        )
    return QueryContractResolution(
        status="blocked" if unsafe else "unresolved",
        entry=None,
        diagnostics=diagnostics,
        exploration_request=_exploration_request(
            project_key=project_key,
            entry=entry,
            query_terms=terms,
            attempts=attempts,
            budget=active_budget,
        ),
    )
