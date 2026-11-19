from __future__ import annotations

import pytest
from app.services.resource_pool.auto_classify import classify_site_entries_batch

pytestmark = pytest.mark.unit


def test_batch_preserves_row_identity_and_marks_unknown_entries_unvalidated() -> None:
    rows = [
        {"index": 7, "site_url": "https://example.test/feed.xml"},
        {"index": 2, "site_url": "https://example.test/about"},
    ]
    known, unknown = classify_site_entries_batch(rows)

    assert [known["index"], unknown["index"]] == [7, 2]
    assert "source" not in rows[0]
    assert known["channel_key"] == "generic_web.rss"
    assert known["source"] == "rule"
    assert known["capabilities"]["keyword_mode"] == "filter"
    assert unknown["channel_key"] == "url_pool"
    assert unknown["source"] == "fallback"
    assert unknown["validated"] is False
    assert unknown["capabilities"]["supports_query_terms"] is False
