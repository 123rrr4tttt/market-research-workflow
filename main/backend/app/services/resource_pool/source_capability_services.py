"""Compatibility exports for shared source capability services."""

from .search_template_service import SearchTemplateExecutionResult
from .search_template_service import SearchTemplateRawCandidate
from .search_template_service import build_search_template_urls
from .search_template_service import collect_sitemap_urls
from .search_template_service import execute_feed_probe
from .search_template_service import execute_search_template
from .search_template_service import execute_sitemap_probe
from .search_template_service import extract_feed_candidates
from .search_template_service import extract_link_candidates_from_html
from .search_template_service import normalize_candidate_url
from .search_template_service import normalize_search_template_placeholders
from .search_template_service import resolve_search_template_pagination
from .search_result_parser_service import SearchResultParserProfile
from .search_result_parser_service import SearchResultParserModule
from .search_result_parser_service import parse_search_result_candidates
from .search_result_parser_service import resolve_search_result_parser_modules
from .search_result_parser_service import resolve_search_result_parser_profile
from .search_result_parser_profiles import ParserProfileCapability
from .search_result_parser_profiles import resolve_parser_profile_capability

__all__ = [
    "SearchTemplateExecutionResult",
    "SearchTemplateRawCandidate",
    "build_search_template_urls",
    "collect_sitemap_urls",
    "execute_feed_probe",
    "execute_search_template",
    "execute_sitemap_probe",
    "extract_feed_candidates",
    "extract_link_candidates_from_html",
    "parse_search_result_candidates",
    "resolve_search_result_parser_modules",
    "normalize_candidate_url",
    "normalize_search_template_placeholders",
    "resolve_search_result_parser_profile",
    "resolve_search_template_pagination",
    "SearchResultParserModule",
    "SearchResultParserProfile",
    "ParserProfileCapability",
    "resolve_parser_profile_capability",
]
