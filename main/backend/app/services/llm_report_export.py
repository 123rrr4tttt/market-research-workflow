from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated, Any, Literal, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import llm_report_request_failures

from .llm_report_export_token_state import (
    clear_llm_report_export_token_state_memory,
    is_llm_report_export_token_revoked,
    is_llm_report_export_token_used,
    mark_llm_report_export_token_used_persistent,
    revoke_llm_report_export_token_persistent,
)


ExportFormat = Literal["pdf", "docx"]
ResetTelemetryBoundaryContext = dict[str, Any] | None


@dataclass(frozen=True)
class LlmReportExportArtifact:
    content: bytes
    media_type: str
    extension: str


class LlmReportExportTokenError(ValueError):
    """Raised when a caller supplied report export token cannot be trusted."""


_FAILURE_WITNESS = "test:test_w01_report_export_token_failure_is_typed_before_abi_lift"


def _report_export_failure(code: str, message: str, *, site: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": llm_report_request_failures.name,
        "operation": "llm.report.export",
        "owner": "llm.report_export",
        "public_exception": "LlmReportExportTokenError",
        "public_message": message,
        "site": site,
        "witness": _FAILURE_WITNESS,
    }
    context.update(details)
    return llm_report_request_failures.fail(code, message, context)


def _raise_report_export_failure(
    failure: Failure,
    *,
    exception_type: type[Exception] = LlmReportExportTokenError,
    cause: BaseException | None = None,
) -> NoReturn:
    context = failure.context or {}
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not llm_report_request_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != llm_report_request_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != exception_type.__name__
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=llm.report_export.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_report_export_token_failure_is_typed_before_abi_lift
        raise TypeError("LLM report export failure lift context is incomplete or inconsistent")
    if cause is None:
        # kit:boundary owner=llm.report_export.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=llm.report.request.failure witness=test:test_w01_report_export_token_failure_is_typed_before_abi_lift
        raise exception_type(str(context["public_message"]))
    # kit:boundary owner=llm.report_export.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=llm.report.request.failure witness=test:test_w01_report_export_token_failure_is_typed_before_abi_lift
    raise exception_type(str(context["public_message"])) from cause


_USED_EXPORT_ARTIFACT_IDS: set[str] = set()
_REVOKED_EXPORT_ARTIFACT_IDS: set[str] = set()


def reset_llm_report_export_token_state() -> None:
    _USED_EXPORT_ARTIFACT_IDS.clear()
    _REVOKED_EXPORT_ARTIFACT_IDS.clear()
    clear_llm_report_export_token_state_memory()


def revoke_llm_report_export_token(artifact_id: str) -> None:
    normalized_artifact_id = str(artifact_id or "").strip()
    if normalized_artifact_id:
        _REVOKED_EXPORT_ARTIFACT_IDS.add(normalized_artifact_id)
        revoke_llm_report_export_token_persistent(normalized_artifact_id, reason="local_revoke")


def mark_llm_report_export_token_used(payload: dict[str, Any]) -> None:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if artifact_id:
        _USED_EXPORT_ARTIFACT_IDS.add(artifact_id)
        mark_llm_report_export_token_used_persistent(payload)


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def markdown_sha256(markdown: str) -> str:
    return hashlib.sha256(str(markdown or "").encode("utf-8")).hexdigest()


def _token_secret(raw_secret: str | None) -> bytes:
    secret = str(raw_secret or "").strip() or "mrw-local-llm-report-export-token-v1"
    return secret.encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_actor_id(value: str | None) -> str:
    return str(value or "").strip() or "anonymous"


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def sign_llm_report_export_token(payload: dict[str, Any], *, token_secret: str | None) -> str:
    payload_part = _base64url_encode(_canonical_json_bytes(payload))
    signature = hmac.new(_token_secret(token_secret), payload_part.encode("ascii"), hashlib.sha256).digest()
    return f"llmrpt-v1.{payload_part}.{_base64url_encode(signature)}"


def build_llm_report_export_artifact(
    *,
    markdown: str,
    gate: dict[str, Any],
    gate_mode: str,
    trace_id: str | None,
    request_id: str | None,
    project_key: str | None,
    job_id: int | None,
    topic: str | None,
    token_secret: str | None,
    actor_id: str | None = None,
    ttl_seconds: int | None = None,
    issued_at: datetime | None = None,
    one_time_use: bool = True,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence fact_source=llm.report_export witness=test:test_w01_meta",
]:
    digest = markdown_sha256(markdown)
    hard_failures = gate.get("hard_failures") if isinstance(gate.get("hard_failures"), list) else []
    soft_failures = gate.get("soft_failures") if isinstance(gate.get("soft_failures"), list) else []
    missing_items = gate.get("missing_items") if isinstance(gate.get("missing_items"), list) else []
    artifact_seed = {
        "trace_id": trace_id,
        "request_id": request_id,
        "project_key": project_key,
        "job_id": job_id,
        "topic": topic,
        "markdown_sha256": digest,
    }
    artifact_id = hashlib.sha256(_canonical_json_bytes(artifact_seed)).hexdigest()[:32]
    normalized_ttl_seconds = int(ttl_seconds) if ttl_seconds is not None else 3600
    issued_at_dt = issued_at.astimezone(timezone.utc) if isinstance(issued_at, datetime) else _utc_now()
    expires_at_dt = issued_at_dt + timedelta(seconds=normalized_ttl_seconds)
    issued_at_text = _isoformat_utc(issued_at_dt)
    expires_at_text = _isoformat_utc(expires_at_dt)
    normalized_actor_id = _normalize_actor_id(actor_id)
    token_payload = {
        "contract_version": "llm_report.export_artifact_token.v1",
        "artifact_id": artifact_id,
        "markdown_sha256": digest,
        "gate": {
            "decision": str(gate.get("decision") or "fail").strip().lower() or "fail",
            "gate_version": gate.get("gate_version"),
            "hard_failures": hard_failures,
            "soft_failures": soft_failures,
            "missing_items": missing_items,
        },
        "gate_mode": str(gate_mode or "strict").strip().lower() or "strict",
        "trace_id": trace_id,
        "request_id": request_id,
        "project_key": project_key,
        "job_id": job_id,
        "actor_id": normalized_actor_id,
        "issued_at": issued_at_text,
        "expires_at": expires_at_text,
        "ttl_seconds": normalized_ttl_seconds,
        "one_time_use": bool(one_time_use),
    }
    return {
        "contract_version": "llm_report.export_artifact.v1",
        "artifact_id": artifact_id,
        "artifact_token": sign_llm_report_export_token(token_payload, token_secret=token_secret),
        "artifact_sha256": digest,
        "markdown_sha256": digest,
        "markdown_size_bytes": len(str(markdown or "").encode("utf-8")),
        "gate_decision": token_payload["gate"]["decision"],
        "gate_mode": token_payload["gate_mode"],
        "trace_id": trace_id,
        "request_id": request_id,
        "project_key": project_key,
        "job_id": job_id,
        "actor_id": normalized_actor_id,
        "issued_at": issued_at_text,
        "expires_at": expires_at_text,
        "ttl_seconds": normalized_ttl_seconds,
        "one_time_use": bool(one_time_use),
    }


def verify_llm_report_export_token(
    token: str,
    *,
    markdown: str,
    token_secret: str | None,
    actor_id: str | None = None,
    now: datetime | None = None,
    enforce_one_time_use: bool = True,
) -> dict[str, Any]:
    parts = str(token or "").strip().split(".")
    if len(parts) != 3 or parts[0] != "llmrpt-v1":
        _raise_report_export_failure(
            _report_export_failure(
                "invalid_export_token_format",
                "invalid_export_token_format",
                site="verify_llm_report_export_token.format",
            )
        )
    payload_part = parts[1]
    expected_signature = hmac.new(_token_secret(token_secret), payload_part.encode("ascii"), hashlib.sha256).digest()
    try:
        supplied_signature = _base64url_decode(parts[2])
    except Exception as exc:  # noqa: BLE001
        _raise_report_export_failure(
            _report_export_failure(
                "invalid_export_token_signature",
                "invalid_export_token_signature",
                site="verify_llm_report_export_token.signature_decode",
            ),
            cause=exc,
        )
    if not hmac.compare_digest(expected_signature, supplied_signature):
        _raise_report_export_failure(
            _report_export_failure(
                "invalid_export_token_signature",
                "invalid_export_token_signature",
                site="verify_llm_report_export_token.signature",
            )
        )
    try:
        payload = json.loads(_base64url_decode(payload_part).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        _raise_report_export_failure(
            _report_export_failure(
                "invalid_export_token_payload",
                "invalid_export_token_payload",
                site="verify_llm_report_export_token.payload_decode",
            ),
            cause=exc,
        )
    if not isinstance(payload, dict):
        _raise_report_export_failure(
            _report_export_failure(
                "invalid_export_token_payload",
                "invalid_export_token_payload",
                site="verify_llm_report_export_token.payload_shape",
            )
        )
    if payload.get("contract_version") != "llm_report.export_artifact_token.v1":
        _raise_report_export_failure(
            _report_export_failure(
                "unsupported_export_token_contract",
                "unsupported_export_token_contract",
                site="verify_llm_report_export_token.contract_version",
            )
        )
    expected_hash = str(payload.get("markdown_sha256") or "").strip()
    if not expected_hash or expected_hash != markdown_sha256(markdown):
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_markdown_hash_mismatch",
                "export_token_markdown_hash_mismatch",
                site="verify_llm_report_export_token.markdown_hash",
            )
        )
    if not isinstance(payload.get("gate"), dict):
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_missing_gate",
                "export_token_missing_gate",
                site="verify_llm_report_export_token.gate",
            )
        )
    expires_at = _parse_datetime(payload.get("expires_at"))
    if expires_at is None:
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_missing_expiry",
                "export_token_missing_expiry",
                site="verify_llm_report_export_token.expires_at",
            )
        )
    if (now.astimezone(timezone.utc) if isinstance(now, datetime) else _utc_now()) > expires_at:
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_expired",
                "export_token_expired",
                site="verify_llm_report_export_token.expired",
            )
        )
    expected_actor_id = _normalize_actor_id(str(payload.get("actor_id") or ""))
    supplied_actor_id = _normalize_actor_id(actor_id)
    if expected_actor_id != supplied_actor_id:
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_actor_mismatch",
                "export_token_actor_mismatch",
                site="verify_llm_report_export_token.actor_id",
            )
        )
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if artifact_id in _REVOKED_EXPORT_ARTIFACT_IDS or is_llm_report_export_token_revoked(artifact_id):
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_revoked",
                "export_token_revoked",
                site="verify_llm_report_export_token.revoked",
            )
        )
    if (
        enforce_one_time_use
        and bool(payload.get("one_time_use", True))
        and (artifact_id in _USED_EXPORT_ARTIFACT_IDS or is_llm_report_export_token_used(artifact_id))
    ):
        _raise_report_export_failure(
            _report_export_failure(
                "export_token_already_used",
                "export_token_already_used",
                site="verify_llm_report_export_token.one_time_use",
            )
        )
    return payload


def export_gate_from_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    return {
        "decision": str(gate.get("decision") or "fail").strip().lower() or "fail",
        "gate_version": gate.get("gate_version"),
        "hard_failures": gate.get("hard_failures") if isinstance(gate.get("hard_failures"), list) else [],
        "soft_failures": gate.get("soft_failures") if isinstance(gate.get("soft_failures"), list) else [],
        "missing_items": gate.get("missing_items") if isinstance(gate.get("missing_items"), list) else [],
    }


def _markdown_lines(markdown: str) -> list[str]:
    return [line.rstrip() for line in str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]


@dataclass(frozen=True)
class MarkdownBlock:
    kind: str
    text: str = ""
    level: int = 0
    items: tuple[str, ...] = ()
    ordered: bool = False
    rows: tuple[tuple[str, ...], ...] = ()


_TEMPLATE_RENDERER_ID = "mrw-llm-report-template-renderer-v2"
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_NUMBER_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$")
_EXPORT_TOKEN_RE = re.compile(r"\bllmrpt-v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _redact_export_sensitive_text(text: str) -> str:
    redacted = _EXPORT_TOKEN_RE.sub("[redacted-export-token]", str(text or ""))
    return re.sub(
        r"\b(export_token|token_secret)\b\s*[:=]\s*[^,\s;]+",
        r"\1: [redacted]",
        redacted,
        flags=re.IGNORECASE,
    )


def _pdf_comment_text(text: str) -> str:
    safe = _redact_export_sensitive_text(text)
    safe = re.sub(r"[\r\n%]+", " ", safe)
    return safe.encode("ascii", errors="ignore").decode("ascii")[:180]


def _sanitize_markdown_lines(markdown: str) -> list[str]:
    sanitized: list[str] = []
    for line in _markdown_lines(markdown):
        if "artifact_token" in line.lower():
            continue
        sanitized.append(_redact_export_sensitive_text(line))
    return sanitized


def _reset_telemetry_boundary_note_markdown(context: ResetTelemetryBoundaryContext) -> str:
    if not isinstance(context, dict) or not context:
        return ""
    scope = str(context.get("scope") or "").strip()
    scheduled_evidence_write = str(context.get("scheduled_evidence_write") or "").strip()
    scheduled_completion_proof = str(context.get("scheduled_completion_proof") or "").strip()
    if scope != "ui_read_only_evidence_context":
        return ""
    if scheduled_evidence_write != "none":
        scheduled_evidence_write = "none"
    if scheduled_completion_proof != "unchanged":
        scheduled_completion_proof = "unchanged"
    lines = [
        "## Reset telemetry boundary context",
        "",
        "- ui_read_only_evidence_context",
        "- not report proof",
        "- not scheduled_run_evidence proof",
        f"- scheduled_evidence_write={scheduled_evidence_write}",
        f"- scheduled_completion_proof {scheduled_completion_proof}",
    ]
    return "\n".join(lines)


def _markdown_with_reset_telemetry_boundary_note(markdown: str, context: ResetTelemetryBoundaryContext) -> str:
    note = _reset_telemetry_boundary_note_markdown(context)
    if not note:
        return str(markdown or "")
    return f"{str(markdown or '').rstrip()}\n\n{note}"


def _clean_inline_markdown(text: str) -> str:
    cleaned = _redact_export_sensitive_text(text)
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\\)([*`~]+)", "", cleaned)
    cleaned = cleaned.replace("\\_", "_")
    cleaned = cleaned.replace("\\|", "|")
    return cleaned.strip()


def _is_table_separator(line: str) -> bool:
    stripped = line.strip().strip("|").strip()
    if not stripped or "|" not in line:
        return False
    cells = [cell.strip() for cell in stripped.split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _split_markdown_table_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return tuple(_clean_inline_markdown(cell) for cell in stripped.split("|"))


def _looks_like_table(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    current = lines[index].strip()
    return "|" in current and current.startswith("|") and _is_table_separator(lines[index + 1])


def _parse_markdown_blocks(markdown: str) -> list[MarkdownBlock]:
    lines = _sanitize_markdown_lines(markdown)
    blocks: list[MarkdownBlock] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped:
            index += 1
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            blocks.append(
                MarkdownBlock(
                    kind="heading",
                    level=len(heading_match.group(1)),
                    text=_clean_inline_markdown(heading_match.group(2)),
                )
            )
            index += 1
            continue

        if _looks_like_table(lines, index):
            rows = [_split_markdown_table_row(lines[index])]
            index += 2
            while index < len(lines):
                candidate = lines[index].strip()
                if not candidate or not candidate.startswith("|") or "|" not in candidate.strip("|"):
                    break
                rows.append(_split_markdown_table_row(lines[index]))
                index += 1
            blocks.append(MarkdownBlock(kind="table", rows=tuple(rows)))
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(_clean_inline_markdown(re.sub(r"^\s*>\s?", "", lines[index].strip())))
                index += 1
            blocks.append(MarkdownBlock(kind="quote", text=" ".join(part for part in quote_lines if part)))
            continue

        bullet_match = _BULLET_RE.match(raw_line)
        number_match = _NUMBER_RE.match(raw_line)
        if bullet_match or number_match:
            ordered = bool(number_match)
            items: list[str] = []
            while index < len(lines):
                current = lines[index]
                current_match = _NUMBER_RE.match(current) if ordered else _BULLET_RE.match(current)
                if not current_match:
                    break
                items.append(_clean_inline_markdown(current_match.group(2 if ordered else 1)))
                index += 1
            blocks.append(MarkdownBlock(kind="list", items=tuple(items), ordered=ordered))
            continue

        paragraph_parts: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            candidate_stripped = candidate.strip()
            if not candidate_stripped:
                break
            if (
                _HEADING_RE.match(candidate_stripped)
                or _looks_like_table(lines, index)
                or candidate_stripped.startswith(">")
                or _BULLET_RE.match(candidate)
                or _NUMBER_RE.match(candidate)
            ):
                break
            paragraph_parts.append(_clean_inline_markdown(candidate_stripped))
            index += 1
        if paragraph_parts:
            blocks.append(MarkdownBlock(kind="paragraph", text=" ".join(paragraph_parts)))
        else:
            index += 1
    return blocks


def _plain_text_from_markdown(markdown: str) -> list[str]:
    lines: list[str] = []
    for block in _parse_markdown_blocks(markdown):
        if block.kind == "heading":
            lines.append(block.text)
        elif block.kind in {"paragraph", "quote"}:
            lines.append(block.text)
        elif block.kind == "list":
            for item_index, item in enumerate(block.items, start=1):
                marker = f"{item_index}." if block.ordered else "-"
                lines.append(f"{marker} {item}")
        elif block.kind == "table":
            for row in block.rows:
                lines.append(" | ".join(row))
    return lines


def _wrap_pdf_text(text: str, *, max_chars: int = 92) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _pdf_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_text(text: str) -> str:
    encoded = ("\ufeff" + str(text or "")).encode("utf-16-be")
    return f"<{encoded.hex().upper()}>"


def _pdf_text_op(text: str, *, font: str, size: int, x: float, y: float) -> str:
    return f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td {_pdf_text(text)} Tj ET"


def _pdf_line_op(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"{x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S"


def _pdf_rect_fill_op(x: float, y: float, width: float, height: float, gray: float = 0.94) -> str:
    return f"q {gray:.2f} {gray:.2f} {gray:.2f} rg {x:.1f} {y:.1f} {width:.1f} {height:.1f} re f Q"


def render_markdown_to_pdf_bytes(
    markdown: str,
    *,
    reset_telemetry_boundary_context: ResetTelemetryBoundaryContext = None,
) -> bytes:
    blocks = _parse_markdown_blocks(
        _markdown_with_reset_telemetry_boundary_note(markdown, reset_telemetry_boundary_context)
    )
    page_width = 612.0
    margin_left = 54.0
    margin_right = 54.0
    bottom_margin = 68.0
    y = 0.0
    page_number = 0
    current_ops: list[str] = []
    page_ops: list[list[str]] = []

    def begin_page() -> None:
        nonlocal current_ops, page_number, y
        page_number += 1
        y = 718.0
        current_ops = [
            f"% llm_report.export renderer={_TEMPLATE_RENDERER_ID}",
            "q 0.12 0.16 0.20 rg",
            _pdf_text_op("LLM Report Export", font="F2", size=11, x=margin_left, y=760.0),
            "Q",
            "q 0.45 0.50 0.56 rg",
            _pdf_text_op(_TEMPLATE_RENDERER_ID, font="F1", size=8, x=margin_left, y=744.0),
            "Q",
            "q 0.78 0.81 0.86 RG 0.6 w",
            _pdf_line_op(margin_left, 735.0, page_width - margin_right, 735.0),
            "Q",
        ]

    def finish_page() -> None:
        if not current_ops:
            return
        current_ops.extend(
            [
                "q 0.78 0.81 0.86 RG 0.5 w",
                _pdf_line_op(margin_left, 45.0, page_width - margin_right, 45.0),
                "Q",
                "q 0.45 0.50 0.56 rg",
                _pdf_text_op(f"MRW export template v2 | page {page_number}", font="F1", size=8, x=margin_left, y=32.0),
                "Q",
            ]
        )
        page_ops.append(list(current_ops))

    def ensure_space(height: float) -> None:
        nonlocal current_ops
        if not current_ops:
            begin_page()
        if y - height < bottom_margin:
            finish_page()
            begin_page()

    def write_wrapped(
        text: str,
        *,
        font: str,
        size: int,
        x: float,
        max_chars: int,
        leading: float,
        space_before: float = 0.0,
        space_after: float = 0.0,
        color: str = "0.12 0.16 0.20",
        prefix: str = "",
    ) -> None:
        nonlocal y
        wrapped = _wrap_pdf_text(text, max_chars=max_chars)
        ensure_space(space_before + max(1, len(wrapped)) * leading + space_after)
        y -= space_before
        for line_index, line in enumerate(wrapped):
            ensure_space(leading)
            rendered = f"{prefix}{line}" if line_index == 0 else f"{' ' * len(prefix)}{line}"
            current_ops.extend(
                [
                    f"q {color} rg",
                    _pdf_text_op(rendered, font=font, size=size, x=x, y=y),
                    "Q",
                ]
            )
            y -= leading
        y -= space_after

    def write_table(rows: tuple[tuple[str, ...], ...]) -> None:
        nonlocal y
        if not rows:
            return
        column_count = max(len(row) for row in rows)
        table_width = page_width - margin_left - margin_right
        cell_chars = max(10, min(28, int(86 / max(1, column_count))))
        for row_index, raw_row in enumerate(rows):
            row = tuple(raw_row) + tuple("" for _ in range(column_count - len(raw_row)))
            cell_lines = [_wrap_pdf_text(cell, max_chars=cell_chars) for cell in row]
            row_line_count = max(len(lines) for lines in cell_lines)
            row_height = row_line_count * 11.0 + 8.0
            ensure_space(row_height + 3.0)
            if row_index == 0:
                current_ops.append(_pdf_rect_fill_op(margin_left, y - row_height + 8.0, table_width, row_height, gray=0.92))
            current_ops.extend(["q 0.70 0.74 0.79 RG 0.4 w", _pdf_line_op(margin_left, y + 3.0, page_width - margin_right, y + 3.0), "Q"])
            for line_number in range(row_line_count):
                cells = []
                for lines in cell_lines:
                    cell = lines[line_number] if line_number < len(lines) else ""
                    cells.append(cell[:cell_chars].ljust(cell_chars))
                current_ops.extend(
                    [
                        "q 0.12 0.16 0.20 rg",
                        _pdf_text_op(" | ".join(cells).rstrip(), font="F3", size=8, x=margin_left + 6.0, y=y),
                        "Q",
                    ]
                )
                y -= 11.0
            y -= 8.0
        current_ops.extend(["q 0.70 0.74 0.79 RG 0.4 w", _pdf_line_op(margin_left, y + 5.0, page_width - margin_right, y + 5.0), "Q"])
        y -= 10.0

    begin_page()
    for block in blocks or (MarkdownBlock(kind="paragraph", text=""),):
        if block.kind == "heading":
            current_ops.append(f"% llm_report.export heading level={block.level} text={_pdf_comment_text(block.text)}")
            if block.level == 1:
                write_wrapped(block.text, font="F2", size=19, x=margin_left, max_chars=48, leading=23, space_after=8)
            elif block.level == 2:
                write_wrapped(block.text, font="F2", size=15, x=margin_left, max_chars=62, leading=19, space_before=6, space_after=5)
            else:
                write_wrapped(block.text, font="F2", size=12, x=margin_left, max_chars=76, leading=16, space_before=4, space_after=4)
        elif block.kind == "quote":
            current_ops.append(f"% llm_report.export quote text={_pdf_comment_text(block.text)}")
            current_ops.append(_pdf_rect_fill_op(margin_left, y - 8.0, 3.0, 16.0, gray=0.75))
            write_wrapped(
                block.text,
                font="F1",
                size=10,
                x=margin_left + 16.0,
                max_chars=82,
                leading=14,
                space_before=4,
                space_after=8,
                color="0.30 0.34 0.39",
            )
        elif block.kind == "list":
            for item_index, item in enumerate(block.items, start=1):
                marker = f"{item_index}." if block.ordered else "-"
                current_ops.append(f"% llm_report.export list_item text={_pdf_comment_text(item)}")
                write_wrapped(
                    item,
                    font="F1",
                    size=10,
                    x=margin_left + 18.0,
                    max_chars=84,
                    leading=14,
                    prefix=f"{marker} ",
                )
            y -= 5.0
        elif block.kind == "table":
            table_preview = " | ".join(block.rows[0]) if block.rows else ""
            current_ops.append(f"% llm_report.export table text={_pdf_comment_text(table_preview)}")
            write_table(block.rows)
        else:
            current_ops.append(f"% llm_report.export paragraph text={_pdf_comment_text(block.text)}")
            write_wrapped(block.text, font="F1", size=10, x=margin_left, max_chars=92, leading=14, space_after=6)
    finish_page()

    streams = ["\n".join(["q", *ops, "Q"]).encode("utf-8") for ops in page_ops]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    ]
    page_object_ids: list[int] = []
    for stream in streams:
        page_object_id = len(objects) + 1
        content_object_id = page_object_id + 1
        page_object_ids.append(page_object_id)
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("ascii")
    info_object_id = len(objects) + 1
    created = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%S+00'00'")
    objects.append(
        (
            "<< "
            "/Title (LLM Report Export) "
            f"/Producer ({_TEMPLATE_RENDERER_ID}) "
            "/Creator (market-research-workflow) "
            "/Subject (Template-rendered LLM report export) "
            "/Keywords (llm_report.export structured template fidelity) "
            f"/CreationDate ({created}) "
            ">>"
        ).encode("ascii")
    )
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_offset = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info_object_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return out.getvalue()


def _docx_text_run(text: str) -> str:
    return f"<w:r><w:t xml:space=\"preserve\">{escape(str(text or ''))}</w:t></w:r>"


def _docx_paragraph(text: str, *, style: str | None = None, numbering_id: int | None = None, level: int = 0) -> str:
    ppr_parts: list[str] = []
    if style:
        ppr_parts.append(f'<w:pStyle w:val="{style}"/>')
    if numbering_id is not None:
        ppr_parts.append(
            f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{numbering_id}"/></w:numPr>'
        )
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>" if ppr_parts else ""
    return f"<w:p>{ppr}{_docx_text_run(text)}</w:p>"


def _docx_table(rows: tuple[tuple[str, ...], ...]) -> str:
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    table_rows: list[str] = []
    for row_index, raw_row in enumerate(rows):
        row = tuple(raw_row) + tuple("" for _ in range(column_count - len(raw_row)))
        cells = []
        for cell in row:
            cells.append(
                "<w:tc>"
                "<w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr>"
                f"{_docx_paragraph(cell, style='TableHeader' if row_index == 0 else 'TableBody')}"
                "</w:tc>"
            )
        table_rows.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return (
        "<w:tbl>"
        "<w:tblPr><w:tblStyle w:val=\"TableGrid\"/><w:tblW w:w=\"0\" w:type=\"auto\"/>"
        "<w:tblLook w:firstRow=\"1\" w:lastRow=\"0\" w:firstColumn=\"0\" w:lastColumn=\"0\" "
        "w:noHBand=\"0\" w:noVBand=\"1\"/></w:tblPr>"
        f"{''.join(table_rows)}"
        "</w:tbl>"
    )


def _docx_body_from_blocks(blocks: list[MarkdownBlock]) -> str:
    parts = [_docx_paragraph("LLM Report Export", style="Title"), _docx_paragraph(_TEMPLATE_RENDERER_ID, style="Subtitle")]
    for block in blocks:
        if block.kind == "heading":
            style = "Heading1" if block.level == 1 else "Heading2" if block.level == 2 else "Heading3"
            parts.append(_docx_paragraph(block.text, style=style))
        elif block.kind == "quote":
            parts.append(_docx_paragraph(block.text, style="Quote"))
        elif block.kind == "list":
            numbering_id = 2 if block.ordered else 1
            for item in block.items:
                parts.append(_docx_paragraph(item, style="ListParagraph", numbering_id=numbering_id))
        elif block.kind == "table":
            parts.append(_docx_table(block.rows))
        else:
            parts.append(_docx_paragraph(block.text, style="BodyText"))
    return "\n".join(parts)


def _docx_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr><w:pPr><w:spacing w:after="120"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:rPr><w:color w:val="667085"/><w:sz w:val="18"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:rPr><w:b/><w:sz w:val="34"/></w:rPr><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360" w:right="360"/><w:spacing w:before="120" w:after="120"/></w:pPr><w:rPr><w:i/><w:color w:val="475467"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TableHeader"><w:name w:val="Table Header"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TableBody"><w:name w:val="Table Body"/><w:basedOn w:val="Normal"/></w:style>
  <w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/><w:left w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/><w:right w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/></w:tblBorders></w:tblPr></w:style>
</w:styles>
"""


def _docx_numbering_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="-"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>
  <w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>
</w:numbering>
"""


def render_markdown_to_docx_bytes(
    markdown: str,
    *,
    reset_telemetry_boundary_context: ResetTelemetryBoundaryContext = None,
) -> bytes:
    blocks = _parse_markdown_blocks(
        _markdown_with_reset_telemetry_boundary_note(markdown, reset_telemetry_boundary_context)
    )
    body_xml = _docx_body_from_blocks(blocks)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body_xml}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""
    created = datetime.now(timezone.utc).isoformat()
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>LLM Report Export</dc:title>
  <dc:creator>market-research-workflow</dc:creator>
  <dc:description>{_TEMPLATE_RENDERER_ID}</dc:description>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
</cp:coreProperties>
"""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>
""",
        )
        docx.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>
""",
        )
        docx.writestr("docProps/core.xml", core_xml)
        docx.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rIdNumbering" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>
""",
        )
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", _docx_styles_xml())
        docx.writestr("word/numbering.xml", _docx_numbering_xml())
    return out.getvalue()


def render_markdown_export(
    markdown: str,
    export_format: ExportFormat,
    *,
    reset_telemetry_boundary_context: ResetTelemetryBoundaryContext = None,
) -> LlmReportExportArtifact:
    if export_format == "pdf":
        return LlmReportExportArtifact(
            content=render_markdown_to_pdf_bytes(
                markdown,
                reset_telemetry_boundary_context=reset_telemetry_boundary_context,
            ),
            media_type="application/pdf",
            extension="pdf",
        )
    if export_format == "docx":
        return LlmReportExportArtifact(
            content=render_markdown_to_docx_bytes(
                markdown,
                reset_telemetry_boundary_context=reset_telemetry_boundary_context,
            ),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            extension="docx",
        )
    _raise_report_export_failure(
        _report_export_failure(
            "unsupported_export_format",
            f"unsupported export format: {export_format}",
            site="render_markdown_export.export_format",
            public_exception="ValueError",
        ),
        exception_type=ValueError,
    )
