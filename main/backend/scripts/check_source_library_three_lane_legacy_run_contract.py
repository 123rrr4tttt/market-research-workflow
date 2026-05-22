#!/usr/bin/env python3
"""Wave9 source-library three-lane legacy run endpoint contract gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CONTRACT_VERSION = "source_library.three_lane_legacy_run.v1"
LEGACY_ENDPOINT = "/api/v1/source_library/items/demo-item/run"
LEGACY_ROUTE = "/api/v1/source_library/items/{item_key}/run"
REPLACEMENT_ENDPOINT = "/api/v1/ingest/source-library/run"


def _route_exists(app: Any, *, path: str, method: str) -> bool:
    wanted_method = method.upper()
    for route in getattr(app, "routes", []):
        methods = {str(item).upper() for item in (getattr(route, "methods", None) or set())}
        if getattr(route, "path", None) == path and wanted_method in methods:
            return True
    return False


def _body(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return {"_json_error": exc.__class__.__name__, "_text": getattr(response, "text", "")}
    return payload if isinstance(payload, dict) else {"_payload": payload}


def check_contract() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post(
        LEGACY_ENDPOINT,
        json={"project_key": "demo_proj", "async_mode": False, "override_params": {"max_items": 1}},
    )
    body = _body(response)
    details = (((body.get("detail") or {}).get("error") or {}).get("details") or {})
    failures: list[str] = []

    if not _route_exists(app, path=LEGACY_ROUTE, method="POST"):
        failures.append(f"missing legacy route: POST {LEGACY_ROUTE}")
    if not _route_exists(app, path=REPLACEMENT_ENDPOINT, method="POST"):
        failures.append(f"missing replacement route: POST {REPLACEMENT_ENDPOINT}")
    if response.status_code != 410:
        failures.append(f"legacy endpoint must return 410, got {response.status_code}")
    if response.headers.get("x-error-code") != "INVALID_INPUT":
        failures.append(f"legacy endpoint x-error-code must be INVALID_INPUT, got {response.headers.get('x-error-code')}")
    if body.get("status") != "error":
        failures.append(f"legacy endpoint body.status must be error, got {body.get('status')}")
    if ((body.get("error") or {}).get("code")) != "INVALID_INPUT":
        failures.append(f"legacy endpoint body.error.code must be INVALID_INPUT, got {(body.get('error') or {}).get('code')}")
    if ((body.get("meta") or {}).get("deprecated")) != "source_library.legacy_item_run.v1":
        failures.append("legacy endpoint meta.deprecated must be source_library.legacy_item_run.v1")
    if details.get("replacement_endpoint") != REPLACEMENT_ENDPOINT:
        failures.append(f"legacy endpoint replacement must be {REPLACEMENT_ENDPOINT}, got {details.get('replacement_endpoint')}")
    if details.get("legacy_status") != "410_gone":
        failures.append(f"legacy endpoint legacy_status must be 410_gone, got {details.get('legacy_status')}")
    if details.get("runs_source_library_item") is not False:
        failures.append("legacy endpoint must not run source-library item")

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "fail" if failures else "pass",
        "legacy_endpoint": LEGACY_ENDPOINT,
        "legacy_route": LEGACY_ROUTE,
        "replacement_endpoint": REPLACEMENT_ENDPOINT,
        "legacy_response": {
            "status_code": response.status_code,
            "x_error_code": response.headers.get("x-error-code"),
            "status": body.get("status"),
            "error_code": (body.get("error") or {}).get("code"),
            "deprecated": (body.get("meta") or {}).get("deprecated"),
            "details": details,
        },
        "failures": failures,
    }


def main() -> int:
    report = check_contract()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
