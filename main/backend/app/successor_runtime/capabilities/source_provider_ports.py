"""Effect ports for the C2.3 provider/credential boundary.

The port contracts live in ``source_library_c2_shared`` and are re-exported
here for consumers.  The P3 family-local line ships fixture and receipt-only
implementations only; no live provider, environment credential or network
interpreter is registered.
"""

from __future__ import annotations

from app.successor_runtime.capabilities import source_contracts as contracts

__all__ = [
    "CredentialResolverPort",
    "EphemeralCredentialLease",
    "ProviderCallTracer",
    "ProviderEffectGateway",
    "ProviderEffectPort",
    "ProviderReadbackPort",
    "RedactedCredentialRejection",
]

CredentialResolverPort = contracts.CredentialResolverPort
EphemeralCredentialLease = contracts.EphemeralCredentialLease
ProviderCallTracer = contracts.ProviderCallTracer
ProviderEffectGateway = contracts.ProviderEffectGateway
ProviderEffectPort = contracts.ProviderEffectPort
ProviderReadbackPort = contracts.ProviderReadbackPort
RedactedCredentialRejection = contracts.RedactedCredentialRejection
