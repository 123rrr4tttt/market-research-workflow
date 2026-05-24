from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest import url_pool as url_pool_module
from scripts.check_llm_crawler_high_js_replay_readiness import CONFIGURED_SESSION_USER_DATA_DIR_MODES
from scripts.check_llm_crawler_high_js_replay_readiness import DEFAULT_HIGH_JS_TARGETS
from scripts.check_llm_crawler_high_js_replay_readiness import PUBLIC_REPLAY_CONTRACT_VERSION
from scripts.check_llm_crawler_high_js_replay_readiness import X_LAWFUL_SESSION_TARGET_ID
from scripts.check_llm_crawler_replay_manifest import OPT_IN_CONTRACT_VERSION


DEFAULT_OUTPUT_PATH = Path(
    "development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/"
    "2026-05-23/output.public.attempt.json"
)
SESSION_EVIDENCE_CONTRACT_VERSION = "llm_crawler.high_js_session_replay_evidence.v1"
SESSION_USER_DATA_DIR_ENV = "LLM_CRAWLER_HIGH_JS_SESSION_USER_DATA_DIR"
COPY_SESSION_USER_DATA_DIR_ENV = "LLM_CRAWLER_HIGH_JS_COPY_SESSION_USER_DATA_DIR"
CHROME_CANDIDATES = [
    os.environ.get("LLM_CRAWLER_CHROME_PATH", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
]

TargetRunner = Callable[[Mapping[str, Any], str, int], dict[str, Any]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _discover_chrome() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _path_fingerprint(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def _ignore_chrome_runtime_files(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name.startswith("Singleton")
        or name in {
            "Crashpad",
            "BrowserMetrics",
            "GrShaderCache",
            "GraphiteDawnCache",
            "ShaderCache",
        }
    }


def _prepare_session_runtime(
    *,
    root: Path,
    session_user_data_dir: str | Path | None,
    session_user_data_dir_source: str,
    copy_session_user_data_dir: bool,
) -> tuple[Path | None, dict[str, Any], list[str], Path | None]:
    errors: list[str] = []
    if session_user_data_dir is None:
        return (
            None,
            {
                "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
                "requested": False,
                "configured": False,
                "applied": False,
                "source": "none",
                "user_data_dir_mode": "ephemeral_empty_profile",
                "copy_session_user_data_dir": False,
                "credential_material_logged": False,
                "path_disclosed": False,
            },
            errors,
            None,
        )

    source_path = _resolve_path(root, session_user_data_dir)
    exists = source_path.is_dir()
    evidence: dict[str, Any] = {
        "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
        "requested": True,
        "configured": exists,
        "applied": False,
        "source": session_user_data_dir_source,
        "user_data_dir_mode": "configured_path_unavailable",
        "copy_session_user_data_dir": bool(copy_session_user_data_dir),
        "source_path_name": source_path.name,
        "source_path_fingerprint": _path_fingerprint(source_path),
        "credential_material_logged": False,
        "path_disclosed": False,
    }
    if not exists:
        errors.append(f"session user data dir is not available or not a directory: source={session_user_data_dir_source}")
        return None, evidence, errors, None

    if not copy_session_user_data_dir:
        evidence["applied"] = True
        evidence["user_data_dir_mode"] = "operator_profile_direct"
        return source_path, evidence, errors, None

    runtime_dir = Path(tempfile.mkdtemp(prefix="mrw-high-js-session-profile-"))
    try:
        shutil.rmtree(runtime_dir)
        shutil.copytree(source_path, runtime_dir, symlinks=True, ignore=_ignore_chrome_runtime_files)
    except Exception as exc:  # pragma: no cover - platform/filesystem dependent safety path
        shutil.rmtree(runtime_dir, ignore_errors=True)
        errors.append(f"failed to copy session user data dir for replay: {type(exc).__name__}")
        return None, evidence, errors, None

    evidence["applied"] = True
    evidence["user_data_dir_mode"] = "copied_operator_profile"
    evidence["runtime_profile_disposable_copy"] = True
    return runtime_dir, evidence, errors, runtime_dir


def _session_context_for_target(session_evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
        "session_aware_replay_requested": bool(session_evidence.get("requested")),
        "session_context_applied": bool(session_evidence.get("applied")),
        "source": session_evidence.get("source"),
        "user_data_dir_mode": session_evidence.get("user_data_dir_mode"),
        "credential_material_logged": False,
    }


def _redact_diagnostic_text(value: str) -> str:
    redacted = str(value or "")
    redacted = re.sub(r"--user-data-dir=(?:\"[^\"]+\"|'[^']+'|\S+)", "<redacted_user_data_dir>", redacted)
    redacted = re.sub(r"/Users/[^\s'\"<>]+", "/Users/<redacted_path>", redacted)
    redacted = re.sub(r"/home/[^\s'\"<>]+", "/home/<redacted_path>", redacted)
    redacted = re.sub(r"/private/var/folders/[^\s'\"<>]+", "/private/var/folders/<redacted_path>", redacted)
    redacted = re.sub(
        r"[A-Za-z]:\\Users\\[^\s'\"<>]+",
        lambda _match: r"C:\Users\<redacted_path>",
        redacted,
    )
    redacted = re.sub(
        r"%APPDATA%\\?[^\s'\"<>]*",
        lambda _match: r"%APPDATA%\<redacted_path>",
        redacted,
    )
    return redacted


def _title_from_dom(dom: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", dom, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _route_profile(target: Mapping[str, Any]) -> dict[str, Any]:
    profile = url_pool_module._frontdoor_route_profile_for_url(str(target.get("url") or ""))
    router = profile.get("router_contract") if isinstance(profile.get("router_contract"), Mapping) else {}
    fallback = router.get("fallback_boundary") if isinstance(router.get("fallback_boundary"), Mapping) else {}
    return {
        "contract_version": profile.get("contract_version"),
        "domain": profile.get("domain"),
        "route_hint": profile.get("route_hint"),
        "fetch_strategy": profile.get("fetch_strategy"),
        "high_js": profile.get("high_js") is True,
        "render_required": profile.get("render_required") is True,
        "router_state": router.get("router_state"),
        "reason_code": router.get("reason_code"),
        "browser_fetch_required": fallback.get("browser_fetch_required") is True,
        "http_fetch_fallback_allowed": fallback.get("http_fetch_fallback_allowed") is True,
    }


def _success_marker(target_id: str, dom: str, title: str) -> bool:
    lower = dom.lower()
    title_lower = title.lower()
    if target_id == "youtube_search_robotics":
        return "robotics - youtube" in title_lower or "video-title" in lower or "ytd-video-renderer" in lower
    if target_id == "instagram_tag_robotics":
        return "robotics" in lower and "instagram" in lower and bool(title)
    if target_id == "x_search_robotics":
        return "robotics" in lower and ("x.com/search" in lower or "search?q=robotics" in lower)
    return "robotics" in lower


def _classify_browser_result(target: Mapping[str, Any], browser: Mapping[str, Any]) -> dict[str, Any]:
    target_id = str(target.get("target_id") or "")
    dom = str(browser.get("dom") or "")
    stderr = _redact_diagnostic_text(str(browser.get("stderr") or ""))
    title = _title_from_dom(dom)
    lower = dom.lower()
    rendered = bool(len(dom) > 40 and "<html" in lower and "javascript is not available" not in lower)
    markers = {
        "title": title,
        "contains_robotics": "robotics" in lower,
        "contains_login": "login" in lower,
        "contains_captcha": "captcha" in lower,
        "contains_video_title": "video-title" in lower,
        "contains_javascript_disabled": "javascript is not available" in lower,
    }
    success = bool(rendered and _success_marker(target_id, dom, title))
    if success:
        status = "success"
        reason = "Headless Chrome rendered target-specific public search content."
    elif rendered and (markers["contains_login"] or markers["contains_captcha"]):
        status = "auth_or_anti_bot_blocked"
        reason = "Headless Chrome rendered the page, but public content was gated by auth or anti-bot markers."
    elif rendered:
        status = "rendered_without_expected_search_content"
        reason = "Headless Chrome rendered HTML without the target-specific search evidence."
    else:
        status = "browser_runtime_failed"
        reason = stderr[-500:] or "Headless Chrome did not return a usable rendered DOM."
    return {
        "status": status,
        "reason": reason,
        "browser_rendered": rendered,
        "browser_runtime_started": bool(browser.get("browser_runtime_started")),
        "public_network_attempted": bool(browser.get("public_network_attempted")),
        "browser_timed_out": bool(browser.get("timed_out")),
        "returncode": browser.get("returncode"),
        "elapsed_ms": browser.get("elapsed_ms"),
        "rendered_dom_bytes": len(dom.encode("utf-8")),
        "stderr_tail": stderr[-1000:],
        "markers": markers,
    }


def _run_chrome_target(
    target: Mapping[str, Any],
    chrome_path: str,
    timeout_seconds: int,
    *,
    user_data_dir: Path | None = None,
) -> dict[str, Any]:
    url = str(target.get("url") or "")
    started = time.monotonic()
    temp_user_data_dir = Path(tempfile.mkdtemp(prefix="mrw-high-js-chrome-")) if user_data_dir is None else None
    runtime_user_data_dir = user_data_dir or temp_user_data_dir
    cmd = [
        chrome_path,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        f"--user-data-dir={runtime_user_data_dir}",
        "--virtual-time-budget=8000",
        "--dump-dom",
        url,
    ]
    try:
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_seconds)
        return {
            "browser_runtime_started": True,
            "public_network_attempted": True,
            "timed_out": False,
            "returncode": completed.returncode,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "dom": completed.stdout or "",
            "stderr": completed.stderr or "",
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "ignore")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "ignore")
        return {
            "browser_runtime_started": True,
            "public_network_attempted": True,
            "timed_out": True,
            "returncode": None,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "dom": stdout,
            "stderr": stderr,
        }
    finally:
        if temp_user_data_dir is not None:
            shutil.rmtree(temp_user_data_dir, ignore_errors=True)


def _status_counts(results: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _target_result_successful(row: Mapping[str, Any] | None) -> bool:
    if not isinstance(row, Mapping):
        return False
    return str(row.get("status") or "").strip().lower() == "success" and row.get("browser_rendered") is True


def _configured_session_mode(session_evidence: Mapping[str, Any]) -> bool:
    return bool(
        session_evidence.get("requested") is True
        and session_evidence.get("configured") is True
        and session_evidence.get("applied") is True
        and str(session_evidence.get("user_data_dir_mode") or "") in CONFIGURED_SESSION_USER_DATA_DIR_MODES
    )


def _lawful_session_evidence_for_target(
    target: Mapping[str, Any],
    row: Mapping[str, Any] | None,
    session_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    target_id = str(target.get("target_id") or "")
    browser_rendered_success = _target_result_successful(row)
    session_mode_configured = _configured_session_mode(session_evidence)
    required = target_id == X_LAWFUL_SESSION_TARGET_ID
    return {
        "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
        "target_id": target_id,
        "required": required,
        "accepted": bool(required and browser_rendered_success and session_mode_configured),
        "browser_rendered_success": browser_rendered_success,
        "session_mode_configured": session_mode_configured,
        "session_aware_replay_requested": bool(session_evidence.get("requested")),
        "session_context_applied": bool(session_evidence.get("applied")),
        "user_data_dir_mode": session_evidence.get("user_data_dir_mode"),
    }


def _apply_lawful_session_policy(
    target: Mapping[str, Any],
    row: Mapping[str, Any],
    session_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    target_id = str(target.get("target_id") or "")
    lawful_session_evidence = _lawful_session_evidence_for_target(target, row, session_evidence)
    classified = dict(row)
    classified["lawful_session_evidence"] = lawful_session_evidence
    status = str(classified.get("status") or "").strip().lower()
    if (
        target_id == X_LAWFUL_SESSION_TARGET_ID
        and lawful_session_evidence.get("accepted") is not True
        and classified.get("browser_rendered") is True
        and classified.get("public_network_attempted") is True
        and status in {"success", "auth_or_anti_bot_blocked"}
    ):
        classified["pre_session_policy_status"] = classified.get("status")
        classified["status"] = "platform_blocked"
        classified["reason"] = (
            "X high-JS replay rendered, but full success requires explicit configured lawful-session evidence."
        )
    return classified


def _target_result_accepted_for_closure(target: Mapping[str, Any], row: Mapping[str, Any] | None) -> bool:
    if str(target.get("target_id") or "") == X_LAWFUL_SESSION_TARGET_ID:
        lawful_session_evidence = row.get("lawful_session_evidence") if isinstance(row, Mapping) else {}
        return bool(_target_result_successful(row) and lawful_session_evidence.get("accepted") is True)
    return _target_result_successful(row)


def _x_platform_blocker_proven(row: Mapping[str, Any] | None) -> bool:
    if not isinstance(row, Mapping):
        return False
    lawful_session_evidence = row.get("lawful_session_evidence") if isinstance(row.get("lawful_session_evidence"), Mapping) else {}
    markers = row.get("markers") if isinstance(row.get("markers"), Mapping) else {}
    pre_session_status = str(row.get("pre_session_policy_status") or "").strip().lower()
    lawful_session_basis = (
        pre_session_status == "success"
        or (
            pre_session_status == "auth_or_anti_bot_blocked"
            and bool(markers.get("contains_login") or markers.get("contains_captcha"))
        )
    )
    return bool(
        str(row.get("target_id") or "") == X_LAWFUL_SESSION_TARGET_ID
        and str(row.get("status") or "").strip().lower() == "platform_blocked"
        and row.get("browser_rendered") is True
        and row.get("public_network_attempted") is True
        and lawful_session_evidence.get("accepted") is not True
        and lawful_session_basis
    )


def _external_gate_blocker_proven(target: Mapping[str, Any], row: Mapping[str, Any] | None) -> bool:
    if not isinstance(row, Mapping):
        return False
    allowed_statuses = {
        str(status).strip().lower()
        for status in target.get("external_blocker_accept_statuses", [])
        if str(status).strip()
    }
    markers = row.get("markers") if isinstance(row.get("markers"), Mapping) else {}
    auth_or_anti_bot_marker = bool(markers.get("contains_login") or markers.get("contains_captcha"))
    return bool(
        str(row.get("status") or "").strip().lower() in allowed_statuses
        and row.get("browser_rendered") is True
        and row.get("public_network_attempted") is True
        and auth_or_anti_bot_marker
    )


def run_high_js_public_replay(
    *,
    operator: str,
    run_id: str,
    allow_public_network: bool,
    allow_browser_runtime: bool,
    timeout_seconds: int = 20,
    chrome_path: str | None = None,
    evidence_output: str | Path | None = None,
    session_user_data_dir: str | Path | None = None,
    session_user_data_dir_source: str = "explicit",
    copy_session_user_data_dir: bool = False,
    target_runner: TargetRunner | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    root = _repo_root()
    resolved_chrome = chrome_path or _discover_chrome()
    target_results: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    runtime_user_data_dir, session_evidence, session_errors, session_cleanup_dir = _prepare_session_runtime(
        root=root,
        session_user_data_dir=session_user_data_dir,
        session_user_data_dir_source=session_user_data_dir_source if session_user_data_dir else "none",
        copy_session_user_data_dir=copy_session_user_data_dir,
    )
    validation_errors.extend(session_errors)

    if not allow_public_network:
        validation_errors.append("allow_public_network must be true for real high-JS public replay")
    if not allow_browser_runtime:
        validation_errors.append("allow_browser_runtime must be true for real high-JS public replay")
    if target_runner is None and not resolved_chrome:
        validation_errors.append("Chrome runtime not found; set LLM_CRAWLER_CHROME_PATH")

    try:
        for target in DEFAULT_HIGH_JS_TARGETS:
            route = _route_profile(target)
            if validation_errors:
                classified = {
                    "status": "skipped_runtime_not_available",
                    "reason": "; ".join(validation_errors),
                    "browser_rendered": False,
                    "browser_runtime_started": False,
                    "public_network_attempted": False,
                    "browser_timed_out": False,
                    "returncode": None,
                    "elapsed_ms": 0,
                    "rendered_dom_bytes": 0,
                    "stderr_tail": "",
                    "markers": {},
                }
            else:
                browser = (
                    target_runner(target, str(resolved_chrome), timeout_seconds)
                    if target_runner is not None
                    else _run_chrome_target(
                        target,
                        str(resolved_chrome),
                        timeout_seconds,
                        user_data_dir=runtime_user_data_dir,
                    )
                )
                classified = _classify_browser_result(target, browser)
            classified = _apply_lawful_session_policy(target, classified, session_evidence)
            target_results.append(
                {
                    "target_id": target["target_id"],
                    "url": target["url"],
                    "expected_domain": target["expected_domain"],
                    "frontdoor_route_profile": route,
                    "session_context": _session_context_for_target(session_evidence),
                    **classified,
                }
            )
    finally:
        if session_cleanup_dir is not None:
            shutil.rmtree(session_cleanup_dir, ignore_errors=True)
            session_evidence["runtime_profile_cleanup"] = "attempted"

    success_count = sum(1 for row in target_results if row.get("status") == "success" and row.get("browser_rendered") is True)
    public_attempted = sum(1 for row in target_results if row.get("public_network_attempted") is True)
    browser_started = any(row.get("browser_runtime_started") is True for row in target_results)
    public_network_attempted = any(row.get("public_network_attempted") is True for row in target_results)
    by_target_id = {str(row.get("target_id") or ""): row for row in target_results}
    public_probe_targets = list(DEFAULT_HIGH_JS_TARGETS)
    successful_accessible_targets = [
        target
        for target in public_probe_targets
        if _target_result_accepted_for_closure(target, by_target_id.get(str(target.get("target_id") or "")))
    ]
    gate_blocked_targets = [
        target
        for target in public_probe_targets
        if not _target_result_accepted_for_closure(target, by_target_id.get(str(target.get("target_id") or "")))
        and (
            _external_gate_blocker_proven(target, by_target_id.get(str(target.get("target_id") or "")))
            or _x_platform_blocker_proven(by_target_id.get(str(target.get("target_id") or "")))
        )
    ]
    all_probe_targets_accounted_for = len(successful_accessible_targets) + len(gate_blocked_targets) == len(public_probe_targets)
    accessible_public_proven = bool(
        not validation_errors
        and allow_public_network
        and allow_browser_runtime
        and bool(successful_accessible_targets)
        and all_probe_targets_accounted_for
    )
    remaining_external_blockers = []
    for target in gate_blocked_targets:
        target_id = str(target.get("target_id") or "")
        row = by_target_id.get(target_id)
        classification = "platform_blocked" if _x_platform_blocker_proven(row) else "intrinsic_external_auth_or_anti_bot_gate"
        remaining_external_blockers.append(
            {
                "target_id": target_id,
                "url": target.get("url"),
                "status": row.get("status") if isinstance(row, Mapping) else None,
                "reason": row.get("reason") if isinstance(row, Mapping) else None,
                "markers": row.get("markers") if isinstance(row, Mapping) and isinstance(row.get("markers"), Mapping) else {},
                "classification": classification,
                "lawful_session_evidence": (
                    row.get("lawful_session_evidence")
                    if isinstance(row, Mapping) and isinstance(row.get("lawful_session_evidence"), Mapping)
                    else {}
                ),
            }
        )
    external_gate_blockers_proven = bool(remaining_external_blockers and all_probe_targets_accounted_for)
    all_targets_accepted = all(
        _target_result_accepted_for_closure(target, by_target_id.get(str(target.get("target_id") or "")))
        for target in public_probe_targets
    )
    proven = bool(
        not validation_errors
        and allow_public_network
        and allow_browser_runtime
        and public_attempted == len(DEFAULT_HIGH_JS_TARGETS)
        and success_count == len(DEFAULT_HIGH_JS_TARGETS)
        and all_targets_accepted
    )

    return {
        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "operator_opt_in": {
            "contract_version": OPT_IN_CONTRACT_VERSION,
            "operator": operator,
            "run_id": run_id,
            "requested_at": started_at,
            "browser_runtime": resolved_chrome or "",
            "evidence_output": str(evidence_output or DEFAULT_OUTPUT_PATH),
            "output_contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
            "target_ids": [target["target_id"] for target in DEFAULT_HIGH_JS_TARGETS],
            "session_aware_replay_requested": bool(session_evidence.get("requested")),
            "session_context_applied": bool(session_evidence.get("applied")),
            "session_context_source": session_evidence.get("source"),
            "credential_material_logged": False,
            "allow_public_network": bool(allow_public_network),
            "allow_browser_runtime": bool(allow_browser_runtime),
            "allow_high_js_targets": True,
            "acknowledge_external_site_terms": True,
            "acknowledge_rate_limits": True,
            "acknowledge_no_shared_index_edits": True,
        },
        "inputs": {
            "target_count": len(DEFAULT_HIGH_JS_TARGETS),
            "targets": [dict(target) for target in DEFAULT_HIGH_JS_TARGETS],
            "public_high_js_probe_target_ids": [target["target_id"] for target in public_probe_targets],
            "minimum_accessible_success_count": 1,
            "successful_accessible_target_ids": [target["target_id"] for target in successful_accessible_targets],
            "external_gate_target_ids": [target["target_id"] for target in gate_blocked_targets],
            "timeout_seconds": timeout_seconds,
        },
        "outputs": {
            "target_results": target_results,
            "status_counts": _status_counts(target_results),
            "public_targets_attempted": public_attempted,
            "high_js_success_count": success_count,
            "remaining_external_blockers": remaining_external_blockers,
        },
        "validation": {
            "passed": not validation_errors,
            "errors": validation_errors,
            "public_network_attempted": public_network_attempted,
            "browser_runtime_started": browser_started,
            "real_public_high_js_replay_proven": proven,
            "accessible_public_high_js_replay_proven": accessible_public_proven,
            "external_gate_blockers_proven": external_gate_blockers_proven,
            "session_aware_replay_requested": bool(session_evidence.get("requested")),
            "session_context_applied": bool(session_evidence.get("applied")),
        },
        "closure": {
            "real_public_high_js_replay_complete": proven,
            "accessible_public_high_js_replay_complete": accessible_public_proven,
            "remaining_external_blockers": remaining_external_blockers,
            "full_closure_allowed": proven,
            "claim": (
                "real_public_high_js_replay_complete"
                if proven
                else (
                    "accessible_public_high_js_replay_complete_external_targets_blocked"
                    if accessible_public_proven and external_gate_blockers_proven
                    else "real_public_high_js_replay_attempted_not_proven"
                )
            ),
        },
        "evidence": {
            "contract_version": "llm_crawler.high_js_public_replay_evidence.v1",
            "session": session_evidence,
            "credential_material_logged": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an opt-in high-JS public replay through a local headless Chrome runtime.")
    parser.add_argument("--operator", default="codex")
    parser.add_argument("--run-id", default=f"high-js-public-replay-{_utc_now()}")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--chrome-path", default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-browser-runtime", action="store_true")
    parser.add_argument(
        "--session-user-data-dir",
        type=Path,
        default=None,
        help=(
            "Optional operator-provided Chrome user data dir with legal X/Instagram session state. "
            f"Can also be set with {SESSION_USER_DATA_DIR_ENV}."
        ),
    )
    parser.add_argument(
        "--copy-session-user-data-dir",
        action="store_true",
        help=(
            "Copy the operator-provided session user data dir to a disposable temp profile before replay. "
            f"Can also be enabled with {COPY_SESSION_USER_DATA_DIR_ENV}=true."
        ),
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    env_session_user_data_dir = os.environ.get(SESSION_USER_DATA_DIR_ENV)
    session_user_data_dir = args.session_user_data_dir or env_session_user_data_dir
    session_user_data_dir_source = (
        "cli_session_user_data_dir"
        if args.session_user_data_dir is not None
        else (f"env:{SESSION_USER_DATA_DIR_ENV}" if env_session_user_data_dir else "none")
    )
    copy_session_user_data_dir = bool(args.copy_session_user_data_dir or _env_flag(COPY_SESSION_USER_DATA_DIR_ENV))

    result = run_high_js_public_replay(
        operator=args.operator,
        run_id=args.run_id,
        allow_public_network=args.allow_public_network,
        allow_browser_runtime=args.allow_browser_runtime,
        timeout_seconds=args.timeout_seconds,
        chrome_path=args.chrome_path,
        evidence_output=args.output,
        session_user_data_dir=session_user_data_dir,
        session_user_data_dir_source=session_user_data_dir_source,
        copy_session_user_data_dir=copy_session_user_data_dir,
    )
    output_path = _resolve_path(_repo_root(), args.output)
    _write_json(output_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("validation", {}).get("errors"):
        return 1
    if args.strict and not result.get("validation", {}).get("real_public_high_js_replay_proven"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
