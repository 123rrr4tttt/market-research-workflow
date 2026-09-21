"""Discovery application composition root."""

from __future__ import annotations

from ..services.discovery.adapters import DefaultDiscoveryAdapter
from ..services.discovery.application import DiscoveryApplicationService


def create_default_discovery_application() -> DiscoveryApplicationService:
    return DiscoveryApplicationService(adapter=DefaultDiscoveryAdapter())


__all__ = ["create_default_discovery_application"]
