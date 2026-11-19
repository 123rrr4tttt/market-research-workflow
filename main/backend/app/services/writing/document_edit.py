from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import hashlib
import json
from typing import Literal, Protocol, TypeAlias, TypeGuard

from functorial_kit import Failure

from app.contracts.json import JSONObject, JSONValue
from app.services.projects import bind_project
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures

from .document_service import (
    WritingVersionConflictError,
    create_document,
    get_document,
    save_document_with_conflict,
)

WritingEditStatus: TypeAlias = Literal["completed", "failed"]


@dataclass(frozen=True, slots=True)
class EditDocumentCommand:
    """Host-independent input for the original agent writing edit."""

    project_key: str
    call_id: str
    content_md: str
    tool_name: str = "writing.document.insert_paragraph"
    contract_version: str = "writing.document.insert_paragraph.v1"
    operation: str = "append"
    doc_id: int | None = None
    title: str | None = None
    anchor_heading: str | None = None
    anchor_text: str | None = None
    range_start: int | None = None
    range_end: int | None = None
    cursor_offset: int | None = None
    selection_snapshot: JSONObject = field(default_factory=dict[str, JSONValue])
    base_version: int | None = None
    if_match: str | None = None
    allow_latest: bool = False
    create_if_missing: bool = False
    dry_run: bool = False
    idempotency_key: str | None = None
    source_refs: tuple[str, ...] = ()
    provenance: JSONObject = field(default_factory=dict[str, JSONValue])


@dataclass(frozen=True, slots=True)
class EditDocumentObservation:
    """The original tool observation without a tool-platform result type."""

    status: WritingEditStatus
    model_summary: str
    structured_content: JSONObject = field(default_factory=dict[str, JSONValue])
    ui_summary: str | None = None
    error: JSONObject | None = None
    retry_hint: str | None = None


class WritingBodyKernel(Protocol):
    def __call__(
        self,
        body_md: str,
        *,
        content_md: str,
        anchor_heading: str,
        anchor_text: str,
        range_start: int | None,
        range_end: int | None,
        cursor_offset: int | None,
    ) -> str | Failure: ...


@dataclass(frozen=True, slots=True)
class WritingBodyOperationDefinition:
    name: str
    kernel: WritingBodyKernel


def _append_body(
    body_md: str,
    *,
    content_md: str,
    anchor_heading: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
    cursor_offset: int | None,
) -> str | Failure:
    return _join_markdown_blocks(body_md, content_md)


def _prepend_body(
    body_md: str,
    *,
    content_md: str,
    anchor_heading: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
    cursor_offset: int | None,
) -> str | Failure:
    return _join_markdown_blocks(content_md, body_md)


def _insert_after_heading(
    body_md: str,
    *,
    content_md: str,
    anchor_heading: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
    cursor_offset: int | None,
) -> str | Failure:
    if not anchor_heading:
        return _operation_failure(
            "writing_anchor_required",
            "anchor_heading is required for after_heading",
            {"operation": "after_heading", "anchor": "heading"},
        )
    lines = str(body_md or "").splitlines()
    for index, line in enumerate(lines):
        if _heading_matches(line, anchor_heading):
            insert_at = index + 1
            while insert_at < len(lines) and not lines[insert_at].strip():
                insert_at += 1
            updated = lines[:insert_at] + ["", str(content_md or "").strip(), ""] + lines[insert_at:]
            return "\n".join(updated).strip() + "\n"
    return _operation_failure(
        "writing_anchor_not_found",
        f"anchor heading not found: {anchor_heading}",
        {"operation": "after_heading", "anchor": "heading", "value": anchor_heading},
    )


def _replace_text(
    body_md: str,
    *,
    content_md: str,
    anchor_text: str,
    anchor_heading: str,
    range_start: int | None,
    range_end: int | None,
    cursor_offset: int | None,
) -> str | Failure:
    if not anchor_text:
        return _operation_failure(
            "writing_anchor_required",
            "anchor_text is required for replace_text",
            {"operation": "replace_text", "anchor": "text"},
        )
    body = str(body_md or "")
    if anchor_text not in body:
        return _operation_failure(
            "writing_anchor_not_found",
            "anchor_text was not found in the document",
            {"operation": "replace_text", "anchor": "text"},
        )
    return body.replace(anchor_text, str(content_md or "").strip(), 1)


def _replace_range(
    body_md: str,
    *,
    content_md: str,
    range_start: int | None,
    range_end: int | None,
    anchor_heading: str,
    anchor_text: str,
    cursor_offset: int | None,
) -> str | Failure:
    if range_start is None or range_end is None:
        return _operation_failure(
            "writing_range_invalid",
            "range_start and range_end are required for replace_range",
            {"operation": "replace_range"},
        )
    range_failure = _validate_body_range(str(body_md or ""), range_start, range_end)
    if range_failure is not None:
        return range_failure
    return _splice_markdown_range(str(body_md or ""), range_start, range_end, str(content_md or "").strip())


def _insert_at_offset(
    body_md: str,
    *,
    content_md: str,
    cursor_offset: int | None,
    anchor_heading: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
) -> str | Failure:
    if cursor_offset is None:
        return _operation_failure(
            "writing_cursor_offset_required",
            "cursor_offset is required for insert_at_offset",
            {"operation": "insert_at_offset"},
        )
    range_failure = _validate_body_range(str(body_md or ""), cursor_offset, cursor_offset)
    if range_failure is not None:
        return range_failure
    return _splice_markdown_range(
        str(body_md or ""), cursor_offset, cursor_offset, str(content_md or "").strip()
    )


def _insert_after_text(
    body_md: str,
    *,
    content_md: str,
    anchor_text: str,
    anchor_heading: str,
    range_start: int | None,
    range_end: int | None,
    cursor_offset: int | None,
) -> str | Failure:
    if not anchor_text:
        return _operation_failure(
            "writing_anchor_required",
            "anchor_text is required for insert_after_text",
            {"operation": "insert_after_text", "anchor": "text"},
        )
    body = str(body_md or "")
    index = body.find(anchor_text)
    if index < 0:
        return _operation_failure(
            "writing_anchor_not_found",
            "anchor_text was not found in the document",
            {"operation": "insert_after_text", "anchor": "text"},
        )
    insert_at = index + len(anchor_text)
    return _join_markdown_blocks(
        body[:insert_at], _join_markdown_blocks(str(content_md or "").strip(), body[insert_at:])
    )


def _insert_before_text(
    body_md: str,
    *,
    content_md: str,
    anchor_text: str,
    anchor_heading: str,
    range_start: int | None,
    range_end: int | None,
    cursor_offset: int | None,
) -> str | Failure:
    if not anchor_text:
        return _operation_failure(
            "writing_anchor_required",
            "anchor_text is required for insert_before_text",
            {"operation": "insert_before_text", "anchor": "text"},
        )
    body = str(body_md or "")
    index = body.find(anchor_text)
    if index < 0:
        return _operation_failure(
            "writing_anchor_not_found",
            "anchor_text was not found in the document",
            {"operation": "insert_before_text", "anchor": "text"},
        )
    return _join_markdown_blocks(
        _join_markdown_blocks(body[:index], str(content_md or "").strip()), body[index:]
    )


WRITING_EDIT_OPERATION_DEFINITIONS: tuple[WritingBodyOperationDefinition, ...] = (
    WritingBodyOperationDefinition("append", _append_body),
    WritingBodyOperationDefinition("prepend", _prepend_body),
    WritingBodyOperationDefinition("after_heading", _insert_after_heading),
    WritingBodyOperationDefinition("replace_text", _replace_text),
    WritingBodyOperationDefinition("replace_range", _replace_range),
    WritingBodyOperationDefinition("insert_at_offset", _insert_at_offset),
    WritingBodyOperationDefinition("insert_after_text", _insert_after_text),
    WritingBodyOperationDefinition("insert_before_text", _insert_before_text),
)
WRITING_EDIT_OPERATION_NAMES: tuple[str, ...] = tuple(
    definition.name for definition in WRITING_EDIT_OPERATION_DEFINITIONS
)
_WRITING_EDIT_KERNELS: dict[str, WritingBodyKernel] = {
    definition.name: definition.kernel for definition in WRITING_EDIT_OPERATION_DEFINITIONS
}


def writing_edit_operation_schema() -> JSONObject:
    """Return the tool operation schema fragment from the native definitions."""

    return {
        "type": "string",
        "enum": list(WRITING_EDIT_OPERATION_NAMES),
        "default": WRITING_EDIT_OPERATION_NAMES[0],
    }


def apply_writing_body_operation(
    body_md: str,
    *,
    operation: str,
    content_md: str,
    anchor_heading: str = "",
    anchor_text: str = "",
    range_start: int | None = None,
    range_end: int | None = None,
    cursor_offset: int | None = None,
) -> str | Failure:
    kernel = _WRITING_EDIT_KERNELS.get(str(operation or "").strip())
    if kernel is None:
        return _operation_failure(
            "writing_operation_unsupported",
            f"unsupported writing operation: {operation}",
            {"operation": operation},
        )
    return kernel(
        body_md,
        content_md=content_md,
        anchor_heading=anchor_heading,
        anchor_text=anchor_text,
        range_start=range_start,
        range_end=range_end,
        cursor_offset=cursor_offset,
    )


def edit_document(command: EditDocumentCommand) -> EditDocumentObservation | Failure:
    """Run read, replay identification, edit, lock, and writer in original order."""

    project_key = _text(command.project_key)
    content_md = _text(command.content_md)
    if not content_md:
        return _failed_observation(
            "content_md is required for writing document insertion.",
            "missing_content",
            "content_md is required",
        )
    if len(content_md) > 20000:
        return _failed_observation(
            "content_md is too large for one insert operation.",
            "content_too_large",
            "content_md must be <= 20000 characters",
        )

    doc_id = _positive_int(command.doc_id)
    operation = _text(command.operation) or "append"
    source_refs = _normalize_string_list(command.source_refs)
    provenance = _json_object(command.provenance)
    if_match = _text(command.if_match) or None
    create_if_missing = bool(command.create_if_missing)
    title = _text(command.title)
    if not doc_id and title:
        create_if_missing = True

    try:
        with bind_project(project_key):
            if doc_id:
                current: JSONObject = _json_object(get_document(doc_id=doc_id, project_key=project_key))
            elif create_if_missing:
                current = {
                    "id": None,
                    "title": title or "Untitled",
                    "body_md": "",
                    "version": 1,
                    "etag": None,
                }
            else:
                return _failed_observation(
                    "doc_id is required unless create_if_missing=true.",
                    "missing_doc_id",
                    "doc_id is required unless create_if_missing=true",
                )

            old_body = str(current.get("body_md") or "")
            agent_update = _find_replayed_agent_writing_update(
                metadata=current.get("metadata_json"),
                command=command,
                current=current,
                content_md=content_md,
                operation=operation,
            )
            common_content: JSONObject = {
                "contract_version": command.contract_version,
                "project_key": project_key,
                "doc_id": doc_id or current.get("id"),
                "operation": operation,
                "source_refs": source_refs,
                "provenance": provenance,
            }
            if agent_update is not None:
                return EditDocumentObservation(
                    status="completed",
                    model_summary=(
                        "Writing document edit already applied for idempotency key "
                        f"{agent_update.get('idempotency_key') or agent_update.get('call_id')}; "
                        "no duplicate paragraph inserted."
                    ),
                    ui_summary=f"Writing update already applied: {current.get('title') or doc_id or title}.",
                    structured_content={
                        **common_content,
                        "document": current,
                        "replayed": True,
                        "diff": _empty_diff(old_body),
                        "agent_update": agent_update,
                    },
                )

            new_body = apply_writing_body_operation(
                old_body,
                operation=operation,
                content_md=content_md,
                anchor_heading=_text(command.anchor_heading),
                anchor_text=_text(command.anchor_text),
                range_start=_nonnegative_int(command.range_start),
                range_end=_nonnegative_int(command.range_end),
                cursor_offset=_nonnegative_int(command.cursor_offset),
            )
            if isinstance(new_body, Failure):
                return new_body
            if len(new_body) > 50000:
                return _failed_observation(
                    "The updated writing document would exceed the 50000 character limit.",
                    "document_too_large",
                    "updated document would exceed 50000 characters",
                )

            diff = _body_diff_summary(old_body, new_body)
            agent_update = _build_agent_writing_update(
                command=command,
                current=current,
                new_body=new_body,
                operation=operation,
                content_md=content_md,
                diff=diff,
            )
            if command.dry_run:
                return EditDocumentObservation(
                    status="completed",
                    model_summary=(
                        f"Prepared writing document edit preview: +{diff['added_lines']} "
                        f"-{diff['removed_lines']} lines."
                    ),
                    structured_content={
                        **common_content,
                        "dry_run": True,
                        "diff": diff,
                        "agent_update": agent_update,
                    },
                )

            if doc_id:
                current_version = _positive_int(current.get("version")) or 1
                current_etag = _text(current.get("etag")) or None
                if not command.base_version and not if_match and not command.allow_latest:
                    return EditDocumentObservation(
                        status="failed",
                        model_summary=(
                            "Writing mutation needs base_version/if_match from writing.document.read, "
                            "or allow_latest=true for an explicit latest-version edit."
                        ),
                        structured_content={
                            "contract_version": command.contract_version,
                            "project_key": project_key,
                            "doc_id": doc_id,
                            "current_version": current_version,
                            "current_etag": current_etag,
                            "retry_arguments": _retry_arguments(
                                command,
                                base_version=current_version,
                                if_match=current_etag,
                            ),
                        },
                        error={
                            "code": "version_lock_required",
                            "message": "base_version or if_match required",
                        },
                        retry_hint="Call writing.document.read first, then retry with base_version and if_match.",
                    )
                saved = save_document_with_conflict(
                    doc_id=doc_id,
                    project_key=project_key,
                    body_md=new_body,
                    title=_text(command.title) or None,
                    base_version=_positive_int(command.base_version)
                    or (current_version if command.allow_latest else None),
                    if_match=if_match or (current_etag if command.allow_latest else None),
                    updated_by_user_id="agent_core",
                    metadata_json=_append_agent_writing_update(current.get("metadata_json"), agent_update),
                )
            else:
                metadata_json = _append_agent_writing_update(
                    {
                        "created_by": "agent_core",
                        "agent_core_call_id": command.call_id,
                        "source_refs": source_refs,
                        "provenance": provenance,
                    },
                    agent_update,
                )
                saved = create_document(
                    project_key=project_key,
                    title=_text(command.title) or _text(current.get("title")) or "Untitled",
                    body_md=new_body,
                    updated_by_user_id="agent_core",
                    metadata_json=metadata_json,
                )
                doc_id = _positive_int(saved.get("id")) or 0
                common_content["doc_id"] = doc_id
    except WritingVersionConflictError as exc:
        return EditDocumentObservation(
            status="failed",
            model_summary=f"Writing document version conflict: current version is {exc.current_version}.",
            structured_content={"conflict": _json_object(exc.server_snapshot)},
            error={
                "code": "writing_version_conflict",
                "message": str(exc),
                "current_version": exc.current_version,
            },
            retry_hint="Read the document again and retry against the current version.",
        )
    except ValueError as exc:
        return _failed_observation(str(exc), "invalid_writing_operation", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _failed_observation(
            f"Failed to update writing document: {exc}", exc.__class__.__name__, str(exc)
        )

    document_title = _text((saved or {}).get("title") or current.get("title") or command.title or "Untitled")
    inserted_excerpt = " ".join(content_md.split())[:180]
    source_ref_count = len(source_refs)
    return EditDocumentObservation(
        status="completed",
        model_summary=(
            f"Updated writing document {doc_id} ({document_title}): operation={operation}, "
            f"+{diff['added_lines']} -{diff['removed_lines']} lines, source_refs={source_ref_count}. "
            f"Inserted excerpt: {inserted_excerpt}"
        ),
        ui_summary=f"Updated writing document {doc_id}: {document_title}.",
        structured_content={
            **common_content,
            "document": _json_object(saved),
            "diff": diff,
            "agent_update": agent_update,
        },
    )


def _operation_failure(code: str, message: str, context: JSONObject) -> Failure:
    return agent_runtime_failures.fail(code, message, context)


def _failed_observation(model_summary: str, code: str, message: str) -> EditDocumentObservation:
    return EditDocumentObservation(
        status="failed",
        model_summary=model_summary,
        error={"code": code, "message": message},
    )


def _text(value: object) -> str:
    return str(value or "").strip()


def _positive_int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)) or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)) or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _is_json_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_json_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, str)


def _json_value(value: object) -> JSONValue:
    if _is_json_mapping(value):
        normalized_object: dict[str, JSONValue] = {
            str(key): _json_value(item) for key, item in value.items()
        }
        return normalized_object
    if _is_json_sequence(value):
        normalized_sequence: list[JSONValue] = [_json_value(item) for item in value]
        return normalized_sequence
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _json_object(value: object) -> JSONObject:
    normalized = _json_value(value)
    return dict(normalized) if isinstance(normalized, dict) else {}


def _json_list(value: object) -> list[JSONValue]:
    normalized = _json_value(value)
    return list(normalized) if isinstance(normalized, list) else []


def _normalize_string_list(values: object) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in _json_list(values):
        item = _text(value)
        if item and item not in out:
            out.append(item)
    return out


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_json_value(
    value: object,
    *,
    max_items: int = 30,
    max_depth: int = 5,
    max_string: int = 500,
) -> JSONValue:
    if max_depth <= 0:
        if _is_json_mapping(value) or _is_json_sequence(value):
            return "[truncated]"
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        return str(value)
    if _is_json_mapping(value):
        compacted: dict[str, JSONValue] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                compacted["_truncated"] = True
                compacted["_omitted_count"] = max(0, len(value) - max_items)
                break
            compacted[_text(key)] = _compact_json_value(
                item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string
            )
        return compacted
    if _is_json_sequence(value):
        items = list(value)
        compacted_items: list[JSONValue] = [
            _compact_json_value(
                item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            compacted_items.append({"_truncated": True, "_omitted_count": len(items) - max_items})
        return compacted_items
    if isinstance(value, str):
        return value[:max_string] + "..." if len(value) > max_string else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _join_markdown_blocks(first: str, second: str) -> str:
    left = str(first or "").strip()
    right = str(second or "").strip()
    if not left:
        return f"{right}\n" if right else ""
    if not right:
        return f"{left}\n"
    return f"{left}\n\n{right}\n"


def _heading_matches(line: str, anchor_heading: str) -> bool:
    left = _text(line).lstrip("#").strip().lower()
    right = _text(anchor_heading).lstrip("#").strip().lower()
    return bool(left and right and left == right)


def _validate_body_range(body_md: str, start: int, end: int) -> Failure | None:
    if start < 0 or end < 0:
        return _operation_failure(
            "writing_range_invalid", "range offsets must be >= 0", {"start": start, "end": end}
        )
    if start > end:
        return _operation_failure(
            "writing_range_invalid",
            "range_start must be <= range_end",
            {"start": start, "end": end},
        )
    body_length = len(str(body_md or ""))
    if end > body_length:
        return _operation_failure(
            "writing_range_invalid",
            "range_end is outside the document",
            {"start": start, "end": end, "body_length": body_length},
        )
    return None


def _splice_markdown_range(body_md: str, start: int, end: int, content_md: str) -> str:
    body = str(body_md or "")
    before = body[:start]
    after = body[end:]
    if not before:
        return _join_markdown_blocks(content_md, after)
    if not after:
        return _join_markdown_blocks(before, content_md)
    return _join_markdown_blocks(_join_markdown_blocks(before, content_md), after)


def _body_diff_summary(old_body: str, new_body: str) -> JSONObject:
    old_lines = str(old_body or "").splitlines()
    new_lines = str(new_body or "").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines, new_lines, fromfile="before.md", tofile="after.md", lineterm="", n=3
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return {
        "added_lines": added,
        "removed_lines": removed,
        "old_line_count": len(old_lines),
        "new_line_count": len(new_lines),
        "diff_excerpt": "\n".join(diff_lines[:120]),
        "diff_truncated": len(diff_lines) > 120,
    }


def _empty_diff(body: str) -> JSONObject:
    line_count = len(str(body or "").splitlines())
    return {
        "added_lines": 0,
        "removed_lines": 0,
        "old_line_count": line_count,
        "new_line_count": line_count,
        "diff_excerpt": "",
        "diff_truncated": False,
    }


def _first_nonempty_line(value: str, *, max_chars: int = 240) -> str:
    for line in str(value or "").splitlines():
        normalized = line.strip()
        if normalized:
            return normalized[:max_chars]
    return _text(value)[:max_chars]


def _find_anchor_line(body_md: str, content_md: str) -> int | None:
    body = str(body_md or "")
    for candidate in (_text(content_md), _first_nonempty_line(content_md)):
        if not candidate:
            continue
        offset = body.find(candidate)
        if offset >= 0:
            return body[:offset].count("\n") + 1
    return None


def _normalize_selection_snapshot(value: object) -> JSONObject:
    normalized = _json_object(value)
    return {
        key: value[:1400] if isinstance(value := normalized.get(key), str) else value
        for key in (
            "text", "selected_text", "start", "end", "line", "active_heading", "before", "after"
        )
        if key in normalized
    }


def _agent_writing_idempotency_key(
    *,
    command: EditDocumentCommand,
    current: JSONObject,
    content_md: str,
    operation: str,
) -> str:
    explicit = _text(command.idempotency_key) or _text(command.provenance.get("idempotency_key"))
    if explicit:
        return explicit[:240]
    selection_snapshot = _normalize_selection_snapshot(command.selection_snapshot)
    return _stable_hash(
        {
            "session_anchor": command.provenance.get("session_id") or command.provenance.get("message_id"),
            "doc_id": current.get("id") or command.doc_id or _text(command.title),
            "operation": operation,
            "anchor_heading": _text(command.anchor_heading),
            "anchor_text": _text(command.anchor_text),
            "range_start": _nonnegative_int(command.range_start),
            "range_end": _nonnegative_int(command.range_end),
            "cursor_offset": _nonnegative_int(command.cursor_offset),
            "selection": selection_snapshot,
            "content_hash": _stable_hash({"content_md": content_md}),
        }
    )


def _build_agent_writing_update(
    *,
    command: EditDocumentCommand,
    current: JSONObject,
    new_body: str,
    operation: str,
    content_md: str,
    diff: JSONObject,
) -> JSONObject:
    old_version = _positive_int(current.get("version"))
    old_body = str(current.get("body_md") or "")
    selection_snapshot = _normalize_selection_snapshot(command.selection_snapshot)
    selection_text = _text(selection_snapshot.get("selected_text") or selection_snapshot.get("text"))
    explicit_anchor_text = _text(command.anchor_text)
    anchor_text = selection_text or explicit_anchor_text or _first_nonempty_line(content_md)
    content_hash = _stable_hash({"content_md": content_md})
    idempotency_key = _agent_writing_idempotency_key(
        command=command, current=current, content_md=content_md, operation=operation
    )
    anchor_id = f"agent-{_stable_hash({'idempotency_key': idempotency_key, 'content_hash': content_hash})}"
    inserted_text = _text(content_md)
    replaced_text = _extract_replaced_writing_text(
        old_body,
        operation=operation,
        anchor_text=explicit_anchor_text or selection_text,
        range_start=_nonnegative_int(command.range_start),
        range_end=_nonnegative_int(command.range_end),
    )
    provenance = _json_object(command.provenance)
    if selection_snapshot:
        provenance.setdefault("selection_snapshot", selection_snapshot)
    return {
        "id": anchor_id,
        "anchor_id": anchor_id,
        "call_id": command.call_id,
        "idempotency_key": idempotency_key,
        "tool_name": command.tool_name,
        "actor": "agent_core",
        "operation": operation,
        "created_at": _utcnow_iso(),
        "doc_id": current.get("id"),
        "title": current.get("title"),
        "old_version": old_version,
        "new_version": 1 if current.get("id") is None else ((old_version + 1) if old_version else None),
        "content_hash": content_hash,
        "inserted_text": inserted_text[:2000],
        "inserted_text_truncated": len(inserted_text) > 2000,
        "replaced_text": replaced_text[:2000],
        "replaced_text_truncated": len(replaced_text) > 2000,
        "summary": f"{operation} via AgentCore: +{diff.get('added_lines')} -{diff.get('removed_lines')} lines",
        "diff": _compact_json_value(diff, max_items=8, max_depth=3, max_string=1200),
        "source_refs": _normalize_string_list(command.source_refs),
        "provenance": _compact_json_value(provenance, max_items=20, max_depth=4),
        "locator": {
            "anchor_id": anchor_id,
            "anchor_text": anchor_text,
            "anchor_heading": _text(command.anchor_heading) or None,
            "anchor_line": _find_anchor_line(new_body, content_md),
            "range_start": _nonnegative_int(command.range_start),
            "range_end": _nonnegative_int(command.range_end),
            "cursor_offset": _nonnegative_int(command.cursor_offset),
            "selection_snapshot": selection_snapshot or None,
            "content_hash": content_hash,
        },
    }


def _find_replayed_agent_writing_update(
    *,
    metadata: object,
    command: EditDocumentCommand,
    current: JSONObject,
    content_md: str,
    operation: str,
) -> JSONObject | None:
    normalized_metadata = _json_object(metadata)
    idempotency_key = _agent_writing_idempotency_key(
        command=command, current=current, content_md=content_md, operation=operation
    )
    entries = [
        _json_object(entry)
        for entry in _json_list(normalized_metadata.get("agent_updates"))
        if isinstance(entry, Mapping)
    ]
    for item in reversed(entries):
        if _text(item.get("call_id") or "") == command.call_id:
            return item
        if idempotency_key and _text(item.get("idempotency_key") or "") == idempotency_key:
            return item
    return None


def _extract_replaced_writing_text(
    body_md: str,
    *,
    operation: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
) -> str:
    body = str(body_md or "")
    normalized_operation = _text(operation)
    if normalized_operation == "replace_range" and range_start is not None and range_end is not None:
        if 0 <= range_start <= range_end <= len(body):
            return body[range_start:range_end]
        return ""
    if normalized_operation == "replace_text" and anchor_text:
        index = body.find(anchor_text)
        if index >= 0:
            return body[index : index + len(anchor_text)]
    return ""


def _append_agent_writing_update(metadata: object, update: JSONObject, *, max_items: int = 30) -> JSONObject:
    next_metadata = _json_object(metadata)
    existing = [
        _json_object(item)
        for item in _json_list(next_metadata.get("agent_updates"))
        if isinstance(item, Mapping)
    ]
    next_updates = [*existing, _json_object(update)][-max_items:]
    next_metadata["agent_updates"] = next_updates
    next_metadata["last_agent_update"] = dict(update)
    next_metadata["agent_update_count"] = len(next_updates)
    return next_metadata


def _retry_arguments(
    command: EditDocumentCommand,
    *,
    base_version: int,
    if_match: str | None,
) -> JSONObject:
    arguments: JSONObject = {
        "project_key": command.project_key,
        "content_md": command.content_md,
        "operation": command.operation,
        "base_version": base_version,
        "if_match": if_match,
    }
    optional_fields: tuple[tuple[str, object], ...] = (
        ("doc_id", command.doc_id),
        ("title", command.title),
        ("anchor_heading", command.anchor_heading),
        ("anchor_text", command.anchor_text),
        ("range_start", command.range_start),
        ("range_end", command.range_end),
        ("cursor_offset", command.cursor_offset),
        ("selection_snapshot", command.selection_snapshot),
        ("allow_latest", command.allow_latest),
        ("create_if_missing", command.create_if_missing),
        ("dry_run", command.dry_run),
        ("idempotency_key", command.idempotency_key),
        ("source_refs", list(command.source_refs)),
        ("provenance", command.provenance),
    )
    for key, value in optional_fields:
        if value:
            arguments[key] = value
    return arguments


__all__ = [
    "EditDocumentCommand",
    "EditDocumentObservation",
    "WritingBodyOperationDefinition",
    "WRITING_EDIT_OPERATION_DEFINITIONS",
    "WRITING_EDIT_OPERATION_NAMES",
    "apply_writing_body_operation",
    "edit_document",
    "writing_edit_operation_schema",
]
