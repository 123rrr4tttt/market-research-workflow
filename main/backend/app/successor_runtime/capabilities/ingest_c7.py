"""C7 family-owned capability facade.

The canonical C7 contracts and pure staging vocabulary live in
``ingest_c7_common`` so sibling C7 capability modules share one DTO identity
without importing each other's implementation modules.  This facade re-exports
the family-common surface for adapters, tests and the evidence generator.

P4 C7 scaffolding only.  No network, database, provider, index, graph,
credential or canonical write work is performed here.
"""

from __future__ import annotations

from app.successor_runtime.capabilities import ingest_c7_common as _common
from app.successor_runtime.capabilities.ingest_c7_common import *

__all__ = list(_common.__all__)
