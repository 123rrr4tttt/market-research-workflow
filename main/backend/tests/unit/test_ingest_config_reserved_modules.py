from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402

from app.api.ingest import (  # noqa: E402
    IngestConfigUpsertPayload,
    post_ingest_config_endpoint,
)
from app.services.ingest_config import service as ingest_config_service  # noqa: E402


class IngestConfigReservedModuleTests(unittest.TestCase):
    def test_platform_modules_upsert_is_rejected_before_database(self) -> None:
        session = MagicMock()
        session.execute.side_effect = AssertionError("database must not be read")
        session_factory = MagicMock()
        session_factory.return_value.__enter__.return_value = session

        with (
            patch.object(ingest_config_service, "SessionLocal", session_factory),
            patch.object(ingest_config_service, "bind_schema"),
            self.assertRaisesRegex(ValueError, "module selection CAS owner"),
        ):
            ingest_config_service.upsert_config(
                "project",
                "platform.modules",
                "module_selection",
                payload={"selection_revision": 1},
            )
        session_factory.assert_not_called()

    def test_other_config_key_keeps_original_upsert_behavior(self) -> None:
        existing = MagicMock()
        existing.project_key = "project"
        existing.config_key = "social_forum"
        existing.config_type = "social_forum"
        existing.payload = {"k": "v"}
        existing.created_at = None
        existing.updated_at = None
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = existing
        session_factory = MagicMock()
        session_factory.return_value.__enter__.return_value = session

        with (
            patch.object(ingest_config_service, "SessionLocal", session_factory),
            patch.object(ingest_config_service, "bind_schema"),
        ):
            saved = ingest_config_service.upsert_config(
                "project",
                "social_forum",
                "social_forum",
                payload={"k": "v"},
            )

        self.assertEqual(existing.config_type, "social_forum")
        self.assertEqual(existing.payload, {"k": "v"})
        session.add.assert_not_called()
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(existing)
        self.assertEqual(saved["config_key"], "social_forum")
        self.assertEqual(saved["payload"], {"k": "v"})

    def test_reserved_module_rejection_maps_to_invalid_input(self) -> None:
        body = IngestConfigUpsertPayload(
            project_key="project",
            config_key="platform.modules",
            config_type="module_selection",
            payload={"selection_revision": 1},
        )
        with self.assertRaises(HTTPException) as caught:
            post_ingest_config_endpoint(body)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(
            caught.exception.detail["error"]["code"],
            "INVALID_INPUT",
        )


if __name__ == "__main__":
    unittest.main()
