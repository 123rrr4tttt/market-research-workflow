"""S2c ops-domain typed read-only/control-plane surfaces.

Every module in this package is a pure successor surface.  It records typed
readback/control decisions only and never performs a runtime effect.
"""

from .base import AUTHORITY_KEYS, authority_ceiling, require_authority_false

__all__ = [
    "AUTHORITY_KEYS",
    "authority_ceiling",
    "require_authority_false",
]
