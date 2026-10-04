"""Effect ports for the C2.3 provider/credential boundary.

The port contracts live in ``source_library_c2_shared`` and are re-exported
here for consumers.  The P3 family-local line ships fixture and receipt-only
implementations only; no live provider, environment credential or network
interpreter is registered.
"""

from __future__ import annotations

from app.successor_runtime.capabilities import source_library_c2_shared as _shared

__all__ = [
    "CredentialResolverPort",
    "EphemeralCredentialLease",
    "ProviderCallTracer",
    "ProviderEffectGateway",
    "ProviderEffectPort",
    "ProviderReadbackPort",
    "RedactedCredentialRejection",
]

CredentialResolverPort = _shared.CredentialResolverPort
EphemeralCredentialLease = _shared.EphemeralCredentialLease
ProviderCallTracer = _shared.ProviderCallTracer
ProviderEffectGateway = _shared.ProviderEffectGateway
ProviderEffectPort = _shared.ProviderEffectPort
ProviderReadbackPort = _shared.ProviderReadbackPort
RedactedCredentialRejection = _shared.RedactedCredentialRejection
