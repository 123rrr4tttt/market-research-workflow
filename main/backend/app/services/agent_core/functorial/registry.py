"""FunctorialCatalog — mutable registry for the lightweight development projection.

This is not a production canonical authority. Persistence is local JSONL under
``.data/functorial/``; writes are append-only and current records are versioned.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, NoReturn, TypeAlias

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import (
    agent_functorial_projection_failures,
)

_COLLECTIONS = ("operators", "motifs", "workflows")
_FAILURE_WITNESS = "test:test_w02_functorial_projection_failure_lifts"
ProjectionFailure: TypeAlias = Failure


class CatalogLoadError(RuntimeError):
    """Raised when persisted projection bytes are malformed."""


def _projection_failure(code: str, message: str, *, collection: str | None = None) -> Failure:
    context: dict[str, Any] = {
        "owner": "agent_core.functorial.registry",
        "operation": "functorial.catalog",
        "failure_family": agent_functorial_projection_failures.name,
        "witness": _FAILURE_WITNESS,
    }
    if collection is not None:
        context["collection"] = collection
    return agent_functorial_projection_failures.fail(code, message, context)


def _raise_projection_failure(value: Failure, exception_type: type[Exception]) -> NoReturn:
    if not agent_functorial_projection_failures.matches(value):
        # kit:boundary owner=registry.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_functorial_projection_failure_lifts
        raise TypeError("invalid functorial projection failure")  # noqa: TRY003
    # kit:boundary owner=registry.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.functorial_projection.failure witness=test:test_w02_functorial_projection_failure_lifts
    raise exception_type(value.message)


class FunctorialCatalog:
    def __init__(self, data_root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._data_root = data_root or (
            Path(__file__).resolve().parents[4] / ".data" / "functorial"
        )
        self._store: dict[str, dict[str, dict[str, Any]]] = {
            c: {} for c in _COLLECTIONS
        }
        loaded = self._load()
        if isinstance(loaded, Failure):
            _raise_projection_failure(loaded, CatalogLoadError)

    def _path(self, collection: str) -> Path:
        return self._data_root / f"{collection}.jsonl"

    def _load(self) -> None | ProjectionFailure:
        for c in _COLLECTIONS:
            p = self._path(c)
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as exc:
                        return _projection_failure(
                            "catalog_record_malformed",
                            f"malformed functorial catalog line in {p}: {exc}",
                            collection=c,
                        )
                    if not isinstance(item, dict):
                        return _projection_failure(
                            "catalog_record_malformed",
                            f"catalog record must be an object in {p}",
                            collection=c,
                        )
                    key = str(
                        item.get("id")
                        or item.get("operator_id")
                        or item.get("motif_id")
                        or item.get("workflow_id")
                        or ""
                    ).strip()
                    if not key:
                        return _projection_failure(
                            "catalog_record_malformed",
                            f"catalog record id is required in {p}",
                            collection=c,
                        )
                    self._store[c][key] = item

    def _upsert(
        self, collection: str, record_id: str, spec: dict[str, Any]
    ) -> dict[str, Any] | ProjectionFailure:
        if collection not in _COLLECTIONS:
            return _projection_failure(
                "ref_kind_unsupported", f"unknown collection: {collection}", collection=collection
            )
        if not isinstance(spec, dict):
            return _projection_failure(
                "catalog_record_malformed",
                "catalog record must be an object",
                collection=collection,
            )
        record_id = str(record_id or "").strip()
        if not record_id:
            return _projection_failure(
                "ref_id_missing",
                "record id is required",
                collection=collection,
            )
        with self._lock:
            item = dict(spec)
            item["id"] = record_id
            previous = self._store[collection].get(record_id)
            item["revision"] = int((previous or {}).get("revision", 0)) + 1
            self._store[collection][record_id] = item
            self._path(collection).parent.mkdir(parents=True, exist_ok=True)
            with self._path(collection).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
            return item

    def upsert_operator(self, operator_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        result = self._upsert("operators", operator_id, spec)
        if isinstance(result, Failure):
            _raise_projection_failure(result, ValueError)
        return result

    def upsert_motif(self, motif_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        result = self._upsert("motifs", motif_id, spec)
        if isinstance(result, Failure):
            _raise_projection_failure(result, ValueError)
        return result

    def upsert_workflow(self, workflow_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        result = self._upsert("workflows", workflow_id, spec)
        if isinstance(result, Failure):
            _raise_projection_failure(result, ValueError)
        return result

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        if collection not in _COLLECTIONS:
            return None
        return self._store[collection].get(str(record_id or "").strip())

    def list(self, collection: str) -> list[dict[str, Any]]:
        if collection not in _COLLECTIONS:
            return []
        return [self._store[collection][k] for k in sorted(self._store[collection])]


catalog = FunctorialCatalog()
