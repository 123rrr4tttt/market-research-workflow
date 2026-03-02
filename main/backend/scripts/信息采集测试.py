#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.ingest.single_url import ingest_single_url
from app.services.projects import bind_project
from app.settings.config import settings


DEFAULT_URLS = [
    "https://arxiv.org/abs/1706.03762",
    "https://www.bbc.com/news/articles/c79qnq38r7wo",
    "https://www.nature.com/search?q=embodied+intelligence",
    "https://github.com/openai/openai-python/stargazers",
    "https://www.google.com/search?q=embodied+ai+startup",
    "https://www.actiontoaction.ai/",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="信息采集测试（逐 URL 跑 single_url 链路）")
    parser.add_argument("--project-key", default="demo_proj", help="项目键，默认 demo_proj")
    parser.add_argument("--url", action="append", default=[], help="单个 URL，可重复传入")
    parser.add_argument("--urls-file", default="", help="URL 文件路径（每行一个 URL，# 开头为注释）")
    parser.add_argument("--query-term", action="append", default=[], help="query_terms，可重复传入")
    parser.add_argument("--strict-mode", action="store_true", help="single_url strict_mode=true")
    parser.add_argument(
        "--enable-strict-gate",
        choices=["keep", "on", "off"],
        default="keep",
        help="是否切换 ingest_enable_strict_gate，默认 keep（不改）",
    )
    parser.add_argument("--json-out", default="", help="结果 JSON 输出路径")
    parser.add_argument("--self-check", action="store_true", help="执行结果字段自检并在失败时返回非0")
    parser.add_argument(
        "--use-default-sample",
        action="store_true",
        help="未传 URL 时使用默认样本 URL 列表",
    )
    return parser


def _load_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = [str(x).strip() for x in args.url if str(x or "").strip()]
    if args.urls_file:
        path = Path(args.urls_file).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"urls file not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            row = line.strip()
            if not row or row.startswith("#"):
                continue
            urls.append(row)
    if not urls and args.use_default_sample:
        urls = list(DEFAULT_URLS)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def _fetch_doc_preview(doc_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        doc = session.query(Document).filter(Document.id == int(doc_id)).first()
        if doc is None:
            return None
        content = str(doc.content or "").strip()
        return {
            "id": int(doc.id),
            "title": str(doc.title or ""),
            "uri": str(doc.uri or ""),
            "content_len": len(content),
            "content_head": content[:260].replace("\n", " "),
        }


def _resolve_doc_ids(result: dict[str, Any]) -> list[int]:
    out: list[int] = []
    doc_id = result.get("document_id")
    if isinstance(doc_id, int) and doc_id > 0:
        out.append(doc_id)
    crawler = result.get("crawler_dispatch")
    if isinstance(crawler, dict):
        for k in ("valid_output_doc_ids", "output_doc_ids"):
            for item in crawler.get(k) or []:
                try:
                    v = int(item)
                except Exception:
                    continue
                if v > 0 and v not in out:
                    out.append(v)
    return out


def _compute_rejected_count(result: dict[str, Any]) -> int:
    raw = result.get("rejected_count")
    try:
        if raw is not None:
            return max(0, int(raw))
    except Exception:
        pass
    rb = result.get("rejection_breakdown")
    if isinstance(rb, dict):
        total = 0
        for v in rb.values():
            try:
                total += max(0, int(v))
            except Exception:
                continue
        return total
    return 0


def _validate_row_shape(row: dict[str, Any]) -> list[str]:
    required = ("status", "inserted_valid", "rejected_count", "rejection_breakdown", "doc_id", "content_len")
    missing: list[str] = []
    for key in required:
        if key not in row:
            missing.append(key)
    if not isinstance(row.get("rejection_breakdown"), dict):
        missing.append("rejection_breakdown(dict)")
    return missing


def main() -> int:
    args = _build_parser().parse_args()
    urls = _load_urls(args)
    if not urls:
        print("未提供 URL。可用 --url/--urls-file，或加 --use-default-sample。", file=sys.stderr)
        return 2

    if args.enable_strict_gate == "on":
        settings.ingest_enable_strict_gate = True
    elif args.enable_strict_gate == "off":
        settings.ingest_enable_strict_gate = False

    query_terms = [str(x).strip() for x in args.query_term if str(x or "").strip()]
    rows: list[dict[str, Any]] = []

    print(f"开始执行：project_key={args.project_key}, strict_mode={bool(args.strict_mode)}, strict_gate={settings.ingest_enable_strict_gate}")
    print(f"URL 数量：{len(urls)}")
    print()

    with bind_project(args.project_key):
        for idx, url in enumerate(urls, 1):
            result = ingest_single_url(
                url=url,
                query_terms=query_terms or None,
                strict_mode=bool(args.strict_mode),
            )
            resolved_doc_ids = _resolve_doc_ids(result)
            previews = [_fetch_doc_preview(i) for i in resolved_doc_ids]
            previews = [x for x in previews if isinstance(x, dict)]
            primary = previews[0] if previews else None

            row = {
                "index": idx,
                "url": url,
                "status": result.get("status"),
                "inserted": int(result.get("inserted") or 0),
                "inserted_valid": int(result.get("inserted_valid") or 0),
                "skipped": int(result.get("skipped") or 0),
                "rejected_count": _compute_rejected_count(result),
                "quality_score": result.get("quality_score"),
                "structured_extraction_status": result.get("structured_extraction_status"),
                "rejection_breakdown": result.get("rejection_breakdown") or {},
                "pre_fetch_reason": (result.get("pre_fetch_url_gate") or {}).get("reason"),
                "pre_write_reason": (result.get("pre_write_content_gate") or {}).get("reason"),
                "document_ids": resolved_doc_ids,
                "doc_id": int(primary["id"]) if primary and isinstance(primary.get("id"), int) else None,
                "content_len": int(primary["content_len"]) if primary and isinstance(primary.get("content_len"), int) else None,
                "primary_doc": primary,
            }
            rows.append(row)

            print(f"[{idx}] {url}")
            print(
                f"  status={row['status']} inserted={row['inserted']} inserted_valid={row['inserted_valid']} skipped={row['skipped']}"
            )
            print(f"  quality={row['quality_score']} structured={row['structured_extraction_status']}")
            if row["rejection_breakdown"]:
                print(f"  rejection_breakdown={row['rejection_breakdown']}")
            if row["rejected_count"]:
                print(f"  rejected_count={row['rejected_count']}")
            if row["pre_fetch_reason"]:
                print(f"  pre_fetch_reason={row['pre_fetch_reason']}")
            if row["pre_write_reason"]:
                print(f"  pre_write_reason={row['pre_write_reason']}")
            if primary:
                print(f"  doc_id={primary['id']} content_len={primary['content_len']}")
                print(f"  title={primary['title'][:120]}")
                print(f"  head={primary['content_head']}")
            print()

    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "project_key": args.project_key,
        "strict_mode": bool(args.strict_mode),
        "strict_gate": bool(settings.ingest_enable_strict_gate),
        "url_count": len(rows),
        "success_count": sum(1 for x in rows if x.get("status") == "success"),
        "degraded_count": sum(1 for x in rows if x.get("status") == "degraded_success"),
        "failed_count": sum(1 for x in rows if x.get("status") == "failed"),
        "inserted_valid_total": sum(int(x.get("inserted_valid") or 0) for x in rows),
    }
    payload = {"summary": summary, "results": rows}

    if args.self_check:
        failed: list[dict[str, Any]] = []
        for row in rows:
            missing = _validate_row_shape(row)
            if missing:
                failed.append({"url": row.get("url"), "missing": missing})
        summary["self_check"] = {
            "ok": not failed,
            "failed_count": len(failed),
            "failed_rows": failed[:20],
        }

    out_path = args.json_out.strip()
    if not out_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = str((BACKEND_ROOT / "scripts" / f"信息采集测试结果_{ts}.json").resolve())
    out_file = Path(out_path).expanduser().resolve()
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("汇总：")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"结果已写入：{out_file}")
    if args.self_check and not bool((summary.get("self_check") or {}).get("ok")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
