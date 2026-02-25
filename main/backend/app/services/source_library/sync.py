from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import SharedIngestChannel, SharedSourceLibraryItem
from ..projects import bind_schema
from .loader import load_global_library_files


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    return {}


def sync_shared_library_from_files() -> Dict[str, Any]:
    data = load_global_library_files()
    channels_data = data.get("channels", [])
    items_data = data.get("items", [])

    upserted_channels = 0
    upserted_items = 0

    with bind_schema("public"):
        with SessionLocal() as session:
            for payload in channels_data:
                channel_key = str(payload.get("channel_key", "")).strip()
                if not channel_key:
                    continue
                row = session.execute(
                    select(SharedIngestChannel).where(SharedIngestChannel.channel_key == channel_key)
                ).scalar_one_or_none()
                if row is None:
                    row = SharedIngestChannel(channel_key=channel_key)
                    session.add(row)

                row.name = str(payload.get("name") or channel_key)
                row.kind = str(payload.get("kind") or "unknown")
                row.provider = str(payload.get("provider") or "unknown")
                row.description = payload.get("description")
                row.credential_refs = _as_list(payload.get("credential_refs"))
                row.default_params = _as_dict(payload.get("default_params"))
                row.param_schema = _as_dict(payload.get("param_schema"))
                row.extends_channel_key = payload.get("extends_channel_key")
                row.enabled = bool(payload.get("enabled", True))
                row.extra = _as_dict(payload.get("extra"))
                upserted_channels += 1

            for payload in items_data:
                item_key = str(payload.get("item_key", "")).strip()
                channel_key = str(payload.get("channel_key", "")).strip()
                if not item_key or not channel_key:
                    continue
                row = session.execute(
                    select(SharedSourceLibraryItem).where(SharedSourceLibraryItem.item_key == item_key)
                ).scalar_one_or_none()
                if row is None:
                    row = SharedSourceLibraryItem(item_key=item_key)
                    session.add(row)

                row.name = str(payload.get("name") or item_key)
                row.channel_key = channel_key
                row.description = payload.get("description")
                row.params = _as_dict(payload.get("params"))
                row.tags = _as_list(payload.get("tags"))
                row.schedule = payload.get("schedule")
                row.extends_item_key = payload.get("extends_item_key")
                row.enabled = bool(payload.get("enabled", True))
                row.extra = _as_dict(payload.get("extra"))
                upserted_items += 1

            session.commit()

    return {
        "upserted_channels": upserted_channels,
        "upserted_items": upserted_items,
    }

