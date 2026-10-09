from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.services.resource_pool import auto_classify

pytestmark = pytest.mark.unit


def test_raw_batch_index_rejects_and_malformed_llm_index_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_classify, "_llm_available", lambda: True)
    monkeypatch.setattr(auto_classify, "get_llm_config", lambda _name: None)
    assert auto_classify._integer(memoryview(b"12")) == 12
    assert not auto_classify._is_string_object_dict({1: "not-a-json-row"})

    for invalid_index in ("bad", object()):
        native_error: TypeError | ValueError
        try:
            int(invalid_index)
        except (TypeError, ValueError) as exc:
            native_error = exc
        else:
            raise AssertionError("test input must fail native int conversion")

        with pytest.raises(type(native_error)) as raised:
            auto_classify._llm_classify_batch(
                [{"index": invalid_index, "site_url": "https://example.test"}]
            )
        assert str(raised.value) == str(native_error)
        assert isinstance(raised.value.__cause__, type(native_error))
        assert str(raised.value.__cause__) == str(native_error)

    model = SimpleNamespace(
        invoke=lambda _prompt: SimpleNamespace(
            content=(
                '{"items":['
                '{"index":"bad","entry_type":"domain_root","channel_key":"url_pool"},'
                '{"index":0,"entry_type":"domain_root","channel_key":"url_pool"}'
                "]}"
            )
        )
    )
    monkeypatch.setattr(auto_classify, "get_chat_model", lambda **_kwargs: model)

    result = auto_classify._llm_classify_batch(
        [{"index": 0, "site_url": "https://example.test"}]
    )

    assert list(result) == [0]
