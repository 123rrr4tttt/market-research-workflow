#!/usr/bin/env python3
"""Repair the extra JSON serialization layer in the Stage 5 values export.

The original exporter serialized ``event_note`` (already canonical JSON text)
twice.  The repair is deliberately scoped to that field and removes exactly
one extra backslash layer; it never performs a global slash replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (_REPO_ROOT / "main" / "backend", _REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.successor_runtime.research.codec import canonical_bytes


EVENT_NOTE_MARKER = '"event_note": "'
EVENT_DIGEST_MARKER = '", "event_digest"'


def _repair_event_note_layer(line: str) -> tuple[str, bool, int]:
    """Remove one exporter-added JSON layer from each event_note value."""

    position = 0
    changed = False
    repaired_fields = 0
    while True:
        try:
            start = line.index(EVENT_NOTE_MARKER, position) + len(EVENT_NOTE_MARKER)
        except ValueError:
            break
        end = line.index(EVENT_DIGEST_MARKER, start)
        raw_value = line[start:end]
        # _event_note() uses json.dumps(metadata), so its canonical text has
        # one quote-escape layer.  The broken export contains two layers.
        repaired_value = raw_value.replace("\\\\", "\\")
        if repaired_value != raw_value:
            line = line[:start] + repaired_value + line[end:]
            changed = True
            repaired_fields += 1
        position = start + len(repaired_value) + len(EVENT_DIGEST_MARKER)
    return line, changed, repaired_fields


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_rows(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    rows: list[dict[str, Any]] = []
    invalid_nested_event_notes: list[int] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(raw_line)
        rows.append(row)
        content = row.get("content_json") or {}
        payload = content.get("payload", content) if isinstance(content, dict) else {}
        for event in payload.get("events", []) if isinstance(payload, dict) else []:
            note = event.get("event_note") if isinstance(event, dict) else None
            if note:
                try:
                    parsed_note = json.loads(note)
                except json.JSONDecodeError:
                    invalid_nested_event_notes.append(line_number)
                    continue
                if not isinstance(parsed_note, dict):
                    invalid_nested_event_notes.append(line_number)
    return rows, invalid_nested_event_notes


def _content_digest_mismatches(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for line_number, row in enumerate(rows, 1):
        content = row.get("content_json")
        if not isinstance(content, dict):
            continue
        actual = hashlib.sha256(canonical_bytes(content)).hexdigest()
        expected = str(row.get("content_digest") or "")
        if actual != expected:
            mismatches.append(
                {
                    "line": str(line_number),
                    "value_id": str(row.get("value_id") or ""),
                    "expected": expected,
                    "actual": actual,
                }
            )
    return mismatches


def repair_file(source: Path, output: Path) -> dict[str, Any]:
    changed_lines: list[int] = []
    repaired_fields = 0
    output_lines: list[str] = []
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        try:
            json.loads(raw_line)
            output_line = raw_line
        except json.JSONDecodeError:
            output_line, changed, field_count = _repair_event_note_layer(raw_line)
            if not changed:
                raise ValueError(f"unrepairable JSONL line {source}:{line_number}")
            changed_lines.append(line_number)
            repaired_fields += field_count
        output_lines.append(output_line)

    output.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    rows, invalid_notes = _validate_rows(output)
    if invalid_notes:
        raise ValueError(f"nested event_note JSON remains invalid in {output}: {invalid_notes}")
    digest_mismatches = _content_digest_mismatches(rows)
    if digest_mismatches:
        raise ValueError(f"content_digest mismatches in {output}: {digest_mismatches}")
    return {
        "source": str(source),
        "output": str(output),
        "row_count": len(rows),
        "changed_lines": changed_lines,
        "repaired_event_note_fields": repaired_fields,
        "content_digest_mismatches": digest_mismatches,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "row_digests": [
            {
                "line": index,
                "value_id": row.get("value_id"),
                "canonical_json_sha256": _canonical_digest(row),
            }
            for index, row in enumerate(rows, 1)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--restore", type=Path, required=True)
    parser.add_argument("--source-output", type=Path, required=True)
    parser.add_argument("--restore-output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--digest-log", type=Path, required=True)
    args = parser.parse_args()

    source_result = repair_file(args.source, args.source_output)
    restore_result = repair_file(args.restore, args.restore_output)
    source_rows, _ = _validate_rows(args.source_output)
    restore_rows, _ = _validate_rows(args.restore_output)
    if source_rows != restore_rows:
        raise ValueError("corrected source/restore rows are not semantically equal")

    digest_lines = [
        f"{source_result['output_sha256']}  {args.source_output}",
        f"{restore_result['output_sha256']}  {args.restore_output}",
    ]
    for source_row, restore_row in zip(source_result["row_digests"], restore_result["row_digests"]):
        digest_lines.append(
            f"line={source_row['line']} value_id={source_row['value_id']} "
            f"source_row_sha256={source_row['canonical_json_sha256']} "
            f"restore_row_sha256={restore_row['canonical_json_sha256']} equal={source_row['canonical_json_sha256'] == restore_row['canonical_json_sha256']}"
        )
    args.digest_log.write_text("\n".join(digest_lines) + "\n", encoding="utf-8")

    result = {
        "schema": "mrw.stage5.recovery.values-jsonl-correction.v1",
        "status": "PASS_LOCAL_VALUES_JSONL_CORRECTION_NOT_AUTHORITY",
        "authoritative": False,
        "codec": {
            "name": "event_note_extra_json_layer",
            "operation": "remove exactly one backslash layer within event_note fields only",
            "global_backslash_replacement": False,
            "canonical_origin": "c9_projection_sources._event_note -> json.dumps(metadata, sort_keys=True, separators=(\",\", \":\"))",
        },
        "historical_bad_evidence": {
            "source": str(args.source),
            "restore": str(args.restore),
            "invalid_lines": [3, 4, 12],
            "preserved": True,
        },
        "source": source_result,
        "restore": restore_result,
        "semantic_equality": {
            "rows_equal": source_rows == restore_rows,
            "source_row_count": len(source_rows),
            "restore_row_count": len(restore_rows),
            "canonical_row_digest_equal": all(
                left["canonical_json_sha256"] == right["canonical_json_sha256"]
                for left, right in zip(source_result["row_digests"], restore_result["row_digests"])
            ),
        },
        "execution_boundary": "derived from retained JSONL bytes; no database restore or Stage 5 rerun",
        "authority_ceiling": ["LOCAL_STAGE5_RECOVERY_ONLY", "NOT_AUTHORITY", "RELEASE_DEFERRED"],
    }
    args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "result": str(args.result), "rows": len(source_rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
