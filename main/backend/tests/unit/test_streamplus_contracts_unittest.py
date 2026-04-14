import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


contracts = _load_module("streamplus_contracts", "app/services/streamplus/contracts.py")
url_utils = _load_module("url_utils", "app/services/resource_pool/url_utils.py")
gate_reason_codes = _load_module("gate_reason_codes", "app/services/ingest/gate_reason_codes.py")


class StreamplusContractsTests(unittest.TestCase):
    def test_normalize_url_drops_tracking_and_fragment(self):
        raw = "https://Example.com/path/?utm_source=x&b=2&a=1#frag"
        self.assertEqual(url_utils.normalize_url(raw), "https://example.com/path?a=1&b=2")

    def test_source_item_capability_defaults_contract(self):
        self.assertEqual(contracts.SOURCE_ITEM_CAPABILITY_DEFAULT["rate_limit_class"], "normal")
        self.assertTrue(contracts.SOURCE_ITEM_CAPABILITY_DEFAULT["supports_incremental"])
        self.assertFalse(contracts.SOURCE_ITEM_CAPABILITY_DEFAULT["supports_backfill"])

    def test_reason_code_alias_and_category(self):
        self.assertEqual(gate_reason_codes.normalize_reason_code("http_429"), "rate_limited")
        self.assertEqual(gate_reason_codes.reason_category("http_429"), "policy")

    def test_idempotency_key_stable(self):
        k1 = contracts.build_idempotency_key(canonical_url="https://example.com/a", content_hash="abc", scope="project")
        k2 = contracts.build_idempotency_key(canonical_url="https://example.com/a", content_hash="ABC", scope="PROJECT")
        self.assertEqual(k1, k2)


if __name__ == "__main__":
    unittest.main()
