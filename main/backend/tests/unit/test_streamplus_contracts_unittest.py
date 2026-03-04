import unittest

from app.api.source_library import _normalize_source_item_capability
from app.services.resource_pool.url_utils import normalize_url
from app.services.streamplus.contracts import (
    SOURCE_ITEM_CAPABILITY_DEFAULT,
    build_idempotency_key,
    canonicalize_url,
)


class StreamplusContractsTests(unittest.TestCase):
    def test_normalize_url_drops_tracking_and_fragment(self):
        raw = "https://Example.com/path/?utm_source=x&b=2&a=1#frag"
        self.assertEqual(canonicalize_url(raw), "https://example.com/path?a=1&b=2")
        self.assertEqual(normalize_url(raw), "https://example.com/path?a=1&b=2")

    def test_source_item_capability_defaults(self):
        capability = dict(SOURCE_ITEM_CAPABILITY_DEFAULT)
        self.assertEqual(capability["rate_limit_class"], "normal")
        self.assertTrue(capability["supports_incremental"])
        self.assertFalse(capability["supports_backfill"])

    def test_normalize_source_item_capability_defaults(self):
        extra = _normalize_source_item_capability({"foo": 1})
        capability = extra["capability"]
        self.assertEqual(capability["rate_limit_class"], "normal")
        self.assertTrue(capability["supports_incremental"])
        self.assertFalse(capability["supports_backfill"])

    def test_idempotency_key_stable(self):
        k1 = build_idempotency_key(canonical_url="https://example.com/a", content_hash="abc", scope="project")
        k2 = build_idempotency_key(canonical_url="https://example.com/a", content_hash="ABC", scope="PROJECT")
        self.assertEqual(k1, k2)


if __name__ == "__main__":
    unittest.main()
