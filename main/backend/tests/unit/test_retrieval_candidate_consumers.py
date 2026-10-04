from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from functorial_kit.core.failure import Failure
from app.services.discovery.adapters import DefaultDiscoveryAdapter
from app.services.search import web
from app.services.search.candidate_contracts import CandidateSearchRequest
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    DEFAULT_CANDIDATE_NATIVE_SOURCE,
    CandidateNativeSource,
    compile_candidate_native_contribution,
)

pytestmark = pytest.mark.unit


def test_default_discovery_legacy_list_comes_from_same_typed_call() -> None:
    adapter = DefaultDiscoveryAdapter()
    row = {"title": "A", "link": "https://example.org/a?utm_source=ad", "snippet": "text", "source": "searxng"}
    with patch.object(web, "_searxng_search", return_value=[row]):
        bundle = adapter.search_candidates(CandidateSearchRequest(topic="topic", provider="searxng", keywords=("topic",), exclude_existing=False))
    with patch.object(web, "_searxng_search", return_value=[row]):
        legacy = adapter.search(topic="topic", provider="searxng", keywords=("topic",), exclude_existing=False)
    assert isinstance(legacy, list)
    assert legacy == bundle.legacy_list()
    assert legacy[0]["link"] == "https://example.org/a"
    assert bundle.candidates[0].resource_uri == legacy[0]["link"]


def test_nondefault_native_definition_uses_same_consumer_and_codec() -> None:
    alternative = replace(
        DEFAULT_CANDIDATE_NATIVE_SOURCE,
        contribution_id="mrw.retrieval.candidate.local.v1",
        operation_id="retrieval.candidate.local-discover.v1",
        default_provider="searxng",
    )
    native = compile_candidate_native_contribution(alternative)
    assert not isinstance(native, Failure)
    assert native.definition.source == alternative
    codec = native.definition.request_codec
    request = CandidateSearchRequest(topic="local", keywords=("local",), exclude_existing=False)
    assert codec.decode_payload(codec.encode_payload(request)) == request
    adapter = DefaultDiscoveryAdapter(alternative)
    row = {"title": "Local", "link": "https://example.org/local", "snippet": "local", "source": "searxng"}
    with patch.object(web, "_searxng_search", return_value=[row]) as search:
        bundle = adapter.search_candidates(request)
    assert search.call_count == 1
    assert bundle.request.provider == "searxng"
    assert bundle.candidates[0].resource_uri == "https://example.org/local"
    assert bundle.observations[0].route == "explicit:searxng"
    assert native.projection.id == alternative.contribution_id


def test_invalid_provider_declaration_rejected_before_binding() -> None:
    invalid = CandidateNativeSource(
        contribution_id="candidate.invalid.v1",
        operation_id="candidate.invalid.search.v1",
        owner="test",
        default_provider="unimplemented-provider",
    )
    assert isinstance(compile_candidate_native_contribution(invalid), Failure)
