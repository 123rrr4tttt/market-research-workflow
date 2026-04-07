#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.base import SessionLocal


EPS = 1e-9


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _reward_proxy(row: dict[str, Any]) -> float:
    features = row.get("features_json") or {}
    dup_ratio = _to_float(features.get("dup_ratio"), 0.0)
    peak_pressure = _to_float(features.get("peak_pressure"), 0.0)
    overlap = _to_float(row.get("vector_overlap"), 0.0)
    offpeak = _to_float(row.get("offpeak_confidence"), 0.0)
    reward = (0.5 * offpeak) + (0.3 * overlap) + (0.2 * (1.0 - peak_pressure))
    reward *= max(0.0, min(1.0, 1.0 - dup_ratio))
    return max(0.0, min(1.0, reward))


def _bootstrap_ci(values: list[float], n_bootstrap: int = 300, alpha: float = 0.05) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    mean = sum(values) / float(len(values))
    if len(values) == 1:
        return {"mean": mean, "ci_low": mean, "ci_high": mean}
    boots: list[float] = []
    for _ in range(max(50, n_bootstrap)):
        sample = [values[random.randint(0, len(values) - 1)] for _ in range(len(values))]
        boots.append(sum(sample) / float(len(sample)))
    boots.sort()
    lo_idx = int((alpha / 2.0) * (len(boots) - 1))
    hi_idx = int((1.0 - alpha / 2.0) * (len(boots) - 1))
    return {"mean": mean, "ci_low": float(boots[lo_idx]), "ci_high": float(boots[hi_idx])}


def _table_exists(table_name: str, schema: str = "public") -> bool:
    with SessionLocal() as session:
        row = session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :name LIMIT 1"
            ),
            {"schema": schema, "name": table_name},
        ).first()
        return row is not None


def _load_from_db(days: int, policy_version: str | None = None, limit: int = 300000) -> list[dict[str, Any]]:
    if not _table_exists("prompt_time_policy_decision_logs", schema="public"):
        return []
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    where = ["l.created_at >= :since"]
    params: dict[str, Any] = {"since": since, "limit": int(max(100, limit))}
    if policy_version and str(policy_version).strip():
        where.append("l.policy_version = :policy_version")
        params["policy_version"] = str(policy_version).strip()

    has_feedback = _table_exists("prompt_time_window_feedback", schema="public")
    feedback_join = ""
    if has_feedback:
        feedback_join = (
            "LEFT JOIN public.prompt_time_window_feedback f "
            "ON f.request_id = l.request_id "
            "AND f.source_domain = l.source_domain "
            "AND f.noun_group_id = l.noun_group_id "
            "AND f.window = l.window "
        )

    sql = (
        "SELECT l.request_id, l.source_domain, l.noun_group_id, l.window, l.chosen_window, l.is_chosen, "
        "l.p_base, l.p_new, l.vector_overlap, l.offpeak_confidence, l.features_json, "
        "l.policy_version, l.created_at, "
        + ("f.observed_reward " if has_feedback else "NULL::numeric AS observed_reward ")
        + "FROM public.prompt_time_policy_decision_logs l "
        + feedback_join
        + " WHERE "
        + " AND ".join(where)
        + " ORDER BY l.created_at DESC LIMIT :limit"
    )
    with SessionLocal() as session:
        rows = session.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def _load_input_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("rows")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("input json must be list[object] or {'rows': [...]}")
    return [dict(x) for x in rows if isinstance(x, dict)]


def _group_contexts(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("request_id") or ""),
            str(row.get("source_domain") or "unknown"),
            str(row.get("noun_group_id") or "unknown"),
        )
        if not key[0]:
            continue
        grouped[key].append(row)
    return grouped


def evaluate_ope(
    rows: list[dict[str, Any]],
    *,
    switch_lambda: float = 10.0,
    dros_lambda: float = 1.0,
    n_bootstrap: int = 300,
) -> dict[str, Any]:
    grouped = _group_contexts(rows)
    replay_vals: list[float] = []
    ips_vals: list[float] = []
    snips_num = 0.0
    snips_den = 0.0
    dr_vals: list[float] = []
    switch_dr_vals: list[float] = []
    dros_vals: list[float] = []

    contexts_used = 0
    replay_matches = 0
    for _, actions in grouped.items():
        if not actions:
            continue
        by_window = {str(a.get("window") or ""): a for a in actions}
        behavior_window = str(actions[0].get("chosen_window") or "")
        if behavior_window not in by_window:
            continue
        target_window = max(actions, key=lambda x: _to_float(x.get("p_new"), 0.0)).get("window") or ""
        behavior_row = by_window[behavior_window]
        reward = _to_float(behavior_row.get("observed_reward"), float("nan"))
        if math.isnan(reward):
            reward = _reward_proxy(behavior_row)
        reward = max(0.0, min(1.0, reward))

        p_b = max(EPS, _to_float(behavior_row.get("p_base"), 0.0))
        p_e = max(0.0, _to_float(behavior_row.get("p_new"), 0.0))
        w = p_e / p_b

        q_hat_by_action: dict[str, float] = {w_name: _reward_proxy(row) for w_name, row in by_window.items()}
        q_pi_e = 0.0
        for row in actions:
            a = str(row.get("window") or "")
            q_pi_e += max(0.0, _to_float(row.get("p_new"), 0.0)) * q_hat_by_action.get(a, 0.0)
        q_b = q_hat_by_action.get(behavior_window, 0.0)

        ips = w * reward
        dr = q_pi_e + (w * (reward - q_b))
        switch_dr = dr if w <= max(EPS, switch_lambda) else q_pi_e
        shrink = w / (w + max(EPS, dros_lambda))
        dros = q_pi_e + (shrink * (reward - q_b))

        contexts_used += 1
        ips_vals.append(ips)
        snips_num += ips
        snips_den += w
        dr_vals.append(dr)
        switch_dr_vals.append(switch_dr)
        dros_vals.append(dros)
        if target_window == behavior_window:
            replay_matches += 1
            replay_vals.append(reward)

    replay = _bootstrap_ci(replay_vals, n_bootstrap=n_bootstrap) if replay_vals else {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    ips = _bootstrap_ci(ips_vals, n_bootstrap=n_bootstrap) if ips_vals else {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    dr = _bootstrap_ci(dr_vals, n_bootstrap=n_bootstrap) if dr_vals else {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    switch_dr = _bootstrap_ci(switch_dr_vals, n_bootstrap=n_bootstrap) if switch_dr_vals else {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    dros = _bootstrap_ci(dros_vals, n_bootstrap=n_bootstrap) if dros_vals else {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    snips_mean = snips_num / max(EPS, snips_den)
    snips = {"mean": snips_mean, "ci_low": snips_mean, "ci_high": snips_mean}

    return {
        "summary": {
            "contexts_total": len(grouped),
            "contexts_used": contexts_used,
            "replay_match_rate": (float(replay_matches) / float(max(1, contexts_used))),
        },
        "estimators": {
            "replay": replay,
            "ips": ips,
            "snips": snips,
            "dr": dr,
            "switch_dr": switch_dr,
            "dros": dros,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline OPE for prompt-time-density policy.")
    parser.add_argument("--input-json", help="Optional offline rows json for OPE")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--policy-version", default="")
    parser.add_argument("--switch-lambda", type=float, default=10.0)
    parser.add_argument("--dros-lambda", type=float, default=1.0)
    parser.add_argument("--bootstrap", type=int, default=300)
    parser.add_argument("--output", default=".artifacts/prompt_time_density_ope.json")
    args = parser.parse_args()

    rows = _load_input_json(Path(args.input_json)) if args.input_json else _load_from_db(args.days, args.policy_version)
    report = evaluate_ope(
        rows,
        switch_lambda=max(EPS, args.switch_lambda),
        dros_lambda=max(EPS, args.dros_lambda),
        n_bootstrap=max(50, args.bootstrap),
    )
    report["meta"] = {
        "rows": len(rows),
        "days": int(args.days),
        "policy_version": str(args.policy_version or "").strip() or None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out_path), "rows": len(rows), "contexts_used": report["summary"]["contexts_used"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
