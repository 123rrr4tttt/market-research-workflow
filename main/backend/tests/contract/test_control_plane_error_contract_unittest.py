from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract


class ControlPlaneErrorContractTestCase(unittest.TestCase):
    def _build_app(self):
        try:
            from fastapi import FastAPI
            from app.api.config import router as config_router
            from app.api.dashboard import router as dashboard_router
            from app.api.llm_config import router as llm_config_router
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import routers for control-plane contract test: {exc}")
        app = FastAPI()
        app.include_router(config_router, prefix="/api/v1")
        app.include_router(dashboard_router, prefix="/api/v1")
        app.include_router(llm_config_router, prefix="/api/v1")
        return app

    def test_config_env_empty_payload_returns_structured_invalid_input(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        response = client.post("/api/v1/config/env", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("没有需要更新的字段", payload["detail"]["error"]["message"])

    def test_config_env_read_failure_returns_structured_internal_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.config.load_env_settings", side_effect=RuntimeError("env file unreadable")):
            response = client.get("/api/v1/config/env")

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)

    def test_config_reload_failure_returns_structured_internal_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.config.reload_settings", side_effect=RuntimeError("reload failed")):
            response = client.post("/api/v1/config/reload")

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)

    def test_dashboard_stats_runtime_failure_returns_structured_internal_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())

        class _BoomSessionLocal:
            def __enter__(self):
                raise RuntimeError("boom")

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("app.api.dashboard.SessionLocal", return_value=_BoomSessionLocal()):
            response = client.get("/api/v1/dashboard/stats")

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertIn("获取统计数据失败", payload["detail"]["error"]["message"])

    def test_llm_config_service_not_found_returns_structured_not_found(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())

        app = client.app
        app.dependency_overrides = {}
        app.dependency_overrides.__setitem__(
            __import__("app.api.llm_config", fromlist=["get_db"]).get_db,
            lambda: Mock(),
        )
        with patch("app.api.llm_config.llm_config_service.get_config", return_value=None):
            response = client.get("/api/v1/llm-config/service/missing")
        app.dependency_overrides = {}

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertIn("服务配置 'missing' 不存在", payload["detail"]["error"]["message"])

    def test_llm_config_create_duplicate_returns_structured_invalid_input(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())

        fake_db = Mock()
        app = client.app
        app.dependency_overrides = {}
        app.dependency_overrides.__setitem__(
            __import__("app.api.llm_config", fromlist=["get_db"]).get_db,
            lambda: fake_db,
        )
        with patch(
            "app.api.llm_config.llm_config_service.get_config",
            return_value=SimpleNamespace(service_name="svc"),
        ):
            response = client.post("/api/v1/llm-config", json={"service_name": "svc", "enabled": True})
        app.dependency_overrides = {}

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("服务配置 'svc' 已存在", payload["detail"]["error"]["message"])

    def test_llm_config_copy_from_same_project_returns_structured_invalid_input(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.llm_config._assert_project_exists", side_effect=lambda project_key: project_key):
            response = client.post(
                "/api/v1/llm-config/projects/demo_proj/copy-from",
                json={"source_project_key": "demo_proj", "overwrite": False},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)

    def test_llm_config_copy_from_missing_project_returns_structured_not_found(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch("app.api.llm_config._assert_project_exists", side_effect=HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "项目不存在"}})):
            response = client.post(
                "/api/v1/llm-config/projects/demo_proj/copy-from",
                json={"source_project_key": "missing_proj", "overwrite": False},
            )

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)


if __name__ == "__main__":
    unittest.main()
