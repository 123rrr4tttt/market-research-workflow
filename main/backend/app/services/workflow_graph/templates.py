from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from app.services.ingest_config.service import get_config as get_ingest_config
from app.services.ingest_config.service import upsert_config as upsert_ingest_config
from app.services.projects import current_project_key

CONFIG_KEY = "workflow_graph_templates_v1"
CONFIG_TYPE = "workflow_graph_templates"


class WorkflowGraphTemplateService:
    def list_templates(self) -> dict[str, Any]:
        state = self._load_state()
        items = [self._serialize_template_summary(item) for item in state["templates"].values()]
        items.sort(key=lambda x: (str(x.get("updated_at") or ""), str(x.get("template_id") or "")), reverse=True)
        return {
            "items": items,
            "base_version": state["base_version"],
        }

    def create_template(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        template_id = str(payload.get("template_id") or "").strip() or f"tpl_{uuid4().hex}"
        now = _utcnow()
        state = self._mutate(
            base_version=_read_base_version(payload),
            mutator=lambda s: _create_template_mutation(s, template_id=template_id, payload=payload, now=now),
        )
        return {
            "template": self._serialize_template_detail(state["templates"][template_id]),
            "base_version": state["base_version"],
        }

    def get_template(self, template_id: str) -> dict[str, Any]:
        state = self._load_state()
        template = state["templates"].get(str(template_id))
        if template is None:
            raise KeyError(f"template not found: {template_id}")
        return {
            "template": self._serialize_template_detail(template),
            "base_version": state["base_version"],
        }

    def patch_template(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        tid = str(template_id).strip()
        if not tid:
            raise ValueError("template_id is required")

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            template = state["templates"].get(tid)
            if template is None:
                raise KeyError(f"template not found: {tid}")
            if "name" in payload:
                template["name"] = str(payload.get("name") or "").strip()
            if "description" in payload:
                template["description"] = str(payload.get("description") or "").strip()
            if "metadata" in payload:
                metadata = payload.get("metadata")
                if metadata is None:
                    template["metadata"] = {}
                elif isinstance(metadata, Mapping):
                    template["metadata"] = dict(metadata)
                else:
                    raise ValueError("metadata must be a mapping")
            template["updated_at"] = _utcnow()
            return state

        state = self._mutate(base_version=_read_base_version(payload), mutator=_mutator)
        return {
            "template": self._serialize_template_detail(state["templates"][tid]),
            "base_version": state["base_version"],
        }

    def delete_template(self, template_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        tid = str(template_id).strip()
        if not tid:
            raise ValueError("template_id is required")

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            if tid not in state["templates"]:
                raise KeyError(f"template not found: {tid}")
            state["templates"].pop(tid, None)
            return state

        state = self._mutate(base_version=_read_base_version(payload or {}), mutator=_mutator)
        return {"deleted": True, "template_id": tid, "base_version": state["base_version"]}

    def list_versions(self, template_id: str) -> dict[str, Any]:
        state = self._load_state()
        template = self._must_get_template(state, template_id)
        items = [self._serialize_version_summary(item) for item in template["versions"].values()]
        items.sort(key=lambda x: (str(x.get("created_at") or ""), str(x.get("version_id") or "")), reverse=True)
        return {
            "template_id": template["template_id"],
            "active_version_id": template.get("active_version_id"),
            "items": items,
            "base_version": state["base_version"],
        }

    def create_version(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        dsl = payload.get("dsl")
        if not isinstance(dsl, Mapping):
            raise ValueError("dsl is required and must be a mapping")
        tid = str(template_id).strip()
        if not tid:
            raise ValueError("template_id is required")
        version_id = str(payload.get("version_id") or "").strip() or f"ver_{uuid4().hex}"
        now = _utcnow()

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            template = self._must_get_template(state, tid)
            if version_id in template["versions"]:
                raise ValueError(f"version already exists: {version_id}")
            template["versions"][version_id] = {
                "version_id": version_id,
                "dsl": dict(dsl),
                "created_at": now,
            }
            if not template.get("active_version_id"):
                template["active_version_id"] = version_id
            template["updated_at"] = now
            return state

        state = self._mutate(base_version=_read_base_version(payload), mutator=_mutator)
        template = self._must_get_template(state, tid)
        return {
            "template_id": tid,
            "active_version_id": template.get("active_version_id"),
            "version": self._serialize_version_detail(template["versions"][version_id]),
            "base_version": state["base_version"],
        }

    def get_version(self, template_id: str, version_id: str) -> dict[str, Any]:
        state = self._load_state()
        template = self._must_get_template(state, template_id)
        version = self._must_get_version(template, version_id)
        return {
            "template_id": template["template_id"],
            "active_version_id": template.get("active_version_id"),
            "version": self._serialize_version_detail(version),
            "base_version": state["base_version"],
        }

    def activate_version(
        self,
        template_id: str,
        version_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        tid = str(template_id).strip()
        vid = str(version_id).strip()
        if not tid or not vid:
            raise ValueError("template_id and version_id are required")

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            template = self._must_get_template(state, tid)
            self._must_get_version(template, vid)
            template["active_version_id"] = vid
            template["updated_at"] = _utcnow()
            return state

        state = self._mutate(base_version=_read_base_version(payload or {}), mutator=_mutator)
        return {
            "template_id": tid,
            "version_id": vid,
            "active_version_id": vid,
            "base_version": state["base_version"],
        }

    def resolve_version_dsl(self, template_id: str, version_id: str | None = None) -> tuple[dict[str, Any], str]:
        state = self._load_state()
        template = self._must_get_template(state, template_id)
        resolved_version_id = str(version_id or "").strip() or str(template.get("active_version_id") or "").strip()
        if not resolved_version_id:
            raise ValueError(f"template has no active version: {template_id}")
        version = self._must_get_version(template, resolved_version_id)
        return deepcopy(version["dsl"]), resolved_version_id

    def _load_state(self) -> dict[str, Any]:
        project_key = current_project_key()
        cfg = get_ingest_config(project_key, CONFIG_KEY)
        payload = cfg.get("payload") if isinstance(cfg, Mapping) else None
        return _normalize_state(payload)

    def _save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        project_key = current_project_key()
        saved = upsert_ingest_config(project_key, CONFIG_KEY, CONFIG_TYPE, payload=deepcopy(state))
        payload = saved.get("payload") if isinstance(saved, Mapping) else None
        return _normalize_state(payload)

    def _mutate(self, *, base_version: int | None, mutator: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        state = self._load_state()
        current = int(state["base_version"])
        if base_version is not None and base_version != current:
            raise ValueError(f"conflict: base_version mismatch expected={base_version} actual={current}")
        updated = mutator(deepcopy(state))
        updated["base_version"] = current + 1
        return self._save_state(updated)

    @staticmethod
    def _must_get_template(state: Mapping[str, Any], template_id: str) -> dict[str, Any]:
        tid = str(template_id).strip()
        template = state["templates"].get(tid)
        if template is None:
            raise KeyError(f"template not found: {template_id}")
        return template

    @staticmethod
    def _must_get_version(template: Mapping[str, Any], version_id: str) -> dict[str, Any]:
        vid = str(version_id).strip()
        version = template["versions"].get(vid)
        if version is None:
            raise KeyError(f"version not found: {version_id}")
        return version

    @staticmethod
    def _serialize_template_summary(template: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "template_id": template.get("template_id"),
            "name": template.get("name"),
            "description": template.get("description"),
            "metadata": deepcopy(template.get("metadata") or {}),
            "active_version_id": template.get("active_version_id"),
            "versions_count": len(template.get("versions") or {}),
            "created_at": template.get("created_at"),
            "updated_at": template.get("updated_at"),
        }

    def _serialize_template_detail(self, template: Mapping[str, Any]) -> dict[str, Any]:
        versions = [self._serialize_version_summary(item) for item in (template.get("versions") or {}).values()]
        versions.sort(key=lambda x: (str(x.get("created_at") or ""), str(x.get("version_id") or "")), reverse=True)
        return {
            **self._serialize_template_summary(template),
            "versions": versions,
        }

    @staticmethod
    def _serialize_version_summary(version: Mapping[str, Any]) -> dict[str, Any]:
        dsl = version.get("dsl")
        nodes = dsl.get("nodes") if isinstance(dsl, Mapping) else None
        node_count = len(nodes) if isinstance(nodes, list) else None
        return {
            "version_id": version.get("version_id"),
            "created_at": version.get("created_at"),
            "node_count": node_count,
        }

    @staticmethod
    def _serialize_version_detail(version: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "version_id": version.get("version_id"),
            "created_at": version.get("created_at"),
            "dsl": deepcopy(version.get("dsl") or {}),
        }


def _create_template_mutation(
    state: dict[str, Any],
    *,
    template_id: str,
    payload: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    if template_id in state["templates"]:
        raise ValueError(f"template already exists: {template_id}")
    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping")
    state["templates"][template_id] = {
        "template_id": template_id,
        "name": str(payload.get("name") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "metadata": dict(metadata or {}),
        "active_version_id": None,
        "created_at": now,
        "updated_at": now,
        "versions": {},
    }
    return state


def _normalize_state(payload: Any) -> dict[str, Any]:
    state = payload if isinstance(payload, Mapping) else {}
    raw_templates = state.get("templates")
    templates: dict[str, dict[str, Any]] = {}
    if isinstance(raw_templates, Mapping):
        for raw_tid, raw_template in raw_templates.items():
            tid = str(raw_tid or "").strip()
            if not tid or not isinstance(raw_template, Mapping):
                continue
            raw_versions = raw_template.get("versions")
            versions: dict[str, dict[str, Any]] = {}
            if isinstance(raw_versions, Mapping):
                for raw_vid, raw_version in raw_versions.items():
                    vid = str(raw_vid or "").strip()
                    if not vid or not isinstance(raw_version, Mapping):
                        continue
                    dsl = raw_version.get("dsl")
                    versions[vid] = {
                        "version_id": vid,
                        "dsl": dict(dsl) if isinstance(dsl, Mapping) else {},
                        "created_at": str(raw_version.get("created_at") or _utcnow()),
                    }
            templates[tid] = {
                "template_id": tid,
                "name": str(raw_template.get("name") or "").strip(),
                "description": str(raw_template.get("description") or "").strip(),
                "metadata": dict(raw_template.get("metadata") or {})
                if isinstance(raw_template.get("metadata"), Mapping)
                else {},
                "active_version_id": str(raw_template.get("active_version_id") or "").strip() or None,
                "created_at": str(raw_template.get("created_at") or _utcnow()),
                "updated_at": str(raw_template.get("updated_at") or _utcnow()),
                "versions": versions,
            }

    raw_base_version = state.get("base_version", 0)
    try:
        base_version = int(raw_base_version)
    except Exception:  # noqa: BLE001
        base_version = 0
    if base_version < 0:
        base_version = 0
    return {
        "base_version": base_version,
        "templates": templates,
    }


def _read_base_version(payload: Mapping[str, Any]) -> int | None:
    if "base_version" not in payload:
        return None
    raw = payload.get("base_version")
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("base_version must be an integer") from exc
    if value < 0:
        raise ValueError("base_version must be >= 0")
    return value


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
