from __future__ import annotations

import pytest

from app.composition.ingest import configure_ingest_adapters
from app.services.ingest import provider_ports


def test_FAILURE_PRESERVED__unconfigured_provider_fails_closed() -> None:
    original = provider_ports._POLICY_ADAPTER_RESOLVER
    provider_ports._POLICY_ADAPTER_RESOLVER = None
    try:
        with pytest.raises(RuntimeError, match="policy adapter provider is not configured"):
            provider_ports.get_policy_adapter("CA")
    finally:
        provider_ports._POLICY_ADAPTER_RESOLVER = original


def test_INVARIANT__composition_registers_ingest_providers() -> None:
    configure_ingest_adapters()
    assert provider_ports._POLICY_ADAPTER_RESOLVER is not None
    assert provider_ports._REDDIT_ADAPTER_FACTORY is not None
    assert provider_ports._GOOGLE_NEWS_ADAPTER_FACTORY is not None


def test_INVARIANT__policy_provider_preserves_legiscan_and_error_routes() -> None:
    configure_ingest_adapters()
    provider = provider_ports._POLICY_ADAPTER_RESOLVER
    assert provider is not None
    assert provider("CA", None).state == "CA"
    with pytest.raises(RuntimeError, match="LEGISCAN_API_KEY"):
        provider("CA", "legiscan")
    with pytest.raises(ValueError, match="暂无州 NY"):
        provider("NY", None)
