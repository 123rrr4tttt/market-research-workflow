"""P2 C2.1 contract/digest/codec/program/taxonomy/precedence contracts."""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.source_resolution import (
    RESOURCE_CEILING,
    SOURCE_EXECUTION_REQUEST_SCHEMA,
    SOURCE_ITEM_DEFINITION_SCHEMA,
    SOURCE_RESOLUTION_KIND,
    SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA,
    SOURCE_RESOLUTION_OWNER,
    SOURCE_MODE_SCHEMA,
    SOURCE_REJECTION_SCHEMA,
    SOURCE_RESOLUTION_OBSERVATION_SCHEMA,
    SOURCE_TAXONOMY_SCHEMA,
    SOURCE_WARNING_SCHEMA,
    AuthenticatedProjectScope,
    ChannelCatalogSnapshot,
    NormalizedParamsSnapshot,
    RejectedResolution,
    SourceResolutionPayload,
    build_source_resolution_bundle,
    build_source_resolution_catalog,
    build_source_resolution_registry,
    deployment_catalog_digest,
    decode_historical_source_resolution_payload,
    payload_from_dicts,
    project_scope_digest,
    resource_ceiling_digest,
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_resolution_interpreters import (
    normalize_item_taxonomy_dict,
    resolve_source_execution_request,
)
from app.successor_runtime.capabilities.source_resolution_program import (
    build_source_resolution_program,
    compile_source_resolution_program,
)
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.program import Atom, decode_program_spec

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = project_scope_digest(PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION)
ITEM_REVISION = 3
ITEM_INCARNATION = "item-inc-3"
DEPLOYMENT_CATALOG_DIGEST = deployment_catalog_digest()

_SHARED_ROOT_RELATIVES = (
    "language/program.py",
    "language/compile.py",
    "language/plan.py",
    "runtime/reducer.py",
    "runtime/transitions.py",
    "runtime/assignments.py",
    "runtime/work_items.py",
)
_SHARED_ROOT_BASELINE = {
    "language/program.py": ("eba5147e44ada7ee264606cb64347132b902d86beebba14b9b9a1c3bb6f01e02"),
    # P3 locality rebind changed the reviewed shared compile/plan bytes after
    # the P0 baseline; packet v4 bound the new authoritative locality hashes.
    # This P2 contract baseline is corrected to the current reviewed shared
    # roots (compile=91b063..., plan=a8f5ab...), invalidating packet v3/v4
    # source-byte baselines until the additive v5 packet.
    "language/compile.py": ("91b06329b8476d06193e8030746288be5550f065b6f471b81dce650608d61dd5"),
    "language/plan.py": ("a8f5ab8ccc38c56ebfb67b6b7a1b36132bf45e132014f6d2a2ed0ee3ba7cfb82"),
    "runtime/reducer.py": ("0462576d08ec7748aaf96fabf739707ca44b3b6a4a9c1f85f52574122af31856"),
    "runtime/transitions.py": ("5fca6cda9ec554e660ea615ec32a848d819d7be48dc2a32ef5481f4bd5a88b4b"),
    "runtime/assignments.py": ("5cf914fbb3c49bc00f929ab184c5c5014f8013a6526af57e3283a12a8b8ca0b0"),
    "runtime/work_items.py": ("5acf8ecdfc4c85aec16af6798f7ea24053b7b77a3ab49187a6a3387a4c5d75f2"),
}

# Additive candidate witness for the current worktree. The historical
# baseline remains authoritative for the original packet; this candidate is
# accepted only with its explicit non-authoritative witness and exact bytes.
_SHARED_ROOT_CANDIDATE = {
    "language/program.py": "d6cafde456556d97a0432064accdaaad6f8a8d7030bb7b27bcd31c0d69a93639",
    "language/compile.py": "7ded4fd0a05765cccac5aee262ce0d94267c7d9e71ff0d08869e03374c7aae2c",
    "language/plan.py": "33219cf74d2113e91cd17b58c0878bbb3089db012c79f8c60cdefa16e5b22530",
    "runtime/reducer.py": "cea068c447de63f7106df8694b3acb7cec32effc9d88415abfaa3d957a14d928",
    "runtime/transitions.py": "87a1f2fc993d2f143b4f31df786e45c3ded48081349f35fa8ed25ec81cc1bbaa",
    "runtime/assignments.py": "ad1ac001d946b0de892cc28d0aa6f88df5cc84fe8608f3d12973a2e22ef927b6",
    "runtime/work_items.py": "2570926ac90b2c3d4008028c1328d7f44890fd521c42cc54de76142aae2abff6",
}
_SHARED_ROOT_CANDIDATE_WITNESS = {
    "schema": "mrw.successor_runtime.shared_root_rebind.v1",
    "candidate_id": "simp04-program-atoms-2026-10-03",
    "disposition": "CANDIDATE_NOT_AUTHORITY",
    "reason": "current shared-root bytes include the SIMP-04 static source-order program_atoms traversal",
    "requires": "independent exact-byte review before any authority claim",
    "candidate_state_digest": "a94c2562d290843ff607738f7d8dea17e1866769a8332a94fa1e0509263aa7f3",
}
_SHARED_ROOT_CANDIDATE_WITNESS_DIGEST = "bec1a4516386878fe5fb231ff17e8e4edede0aabf6e42c49263f2691a40df5d0"


def _bundle():
    return build_source_resolution_bundle()


def _catalog():
    return build_source_resolution_catalog(_bundle())


def _registry():
    return build_source_resolution_registry(_bundle())


def _channels():
    return [
        {
            "channel_key": "handler.cluster",
            "provider_type": "native",
            "enabled": True,
        },
        {
            "channel_key": "generic_web.search_template",
            "provider": "generic_web",
            "provider_type": "native",
            "enabled": True,
        },
        {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "enabled": True,
        },
        {"channel_key": "market.default", "provider_type": "native", "enabled": True},
    ]


def _item(**overrides):
    values = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 9},
        "extra": {
            "stable_handler_cluster": True,
            "expected_entry_type": "search_template",
        },
        "revision": ITEM_REVISION,
        "incarnation": ITEM_INCARNATION,
    }
    values.update(overrides)
    values.setdefault("content_digest", source_item_definition_content_digest(values))
    return values


def _payload(**overrides):
    values = {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": RESOLVED_SCHEMA,
        "scope_incarnation": SCOPE_INCARNATION,
        "scope_digest": SCOPE_DIGEST,
        "channels": _channels(),
        "item": _item(),
        "params": {
            "query_terms": ["x"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    }
    values.update(overrides)
    if "item" in overrides:
        values["item"] = _item(**overrides["item"])
    return payload_from_dicts(**values)


def _program(payload):
    return build_source_resolution_program(
        payload=payload,
        catalog=_catalog(),
        program_id="c2-1.contracts.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )


def _plan(program):
    return compile_source_resolution_program(program, _catalog(), operation_contracts=_registry())


def _shared_state(root: Path) -> dict[str, object]:
    return {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in _SHARED_ROOT_RELATIVES}


def _accepted_shared_state(current: dict[str, str]) -> dict[str, str]:
    if current == _SHARED_ROOT_BASELINE:
        return _SHARED_ROOT_BASELINE
    witness_digest = hashlib.sha256(
        json.dumps(
            _SHARED_ROOT_CANDIDATE_WITNESS,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    assert witness_digest == _SHARED_ROOT_CANDIDATE_WITNESS_DIGEST
    candidate_digest = hashlib.sha256(
        json.dumps(
            _SHARED_ROOT_CANDIDATE,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    assert candidate_digest == _SHARED_ROOT_CANDIDATE_WITNESS["candidate_state_digest"]
    assert current == _SHARED_ROOT_CANDIDATE, current
    return _SHARED_ROOT_CANDIDATE


def test_operation_kind_owner_and_catalog_are_exact() -> None:
    bundle = _bundle()
    catalog = _catalog()
    registry = _registry()
    contract = bundle.operation
    assert SOURCE_RESOLUTION_KIND == "source_library.resolve_execution_request.v1"
    assert contract.owner_capability_id == SOURCE_RESOLUTION_OWNER
    assert contract.ref.kind == SOURCE_RESOLUTION_KIND
    assert contract.ref.contract_version == "1.0.0"
    assert catalog.lookup(SOURCE_RESOLUTION_KIND) == contract.ref
    assert registry.resolve_required(contract.ref).ref == contract.ref
    assert contract.effect_profile_ref.profile_id == ("mrw.source.resolve-execution-request.effect.v2")
    assert contract.authority_profile_ref.profile_id == ("mrw.source.resolve-execution-request.authority.v2")
    observation_profile = bundle.profiles["observation"]
    for dimension in (
        "project_scope",
        "item_revision",
        "item_incarnation",
        "item_content_digest",
        "catalog_revision",
        "catalog_incarnation",
        "catalog_digest",
    ):
        assert dimension in observation_profile.dimensions
    failure_profile = bundle.profiles["failure"]
    assert "RESOURCE_CEILING_EXCEEDED" in failure_profile.typed_failures


def test_deployment_catalog_digest_is_distinct_from_operation_catalog() -> None:
    catalog = _catalog()
    assert DEPLOYMENT_CATALOG_DIGEST != catalog.catalog_digest
    assert DEPLOYMENT_CATALOG_DIGEST == deployment_catalog_digest()
    assert DEPLOYMENT_CATALOG_DIGEST == ("b3a7be980b359fedc3844fd12767f2b7e6631e3d1546683b9da16dcb2b009a83")


def test_payload_codec_round_trip_and_extra_field_reject() -> None:
    bundle = _bundle()
    payload = _payload()
    codec = bundle.payload_codec()
    encoded = codec.encode_payload(payload)
    decoded = codec.decode_payload(encoded)
    assert decoded == payload
    assert decoded.payload_digest == payload.payload_digest

    with_extra = dict(encoded)
    with_extra["unexpected_field"] = "must-reject"
    with pytest.raises(ValueError, match="extra"):
        codec.decode_payload(with_extra)

    with_missing = {key: value for key, value in encoded.items() if key != "item"}
    with pytest.raises(ValueError, match="missing"):
        codec.decode_payload(with_missing)


def test_payload_and_catalog_digests_fail_closed() -> None:
    payload = _payload()
    with pytest.raises(ValueError, match="payload_digest"):
        SourceResolutionPayload(
            schema_version=payload.schema_version,
            operation_kind=payload.operation_kind,
            project_scope=payload.project_scope,
            catalog=payload.catalog,
            item=payload.item,
            params=freeze_json_object({"query_terms": ["tampered"]}),
            payload_digest=payload.payload_digest,
        )
    with pytest.raises(ValueError, match="digest"):
        ChannelCatalogSnapshot(
            schema_version=payload.catalog.schema_version,
            revision=payload.catalog.revision,
            incarnation=payload.catalog.incarnation,
            digest="2" * 64,
            entries=payload.catalog.entries,
        )
    with pytest.raises(ValueError, match="scope_digest"):
        AuthenticatedProjectScope(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            incarnation=SCOPE_INCARNATION,
            scope_digest="not-a-digest",
        )
    with pytest.raises(ValueError, match="scope_digest"):
        AuthenticatedProjectScope(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            incarnation=SCOPE_INCARNATION,
            scope_digest="2" * 64,
        )


def test_scope_digest_matches_canonical_compute_scope_digest_and_rejects_aba() -> None:
    from app.successor_runtime.substrate.postgres.session import (
        compute_scope_digest,
    )

    expected = compute_scope_digest(
        PROJECT_KEY,
        RESOLVED_SCHEMA,
        REGISTRY_REVISION,
        SCOPE_INCARNATION,
    )
    assert project_scope_digest(PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION) == expected
    scope = AuthenticatedProjectScope(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        incarnation=SCOPE_INCARNATION,
        scope_digest="",
    )
    assert scope.scope_digest == expected
    payload = _payload(scope_digest=expected)
    assert payload.project_scope.scope_digest == expected

    with pytest.raises(ValueError, match="scope_digest"):
        AuthenticatedProjectScope(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            incarnation="scope-inc-other",
            scope_digest=expected,
        )


def test_item_identity_is_required_and_digest_verified() -> None:
    incomplete = _item()
    del incomplete["content_digest"]
    with pytest.raises(ValueError, match="content_digest"):
        payload_from_dicts(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            scope_incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
            channels=_channels(),
            item=incomplete,
            params={"query_terms": ["x"]},
        )
    tampered = _item(content_digest="2" * 64)
    with pytest.raises(ValueError, match="content_digest"):
        _payload(item=tampered)
    payload = _payload()
    assert payload.item.revision == ITEM_REVISION
    assert payload.item.incarnation == ITEM_INCARNATION
    assert payload.item.content_digest == source_item_definition_content_digest(_item())


def test_historical_payload_requires_explicit_decoder_and_preserves_identity() -> None:
    historical = dataclasses.replace(
        _payload(),
        schema_version=SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA,
        payload_digest="",
    )
    encoded = _bundle().payload_codec().encode_payload(historical)
    with pytest.raises(ValueError, match="historical resolution payload"):
        _bundle().payload_codec().decode_payload(encoded)
    decoded = decode_historical_source_resolution_payload(encoded)
    assert _bundle().payload_codec().encode_payload(decoded) == encoded
    assert decoded.payload_digest == historical.payload_digest

    wrong_version = dict(encoded)
    wrong_version["schema_version"] = "mrw.source.unknown.v9"
    with pytest.raises(ValueError, match="exact C2 payload schema"):
        decode_historical_source_resolution_payload(wrong_version)


def test_versioned_schema_maps_are_pinned() -> None:
    pinned = {
        SOURCE_ITEM_DEFINITION_SCHEMA.schema_ref: ("55d7007b0b87206b17f31dbf72e096e415ed2550e4de04883248215eeca49371"),
        SOURCE_TAXONOMY_SCHEMA.schema_ref: ("da0661b45a19007a5b3fa8d7f582434b2a62c726a5f39157887632907c203442"),
        SOURCE_MODE_SCHEMA.schema_ref: ("cf2c533ea4ece1d59e1e088449fbf89ad7814f5d1675ec833ebb50205c0c7fb3"),
        SOURCE_EXECUTION_REQUEST_SCHEMA.schema_ref: (
            "6c6c060b22e7cb01a474e82f46ba0091f9ee81cc99e32055b2d74c0cff728aba"
        ),
        SOURCE_WARNING_SCHEMA.schema_ref: ("538fe5dce05af8b29c291a66c3a71ad623160750669472566e7bcb287985f847"),
        SOURCE_REJECTION_SCHEMA.schema_ref: ("c251325496d94a31132adf9522605f100103d10559ee255031675db26cfa463a"),
        SOURCE_RESOLUTION_OBSERVATION_SCHEMA.schema_ref: (
            "b25c6eb29805719375a07e43f50c81f9d93a3384b267b722c7789f8cd2f826d7"
        ),
    }
    for schema in (
        SOURCE_ITEM_DEFINITION_SCHEMA,
        SOURCE_TAXONOMY_SCHEMA,
        SOURCE_MODE_SCHEMA,
        SOURCE_EXECUTION_REQUEST_SCHEMA,
        SOURCE_WARNING_SCHEMA,
        SOURCE_REJECTION_SCHEMA,
        SOURCE_RESOLUTION_OBSERVATION_SCHEMA,
    ):
        assert schema.schema_digest == pinned[schema.schema_ref]
    assert ("revision", True) in SOURCE_ITEM_DEFINITION_SCHEMA.field_requiredness
    assert ("project_scope", True) in (SOURCE_EXECUTION_REQUEST_SCHEMA.field_requiredness)
    assert ("catalog_digest", True) in (SOURCE_RESOLUTION_OBSERVATION_SCHEMA.field_requiredness)


def test_profile_and_contract_digests_are_pinned() -> None:
    bundle = _bundle()
    profiles = bundle.profiles
    assert profiles["observation"].profile_digest == (
        "eb5f5b75c53f7fbaa25c339302d46886fd98bdd7fd136a5d3c6997e4d37c69e0"
    )
    assert profiles["failure"].profile_digest == ("c3f850c5453f687a32c6b99996787fe656514035a82b950ee68c250e958d36d8")
    assert bundle.operation.ref.contract_digest == ("6ced6266314f92d80b4590532c2fa491c407a64a7923cd587499c05ebbfc66d4")


def test_resource_ceiling_rejects_over_limit_inputs() -> None:
    too_many_channels = [{"channel_key": f"ch.{index}", "enabled": True} for index in range(257)]
    catalog_rejected = resolve_source_execution_request(_payload(channels=too_many_channels))
    assert isinstance(catalog_rejected, RejectedResolution)
    assert catalog_rejected.rejection.code == "RESOURCE_CEILING_EXCEEDED"

    many_terms = resolve_source_execution_request(
        _payload(params={"query_terms": [f"t{index}" for index in range(33)]})
    )
    assert isinstance(many_terms, RejectedResolution)
    assert many_terms.rejection.code == "RESOURCE_CEILING_EXCEEDED"
    assert "query terms" in many_terms.rejection.message

    many_urls = resolve_source_execution_request(
        _payload(
            item=_item(item_key="report.urls", channel_key="market.default"),
            params={"urls": [f"https://example.com/{index}" for index in range(257)]},
        )
    )
    assert isinstance(many_urls, RejectedResolution)
    assert many_urls.rejection.code == "RESOURCE_CEILING_EXCEEDED"
    assert "urls" in many_urls.rejection.message

    many_site_entries = resolve_source_execution_request(
        _payload(params={"site_entries": [f"https://example.com/{index}" for index in range(257)]})
    )
    assert isinstance(many_site_entries, RejectedResolution)
    assert many_site_entries.rejection.code == "RESOURCE_CEILING_EXCEEDED"
    assert "site entries" in many_site_entries.rejection.message

    long_scalar = resolve_source_execution_request(
        _payload(params={"query_terms": ["x" * (RESOURCE_CEILING.max_scalar_length + 1)]})
    )
    assert isinstance(long_scalar, RejectedResolution)
    assert long_scalar.rejection.code == "RESOURCE_CEILING_EXCEEDED"
    assert "scalar" in long_scalar.rejection.message

    big_payload = _payload(params={f"key{index}": "v" * 2000 for index in range(40)})
    bytes_rejected = resolve_source_execution_request(big_payload)
    assert isinstance(bytes_rejected, RejectedResolution)
    assert bytes_rejected.rejection.code == "RESOURCE_CEILING_EXCEEDED"
    assert "payload bytes" in bytes_rejected.rejection.message


def test_resource_ceiling_digest_is_bound_into_resource_profile() -> None:
    bundle = _bundle()
    profile = bundle.profiles["resource"]
    assert resource_ceiling_digest() == RESOURCE_CEILING.ceiling_digest
    assert profile.budget_ref.endswith(":" + resource_ceiling_digest())


def test_params_snapshot_to_dict_maps_raw_flag_field() -> None:
    snapshot = NormalizedParamsSnapshot.from_dict({"query_terms": ["x"], "_allow_internal_generic_web": True})
    restored = snapshot.to_dict()
    assert restored["_allow_internal_generic_web"] is True


def test_program_ast_single_atom_and_plan_exact() -> None:
    payload = _payload()
    program = _program(payload)
    assert isinstance(program.root, Atom)
    assert program.root.node_kind == "atom"
    assert program.root.operation.operation_id == ("source_library.resolve_execution_request")
    assert program.root.operation.contract_ref.kind == SOURCE_RESOLUTION_KIND
    assert program.root.input_type.type_id == "SourceResolutionPayload.v1"
    assert program.root.output_type.type_id == "SourceResolutionResult.v1"

    decoded = decode_program_spec(
        {
            "program": json.loads(program.canonical_json()),
            "program_digest": program.digest(),
        }
    )
    assert decoded.program_digest == program.program_digest
    assert decoded.root.ast_digest() == program.root.ast_digest()

    plan = _plan(program)
    assert plan.program_id == program.program_id
    assert plan.program_digest == program.program_digest
    effect_steps = [
        step for step in plan.ordered_steps if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    assert effect_steps[0].operation_contract_ref == program.root.operation.contract_ref
    assert not any(step.step_kind == "ADMISSION" for step in plan.ordered_steps)
    assert plan.input_type.type_id == "SourceResolutionPayload.v1"
    assert plan.output_type.type_id == "SourceResolutionResult.v1"

    ref = program.root.operation.payload_ref
    assert ref.project_key == PROJECT_KEY
    assert ref.object_type.type_id == "SourceResolutionPayload.v1"
    metadata = dict(program.metadata)
    assert metadata["catalog_digest"] == payload.catalog.digest
    assert metadata["catalog_revision"] == payload.catalog.revision
    assert metadata["catalog_incarnation"] == payload.catalog.incarnation
    assert metadata["payload_content_digest"] == ref.content_digest


def test_taxonomy_normalization_idempotence() -> None:
    payload = _payload()
    first = normalize_item_taxonomy_dict(
        {
            "item_key": payload.item.item_key,
            "channel_key": payload.item.channel_key,
            "extra": dict(payload.item.extra),
        }
    )
    second = normalize_item_taxonomy_dict(first)
    assert first == second
    assert first["item_type"] == "service_aggregated"
    assert first["managed_by"] == "system"
    assert second["extra"]["item_type"] == "service_aggregated"


def test_ordered_mode_precedence_and_counterexample() -> None:
    url_payload = _payload(
        item={
            "item_key": "report.urls",
            "channel_key": "market.default",
            "enabled": True,
        },
        params={"urls": ["https://example.com/a"], "source_mode": "site_search"},
    )
    url_result = resolve_source_execution_request(url_payload)
    assert isinstance(url_result, RejectedResolution) is False
    assert url_result.request.source_mode.mode == "url_execution"
    assert [warning.code for warning in url_result.request.warnings] == ["SOURCE_MODE_OVERRIDDEN_BY_URLS"]

    crawler_payload = _payload(
        item=_item(
            item_key="crawler.item",
            channel_key="crawler.demo_proj",
            extra={},
        ),
        params={},
    )
    crawler_result = resolve_source_execution_request(crawler_payload)
    assert crawler_result.request.source_mode.mode == "provider_harvest"
    assert crawler_result.request.taxonomy.channel_family == "crawler_provider"

    site_coercion = _payload(
        item=_item(
            item_key="crawler.site",
            channel_key="crawler.demo_proj",
            extra={},
        ),
        params={
            "site_entries": ["https://example.com/search"],
            "source_mode": "protocol_search",
        },
    )
    coerced = resolve_source_execution_request(site_coercion)
    assert coerced.request.source_mode.mode == "site_search"
    assert [warning.code for warning in coerced.request.warnings] == [
        "SOURCE_MODE_COERCED_BY_SITE_SEARCH",
        "SITE_SEARCH_FORCED_HANDLER_CLUSTER",
    ]

    invalid_mode = _payload(
        item=_item(
            item_key="plain.item",
            channel_key="market.default",
            extra={},
        ),
        params={"query_terms": ["a"], "source_mode": "not_a_mode"},
    )
    invalid_result = resolve_source_execution_request(invalid_mode)
    assert invalid_result.request.source_mode.mode == "protocol_search"
    assert [warning.code for warning in invalid_result.request.warnings] == ["SOURCE_MODE_INVALID_IGNORED"]
    assert invalid_result.request.warnings[0].ordered_payload == ("not_a_mode",)

    explicit_honored = resolve_source_execution_request(
        _payload(
            item=_item(
                item_key="crawler.explicit",
                channel_key="crawler.demo_proj",
                extra={},
            ),
            params={"source_mode": "provider_harvest"},
        )
    )
    assert explicit_honored.request.source_mode.mode == "provider_harvest"
    assert explicit_honored.request.warnings == ()


def test_generic_web_direct_internal_only() -> None:
    direct = _payload(
        item={
            "item_key": "generic_web.demo",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "item_type": "user_defined",
            "managed_by": "user",
        },
        params={"query_terms": ["robotics"]},
    )
    rejected = resolve_source_execution_request(direct)
    assert isinstance(rejected, RejectedResolution)
    assert rejected.rejection.code == "FORBIDDEN_INTERNAL_ADAPTER"

    raw_flag = resolve_source_execution_request(
        _payload(
            item=_item(
                item_key="generic_web.demo.flag",
                channel_key="generic_web.search_template",
                item_type="user_defined",
                managed_by="user",
            ),
            params={
                "query_terms": ["robotics"],
                "_allow_internal_generic_web": True,
            },
        )
    )
    assert isinstance(raw_flag, RejectedResolution)
    assert raw_flag.rejection.code == "FORBIDDEN_INTERNAL_ADAPTER"

    internal = _payload(
        item={
            "item_key": "generic_web.internal",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "item_type": "service_aggregated",
            "managed_by": "system",
        },
        params={"query_terms": ["robotics"]},
    )
    resolved = resolve_source_execution_request(internal)
    assert not isinstance(resolved, RejectedResolution)
    assert resolved.request.source_mode.mode == "site_search"
    assert resolved.request.taxonomy.internal_adapter_only
    assert [warning.code for warning in resolved.request.warnings] == [
        "SITE_SEARCH_FORCED_HANDLER_CLUSTER",
        "GENERIC_WEB_INTERNAL_ADAPTER_DETECTED",
    ]


def test_no_provider_or_credential_work() -> None:
    bundle = _bundle()
    profiles = bundle.profiles
    assert profiles["effect"].external_visibility == "NONE"
    assert profiles["effect"].network_required is False
    assert profiles["effect"].execution_class == "PURE_TRANSFORM"
    assert profiles["authority"].canonical_owner == SOURCE_RESOLUTION_OWNER
    assert profiles["authority"].credential_refs == ()
    assert profiles["interpreter"].credential_requirements_ref is None
    for module_name in (
        "app.successor_runtime.capabilities.source_resolution",
        "app.successor_runtime.capabilities.source_resolution_program",
        "app.successor_runtime.capabilities.source_resolution_interpreters",
    ):
        source = inspect.getsource(__import__(module_name, fromlist=["*"]))
        assert "from app.services" not in source
        assert "import app.services" not in source
        assert "run_item_payload(" not in source
        assert "def _run_source_mode" not in source
        for banned in ("socket", "httpx", "sqlalchemy", "requests."):
            assert banned not in source


def test_shared_root_hashes_unchanged() -> None:
    root = _BACKEND_ROOT / "app" / "successor_runtime"
    before = _shared_state(root)
    accepted_before = _accepted_shared_state(before)
    bundle = _bundle()
    payload = _payload()
    program = _program(payload)
    _plan(program)
    resolve_source_execution_request(payload)
    assert bundle.operation.ref.contract_digest
    after = _shared_state(root)
    assert after == accepted_before


def test_import_boundaries_and_dependency_lint() -> None:
    from scripts.check_successor_runtime_dependencies import check

    adapter_source = inspect.getsource(__import__("app.successor_migration.legacy_source_library", fromlist=["*"]))
    assert "from app.services.source_library.item_resolver import" in adapter_source
    assert "from app.services.source_library.resolver import" in adapter_source
    assert "run_item_payload(" not in adapter_source
    assert "import run_item_payload" not in adapter_source
    assert "def _run_source_mode" not in adapter_source
    report = check(_BACKEND_ROOT / "app" / "successor_runtime")
    assert report["ok"], report["violations"]
