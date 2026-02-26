"""Resource pool extraction service."""

from .append_adapter import DefaultResourcePoolAppendAdapter
from .auto_classify import classify_site_entry
from .capture_config import get_capture_config, upsert_capture_config
from .extract import append_url, extract_from_documents, extract_from_tasks
from .resolver import list_urls
from .site_entries import get_site_entry_by_url, list_site_entries, upsert_site_entry
from .site_entry_discovery import (
    discover_site_entries_from_urls,
    write_discovered_site_entries,
)
from .unified_search import unified_search_by_item

__all__ = [
    "classify_site_entry",
    "append_url",
    "DefaultResourcePoolAppendAdapter",
    "discover_site_entries_from_urls",
    "extract_from_documents",
    "extract_from_tasks",
    "get_capture_config",
    "get_site_entry_by_url",
    "list_urls",
    "list_site_entries",
    "unified_search_by_item",
    "upsert_site_entry",
    "upsert_capture_config",
    "write_discovered_site_entries",
]
