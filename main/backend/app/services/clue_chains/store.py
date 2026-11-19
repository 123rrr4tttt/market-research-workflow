from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Annotated, Mapping, Protocol, SupportsIndex, SupportsInt, TypedDict, TypeGuard

from app.services.ingest_config.service import get_config as get_ingest_config
from app.services.ingest_config.service import upsert_config as upsert_ingest_config
from app.services.projects import current_project_key

from .contracts import CONFIG_KEY, CONFIG_TYPE, STATE_CONTRACT_VERSION


class ClueChainRecord(TypedDict):
    chain: dict[str, object]
    hops: dict[str, dict[str, object]]
    evidence: dict[str, dict[str, object]]
    candidates: dict[str, dict[str, object]]
    decisions: dict[str, dict[str, object]]
    edges: dict[str, dict[str, object]]
    alias_index: dict[str, str]
    events: list[dict[str, object]]


class ClueChainState(TypedDict):
    contract_version: str
    base_version: int
    chains: dict[str, ClueChainRecord]


class ClueChainStore(Protocol):
    @property
    def project_key(self) -> str | None: ...

    def load_state(self) -> ClueChainState: ...

    def save_state(self, state: Mapping[str, object]) -> ClueChainState: ...


class InMemoryClueChainStore:
    def __init__(self, *, project_key: str = "demo_proj", initial_state: Mapping[str, object] | None = None) -> None:
        self._project_key = project_key
        self._state = normalize_state(initial_state)
        self._lock = RLock()

    @property
    def project_key(self) -> str:
        return self._project_key

    def load_state(self) -> ClueChainState:
        with self._lock:
            return deepcopy(self._state)

    def save_state(self, state: Mapping[str, object]) -> ClueChainState:
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

    def load_state(self) -> ClueChainState:
        cfg = get_ingest_config(self.project_key, self._config_key)
        payload = cfg.get("payload") if cfg is not None else None
        return normalize_state(payload)

    def save_state(self, state: Mapping[str, object]) -> ClueChainState:
        saved = upsert_ingest_config(self.project_key, self._config_key, CONFIG_TYPE, payload=deepcopy(dict(state)))
        payload = saved.get("payload")
        return normalize_state(payload)


def build_clue_chain_store(
    *, project_key: str | None = None
) -> Annotated[
    IngestConfigClueChainStore,
    "kit:prepared-command effect_boundary=ingest_config_clue_chain_store "
    "witness=test:test_service_results_declare_sources_and_effect_authority",
]:
    return IngestConfigClueChainStore(project_key=project_key)


def normalize_state(payload: object) -> ClueChainState:
    raw = _object_mapping_or_empty(payload)
    raw_chains = _object_mapping_or_empty(raw.get("chains"))
    chains: dict[str, ClueChainRecord] = {}
    for raw_chain_id, raw_record_value in raw_chains.items():
        chain_id = str(raw_chain_id or "").strip()
        if not chain_id or not _is_object_mapping(raw_record_value):
            continue
        raw_record = raw_record_value
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


def _record_map(raw: object, id_field: str) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    if not _is_object_mapping(raw):
        return out
    for raw_key, raw_value in raw.items():
        item = _string_object_mapping(raw_value)
        if item is None:
            continue
        item_id = str(item.get(id_field) or raw_key or "").strip()
        if not item_id:
            continue
        item[id_field] = item_id
        out[item_id] = item
    return out


def _record_list(raw: object) -> list[dict[str, object]]:
    if not _is_object_list(raw):
        return []
    return [item for value in raw if (item := _string_object_mapping(value)) is not None]


def _string_map(raw: object) -> dict[str, str]:
    out: dict[str, str] = {}
    if not _is_object_mapping(raw):
        return out
    for key, value in raw.items():
        left = str(key or "").strip()
        right = str(value or "").strip()
        if left and right:
            out[left] = right
    return out


def _dict_or_empty(raw: object) -> dict[str, object]:
    return _string_object_mapping(raw) or {}


def _object_mapping_or_empty(raw: object) -> Mapping[object, object]:
    return raw if _is_object_mapping(raw) else {}


def _safe_int(value: object, *, default: int) -> int:
    if not _is_int_convertible(value):
        return default
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return default


def _is_int_convertible(value: object) -> TypeGuard[str | bytes | bytearray | SupportsInt | SupportsIndex]:
    return isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex))


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _string_object_mapping(value: object) -> dict[str, object] | None:
    if not _is_object_mapping(value):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result
