from __future__ import annotations

import urllib.request
from unittest.mock import Mock

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.mocked]


def fetch_json(url: str) -> tuple[int, str]:
    """Tiny demo function that depends on external HTTP."""
    with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
        body = response.read().decode("utf-8")
        return response.status, body


def test_fetch_json_mocks_external_http_with_monkeypatch(monkeypatch: pytest.MonkeyPatch):
    fake_response = Mock()
    fake_response.status = 200
    fake_response.read.return_value = b'{"ok": true}'

    fake_context_manager = Mock()
    fake_context_manager.__enter__ = Mock(return_value=fake_response)
    fake_context_manager.__exit__ = Mock(return_value=False)

    fake_urlopen = Mock(return_value=fake_context_manager)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status, body = fetch_json("https://api.example.com/health")

    assert status == 200
    assert body == '{"ok": true}'
    fake_urlopen.assert_called_once_with("https://api.example.com/health", timeout=2)
