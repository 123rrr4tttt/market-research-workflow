import unittest


CONTRACT_SCHEMA = {
    "required": ["status", "inserted", "degradation_flags", "rejection_breakdown"],
    "status_values": {"success", "degraded_success", "failed"},
}


def validate_contract(payload: dict) -> tuple[bool, str]:
    for key in CONTRACT_SCHEMA["required"]:
        if key not in payload:
            return False, f"missing:{key}"
    if payload["status"] not in CONTRACT_SCHEMA["status_values"]:
        return False, "invalid:status"
    if not isinstance(payload["degradation_flags"], list):
        return False, "invalid:degradation_flags"
    if not isinstance(payload["rejection_breakdown"], dict):
        return False, "invalid:rejection_breakdown"
    return True, "ok"


def inject_fault(base: dict, *, timeout=False, retry_exhausted=False, idempotent_duplicate=False) -> dict:
    payload = dict(base)
    flags = list(payload.get("degradation_flags") or [])
    breakdown = dict(payload.get("rejection_breakdown") or {})

    if timeout:
        flags.append("fetch_timeout")
        breakdown["timeout"] = breakdown.get("timeout", 0) + 1
    if retry_exhausted:
        flags.append("retry_exhausted")
        breakdown["retry"] = breakdown.get("retry", 0) + 1
    if idempotent_duplicate:
        flags.append("document_already_exists")
        breakdown["idempotent_duplicate"] = breakdown.get("idempotent_duplicate", 0) + 1

    payload["degradation_flags"] = sorted(set(flags))
    payload["rejection_breakdown"] = breakdown
    payload["status"] = "degraded_success" if payload["degradation_flags"] else payload.get("status", "success")
    return payload


class R81BContractFaultTests(unittest.TestCase):
    def test_contract_required_fields(self):
        payload = {
            "status": "success",
            "inserted": 1,
            "degradation_flags": [],
            "rejection_breakdown": {},
        }
        ok, reason = validate_contract(payload)
        self.assertTrue(ok, reason)

    def test_fault_injection_timeout_retry_idempotent(self):
        base = {
            "status": "success",
            "inserted": 1,
            "degradation_flags": [],
            "rejection_breakdown": {},
        }
        mutated = inject_fault(base, timeout=True, retry_exhausted=True, idempotent_duplicate=True)
        ok, reason = validate_contract(mutated)
        self.assertTrue(ok, reason)
        self.assertEqual(mutated["status"], "degraded_success")
        self.assertIn("fetch_timeout", mutated["degradation_flags"])
        self.assertIn("retry_exhausted", mutated["degradation_flags"])
        self.assertIn("document_already_exists", mutated["degradation_flags"])
        self.assertEqual(mutated["rejection_breakdown"]["timeout"], 1)
        self.assertEqual(mutated["rejection_breakdown"]["retry"], 1)
        self.assertEqual(mutated["rejection_breakdown"]["idempotent_duplicate"], 1)


if __name__ == "__main__":
    unittest.main()
