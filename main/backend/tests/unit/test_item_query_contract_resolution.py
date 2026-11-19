from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from app.composition.resource_pool import RequestsHttpFetchPort
from app.services.ingest.adapters import http_utils
from app.services.resource_pool import http_port
from app.services.resource_pool import search_capabilities, search_contract_discovery, search_template_service
from app.services.resource_pool.http_port import (
    HttpFetchError,
    HttpFetchFailureReason,
    HttpFetchResponse,
    set_http_fetch_port,
)
from mrw_functorial_kit.core.provider_port_failures import resource_pool_http_fetch_failures
from app.services.resource_pool.search_capabilities import SearchCapabilityScore
from app.services.resource_pool.search_contract_discovery import (
    QueryDiscoveryBudget,
    SearchTemplateExecutionResult,
    discover_search_contract,
    query_discovery_parameter_schema,
    resolve_query_contract,
)
from app.services.resource_pool.site_entry_discovery import extract_opensearch_templates


class _PolicyPort:
    def __init__(self, html: str) -> None:
        self.html = html
        self.urls: list[str] = []

    def fetch_html(
        self,
        url: str,
        *,
        headers: Any = None,
        params: Any = None,
        cookies: Any = None,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.5,
        target_policy: Any = None,
    ) -> tuple[str, HttpFetchResponse]:
        self.urls.append(url)
        response = HttpFetchResponse(
            text=self.html,
            content=self.html.encode(),
            headers={"content-type": "text/html"},
            status_code=200,
            final_url=url,
        )
        return self.html, response


def _execution(template: str, selected: bool = True) -> SearchTemplateExecutionResult:
    candidate = SearchCapabilityScore(
        url="https://example.com/reports/ai-example",
        strategy="search_template",
        fetchability="ok",
        matched_by="title",
        route_kind="article",
        candidate_quality="high",
        score=1.2,
        usable_for_search=True,
    )
    return SearchTemplateExecutionResult(
        template=template,
        search_urls=[template.replace("{{q}}", "ai")],
        pages_scanned=1,
        raw_candidates=[SimpleNamespace(url=candidate.url)] if selected else [],
        selected_candidates=[candidate] if selected else [],
        used_term_fallback=False,
    )


def test_query_discovery_budget_is_thread_safe_and_templates_are_per_source() -> None:
    import threading

    budget = QueryDiscoveryBudget(max_requests=10, max_templates=10, timeout_seconds=30)
    request_results: list[bool] = []
    template_a: list[bool] = []
    template_b: list[bool] = []
    lock = threading.Lock()

    def acquire_request() -> None:
        acquired, _ = budget.try_acquire_request("https://example.com")
        with lock:
            request_results.append(acquired)

    def acquire_template(source_key: str, output: list[bool]) -> None:
        for _ in range(25):
            acquired, _ = budget.try_acquire_template("template", source_key=source_key)
            with lock:
                output.append(acquired)

    threads = [threading.Thread(target=acquire_request) for _ in range(25)]
    threads.extend(
        [
            threading.Thread(target=acquire_template, args=("source-a", template_a)),
            threading.Thread(target=acquire_template, args=("source-b", template_b)),
        ]
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(request_results) == 10
    assert sum(template_a) == 10
    assert sum(template_b) == 10
    diagnostics = budget.diagnostics
    assert diagnostics["used_templates_by_source"] == {"source-a": 10, "source-b": 10}


def test_query_discovery_parameter_schema_is_authoritative() -> None:
    schema = query_discovery_parameter_schema()
    assert schema["query_discovery_max_requests"]["default"] == 4
    assert schema["query_discovery_max_templates"]["maximum"] == 6
    assert schema["query_discovery_timeout_seconds"]["maximum"] == 60
    assert schema["agent_search_templates"]["items"]["properties"]["reason"]["minLength"] == 1


def test_query_discovery_budget_invalid_params_normalize_to_schema_defaults() -> None:
    budget = QueryDiscoveryBudget.from_params(
        {
            "query_discovery_max_requests": object(),
            "query_discovery_max_templates": None,
            "query_discovery_timeout_seconds": object(),
        }
    )

    assert budget.max_requests == 4
    assert budget.max_templates == 3
    assert budget.timeout_seconds == 15.0


def test_opensearch_description_extracts_html_query_template() -> None:
    xml = """
    <OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
      <Url type="text/html" template="/search?q={searchTerms}&amp;from=0"/>
    </OpenSearchDescription>
    """
    assert extract_opensearch_templates(xml, base_url="https://example.com") == [
        "https://example.com/search?q={{q}}&from=0"
    ]


def test_resolve_query_contract_verifies_homepage_get_form_without_persistence() -> None:
    homepage = """
    <html><body>
      <form action="/search" method="get"><input name="query" type="text"></form>
    </body></html>
    """
    port = _PolicyPort(homepage)
    original_port = http_port._http_fetch_port
    set_http_fetch_port(port)
    execution = _execution("https://example.com/search?query={{q}}")
    try:
        with (
            patch(
                "app.services.ingest.adapters.http_utils.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
            ),
            patch(
                "app.services.resource_pool.search_contract_discovery.execute_search_template",
                return_value=execution,
            ) as execute,
            patch(
                "app.services.resource_pool.search_contract_discovery.upsert_site_entry",
            ) as upsert,
        ):
            result = resolve_query_contract(
                project_key="demo",
                entry={"site_url": "https://example.com", "entry_type": "domain_root"},
                query_terms=["AI example"],
                probe_timeout=2.0,
                params={},
            )
    finally:
        set_http_fetch_port(original_port)

    assert result.status == "verified"
    assert result.entry is not None
    assert result.entry["entry_type"] == "search_template"
    assert result.entry["template"] == "https://example.com/search?query={{q}}"
    assert result.entry["capabilities"] == {
        "supports_query_terms": True,
        "keyword_mode": "search",
    }
    assert result.execution is execution
    assert result.execution.selected_candidates[0].usable_for_search is True
    assert result.diagnostics["reason_codes"] == ["verified_query_results"]
    assert result.diagnostics["persisted"] is False
    assert result.exploration_request is None
    execute.assert_called_once()
    upsert.assert_not_called()
    assert port.urls == ["https://example.com/"]


def test_resolve_query_contract_zero_score_never_becomes_verified_and_requests_exploration() -> None:
    port = _PolicyPort("<html><body>No forms</body></html>")
    original_port = http_port._http_fetch_port
    set_http_fetch_port(port)
    try:
        with (
            patch(
                "app.services.ingest.adapters.http_utils.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
            ),
            patch(
                "app.services.resource_pool.search_contract_discovery.execute_search_template",
                side_effect=lambda **kwargs: _execution(kwargs["template"], selected=False),
            ),
        ):
            result = resolve_query_contract(
                project_key="demo",
                entry={"site_url": "https://example.com", "entry_type": "domain_root"},
                query_terms=["AI example"],
                probe_timeout=2.0,
                params={"query_discovery_max_templates": 3},
            )
    finally:
        set_http_fetch_port(original_port)

    assert result.status == "unresolved"
    assert result.entry is None
    assert result.execution is None
    assert "probe_no_results" in result.diagnostics["reason_codes"]
    assert result.exploration_request is not None
    assert result.exploration_request["status"] == "requested"
    assert result.exploration_request["remaining_budget"]["remaining_templates"] == 0
    assert "source.web.search" in result.exploration_request["required_tools"]


def test_foreign_agent_proposal_is_skipped_for_this_source_not_blocked() -> None:
    port = _PolicyPort("<html><body></body></html>")
    original_port = http_port._http_fetch_port
    set_http_fetch_port(port)
    try:
        with (
            patch(
                "app.services.ingest.adapters.http_utils.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
            ),
            patch(
                "app.services.resource_pool.search_contract_discovery.execute_search_template",
            ) as execute,
        ):
            result = resolve_query_contract(
                project_key="demo",
                entry={"site_url": "https://example.com", "entry_type": "domain_root"},
                query_terms=["AI example"],
                probe_timeout=2.0,
                params={
                    "query_discovery_max_requests": 0,
                    "query_discovery_max_templates": 0,
                    "agent_search_templates": [
                        {
                            "template": "https://other.example/search?q={{q}}",
                            "evidence_url": "https://other.example/evidence",
                            "reason": "Belongs to another source",
                        }
                    ],
                },
            )
    finally:
        set_http_fetch_port(original_port)

    assert result.status == "budget_exhausted"
    assert "unsafe_target" not in result.diagnostics["reason_codes"]
    agent_attempts = [
        row for row in result.diagnostics["attempts"] if row["phase"] == "agent_proposal"
    ]
    assert agent_attempts == [
        {
            "phase": "agent_proposal",
            "target": "https://other.example/search?q={{q}}",
            "status": "skipped",
            "reason_code": "proposal_not_for_source",
        }
    ]
    execute.assert_not_called()


def test_discover_search_contract_requires_positive_selected_evidence_to_persist() -> None:
    entry = {
        "site_url": "https://example.com",
        "domain": "example.com",
        "entry_type": "search_template",
        "template": None,
        "capabilities": {},
        "source": "manual",
        "source_ref": {},
        "tags": [],
        "enabled": True,
        "extra": {},
    }
    with (
        patch(
            "app.services.resource_pool.search_contract_discovery.get_site_entry_by_url",
            return_value=entry,
        ),
        patch(
            "app.services.resource_pool.search_contract_discovery.execute_search_template",
            return_value=SimpleNamespace(
                raw_candidates=[SimpleNamespace(url="https://example.com/a")],
                selected_candidates=[],
                diagnostics={"search_service": "basic"},
            ),
        ) as execute,
        patch(
            "app.services.resource_pool.search_contract_discovery.upsert_site_entry",
        ) as upsert,
    ):
        result = discover_search_contract(
            scope="project",
            project_key="demo",
            site_url="https://example.com",
            query_terms=["AI example"],
            suffixes=[""],
            persist=True,
        )

    assert result.best_template is None
    assert result.best_score == 0
    assert result.persisted_entry is None
    assert execute.called
    upsert.assert_not_called()


@pytest.mark.parametrize("route", ["search_template", "rss", "sitemap"])
@pytest.mark.parametrize(
    "reason", [HttpFetchFailureReason.UNSAFE_TARGET, HttpFetchFailureReason.REQUEST_BUDGET_EXHAUSTED]
)
def test_query_probes_preserve_policy_failure_identity(route: str, reason: HttpFetchFailureReason) -> None:
    url = "https://example.com/search?q={{q}}" if route == "search_template" else "https://example.com/feed.xml"
    failure = resource_pool_http_fetch_failures.fail(reason.value, "blocked by policy", {"url": url})
    error = HttpFetchError(
        failure.message,
        reason=reason,
        reason_code=reason.value,
        url=url,
        retryable=False,
        failure=failure,
    )
    with patch.object(search_template_service, "fetch_html", side_effect=error) as fetch:
        if route == "search_template":
            execution = search_template_service.execute_search_template(
                template=url,
                query_terms=["river"],
                params={"enable_search_service_fallback": True},
                probe_timeout=1,
                allow_term_fallback=False,
            )
        elif route == "rss":
            execution = search_template_service.execute_feed_probe(
                feed_url=url, query_terms=["river"], probe_timeout=1, allow_term_fallback=False,
            )
        else:
            execution = search_template_service.execute_sitemap_probe(
                sitemap_url=url, query_terms=["river"], probe_timeout=1,
                max_depth=1, max_sitemaps=1, allow_term_fallback=False,
            )

    fetch.assert_called_once()
    assert execution.selected_candidates == []
    assert execution.errors[0]["reason_code"] == reason.value
    assert execution.errors[0]["failure_family"] == failure.family
    assert execution.errors[0]["failure_code"] == failure.code
    assert execution.errors[0]["failure_context"] == failure.context
    assert search_contract_discovery._execution_reason_codes(execution) == [reason.value]


@pytest.mark.parametrize("opensearch", [False, True])
def test_native_query_discovery_stops_after_policy_rejection(opensearch: bool) -> None:
    homepage = (
        '<link rel="search" type="application/opensearchdescription+xml" href="/opensearch.xml">'
        '<link rel="search" type="application/opensearchdescription+xml" href="/second.xml">'
        if opensearch
        else '<form action="/search" method="get"><input name="query" type="text"></form>'
    )

    class _Session:
        headers: dict[str, str] = {}
        cookies: object = None

        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, **_kwargs: object) -> SimpleNamespace:
            self.urls.append(url)
            return SimpleNamespace(
                text=homepage,
                content=homepage.encode(),
                status_code=200 if len(self.urls) == 1 else 302,
                headers={} if len(self.urls) == 1 else {"Location": "https://attacker.example/path"},
                url=url,
            )

        def close(self) -> None:
            pass

    session = _Session()
    original_port = http_port._http_fetch_port
    set_http_fetch_port(RequestsHttpFetchPort())
    try:
        with (
            patch.object(http_utils.requests, "Session", return_value=session),
            patch.object(
                http_utils.socket, "getaddrinfo",
                return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
            ),
        ):
            resolution = resolve_query_contract(
                project_key="demo",
                entry={"site_url": "https://example.com", "entry_type": "domain_root"},
                query_terms=["river"],
                probe_timeout=1,
                params={"query_discovery_max_requests": 2},
            )
    finally:
        set_http_fetch_port(original_port)

    assert resolution.status == "blocked"
    assert resolution.entry is None
    assert resolution.execution is None
    assert resolution.diagnostics["reason_codes"] == ["unsafe_target"]
    assert len(session.urls) == 2
    assert all(url.startswith("https://example.com/") for url in session.urls)


def test_interface_validation_never_calls_legacy_semantic_llm() -> None:
    candidate = search_contract_discovery.QueryContractCandidate(
        entry_type="search_template",
        template="https://example.com/search?q={{q}}",
        origin="evidence_form",
        evidence_url="https://example.com/",
        reason="observed form",
    )
    unmatched = SearchCapabilityScore(
        url="https://example.com/reports/unrelated",
        strategy="search_template",
        fetchability="ok",
        matched_by="none",
        route_kind="article",
        candidate_quality="low",
        score=0,
        usable_for_search=False,
    )
    with (
        patch.object(
            search_template_service, "fetch_html",
            return_value=('<a href="/reports/unrelated">Unrelated report</a>', None),
        ),
        patch.object(search_capabilities, "score_search_template_candidates", return_value=[unmatched]) as score,
        patch.object(search_capabilities, "_expand_semantic_query_terms_with_llm") as expand,
        patch.object(search_capabilities, "_select_candidates_with_llm") as select_llm,
    ):
        execution = search_contract_discovery._execute_query_candidate(
            candidate,
            query_text="river",
            params={"allow_candidate_semantic_llm": True},
            probe_timeout=1,
            entry_domain="example.com",
        )

    score.assert_called_once()
    expand.assert_not_called()
    select_llm.assert_not_called()
    assert execution.selected_candidates == []
    assert search_contract_discovery._execution_reason_codes(execution) == ["interaction_required"]
