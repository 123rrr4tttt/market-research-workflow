"""Clue Chain service helpers."""

from .external_search_expansion import (
    CONTRACT_VERSION as CLUE_CHAIN_EXTERNAL_SEARCH_EXPANSION_CONTRACT_VERSION,
    ExternalSearchExpansionRequest,
    FixtureExternalSearchProvider,
    LiveHookExternalSearchProvider,
    build_external_search_provider,
    expand_external_search,
    external_search_dedupe_key,
    normalize_external_search_url,
)
from .source_library_expansion import (
    CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION,
    expand_source_library_hop,
    merge_candidate_aliases,
)

__all__ = [
    "CLUE_CHAIN_EXTERNAL_SEARCH_EXPANSION_CONTRACT_VERSION",
    "CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION",
    "ExternalSearchExpansionRequest",
    "FixtureExternalSearchProvider",
    "LiveHookExternalSearchProvider",
    "build_external_search_provider",
    "expand_external_search",
    "expand_source_library_hop",
    "external_search_dedupe_key",
    "merge_candidate_aliases",
    "normalize_external_search_url",
]
