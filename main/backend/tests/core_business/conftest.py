from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


@pytest.fixture(scope="session")
def core_business_client():
    if _IMPORT_ERROR is not None:
        pytest.skip(f"core business tests require backend dependencies: {_IMPORT_ERROR}")
    return TestClient(backend_app, raise_server_exceptions=False)


@pytest.fixture()
def contract_headers() -> dict[str, str]:
    return {
        "X-Project-Key": "demo_proj",
        "X-Request-Id": "main-core-contract",
    }
