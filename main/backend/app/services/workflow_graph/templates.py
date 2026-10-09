from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable, Mapping, NoReturn, SupportsIndex, SupportsInt, TypedDict, TypeGuard
from uuid import uuid4

from app.services.ingest_config.service import get_config as get_ingest_config
from app.services.ingest_config.service import upsert_config as upsert_ingest_config
from app.services.projects import current_project_key
from app.services.workflow_graph.contracts import raise_workflow_graph_legacy, workflow_graph_failure
from app.services.workflow_graph.edit_contract import parse_graph_edit_draft_contract

CONFIG_KEY = "workflow_graph_templates_v1"
CONFIG_TYPE = "workflow_graph_templates"


class _Template(TypedDict):
    template_id: str
    name: str
    description: str
    metadata: dict[str, object]
    active_version_id: str | None
    created_at: str
    updated_at: str
    versions: dict[str, dict[str, object]]


class _TemplateState(TypedDict):
    base_version: int
    templates: dict[str, _Template]


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


def _raise_template_failure(code: str, message: str, *, exception_type: type[Exception] = ValueError, cause: BaseException | None = None) -> NoReturn:
    failure = workflow_graph_failure(code, message, owner="workflow_graph.templates", public_exception=exception_type, public_message=message, field="template", index=-1)
    raise_workflow_graph_legacy(failure, exception_type=exception_type, cause=cause)


class WorkflowGraphTemplateService:
    def list_templates(self) -> dict[str, object]:
        state = self._load_state()
        items = [self._serialize_template_summary(item) for item in state["templates"].values()]
        items.sort(key=lambda x: (str(x.get("updated_at") or ""), str(x.get("template_id") or "")), reverse=True)
        return {
            "items": items,
            "base_version": state["base_version"],
        }

    def create_template(self, payload: Mapping[str, object]) -> dict[str, object]:
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

    def get_template(self, template_id: str) -> dict[str, object]:
        state = self._load_state()
        template = state["templates"].get(str(template_id))
        if template is None:
            _raise_template_failure("object_not_found", f"template not found: {template_id}", exception_type=KeyError)
        return {
            "template": self._serialize_template_detail(template),
            "base_version": state["base_version"],
        }

    def patch_template(self, template_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        tid = str(template_id).strip()
        if not tid:
            _raise_template_failure("contract_invalid", "template_id is required")

        def _mutator(state: _TemplateState) -> _TemplateState:
            template = state["templates"].get(tid)
            if template is None:
                _raise_template_failure("object_not_found", f"template not found: {tid}", exception_type=KeyError)
            if "name" in payload:
                template["name"] = str(payload.get("name") or "").strip()
            if "description" in payload:
                template["description"] = str(payload.get("description") or "").strip()
            if "metadata" in payload:
                metadata = payload.get("metadata")
                if metadata is None:
                    template["metadata"] = {}
                elif (metadata_mapping := _string_object_mapping(metadata)) is not None:
                    template["metadata"] = metadata_mapping
                else:
                    _raise_template_failure("contract_invalid", "metadata must be a mapping")
            template["updated_at"] = _utcnow()
            return state

        state = self._mutate(base_version=_read_base_version(payload), mutator=_mutator)
        return {
            "template": self._serialize_template_detail(state["templates"][tid]),
            "base_version": state["base_version"],
        }

    def delete_template(self, template_id: str, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        tid = str(template_id).strip()
        if not tid:
            _raise_template_failure("contract_invalid", "template_id is required")

        def _mutator(state: _TemplateState) -> _TemplateState:
            if tid not in state["templates"]:
                _raise_template_failure("object_not_found", f"template not found: {tid}", exception_type=KeyError)
            state["templates"].pop(tid, None)
            return state

        state = self._mutate(base_version=_read_base_version(payload or {}), mutator=_mutator)
        return {"deleted": True, "template_id": tid, "base_version": state["base_version"]}

    def list_versions(self, template_id: str) -> dict[str, object]:
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

    def create_version(self, template_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        dsl = _string_object_mapping(payload.get("dsl"))
        if dsl is None:
            _raise_template_failure("contract_invalid", "dsl is required and must be a mapping")
        graph_object_kind = str(
            payload.get("graph_object_kind") or payload.get("object_kind") or "template_graph"
        ).strip()
        parse_graph_edit_draft_contract(dsl, object_kind=graph_object_kind)
        tid = str(template_id).strip()
        if not tid:
            _raise_template_failure("contract_invalid", "template_id is required")
        version_id = str(payload.get("version_id") or "").strip() or f"ver_{uuid4().hex}"
        now = _utcnow()

        def _mutator(state: _TemplateState) -> _TemplateState:
            template = self._must_get_template(state, tid)
            if version_id in template["versions"]:
                _raise_template_failure("contract_invalid", f"version already exists: {version_id}")
            template["versions"][version_id] = {
                "version_id": version_id,
                "dsl": dsl,
                "graph_object_kind": graph_object_kind,
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

    def get_version(self, template_id: str, version_id: str) -> dict[str, object]:
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
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        tid = str(template_id).strip()
        vid = str(version_id).strip()
        if not tid or not vid:
            _raise_template_failure("contract_invalid", "template_id and version_id are required")

        def _mutator(state: _TemplateState) -> _TemplateState:
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

    def resolve_version_dsl(self, template_id: str, version_id: str | None = None) -> tuple[dict[str, object], str]:
        state = self._load_state()
        template = self._must_get_template(state, template_id)
        resolved_version_id = str(version_id or "").strip() or str(template.get("active_version_id") or "").strip()
        if not resolved_version_id:
            _raise_template_failure("object_not_found", f"template has no active version: {template_id}")
        version = self._must_get_version(template, resolved_version_id)
        dsl = _string_object_mapping(version.get("dsl"))
        if dsl is None:
            _raise_template_failure("contract_invalid", f"template version dsl is malformed: {resolved_version_id}")
        return deepcopy(dsl), resolved_version_id

    def _load_state(self) -> _TemplateState:
        project_key = current_project_key()
        cfg = get_ingest_config(project_key, CONFIG_KEY)
        payload = cfg.get("payload") if cfg is not None else None
        return _normalize_state(payload)

    def _save_state(self, state: _TemplateState) -> _TemplateState:
        project_key = current_project_key()
        saved = upsert_ingest_config(project_key, CONFIG_KEY, CONFIG_TYPE, payload=deepcopy(dict(state)))
        payload = saved.get("payload")
        return _normalize_state(payload)

    def _mutate(self, *, base_version: int | None, mutator: Callable[[_TemplateState], _TemplateState]) -> _TemplateState:
        state = self._load_state()
        current = int(state["base_version"])
        if base_version is not None and base_version != current:
            _raise_template_failure("revision_conflict", f"conflict: base_version mismatch expected={base_version} actual={current}")
        updated = mutator(deepcopy(state))
        updated["base_version"] = current + 1
        return self._save_state(updated)

    @staticmethod
    def _must_get_template(state: _TemplateState, template_id: str) -> _Template:
        tid = str(template_id).strip()
        template = state["templates"].get(tid)
        if template is None:
            _raise_template_failure("object_not_found", f"template not found: {template_id}", exception_type=KeyError)
        return template

    @staticmethod
    def _must_get_version(template: _Template, version_id: str) -> dict[str, object]:
        vid = str(version_id).strip()
        version = template["versions"].get(vid)
        if version is None:
            _raise_template_failure("object_not_found", f"version not found: {version_id}", exception_type=KeyError)
        return version

    @staticmethod
    def _serialize_template_summary(template: _Template) -> dict[str, object]:
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

    def _serialize_template_detail(self, template: _Template) -> dict[str, object]:
        versions = [self._serialize_version_summary(item) for item in template["versions"].values()]
        versions.sort(key=lambda x: (str(x.get("created_at") or ""), str(x.get("version_id") or "")), reverse=True)
        return {
            **self._serialize_template_summary(template),
            "versions": versions,
        }

    @staticmethod
    def _serialize_version_summary(version: Mapping[str, object]) -> dict[str, object]:
        dsl = _string_object_mapping(version.get("dsl"))
        nodes = dsl.get("nodes") if dsl is not None else None
        node_count = len(nodes) if _is_object_list(nodes) else None
        return {
            "version_id": version.get("version_id"),
            "graph_object_kind": version.get("graph_object_kind") or "template_graph",
            "created_at": version.get("created_at"),
            "node_count": node_count,
        }

    @staticmethod
    def _serialize_version_detail(version: Mapping[str, object]) -> dict[str, object]:
        return {
            "version_id": version.get("version_id"),
            "graph_object_kind": version.get("graph_object_kind") or "template_graph",
            "created_at": version.get("created_at"),
            "dsl": deepcopy(version.get("dsl") or {}),
        }


def _create_template_mutation(
    state: _TemplateState,
    *,
    template_id: str,
    payload: Mapping[str, object],
    now: str,
) -> _TemplateState:
    if template_id in state["templates"]:
        _raise_template_failure("contract_invalid", f"template already exists: {template_id}")
    metadata_value = payload.get("metadata")
    metadata = _string_object_mapping(metadata_value) if metadata_value is not None else {}
    if metadata is None:
        _raise_template_failure("contract_invalid", "metadata must be a mapping")
    state["templates"][template_id] = {
        "template_id": template_id,
        "name": str(payload.get("name") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "metadata": metadata,
        "active_version_id": None,
        "created_at": now,
        "updated_at": now,
        "versions": {},
    }
    return state


def _normalize_state(payload: object) -> _TemplateState:
    state = _string_object_mapping(payload) or {}
    raw_templates = _string_object_mapping(state.get("templates")) or {}
    templates: dict[str, _Template] = {}
    for raw_tid, raw_template_value in raw_templates.items():
        tid = str(raw_tid or "").strip()
        raw_template = _string_object_mapping(raw_template_value)
        if not tid or raw_template is None:
            continue
        raw_versions = _string_object_mapping(raw_template.get("versions")) or {}
        versions: dict[str, dict[str, object]] = {}
        for raw_vid, raw_version_value in raw_versions.items():
            vid = str(raw_vid or "").strip()
            raw_version = _string_object_mapping(raw_version_value)
            if not vid or raw_version is None:
                continue
            versions[vid] = {
                "version_id": vid,
                "dsl": _string_object_mapping(raw_version.get("dsl")) or {},
                "graph_object_kind": str(raw_version.get("graph_object_kind") or "template_graph").strip()
                or "template_graph",
                "created_at": str(raw_version.get("created_at") or _utcnow()),
            }
        templates[tid] = {
            "template_id": tid,
            "name": str(raw_template.get("name") or "").strip(),
            "description": str(raw_template.get("description") or "").strip(),
            "metadata": _string_object_mapping(raw_template.get("metadata")) or {},
            "active_version_id": str(raw_template.get("active_version_id") or "").strip() or None,
            "created_at": str(raw_template.get("created_at") or _utcnow()),
            "updated_at": str(raw_template.get("updated_at") or _utcnow()),
            "versions": versions,
        }

    raw_base_version = state.get("base_version", 0)
    if not _is_int_convertible(raw_base_version):
        raw_base_version = 0
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


def _read_base_version(payload: Mapping[str, object]) -> int | None:
    if "base_version" not in payload:
        return None
    raw = payload.get("base_version")
    if raw is None or raw == "":
        return None
    if not _is_int_convertible(raw):
        _raise_template_failure("contract_invalid", "base_version must be an integer")
    try:
        value = int(raw)
    except Exception as exc:  # noqa: BLE001
        _raise_template_failure("contract_invalid", "base_version must be an integer", cause=exc)
    if value < 0:
        _raise_template_failure("contract_invalid", "base_version must be >= 0")
    return value


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_int_convertible(value: object) -> TypeGuard[str | bytes | bytearray | SupportsInt | SupportsIndex]:
    return isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex))
