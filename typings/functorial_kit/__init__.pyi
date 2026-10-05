from .arch import CONFIG_VERSION, Declarations, GateName, KitConfig, ProjectScan, Ratchet, Registries, ScanInput, SourceFile, Violation, architecture_gate_tests, collect_declarations, config_failures, gate_names, parse_config, ratchet, scan_architecture, scan_project, violation_key
from .contributions import ComposedContributions, Contribution, ContributionCatalog, ContributionCodec, ContributionObject, ContributionRegistries, ContributionSketch, ContributionSpec, compose_contributions, contribution_failures, define_contribution
from .core import (
    Anchor,
    AuthoritativeWriteReturn,
    CanonicalReadReturn,
    Codec,
    Completeness,
    DerivedKind,
    Drift,
    Failure,
    FailureError,
    FailureFamily,
    NonAuthoritative,
    NonAuthoritativeDict,
    NonAuthoritativeReturn,
    PreparedCommandReturn,
    REGISTRY_VERSIONS,
    Registry,
    RegistryKind,
    Vocabulary,
    anchor_of,
    canonicalize,
    code_unit_key,
    codec_failures,
    completeness,
    define_codec,
    define_failure_family,
    define_vocabulary,
    derived,
    derived_kinds,
    digest_of,
    drift_of,
    fold_failures,
    fold_ordered,
    is_failure,
    is_non_authoritative,
    parse_registry,
    registry_failures,
    registry_kinds,
    sha256_hex,
)
from .core import __all__ as _core_all
from .example import Counter, InMemoryCounter, KitExample, Nested, kit_example_codec
from .contribution_compiler import NativeContributionRule, compile_native_contribution
from .contribution_verification import ContributionVerification, VerificationBlockedError, VerificationChanges, VerificationCheck, VerificationPlan, VerificationPrerequisite, VerificationRegistration, VerificationSource, plan_contribution_verification, register_verification_plan
from .law_witness import LawWitness, LawWitnessIssueCode, LawWitnessRegistration, define_law_witness, law_witness_failures, law_witness_reference, register_law_witnesses
from .native_contribution import BindingAccepted, BindingRejected, NativeBindingIssue, NativeContribution, NativeContributionSpec, ProjectedContributionSpec, define_native_contribution
from .sketch import SKETCHES_VERSION, SketchIssue, change_kinds, claim_classes, shapes, validate_sketches
from .laws import Deviation, FailureLaw, FoldSpec, Idempotent, Ordered, PortLawSpec, anchor_laws, codec_laws, fold_laws, port_laws, vector_laws

"""functorial-kit: core primitives, law-suite templates, architecture gates, and scaffold."""
__all__ = [*_core_all, "define_contribution", "contribution_failures", "compose_contributions", "ContributionSpec", "ContributionSketch", "ContributionRegistries", "ContributionObject", "ContributionCatalog", "ContributionCodec", "Contribution", "ComposedContributions", "BindingAccepted", "BindingRejected", "NativeBindingIssue", "NativeContribution", "NativeContributionSpec", "ProjectedContributionSpec", "define_native_contribution", "NativeContributionRule", "compile_native_contribution", "ContributionVerification", "VerificationBlockedError", "VerificationChanges", "VerificationCheck", "VerificationPlan", "VerificationPrerequisite", "VerificationRegistration", "VerificationSource", "plan_contribution_verification", "register_verification_plan", "LawWitness", "LawWitnessIssueCode", "LawWitnessRegistration", "define_law_witness", "law_witness_failures", "law_witness_reference", "register_law_witnesses", "CONFIG_VERSION", "Counter", "Declarations", "Deviation", "FailureLaw", "FoldSpec", "GateName", "Idempotent", "InMemoryCounter", "KitConfig", "KitExample", "Nested", "Ordered", "PortLawSpec", "ProjectScan", "Ratchet", "Registries", "SKETCHES_VERSION", "ScanInput", "SketchIssue", "SourceFile", "Violation", "anchor_laws", "architecture_gate_tests", "change_kinds", "claim_classes", "codec_laws", "collect_declarations", "config_failures", "fold_laws", "gate_names", "kit_example_codec", "parse_config", "port_laws", "ratchet", "scan_architecture", "scan_project", "shapes", "validate_sketches", "vector_laws", "violation_key"]
