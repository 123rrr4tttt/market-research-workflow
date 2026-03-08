#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.projects import bind_project


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    detail: str


def _insert_fixture(prefix: str, project_key: str) -> list[int]:
    ids: list[int] = []
    with bind_project(project_key):
        with SessionLocal() as session:
            for row in session.execute(select(Document).where(Document.title.like(f"{prefix}%"))).scalars().all():
                session.delete(row)
            session.commit()
            rows = [
                Document(
                    state="CA",
                    doc_type="news",
                    title=f"{prefix}-A",
                    publish_date=date(2099, 1, 2),
                    created_at=datetime(2099, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
                    uri="https://news.example.com/same",
                    text_hash=f"{prefix}-h-a",
                    extracted_data={"prompt_group_id": "pg-ai", "source_domain": "news.example.com"},
                ),
                Document(
                    state="CA",
                    doc_type="news",
                    title=f"{prefix}-B",
                    publish_date=date(2099, 1, 2),
                    created_at=datetime(2099, 1, 2, 11, 0, 0, tzinfo=timezone.utc),
                    uri="https://news.example.com/same",
                    text_hash=f"{prefix}-h-b",
                    extracted_data={"prompt_group_id": "pg-ai", "source_domain": "news.example.com"},
                ),
                Document(
                    state="CA",
                    doc_type="news",
                    title=f"{prefix}-C",
                    publish_date=date(2099, 1, 3),
                    created_at=datetime(2099, 1, 3, 8, 0, 0, tzinfo=timezone.utc),
                    uri="https://data.example.org/c",
                    text_hash=f"{prefix}-h-c",
                    extracted_data={"prompt_group_id": "pg-ai", "source_domain": "data.example.org"},
                ),
                Document(
                    state="CA",
                    doc_type="news",
                    title=f"{prefix}-D",
                    publish_date=date(2099, 1, 3),
                    created_at=datetime(2099, 1, 3, 9, 0, 0, tzinfo=timezone.utc),
                    uri="https://finance.example.net/d",
                    text_hash=f"{prefix}-h-d",
                    extracted_data={"prompt_group_id": "pg-fin", "source_domain": "finance.example.net"},
                ),
            ]
            session.add_all(rows)
            session.flush()
            ids = [int(x.id) for x in rows]
            session.commit()
    return ids


def _cleanup(ids: list[int], project_key: str) -> None:
    if not ids:
        return
    with bind_project(project_key):
        with SessionLocal() as session:
            for row in session.execute(select(Document).where(Document.id.in_(ids))).scalars().all():
                session.delete(row)
            session.commit()


def _run_cases(project_key: str, *, case_set: str = "all", fail_fast: bool = False) -> list[CaseResult]:
    client = TestClient(app)
    headers = {"X-Project-Key": project_key, "X-Request-Id": "realcase-prompt-time-density"}
    out: list[CaseResult] = []

    def assert_case(case_id: str, cond: bool, detail: str) -> None:
        out.append(CaseResult(case_id=case_id, passed=bool(cond), detail=detail))
        if fail_fast and not cond:
            raise RuntimeError(f"case failed: {case_id} - {detail}")

    density = client.get(
        "/api/v1/stats/prompt-time-density",
        headers=headers,
        params={"start": "2099-01-01", "end": "2099-01-05", "bucket": "day", "prompt_group_ids": "pg-ai"},
    )
    density_data = (density.json().get("data") or {}).get("items") or []
    assert_case("C1", density.status_code == 200, f"density status={density.status_code}")
    assert_case("C2", len(density_data) >= 2, f"density items={len(density_data)}")

    invalid_bucket = client.get(
        "/api/v1/stats/prompt-time-density",
        headers=headers,
        params={"time_window": "7d", "bucket": "hour"},
    )
    assert_case("C3", invalid_bucket.status_code == 422, f"invalid bucket status={invalid_bucket.status_code}")

    invalid_time_window = client.get(
        "/api/v1/stats/prompt-time-density",
        headers=headers,
        params={"time_window": "foo"},
    )
    assert_case("C4", invalid_time_window.status_code == 422, f"invalid window status={invalid_time_window.status_code}")

    priority = client.get(
        "/api/v1/stats/prompt-time-density/priority",
        headers=headers,
        params=[("end", "2099-01-05"), ("candidate_windows", "7d"), ("candidate_windows", "30d"), ("prompt_group_ids", "pg-ai")],
    )
    priority_data = (priority.json().get("data") or {}).get("items") or []
    assert_case("C5", priority.status_code == 200, f"priority status={priority.status_code}")
    assert_case("C6", len(priority_data) >= 1, f"priority items={len(priority_data)}")
    ranks = [int(x.get("rank") or 0) for x in priority_data]
    assert_case("C7", ranks == sorted(ranks), "priority ranks are sorted")

    invalid_priority = client.get(
        "/api/v1/stats/prompt-time-density/priority",
        headers=headers,
        params=[("candidate_windows", "7days")],
    )
    assert_case("C8", invalid_priority.status_code == 422, f"invalid priority status={invalid_priority.status_code}")

    if case_set == "smoke":
        return [x for x in out if x.case_id in {"C1", "C5", "C8"}]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-case checks for prompt-time-density APIs.")
    parser.add_argument("--project", default="demo_proj")
    parser.add_argument("--case-set", default="all", choices=["all", "smoke"])
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--output", default=".artifacts/realcase_prompt_time_density_report.json")
    args = parser.parse_args()

    prefix = f"REALCASE-PTD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    inserted_ids: list[int] = []
    try:
        inserted_ids = _insert_fixture(prefix=prefix, project_key=args.project)
        results = _run_cases(project_key=args.project, case_set=args.case_set, fail_fast=args.fail_fast)
    finally:
        _cleanup(inserted_ids, project_key=args.project)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    payload: dict[str, Any] = {
        "project_key": args.project,
        "case_set": args.case_set,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": [r.__dict__ for r in results],
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
