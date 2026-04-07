"""Resource pool extraction service."""

from .append_adapter import DefaultResourcePoolAppendAdapter
from .auto_classify import classify_site_entry, classify_site_entries_batch
from .capture_config import get_capture_config, upsert_capture_config
from .extract import append_url, extract_from_documents, extract_from_tasks
from .open_source_source_importer import import_open_source_preset_pack, list_open_source_preset_packs
from .resolver import list_urls
from .search_contract_discovery import discover_search_contract
from .site_entries import get_site_entry_by_url, list_site_entries, simplify_site_entries, upsert_site_entry
from .site_entry_discovery import (
    discover_site_entries_from_urls,
    list_discovery_domains,
    write_discovered_site_entries,
)
from .unified_search import unified_search_by_item, unified_search_by_item_payload

__all__ = [
    "classify_site_entry",
    "classify_site_entries_batch",
    "append_url",
    "DefaultResourcePoolAppendAdapter",
    "discover_site_entries_from_urls",
    "list_discovery_domains",
    "extract_from_documents",
    "extract_from_tasks",
    "get_capture_config",
    "discover_search_contract",
    "get_site_entry_by_url",
    "import_open_source_preset_pack",
    "list_urls",
    "list_open_source_preset_packs",
    "list_site_entries",
    "simplify_site_entries",
    "unified_search_by_item",
    "unified_search_by_item_payload",
    "upsert_site_entry",
    "upsert_capture_config",
    "write_discovered_site_entries",
]
