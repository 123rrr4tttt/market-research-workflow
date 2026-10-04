"""One native candidate discovery declaration and its reusable lowering rule.

The declaration owns identity, endpoint types and the default provider policy.
The existing search kernel remains the only executor; the concrete discovery
callable is supplied by the service composition owner at assembly, so this
module stays free of any ``app.services`` dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from functorial_kit.contribution_compiler import NativeContributionRule, compile_native_contribution
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.canonical import codec_failures
from functorial_kit.core.codec import Codec, define_codec
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.capabilities.retrieval_common import (
    CANDIDATE_BUNDLE_TYPE,
    CANDIDATE_REQUEST_TYPE,
    CandidateBundle,
    CandidateSearchRequest,
)
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.object_types import ObjectType


SUPPORTED_PROVIDERS = frozenset({"auto", "ddg", "google", "serper", "serpstack", "serpapi", "searxng", "yacy"})


@dataclass(frozen=True, slots=True)
class CandidateNativeSource:
    contribution_id: str
    operation_id: str
    owner: str
    default_provider: str = "auto"
    input_type: ObjectType = CANDIDATE_REQUEST_TYPE
    output_type: ObjectType = CANDIDATE_BUNDLE_TYPE


DEFAULT_CANDIDATE_NATIVE_SOURCE = CandidateNativeSource(
    contribution_id="mrw.retrieval.candidate.native.v1",
    operation_id="retrieval.candidate.discover.v1",
    owner="services.search.candidate_search",
)


@dataclass(frozen=True, slots=True)
class CandidateNativeDefinition:
    source: CandidateNativeSource
    request_codec: PayloadCodec
    registry_codec: Codec[CandidateSearchRequest]

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id


@dataclass(frozen=True, slots=True)
class CandidateAssemblyContext:
    """Concrete search callable supplied by the service composition owner."""

    discover: Callable[[CandidateSearchRequest], CandidateBundle]


@dataclass(frozen=True, slots=True)
class CandidateSearchBinding:
    definition: CandidateNativeDefinition
    _discover: Callable[[CandidateSearchRequest], CandidateBundle]

    def discover(self, request: CandidateSearchRequest) -> CandidateBundle:
        effective = request
        if request.provider == "auto" and self.definition.source.default_provider != "auto":
            effective = replace(request, provider=self.definition.source.default_provider)
        return self._discover(effective)


def lower_candidate_native_source(source: CandidateNativeSource) -> CandidateNativeDefinition | Failure:
    issues = []
    for field_name in ("contribution_id", "operation_id", "owner"):
        if not getattr(source, field_name).strip():
            issues.append({"code": "invalid_spec", "path": f"$.source.{field_name}", "message": "must be nonempty"})
    if source.default_provider not in SUPPORTED_PROVIDERS:
        issues.append({"code": "invalid_spec", "path": "$.source.default_provider", "message": "unsupported search provider"})
    if source.input_type != CANDIDATE_REQUEST_TYPE or source.output_type != CANDIDATE_BUNDLE_TYPE:
        issues.append({"code": "invalid_spec", "path": "$.source.endpoints", "message": "candidate endpoint type mismatch"})
    if issues:
        return contribution_failures.fail("CONTRIBUTION_INVALID", "candidate discovery definition invalid", {"issues": tuple(issues)})
    digest = content_digest({"operation_id": source.operation_id, "input": source.input_type.type_id, "output": source.output_type.type_id})
    contract_ref = OperationContractRef(source.operation_id, "1", digest)
    codec = dataclass_codec(
        codec_id=f"{source.operation_id}.request.v1",
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=source.input_type.type_id,
        dto_cls=CandidateSearchRequest,
    )
    def parse_wire(value):
        payload = value.get("payload")
        if not isinstance(payload, dict):
            return codec_failures.fail("CODEC_INVALID_FIELD", "candidate request payload must be an object")
        try:
            return codec.decode_payload(payload)
        except (TypeError, ValueError) as exc:
            return codec_failures.fail("CODEC_INVALID_FIELD", str(exc))

    if source.operation_id == "retrieval.candidate.discover.v1":
        # The default identity is literal so the kit's source/registry scan can
        # compare it with the catalog-derived registry entry.
        registry_codec = define_codec(
            name="retrieval.candidate.discover.v1.request.v1",
            discriminant="CandidateSearchRequest.v1",
            keys=("kind", "payload"),
            parse=parse_wire,
            to_wire=lambda value: {"kind": source.input_type.type_id, "payload": codec.encode_payload(value)},
        )
    else:
        registry_codec = define_codec(
            name=codec.codec_id,
            discriminant=source.input_type.type_id,
            keys=("kind", "payload"),
            parse=parse_wire,
            to_wire=lambda value: {"kind": source.input_type.type_id, "payload": codec.encode_payload(value)},
        )
    return CandidateNativeDefinition(source, codec, registry_codec)


def project_candidate_native_definition(definition: CandidateNativeDefinition) -> ProjectedContributionSpec:
    source = definition.source
    return ProjectedContributionSpec(
        id=source.contribution_id,
        owner=source.owner,
        objects=(
            ContributionObject(source.input_type.type_id, "ObjectType", source.owner),
            ContributionObject(source.output_type.type_id, "ObjectType", source.owner, (source.input_type.type_id,)),
            ContributionObject(source.operation_id, "Capability", source.owner, (source.input_type.type_id, source.output_type.type_id)),
            ContributionObject(definition.request_codec.codec_id, "PayloadCodec", source.owner, (source.operation_id, source.input_type.type_id)),
        ),
        codecs=(definition.registry_codec,),
    )


def assemble_candidate_native_definition(
    definition: CandidateNativeDefinition, context: CandidateAssemblyContext,
) -> CandidateSearchBinding:
    return CandidateSearchBinding(definition, context.discover)


def validate_candidate_native_binding(definition: CandidateNativeDefinition, candidate: object) -> BindingAccepted[CandidateSearchBinding] | BindingRejected:
    if isinstance(candidate, CandidateSearchBinding) and candidate.definition == definition:
        return BindingAccepted(candidate)
    return BindingRejected((NativeBindingIssue("$.binding", "candidate search binding definition mismatch"),))


CANDIDATE_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    CandidateNativeSource, CandidateNativeDefinition, CandidateAssemblyContext, CandidateSearchBinding
](
    lower=lower_candidate_native_source,
    project=project_candidate_native_definition,
    assemble=assemble_candidate_native_definition,
    validate_binding=validate_candidate_native_binding,
)


def compile_candidate_native_contribution(source: CandidateNativeSource):
    return compile_native_contribution(source, CANDIDATE_NATIVE_CONTRIBUTION_RULE)
