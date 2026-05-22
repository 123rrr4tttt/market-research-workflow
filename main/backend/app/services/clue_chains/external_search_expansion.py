from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

CONTRACT_VERSION = "clue_chain.external_search_expansion.v1"
HOP_CONTRACT_VERSION = "clue_chain.hop.v1"
EVIDENCE_CONTRACT_VERSION = "clue_chain.evidence.v1"
CANDIDATE_CONTRACT_VERSION = "clue_chain.candidate.v1"
REPLAY_CONTRACT_VERSION = "clue_chain.external_search_replay.v1"

_TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "spm",
    "fromsource",
    "sc_source",
}

LiveSearchHook = Callable[..., Sequence[Mapping[str, Any]]]


@dataclass(slots=True, frozen=True)
class ExternalSearchExpansionRequest:
    chain_id: str
    query: str
    focus_node_id: str | None = None
    hop_id: str | None = None
    project_key: str | None = None
    provider_name: str = "fixture_external_search"
    limit: int = 10
    live_enabled: bool = False
    fixture_path: str | Path | None = None
    injected_results: Sequence[Mapping[str, Any]] | None = None
    trace_context: Mapping[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class ExternalSearchProviderResponse:
    provider_name: str
    results: list[dict[str, Any]]
    trace: dict[str, Any]
    replay: dict[str, Any]
    fixture_gate: bool
    blocked_reason: str | None = None


class ExternalSearchProvider(Protocol):
    provider_name: str

    def search(self, request: ExternalSearchExpansionRequest) -> ExternalSearchProviderResponse:
        ...


class FixtureExternalSearchProvider:
    """Fixture-backed provider used by default so Clue Chain replay never calls the public network."""

    def __init__(
        self,
        *,
        provider_name: str = "fixture_external_search",
        fixture_path: str | Path | None = None,
        injected_results: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        self.provider_name = _clean_text(provider_name) or "fixture_external_search"
        self.fixture_path = Path(fixture_path) if fixture_path is not None else None
        self.injected_results = injected_results

    def search(self, request: ExternalSearchExpansionRequest) -> ExternalSearchProviderResponse:
        if self.injected_results is not None:
            results = _dict_list(self.injected_results)
            return self._response(
                request,
                results=results,
                mode="injected",
                blocked_reason=None,
                fixture_path=None,
            )

        if self.fixture_path is not None:
            results = _load_fixture_results(self.fixture_path, request.query)
            return self._response(
                request,
                results=results,
                mode="fixture",
                blocked_reason=None,
                fixture_path=self.fixture_path,
            )

        return self._response(
            request,
            results=[],
            mode="blocked",
            blocked_reason="fixture_gate",
            fixture_path=None,
        )

    def _response(
        self,
        request: ExternalSearchExpansionRequest,
        *,
        results: list[dict[str, Any]],
        mode: str,
        blocked_reason: str | None,
        fixture_path: Path | None,
    ) -> ExternalSearchProviderResponse:
        trace = {
            "provider_name": self.provider_name,
            "query": request.query,
            "mode": mode,
            "fixture_gate": True,
            "live_enabled": False,
            "network_allowed": False,
            "blocked_reason": blocked_reason,
            "raw_result_count": len(results),
        }
        replay = {
            "mode": mode,
            "provider_name": self.provider_name,
            "query": request.query,
            "fixture_gate": True,
            "fixture_path": str(fixture_path) if fixture_path is not None else None,
            "raw_results": results,
        }
        return ExternalSearchProviderResponse(
            provider_name=self.provider_name,
            results=results,
            trace=trace,
            replay=replay,
            fixture_gate=True,
            blocked_reason=blocked_reason,
        )


class LiveHookExternalSearchProvider:
    """Explicit-live provider shell; the actual network hook is injected by a caller."""

    def __init__(self, *, provider_name: str, live_searcher: LiveSearchHook | None = None) -> None:
        self.provider_name = _clean_text(provider_name) or "live_external_search"
        self.live_searcher = live_searcher

    def search(self, request: ExternalSearchExpansionRequest) -> ExternalSearchProviderResponse:
        if not request.live_enabled:
            return self._blocked_response(request, blocked_reason="fixture_gate")
        if self.live_searcher is None:
            return self._blocked_response(request, blocked_reason="live_provider_not_configured")

        raw_results = self.live_searcher(
            query=request.query,
            limit=max(1, int(request.limit or 1)),
            provider_name=self.provider_name,
        )
        results = _dict_list(raw_results)
        trace = {
            "provider_name": self.provider_name,
            "query": request.query,
            "mode": "live_hook",
            "fixture_gate": False,
            "live_enabled": True,
            "network_allowed": True,
            "blocked_reason": None,
            "raw_result_count": len(results),
        }
        replay = {
            "mode": "live_hook",
            "provider_name": self.provider_name,
            "query": request.query,
            "fixture_gate": False,
            "fixture_path": None,
            "raw_results": results,
        }
        return ExternalSearchProviderResponse(
            provider_name=self.provider_name,
            results=results,
            trace=trace,
            replay=replay,
            fixture_gate=False,
            blocked_reason=None,
        )

    def _blocked_response(
        self,
        request: ExternalSearchExpansionRequest,
        *,
        blocked_reason: str,
    ) -> ExternalSearchProviderResponse:
        trace = {
            "provider_name": self.provider_name,
            "query": request.query,
            "mode": "blocked",
            "fixture_gate": True,
            "live_enabled": bool(request.live_enabled),
            "network_allowed": bool(request.live_enabled),
            "blocked_reason": blocked_reason,
            "raw_result_count": 0,
        }
        replay = {
            "mode": "blocked",
            "provider_name": self.provider_name,
            "query": request.query,
            "fixture_gate": True,
            "fixture_path": None,
            "raw_results": [],
        }
        return ExternalSearchProviderResponse(
            provider_name=self.provider_name,
            results=[],
            trace=trace,
            replay=replay,
            fixture_gate=True,
            blocked_reason=blocked_reason,
        )


def expand_external_search(
    request: ExternalSearchExpansionRequest | Mapping[str, Any],
    *,
    provider: ExternalSearchProvider | None = None,
    live_searcher: LiveSearchHook | None = None,
) -> dict[str, Any]:
    normalized_request = _coerce_request(request)
    provider = provider or build_external_search_provider(normalized_request, live_searcher=live_searcher)

    query = _clean_text(normalized_request.query)
    provider_name = _clean_text(getattr(provider, "provider_name", normalized_request.provider_name))
    hop_id = normalized_request.hop_id or _stable_id(
        "hop_external_search",
        normalized_request.chain_id,
        normalized_request.focus_node_id,
        provider_name,
        query,
    )

    if not query:
        provider_response = ExternalSearchProviderResponse(
            provider_name=provider_name,
            results=[],
            trace={
                "provider_name": provider_name,
                "query": query,
                "mode": "blocked",
                "fixture_gate": True,
                "live_enabled": bool(normalized_request.live_enabled),
                "network_allowed": False,
                "blocked_reason": "missing_query",
                "raw_result_count": 0,
            },
            replay={
                "mode": "blocked",
                "provider_name": provider_name,
                "query": query,
                "fixture_gate": True,
                "fixture_path": None,
                "raw_results": [],
            },
            fixture_gate=True,
            blocked_reason="missing_query",
        )
    else:
        provider_response = provider.search(normalized_request)
        provider_name = provider_response.provider_name

    merged_results, skipped_count, duplicate_count = _merge_results(
        provider_response.results,
        provider_name=provider_name,
        query=query,
        limit=max(1, int(normalized_request.limit or 1)),
    )

    trace_id = _stable_id(
        "trace_external_search",
        normalized_request.chain_id,
        hop_id,
        provider_name,
        query,
        [item["dedupe_key"] for item in merged_results],
    )
    blocked_reason = provider_response.blocked_reason
    status = "blocked" if blocked_reason else "completed"

    evidence: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(merged_results):
        evidence_id = _stable_id("evidence_external_search", normalized_request.chain_id, hop_id, item["dedupe_key"])
        candidate_id = _stable_id("candidate_external_search", normalized_request.chain_id, item["dedupe_key"])
        evidence.append(
            {
                "contract_version": EVIDENCE_CONTRACT_VERSION,
                "evidence_id": evidence_id,
                "chain_id": normalized_request.chain_id,
                "hop_id": hop_id,
                "focus_node_id": normalized_request.focus_node_id,
                "project_key": normalized_request.project_key,
                "evidence_type": "external_search_result",
                "source_type": "external_search",
                "provider_name": provider_name,
                "query": query,
                "normalized_url": item["normalized_url"],
                "title": item["title"],
                "snippet": item["snippet"],
                "aliases": item["aliases"],
                "dedupe_key": item["dedupe_key"],
                "trace_id": trace_id,
                "fixture_gate": bool(provider_response.fixture_gate),
                "blocked_reason": None,
                "merged_count": item["merged_count"],
                "replay_ref": {
                    "mode": provider_response.replay.get("mode"),
                    "result_index": index,
                    "dedupe_key": item["dedupe_key"],
                },
            }
        )
        candidates.append(
            {
                "contract_version": CANDIDATE_CONTRACT_VERSION,
                "candidate_id": candidate_id,
                "chain_id": normalized_request.chain_id,
                "hop_id": hop_id,
                "focus_node_id": normalized_request.focus_node_id,
                "project_key": normalized_request.project_key,
                "candidate_type": "source_url" if item["normalized_url"] else "external_alias",
                "source_type": "external_search",
                "provider_name": provider_name,
                "query": query,
                "normalized_url": item["normalized_url"],
                "title": item["title"],
                "snippet": item["snippet"],
                "aliases": item["aliases"],
                "dedupe_key": item["dedupe_key"],
                "evidence_refs": [evidence_id],
                "decision_status": "pending_review",
                "requires_decision": True,
                "promotion_allowed": False,
                "fixture_gate": bool(provider_response.fixture_gate),
                "blocked_reason": None,
                "merged_count": item["merged_count"],
            }
        )

    trace = {
        "contract_version": CONTRACT_VERSION,
        "trace_id": trace_id,
        "chain_id": normalized_request.chain_id,
        "hop_id": hop_id,
        "focus_node_id": normalized_request.focus_node_id,
        "project_key": normalized_request.project_key,
        "provider_name": provider_name,
        "query": query,
        "fixture_gate": bool(provider_response.fixture_gate),
        "live_enabled": bool(normalized_request.live_enabled),
        "network_allowed": bool(normalized_request.live_enabled and not provider_response.fixture_gate),
        "blocked_reason": blocked_reason,
        "raw_result_count": len(provider_response.results),
        "candidate_count": len(candidates),
        "evidence_count": len(evidence),
        "duplicate_count": duplicate_count,
        "skipped_count": skipped_count,
        "merged_dedupe_keys": [item["dedupe_key"] for item in merged_results],
        "trace_context": dict(normalized_request.trace_context or {}),
        "provider_trace": dict(provider_response.trace),
    }
    replay = {
        "contract_version": REPLAY_CONTRACT_VERSION,
        "mode": provider_response.replay.get("mode"),
        "provider_name": provider_name,
        "query": query,
        "fixture_gate": bool(provider_response.fixture_gate),
        "fixture_path": provider_response.replay.get("fixture_path"),
        "live_enabled": bool(normalized_request.live_enabled),
        "normalized_results": [
            {
                "normalized_url": item["normalized_url"],
                "title": item["title"],
                "snippet": item["snippet"],
                "aliases": item["aliases"],
                "dedupe_key": item["dedupe_key"],
                "merged_count": item["merged_count"],
            }
            for item in merged_results
        ],
        "provider_replay": dict(provider_response.replay),
    }
    hop = {
        "contract_version": HOP_CONTRACT_VERSION,
        "hop_id": hop_id,
        "chain_id": normalized_request.chain_id,
        "focus_node_id": normalized_request.focus_node_id,
        "project_key": normalized_request.project_key,
        "hop_type": "external_search",
        "status": status,
        "provider_name": provider_name,
        "query": query,
        "fixture_gate": bool(provider_response.fixture_gate),
        "blocked_reason": blocked_reason,
        "candidate_count": len(candidates),
        "evidence_count": len(evidence),
        "trace_id": trace_id,
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "chain_id": normalized_request.chain_id,
        "hop": hop,
        "evidence": evidence,
        "candidates": candidates,
        "trace": trace,
        "replay": replay,
    }


def build_external_search_provider(
    request: ExternalSearchExpansionRequest,
    *,
    live_searcher: LiveSearchHook | None = None,
) -> ExternalSearchProvider:
    if request.live_enabled and request.injected_results is None and request.fixture_path is None:
        return LiveHookExternalSearchProvider(provider_name=request.provider_name, live_searcher=live_searcher)
    return FixtureExternalSearchProvider(
        provider_name=request.provider_name,
        fixture_path=request.fixture_path,
        injected_results=request.injected_results,
    )


def normalize_external_search_url(url: str | None) -> str:
    raw = _clean_text(url)
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme and raw.startswith("//"):
        parsed = urlparse(f"https:{raw}")
    elif not parsed.scheme and parsed.path and "." in parsed.path.split("/")[0]:
        parsed = urlparse(f"https://{raw}")
    if not parsed.netloc:
        return raw

    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_PARAMS
    ]
    canonical_query = urlencode(sorted(query))
    return urlunparse((scheme, netloc, path or "/", "", canonical_query, ""))


def external_search_dedupe_key(result: Mapping[str, Any]) -> str:
    explicit = _clean_text(result.get("dedupe_key"))
    if explicit:
        return explicit
    normalized_url = normalize_external_search_url(
        result.get("normalized_url") or result.get("url") or result.get("link")
    )
    if normalized_url:
        return f"url:{normalized_url}"
    alias_key = _alias_key(_clean_text(result.get("title") or result.get("name")))
    if alias_key:
        return f"alias:{alias_key}"
    return ""


def _merge_results(
    results: Sequence[Mapping[str, Any]],
    *,
    provider_name: str,
    query: str,
    limit: int,
) -> tuple[list[dict[str, Any]], int, int]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    skipped_count = 0
    duplicate_count = 0

    for raw in results:
        if not isinstance(raw, Mapping):
            skipped_count += 1
            continue
        result = dict(raw)
        normalized_url = normalize_external_search_url(
            result.get("normalized_url") or result.get("url") or result.get("link")
        )
        title = _clean_text(result.get("title") or result.get("name"))
        snippet = _clean_text(result.get("snippet") or result.get("description") or result.get("content"))
        aliases = _unique_texts([*list(result.get("aliases") or []), title])
        dedupe_key = external_search_dedupe_key(
            {
                "dedupe_key": result.get("dedupe_key"),
                "normalized_url": normalized_url,
                "title": title,
            }
        )
        if not dedupe_key:
            skipped_count += 1
            continue
        normalized = {
            "provider_name": provider_name,
            "query": query,
            "normalized_url": normalized_url,
            "title": title,
            "snippet": snippet,
            "aliases": aliases,
            "dedupe_key": dedupe_key,
            "merged_count": 1,
        }
        existing = merged.get(dedupe_key)
        if existing is None:
            merged[dedupe_key] = normalized
            order.append(dedupe_key)
            continue

        duplicate_count += 1
        existing["merged_count"] += 1
        if not existing["title"] and title:
            existing["title"] = title
        if not existing["snippet"] and snippet:
            existing["snippet"] = snippet
        existing["aliases"] = _unique_texts([*existing["aliases"], *aliases])

    return [merged[key] for key in order[:limit]], skipped_count, duplicate_count


def _coerce_request(request: ExternalSearchExpansionRequest | Mapping[str, Any]) -> ExternalSearchExpansionRequest:
    if isinstance(request, ExternalSearchExpansionRequest):
        return request
    return ExternalSearchExpansionRequest(
        chain_id=_clean_text(request.get("chain_id")),
        query=_clean_text(request.get("query")),
        focus_node_id=_clean_text(request.get("focus_node_id")) or None,
        hop_id=_clean_text(request.get("hop_id")) or None,
        project_key=_clean_text(request.get("project_key")) or None,
        provider_name=_clean_text(request.get("provider_name")) or "fixture_external_search",
        limit=int(request.get("limit") or 10),
        live_enabled=bool(request.get("live_enabled")),
        fixture_path=request.get("fixture_path"),
        injected_results=request.get("injected_results"),
        trace_context=request.get("trace_context"),
    )


def _load_fixture_results(fixture_path: Path, query: str) -> list[dict[str, Any]]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return _dict_list(payload)
    if not isinstance(payload, Mapping):
        return []
    if isinstance(payload.get("queries"), Mapping):
        query_payload = payload["queries"].get(query) or payload["queries"].get("*") or {}
        if isinstance(query_payload, Mapping):
            return _dict_list(query_payload.get("results") or [])
        return _dict_list(query_payload or [])
    return _dict_list(payload.get("results") or [])


def _dict_list(items: Sequence[Mapping[str, Any]] | Any) -> list[dict[str, Any]]:
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _unique_texts(values: Sequence[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output
