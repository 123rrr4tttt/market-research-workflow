#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.base import SessionLocal


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    q = min(1.0, max(0.0, q))
    if len(values) == 1:
        return float(values[0])
    rank = q * (len(values) - 1)
    low = int(rank)
    high = min(len(values) - 1, low + 1)
    frac = rank - low
    return float(values[low] * (1.0 - frac) + values[high] * frac)


def _table_exists(name: str) -> bool:
    with SessionLocal() as session:
        row = session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:name LIMIT 1"
            ),
            {"name": name},
        ).first()
        return row is not None


def _load_logs(days: int, policy_version: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists("prompt_time_policy_decision_logs"):
        return []
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    where = ["created_at >= :since"]
    params: dict[str, Any] = {"since": since}
    if policy_version and str(policy_version).strip():
        where.append("policy_version = :policy_version")
        params["policy_version"] = str(policy_version).strip()
    sql = (
        "SELECT request_id, policy_version, p_base, p_new, kl_to_base, offpeak_confidence, features_json, created_at "
        "FROM public.prompt_time_policy_decision_logs WHERE "
        + " AND ".join(where)
    )
    with SessionLocal() as session:
        rows = session.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def summarize_health(rows: list[dict[str, Any]], horizon_hours: int = 48) -> dict[str, Any]:
    if not rows:
        return {
            "samples": 0,
            "p95_kl_to_base": 0.0,
            "p95_abs_shift": 0.0,
            "benefit_lift_48h": 0.0,
            "degradation_hours": 0,
            "current_policy_version": None,
            "previous_policy_version": None,
        }

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, horizon_hours))
    early_cutoff = cutoff - timedelta(hours=max(1, horizon_hours))

    kls = [_to_float(r.get("kl_to_base"), 0.0) for r in rows]
    abs_shifts = [abs(_to_float(r.get("p_new"), 0.0) - _to_float(r.get("p_base"), 0.0)) for r in rows]

    recent_scores: list[float] = []
    prev_scores: list[float] = []
    versions: dict[str, int] = {}
    for row in rows:
        version = str(row.get("policy_version") or "")
        if version:
            versions[version] = versions.get(version, 0) + 1
        created_at = row.get("created_at")
        ts = None
        if isinstance(created_at, datetime):
            ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        elif isinstance(created_at, str) and created_at.strip():
            raw = created_at.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(raw)
                ts = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                ts = None
        features = row.get("features_json") or {}
        proxy = _to_float(row.get("offpeak_confidence"), 0.0) + 0.2 * (
            1.0 - _to_float(features.get("dup_ratio"), 0.0)
        )
        if ts is not None and ts >= cutoff:
            recent_scores.append(proxy)
        elif ts is not None and ts >= early_cutoff:
            prev_scores.append(proxy)

    recent_mean = sum(recent_scores) / max(1, len(recent_scores))
    prev_mean = sum(prev_scores) / max(1, len(prev_scores))
    benefit_lift = recent_mean - prev_mean

    sorted_versions = sorted(versions.items(), key=lambda x: x[1], reverse=True)
    current_policy = sorted_versions[0][0] if sorted_versions else None
    previous_policy = sorted_versions[1][0] if len(sorted_versions) > 1 else None
    degradation_hours = horizon_hours if benefit_lift < 0 else 0

    return {
        "samples": len(rows),
        "p95_kl_to_base": _percentile(kls, 0.95),
        "p95_abs_shift": _percentile(abs_shifts, 0.95),
        "benefit_lift_48h": benefit_lift,
        "degradation_hours": degradation_hours,
        "current_policy_version": current_policy,
        "previous_policy_version": previous_policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize prompt-time-density policy health from decision logs.")
    parser.add_argument("--input-json", help="Optional policy log rows json")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--policy-version", default="")
    parser.add_argument("--horizon-hours", type=int, default=48)
    parser.add_argument("--output", default=".artifacts/prompt_time_policy_health.json")
    args = parser.parse_args()

    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
    else:
        rows = _load_logs(days=args.days, policy_version=args.policy_version)

    summary = summarize_health(rows, horizon_hours=args.horizon_hours)
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "samples": int(summary.get("samples") or 0)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
