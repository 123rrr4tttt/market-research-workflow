from __future__ import annotations

import unittest
from typing import Annotated, get_args, get_origin, get_type_hints

from scripts.check_ingest_long_cycle_scheduler_queue_handoff_replay_contract import build_check


class IngestLongCycleQueueHandoffAuthorityTest(unittest.TestCase):
    def test_ingest_long_cycle_scheduler_queue_handoff_authority_metadata(self) -> None:
        return_hint = get_type_hints(build_check, include_extras=True)["return"]
        self.assertIs(get_origin(return_hint), Annotated)
        metadata = get_args(return_hint)[1]
        self.assertEqual(
            metadata,
            "kit:prepared-command effect_boundary=temporary_sqlite.long_cycle_repository "
            "witness=test:test_ingest_long_cycle_scheduler_queue_handoff_authority_metadata",
        )


if __name__ == "__main__":
    unittest.main()
