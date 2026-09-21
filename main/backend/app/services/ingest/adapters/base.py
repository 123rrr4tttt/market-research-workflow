from __future__ import annotations

from collections.abc import Iterable

from ..provider_ports import PolicyDocument

class PolicyAdapter:
    """Base class for policy adapters."""

    def __init__(self, state: str):
        self.state = state

    def fetch_documents(self) -> Iterable[PolicyDocument]:
        raise NotImplementedError

