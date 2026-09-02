"""Nominal TEST_ONLY interpreter for pure C8 movement tests.

P4 ahead-of-time family-local scaffold: this module is the only place that
creates caller-visible test registries, witnesses and registration
capabilities.  Every value here subclasses ``TestOnlySealedValue`` so
production paths can reject it by nominal type.  No production authority
token, production registry constructor or positive production boolean lives
here or anywhere else in the pure package.
"""

from __future__ import annotations

from app.successor_runtime.capabilities.c8_common import (
    C8ProjectionError,
    CanonicalMaterialRead,
    GraphLossProfile,
    ReportVerification,
    TestOnlySealedValue,
    c8_canonical_digest,
    validate_canonical_material,
)

__all__ = [
    "TEST_ONLY_AUTHORITY_ID",
    "TestOnlyAuthority",
    "TestOnlyLossProfileCapability",
    "TestOnlyLossProfileRegistry",
    "TestOnlyLossWitness",
    "TestOnlyMaterialCapability",
    "TestOnlyMaterialIssuanceRegistry",
    "TestOnlyMaterialWitness",
    "TestOnlyVerificationWitness",
    "TestOnlyVerifierCapability",
    "TestOnlyVerifierRegistry",
]

TEST_ONLY_AUTHORITY_ID = "c8.test-only.v1"


class TestOnlyAuthority(TestOnlySealedValue):
    __slots__ = ("_secret", "authority_digest", "authority_id")

    def __init__(self) -> None:
        self.authority_id = TEST_ONLY_AUTHORITY_ID
        self.authority_digest = c8_canonical_digest({"authority_id": self.authority_id})
        self._secret = object()


def _authority() -> TestOnlyAuthority:
    return TestOnlyAuthority()


class _TestOnlyCapability:
    __test__ = False

    __slots__ = (
        "_secret",
        "authority_digest",
        "authority_id",
        "registry_digest",
        "registry_id",
    )

    def __init__(
        self,
        *,
        registry_id: str,
        registry_digest: str,
        authority_id: str,
        authority_digest: str,
        _secret: object,
    ) -> None:
        self.registry_id = registry_id
        self.registry_digest = registry_digest
        self.authority_id = authority_id
        self.authority_digest = authority_digest
        self._secret = _secret


class TestOnlyMaterialCapability(_TestOnlyCapability):
    pass


class TestOnlyVerifierCapability(_TestOnlyCapability):
    pass


class TestOnlyLossProfileCapability(_TestOnlyCapability):
    pass


class _TestOnlyWitness(TestOnlySealedValue):
    __test__ = False

    __slots__ = ("_secret",)

    def __init__(self, *, _secret: object) -> None:
        self._secret = _secret


class TestOnlyMaterialWitness(_TestOnlyWitness):
    __slots__ = ("attestation_digest", "material_identity")

    def __init__(
        self,
        *,
        material_identity: str,
        attestation_digest: str,
        _secret: object,
    ) -> None:
        super().__init__(_secret=_secret)
        self.material_identity = material_identity
        self.attestation_digest = attestation_digest


class TestOnlyVerificationWitness(_TestOnlyWitness):
    __slots__ = ("object_digest", "verification_id")

    def __init__(
        self,
        *,
        verification_id: str,
        object_digest: str,
        _secret: object,
    ) -> None:
        super().__init__(_secret=_secret)
        self.verification_id = verification_id
        self.object_digest = object_digest


class TestOnlyLossWitness(_TestOnlyWitness):
    __slots__ = ("profile_digest", "profile_id")

    def __init__(
        self,
        *,
        profile_id: str,
        profile_digest: str,
        _secret: object,
    ) -> None:
        super().__init__(_secret=_secret)
        self.profile_id = profile_id
        self.profile_digest = profile_digest


class _TestOnlyRegistry:
    def __init__(self, registry_prefix: str) -> None:
        self._authority = _authority()
        self.authority_id = self._authority.authority_id
        self.authority_digest = self._authority.authority_digest
        self.registry_id = f"{registry_prefix}.{self.authority_id}"
        self.registry_digest = c8_canonical_digest(
            {
                "registry_id": self.registry_id,
                "authority_id": self.authority_id,
                "authority_digest": self.authority_digest,
            }
        )

    def _capability(self, cls: type) -> object:
        return cls(
            registry_id=self.registry_id,
            registry_digest=self.registry_digest,
            authority_id=self.authority_id,
            authority_digest=self.authority_digest,
            _secret=self._authority._secret,
        )

    def _check_capability(self, capability: object) -> None:
        if capability._secret is not self._authority._secret:
            raise C8ProjectionError(
                "test-only registration capability is not authentic"
            )
        if (
            capability.registry_id != self.registry_id
            or capability.registry_digest != self.registry_digest
            or capability.authority_id != self.authority_id
            or capability.authority_digest != self.authority_digest
        ):
            raise C8ProjectionError(
                "test-only registration capability is not bound to this registry"
            )


class TestOnlyMaterialIssuanceRegistry(_TestOnlyRegistry):
    __test__ = False

    def __init__(self) -> None:
        super().__init__("c8.material-issuance")
        self._entries: dict[str, CanonicalMaterialRead] = {}
        self._witnesses: dict[str, TestOnlyMaterialWitness] = {}

    def authorize(self) -> TestOnlyMaterialCapability:
        return self._capability(TestOnlyMaterialCapability)

    def register(
        self,
        material: CanonicalMaterialRead,
        capability: TestOnlyMaterialCapability,
    ) -> TestOnlyMaterialWitness:
        self._check_capability(capability)
        validate_canonical_material(material)
        existing = self._entries.get(material.material_identity)
        if existing is not None:
            if existing != material:
                raise C8ProjectionError("material registry key rebinding rejected")
            return self._witnesses[material.material_identity]
        witness = TestOnlyMaterialWitness(
            material_identity=material.material_identity,
            attestation_digest=material.attestation_digest,
            _secret=self._authority._secret,
        )
        self._entries[material.material_identity] = material
        self._witnesses[material.material_identity] = witness
        return witness

    def resolve(self, material_identity: str) -> CanonicalMaterialRead | None:
        return self._entries.get(material_identity)


class TestOnlyVerifierRegistry(_TestOnlyRegistry):
    __test__ = False

    def __init__(self) -> None:
        super().__init__("c8.report-verifier")
        self._entries: dict[str, ReportVerification] = {}

    def authorize(self) -> TestOnlyVerifierCapability:
        return self._capability(TestOnlyVerifierCapability)

    def register(
        self,
        verification: ReportVerification,
        capability: TestOnlyVerifierCapability,
    ) -> TestOnlyVerificationWitness:
        self._check_capability(capability)
        if verification.state != "VERIFIED":
            raise C8ProjectionError("only verified report stages are registered")
        existing = self._entries.get(verification.verification_id)
        if existing is not None and existing != verification:
            raise C8ProjectionError("verifier registry key rebinding rejected")
        self._entries[verification.verification_id] = verification
        return TestOnlyVerificationWitness(
            verification_id=verification.verification_id,
            object_digest=verification.object_digest,
            _secret=self._authority._secret,
        )

    def resolve(self, verification_id: str) -> ReportVerification | None:
        return self._entries.get(verification_id)


class TestOnlyLossProfileRegistry(_TestOnlyRegistry):
    __test__ = False

    def __init__(self) -> None:
        super().__init__("c8.graph-loss-profile")
        self._entries: dict[str, GraphLossProfile] = {}

    def authorize(self) -> TestOnlyLossProfileCapability:
        return self._capability(TestOnlyLossProfileCapability)

    def register(
        self,
        profile: GraphLossProfile,
        capability: TestOnlyLossProfileCapability,
    ) -> TestOnlyLossWitness:
        self._check_capability(capability)
        existing = self._entries.get(profile.profile_id)
        if existing is not None and existing != profile:
            raise C8ProjectionError("loss profile registry key rebinding rejected")
        self._entries[profile.profile_id] = profile
        return TestOnlyLossWitness(
            profile_id=profile.profile_id,
            profile_digest=profile.profile_digest,
            _secret=self._authority._secret,
        )

    def resolve(self, profile_id: str) -> GraphLossProfile | None:
        return self._entries.get(profile_id)
