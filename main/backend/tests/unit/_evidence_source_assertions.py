from __future__ import annotations

from collections.abc import Iterable
import unittest

from scripts.evidence_source_contract import EVIDENCE_SOURCE_UNAVAILABLE, NOT_LIVE


REQUIRED_SOURCE_FIELDS = {
    "path",
    "exists",
    "status",
    "failure_code",
    "execution_status",
    "authority",
    "closure_claim_allowed",
}


def assert_typed_evidence_unavailable(
    testcase: unittest.TestCase,
    contract: dict,
    *,
    expected_missing_paths: Iterable[str] = (),
) -> None:
    testcase.assertEqual(contract["status"], "failed")
    testcase.assertEqual(contract["execution_status"], NOT_LIVE)
    testcase.assertEqual(contract["authority"], "non_authoritative")
    testcase.assertEqual(contract["failure_codes"], [EVIDENCE_SOURCE_UNAVAILABLE])
    testcase.assertFalse(contract["closure_claim_allowed"])

    sources = contract["evidence_sources"]
    unavailable = [
        row
        for row in sources
        if row.get("failure_code") == EVIDENCE_SOURCE_UNAVAILABLE
    ]
    testcase.assertTrue(unavailable)
    for row in sources:
        testcase.assertTrue(REQUIRED_SOURCE_FIELDS.issubset(row))
        testcase.assertEqual(row["execution_status"], NOT_LIVE)
        testcase.assertEqual(row["authority"], "non_authoritative")
        testcase.assertFalse(row["closure_claim_allowed"])
    for path in expected_missing_paths:
        testcase.assertTrue(
            any(row["path"] == path and row["exists"] is False for row in unavailable),
            path,
        )
    testcase.assertTrue(
        any(EVIDENCE_SOURCE_UNAVAILABLE in failure for failure in contract["failures"])
    )
