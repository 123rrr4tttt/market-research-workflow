from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(slots=True)
class PolicyDocument:
    state: str
    title: str
    status: str | None
    publish_date: date | None
    summary: str | None
    content: str
    uri: str | None = None
    source_name: str | None = None


class PolicyAdapter:
    """Base class for policy adapters."""

    def __init__(self, state: str):
        self.state = state

    def fetch_documents(self) -> Iterable[PolicyDocument]:
        raise NotImplementedError


