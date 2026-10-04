from __future__ import annotations

import ast
import json
from pathlib import Path

from mrw_functorial_kit.core.c2_semantics import c2_shared_contract_failures


ROOT = Path(__file__).resolve().parents[1]
C2_SOURCE = ROOT / "main/backend/app/successor_runtime/capabilities/source_library_c2_shared.py"

LEGACY_OWNERS = {"VersionedWarning", "versioned_warning_from_legacy_string", "SourceRejection"}
SCOPE_OWNERS = {"project_scope_digest", "AuthenticatedProjectScope", "SourceExecutionRequest"}
CATALOG_OWNERS = {
    "ChannelCatalogEntry",
    "ChannelCatalogSnapshot",
    "SourceItemDefinition",
    "source_item_definition_from_dict",
    "SourceTaxonomy",
}
MODE_OWNERS = {
    "SourceMode",
    "NormalizedParamsSnapshot",
    "SourceModePlanningPayload",
    "OrderedFoldPolicy",
    "SourceModeTask",
    "SourceModePlan",
    "PlannedPlanning",
    "RejectedPlanning",
    "mode_for_kind",
    "kind_for_mode",
}
TERMINAL_OWNERS = {
    "SourceCollectionTerminal",
    "CollectionCompleted",
    "CollectionPartiallyCompleted",
    "CollectionProviderAccepted",
    "CollectionRejected",
    "CollectionFailed",
    "CollectionCancelled",
    "CollectionOutcomeUnknown",
    "OrderedFailure",
}
PROVIDER_OWNERS = {
    "ResourceCeiling",
    "CredentialRef",
    "ProviderResourcePolicy",
    "ProviderEffectRequest",
    "ProviderAttemptRef",
    "ProviderReceipt",
    "CapturedSourceRecordRef",
    "StagedArtifactRef",
    "CredentialDecisionReceipt",
    "AuthoritativeProviderReadback",
    "NonStartProof",
    "CancelReceipt",
    "CompletedProviderEffect",
    "AcceptedProviderEffect",
    "PartiallyCompletedProviderEffect",
    "RejectedProviderEffect",
    "FailedProviderEffect",
    "OrderedProviderFailure",
    "CancelledProviderEffect",
    "OutcomeUnknownProviderEffect",
    "ReconciledProviderEffect",
    "ProviderHandoff",
    "RedactedCredentialRejection",
}
def _owners_with_contract_rejections() -> set[str]:
    module = ast.parse(C2_SOURCE.read_text(encoding="utf-8"))
    owners: set[str] = set()
    for node in module.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "_reject_c2_contract"
            for child in ast.walk(node)
        ):
            owners.add(node.name)
    return owners


def test_INVARIANT__c2_failure_family_matches_registry() -> None:
    entries = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in entries}
    assert registered["c2.shared.contract_failure"] == c2_shared_contract_failures.codes


def test_INVARIANT__every_c2_constructor_failure_owner_is_classified() -> None:
    classified = (
        {"_validate_resolved_schema", "VersionedSchema", "_require_closed_code"}
        | LEGACY_OWNERS
        | SCOPE_OWNERS
        | CATALOG_OWNERS
        | MODE_OWNERS
        | TERMINAL_OWNERS
        | PROVIDER_OWNERS
    )
    assert _owners_with_contract_rejections() == classified


def test_INVARIANT__c2_failure_categories_are_closed_and_nonempty() -> None:
    expected = {
        "schema_contract_invalid",
        "digest_contract_invalid",
        "scope_contract_invalid",
        "catalog_contract_invalid",
        "mode_contract_invalid",
        "provider_effect_contract_invalid",
        "terminal_contract_invalid",
        "legacy_input_union_invalid",
    }
    assert set(c2_shared_contract_failures.codes) == expected
    for code in expected:
        assert c2_shared_contract_failures.matches(
            c2_shared_contract_failures.fail(code, "registered C2 contract failure")
        )
