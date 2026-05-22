from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Mapping, Protocol

from app.services.ingest_config.service import get_config as get_ingest_config
from app.services.ingest_config.service import upsert_config as upsert_ingest_config
from app.services.projects import current_project_key

from .contracts import CONFIG_KEY, CONFIG_TYPE, STATE_CONTRACT_VERSION


class ClueChainStore(Protocol):
    @property
    def project_key(self) -> str | None: ...

    def load_state(self) -> dict[str, Any]: ...

    def save_state(self, state: Mapping[str, Any]) -> dict[str, Any]: ...


class InMemoryClueChainStore:
    def __init__(self, *, project_key: str = "demo_proj", initial_state: Mapping[str, Any] | None = None) -> None:
        self._project_key = project_key
        self._state = normalize_state(initial_state)
        self._lock = RLock()

    @property
    def project_key(self) -> str:
        return self._project_key

    def load_state(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def save_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._state = normalize_state(state)
            return deepcopy(self._state)


class IngestConfigClueChainStore:
    def __init__(self, *, project_key: str | None = None, config_key: str = CONFIG_KEY) -> None:
        self._project_key = str(project_key or "").strip() or None
        self._config_key = str(config_key or CONFIG_KEY).strip() or CONFIG_KEY

    @property
    def project_key(self) -> str:
        return self._project_key or current_project_key()

    def load_state(self) -> dict[str, Any]:
        cfg = get_ingest_config(self.project_key, self._config_key)
        payload = cfg.get("payload") if isinstance(cfg, Mapping) else None
        return normalize_state(payload)

    def save_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        saved = upsert_ingest_config(self.project_key, self._config_key, CONFIG_TYPE, payload=deepcopy(dict(state)))
        payload = saved.get("payload") if isinstance(saved, Mapping) else None
        return normalize_state(payload)


def build_clue_chain_store(*, project_key: str | None = None) -> IngestConfigClueChainStore:
    return IngestConfigClueChainStore(project_key=project_key)


def normalize_state(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, Mapping) else {}
    raw_chains = raw.get("chains") if isinstance(raw.get("chains"), Mapping) else {}
    chains: dict[str, dict[str, Any]] = {}
    for raw_chain_id, raw_record in raw_chains.items():
        chain_id = str(raw_chain_id or "").strip()
        if not chain_id or not isinstance(raw_record, Mapping):
            continue
        chain = _dict_or_empty(raw_record.get("chain"))
        stored_chain_id = str(chain.get("chain_id") or chain_id).strip()
        if not stored_chain_id:
            continue
        chain["chain_id"] = stored_chain_id
        chains[stored_chain_id] = {
            "chain": chain,
            "hops": _record_map(raw_record.get("hops"), "hop_id"),
            "evidence": _record_map(raw_record.get("evidence"), "evidence_id"),
            "candidates": _record_map(raw_record.get("candidates"), "candidate_id"),
            "decisions": _record_map(raw_record.get("decisions"), "decision_id"),
            "edges": _record_map(raw_record.get("edges"), "edge_id"),
            "alias_index": _string_map(raw_record.get("alias_index")),
            "events": _record_list(raw_record.get("events")),
        }
    return {
        "contract_version": str(raw.get("contract_version") or STATE_CONTRACT_VERSION),
        "base_version": max(0, _safe_int(raw.get("base_version"), default=0)),
        "chains": chains,
    }


def _record_map(raw: Any, id_field: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, Mapping):
        return out
    for raw_key, raw_value in raw.items():
        if not isinstance(raw_value, Mapping):
            continue
        item = dict(raw_value)
        item_id = str(item.get(id_field) or raw_key or "").strip()
        if not item_id:
            continue
        item[id_field] = item_id
        out[item_id] = item
    return out


def _record_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _string_map(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(raw, Mapping):
        return out
    for key, value in raw.items():
        left = str(key or "").strip()
        right = str(value or "").strip()
        if left and right:
            out[left] = right
    return out


def _dict_or_empty(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, Mapping) else {}


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return default
