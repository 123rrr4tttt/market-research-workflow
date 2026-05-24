#!/usr/bin/env python3
"""Build non-secret Single URL provider credential/quota evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib import error, parse, request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_single_url_official_api_provider_maturity import (  # noqa: E402
    PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
)


DEFAULT_OUTPUT = Path(
    "development/latest-dev-docs/automation-runs/single-url-provider-credentials-evidence/"
    "2026-05-24/provider_credentials_configured_only.json"
)


@dataclass(frozen=True)
class ProviderSpec:
    provider_key: str
    credential_groups: tuple[tuple[str, ...], ...]
    live_probe_kind: str | None = None


PROVIDER_SPECS = (
    ProviderSpec("x_twitter", (("TWITTER_BEARER_TOKEN",),), "x_recent_search"),
    ProviderSpec("google_search", (("GOOGLE_SEARCH_API_KEY", "GOOGLE_SEARCH_CSE_ID"),)),
    ProviderSpec("serper", (("SERPER_API_KEY",),)),
    ProviderSpec("serpapi", (("SERPAPI_KEY",), ("SERPAPI_API_KEY",))),
    ProviderSpec("serpstack", (("SERPSTACK_KEY",),)),
    ProviderSpec("bing_search", (("BING_SEARCH_KEY",),)),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def _merged_env(env_file: Path | None, env: Mapping[str, str] | None = None) -> dict[str, str]:
    values = dict(env or os.environ)
    for key, value in _parse_env_file(env_file).items():
        values.setdefault(key, value)
    return values


def _nonempty(values: Mapping[str, str], key: str) -> bool:
    return bool(str(values.get(key) or "").strip())


def _satisfied_group(values: Mapping[str, str], spec: ProviderSpec) -> tuple[str, ...] | None:
    for group in spec.credential_groups:
        if all(_nonempty(values, key) for key in group):
            return group
    return None


def _probe_x_recent_search(values: Mapping[str, str], *, timeout_seconds: float) -> dict[str, Any]:
    token = str(values.get("TWITTER_BEARER_TOKEN") or "").strip()
    if not token:
        return {"status": "not_configured", "quota_status": "not_validated", "provider_specific_quota_validated": False}
    query = parse.urlencode({"query": "robotics lang:en", "max_results": "10"})
    req = request.Request(
        f"https://api.twitter.com/2/tweets/search/recent?{query}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "mrw-single-url-provider-evidence/1.0"},
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            status_code = int(response.status)
            response.read(128)
    except error.HTTPError as exc:
        if exc.code == 429:
            return {
                "status": "rate_limited",
                "http_status": exc.code,
                "quota_status": "rate_limited",
                "provider_specific_quota_validated": False,
            }
        return {
            "status": "failed",
            "http_status": exc.code,
            "quota_status": "not_validated",
            "provider_specific_quota_validated": False,
            "error_type": "HTTPError",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "quota_status": "not_validated",
            "provider_specific_quota_validated": False,
            "error_type": exc.__class__.__name__,
        }
    return {
        "status": "passed" if status_code == 200 else "failed",
        "http_status": status_code,
        "quota_status": "within_quota" if status_code == 200 else "not_validated",
        "provider_specific_quota_validated": status_code == 200,
    }


def _live_probe(spec: ProviderSpec, values: Mapping[str, str], *, timeout_seconds: float) -> dict[str, Any]:
    if spec.live_probe_kind == "x_recent_search":
        return _probe_x_recent_search(values, timeout_seconds=timeout_seconds)
    return {
        "status": "not_implemented",
        "quota_status": "not_validated",
        "provider_specific_quota_validated": False,
    }


def build_provider_credentials_evidence(
    *,
    env_file: Path | None = None,
    env: Mapping[str, str] | None = None,
    allow_live_api: bool = False,
    timeout_seconds: float = 10.0,
    generated_by: str = "build_single_url_provider_credentials_evidence.py",
) -> dict[str, Any]:
    values = _merged_env(env_file, env=env)
    providers: list[dict[str, Any]] = []
    for spec in PROVIDER_SPECS:
        group = _satisfied_group(values, spec)
        if group is None:
            continue
        live = (
            _live_probe(spec, values, timeout_seconds=timeout_seconds)
            if allow_live_api
            else {
                "status": "configured_only",
                "quota_status": "configured_only",
                "provider_specific_quota_validated": False,
            }
        )
        providers.append(
            {
                "provider_key": spec.provider_key,
                "credential_state": "configured",
                "configured_key_names": list(group),
                "configured_key_count": len(group),
                "quota_status": live["quota_status"],
                "live_probe_status": live["status"],
                "live_probe_authorized": bool(allow_live_api),
                "provider_specific_quota_validated": bool(live["provider_specific_quota_validated"]),
                "credential_material_logged": False,
                "live_probe": {
                    key: value
                    for key, value in live.items()
                    if key not in {"quota_status", "provider_specific_quota_validated"}
                },
            }
        )
    return {
        "contract_version": PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
        "evidence_scope": "provider_credentials_quota",
        "generated_by": generated_by,
        "generated_at": _utc_now(),
        "live_probe_authorized": bool(allow_live_api),
        "source": {
            "env_file": str(env_file) if env_file is not None else None,
            "env_file_loaded": bool(env_file is not None and env_file.is_file()),
            "live_api_allowed": bool(allow_live_api),
        },
        "credential_material_logged": False,
        "providers": providers,
        "closure": {
            "provider_credentials_beyond_crossref_satisfied": bool(
                providers and all(provider["provider_specific_quota_validated"] for provider in providers)
            ),
            "configured_provider_count": len(providers),
            "live_quota_validated_provider_count": sum(
                1 for provider in providers if provider["provider_specific_quota_validated"]
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build non-secret Single URL provider credentials/quota evidence.")
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--allow-live-api", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    evidence = build_provider_credentials_evidence(
        env_file=args.env_file,
        allow_live_api=args.allow_live_api,
        timeout_seconds=args.timeout_seconds,
    )
    output_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "OK single_url.provider_credentials_quota_evidence.v1 "
            f"providers={len(evidence['providers'])} "
            f"live_api_allowed={str(args.allow_live_api).lower()} "
            f"credential_material_logged={str(evidence['credential_material_logged']).lower()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
