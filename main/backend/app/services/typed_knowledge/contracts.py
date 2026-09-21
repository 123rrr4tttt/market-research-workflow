from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Annotated, Any, Final, Mapping, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import typed_knowledge_contract_failures

REVIEW_STATE_DRAFT_CANDIDATE = "draft_candidate"
REVIEW_STATE_HUMAN_CONFIRMED = "human_confirmed"
REVIEW_STATE_REVISED = "revised"
REVIEW_STATE_DEPRECATED = "deprecated"
ALLOWED_REVIEW_STATES = frozenset(
    {
        REVIEW_STATE_DRAFT_CANDIDATE,
        REVIEW_STATE_HUMAN_CONFIRMED,
        REVIEW_STATE_REVISED,
        REVIEW_STATE_DEPRECATED,
    }
)

QUALITY_GRADE_GOLD = "gold"
QUALITY_GRADE_SILVER = "silver"
QUALITY_GRADE_BRONZE = "bronze"
QUALITY_GRADE_HOLD = "hold"
ALLOWED_QUALITY_GRADES = frozenset(
    {
        QUALITY_GRADE_GOLD,
        QUALITY_GRADE_SILVER,
        QUALITY_GRADE_BRONZE,
        QUALITY_GRADE_HOLD,
    }
)

VISIBILITY_SCOPE_INTERNAL_ONLY = "internal_only"
VISIBILITY_SCOPE_DOWNSTREAM_READY = "downstream_ready"
REVIEW_STATE_VISIBILITY_SCOPE: Final[Mapping[str, str]] = MappingProxyType(
    {
        REVIEW_STATE_DRAFT_CANDIDATE: VISIBILITY_SCOPE_INTERNAL_ONLY,
        REVIEW_STATE_HUMAN_CONFIRMED: VISIBILITY_SCOPE_DOWNSTREAM_READY,
        REVIEW_STATE_REVISED: VISIBILITY_SCOPE_DOWNSTREAM_READY,
        REVIEW_STATE_DEPRECATED: VISIBILITY_SCOPE_INTERNAL_ONLY,
    }
)

GOVERNANCE_DIMENSION_MATRIX: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "review_state": MappingProxyType(
            {
                "layer": "governance",
                "applies_to": "type_node|knowledge_item|topic_cluster|booklet",
                "phase1_rule": "automation_can_propose_but_human_controls_final_acceptance",
            }
        ),
        "quality_grade": MappingProxyType(
            {
                "layer": "governance",
                "applies_to": "knowledge_item",
                "phase1_rule": "ranking_or_eligibility_signal_not_taxonomy",
            }
        ),
        "locale": MappingProxyType(
            {
                "layer": "attribute",
                "applies_to": "knowledge_item",
                "phase1_rule": "locale_variants_under_same_identity",
            }
        ),
        "provenance": MappingProxyType(
            {
                "layer": "attribute",
                "applies_to": "knowledge_item",
                "phase1_rule": "source_traceability_required",
            }
        ),
    }
)

TOPIC_CLUSTER_MEMBERSHIP_MODE: Final[str] = "thematic_explicit_membership"
BOOKLET_MEMBERSHIP_MODE: Final[str] = "curated_explicit_membership"

DOWNSTREAM_CONTRACT_FIELDS: Final[tuple[str, ...]] = (
    "knowledge_item_key",
    "project_key",
    "canonical_statement",
    "primary_type_node_key",
    "topic_cluster_keys",
    "booklet_keys",
    "review_state",
    "quality_grade",
    "locale",
    "locale_variants",
    "evidence_refs",
    "visibility_scope",
    "updated_at",
)
DOWNSTREAM_CONSUMER_FACETS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "search": ("project_key", "primary_type_node_key", "topic_cluster_keys", "booklet_keys", "quality_grade"),
        "graph": ("knowledge_item_key", "primary_type_node_key", "topic_cluster_keys", "review_state"),
        "writing": ("knowledge_item_key", "canonical_statement", "evidence_refs", "locale", "quality_grade"),
        "reporting": ("project_key", "topic_cluster_keys", "booklet_keys", "quality_grade", "review_state"),
    }
)

WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION: Final[str] = "typed_knowledge.writing_handoff.v1"
WRITING_KNOWLEDGE_HANDOFF_FIELDS: Final[tuple[str, ...]] = (
    "contract_version",
    "knowledge_item_key",
    "project_key",
    "canonical_statement",
    "primary_type_node_key",
    "topic_cluster_keys",
    "booklet_keys",
    "review_state",
    "quality_grade",
    "locale",
    "evidence_refs",
    "visibility_scope",
    "selection_hash",
    "selection_text",
    "facets",
)
WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION: Final[str] = "writing.typed_knowledge_context.v1"
WRITING_KNOWLEDGE_HANDOFF_CONSUMER_BOUNDARY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "source_domain": "typed_knowledge",
        "consumer_domain": "writing",
        "consumer": "writing.keyword_card",
        "card_source_type": "resource",
        "boundary_rule": "consume_typed_knowledge_handoff_as_resource_card_only",
        "non_goal": "graph_projection_or_persistence_writeback",
    }
)

ACTOR_AUTOMATION = "automation"
ACTOR_HUMAN = "human"
ALLOWED_GOVERNANCE_ACTORS = frozenset({ACTOR_AUTOMATION, ACTOR_HUMAN})

PHASE1_TYPE_NODE_PARENT_MODE: Final[str] = "single_primary_parent"
PHASE1_KNOWLEDGE_ITEM_PRIMARY_TYPE_MODE: Final[str] = "single_primary_type"

OBJECT_RESPONSIBILITY_MATRIX: Final[Mapping[str, Mapping[str, tuple[str, ...]]]] = MappingProxyType(
    {
        "type_node": MappingProxyType(
            {
                "responsibilities": (
                    "taxonomy_anchor",
                    "navigation_hierarchy",
                    "project_scoped_type_identity",
                ),
                "non_goals": (
                    "graph_rendering_node",
                    "free_form_tag_bucket",
                ),
            }
        ),
        "knowledge_item": MappingProxyType(
            {
                "responsibilities": (
                    "normalized_downstream_unit",
                    "provenance_traceability",
                    "governance_dimensions",
                ),
                "non_goals": (
                    "raw_document_replacement",
                    "graph_projection_only_identity",
                ),
            }
        ),
        "topic_cluster": MappingProxyType(
            {
                "responsibilities": (
                    "cross_type_thematic_grouping",
                    "many_item_aggregation",
                ),
                "non_goals": (
                    "taxonomy_synonym",
                    "free_form_tag_bucket",
                ),
            }
        ),
        "booklet": MappingProxyType(
            {
                "responsibilities": (
                    "curated_presentation_container",
                    "cross_object_collection",
                ),
                "non_goals": (
                    "taxonomy_replacement",
                    "implicit_membership_from_type_hierarchy",
                ),
            }
        ),
    }
)


class TypedKnowledgeContractError(ValueError):
    """Raised when typed knowledge boundary contracts are violated."""


_FAILURE_CONTEXT_KEYS = frozenset({"owner", "public_exception", "public_message"})


def typed_knowledge_failure(
    code: str,
    message: str,
    *,
    owner: str,
    public_exception: type[Exception] | str = TypedKnowledgeContractError,
    public_message: str | None = None,
    **details: Any,
) -> Failure:
    """Create a closed typed-knowledge contract failure before ABI lifting."""
    context = {
        "owner": owner,
        "public_exception": (
            public_exception.__name__ if isinstance(public_exception, type) else str(public_exception)
        ),
        "public_message": str(public_message if public_message is not None else message),
        **details,
    }
    return typed_knowledge_contract_failures.fail(code, message, context)


def raise_typed_knowledge_legacy(
    failure: Failure,
    exception_type: type[Exception] = TypedKnowledgeContractError,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Lift one closed failure into the established public exception ABI."""
    context = failure.context or {}
    if (
        not typed_knowledge_contract_failures.matches(failure)
        or not _FAILURE_CONTEXT_KEYS <= set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=typed_knowledge.contracts.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_typed_knowledge_failure_lift_rejects_invalid_context
        raise TypeError("typed knowledge failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if cause is None:
        # kit:boundary owner=typed_knowledge.contracts.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=typed_knowledge.contract_failure witness=test:test_typed_knowledge_legacy_contract_abi_is_preserved
        raise exception_type(message)
    # kit:boundary owner=typed_knowledge.contracts.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=typed_knowledge.contract_failure witness=test:test_typed_knowledge_failure_lift_preserves_cause
    raise exception_type(message) from cause


@dataclass(frozen=True, slots=True)
class TypeNode:
    key: str
    project_key: str
    label: str
    primary_parent_key: str | None = None
    aliases: tuple[str, ...] = ()
    review_state: str = REVIEW_STATE_DRAFT_CANDIDATE


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    key: str
    project_key: str
    canonical_statement: str
    primary_type_node_key: str
    evidence_refs: tuple[str, ...]
    topic_cluster_keys: tuple[str, ...] = ()
    booklet_keys: tuple[str, ...] = ()
    review_state: str = REVIEW_STATE_DRAFT_CANDIDATE
    quality_grade: str | None = None
    locale: str | None = None
    locale_variants: Mapping[str, str] = field(default_factory=dict)
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class TopicCluster:
    key: str
    project_key: str
    label: str
    summary: str | None = None
    knowledge_item_keys: tuple[str, ...] = ()
    review_state: str = REVIEW_STATE_DRAFT_CANDIDATE


@dataclass(frozen=True, slots=True)
class Booklet:
    key: str
    project_key: str
    title: str
    description: str | None = None
    included_type_node_keys: tuple[str, ...] = ()
    included_topic_cluster_keys: tuple[str, ...] = ()
    included_knowledge_item_keys: tuple[str, ...] = ()
    review_state: str = REVIEW_STATE_DRAFT_CANDIDATE


@dataclass(frozen=True, slots=True)
class DownstreamKnowledgeContractDraft:
    knowledge_item_key: str
    project_key: str
    canonical_statement: str
    primary_type_node_key: str
    topic_cluster_keys: tuple[str, ...]
    booklet_keys: tuple[str, ...]
    review_state: str
    quality_grade: str | None
    locale: str | None
    locale_variants: Mapping[str, str]
    evidence_refs: tuple[str, ...]
    visibility_scope: str
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class WritingKnowledgeHandoff:
    contract_version: str
    knowledge_item_key: str
    project_key: str
    canonical_statement: str
    primary_type_node_key: str
    topic_cluster_keys: tuple[str, ...]
    booklet_keys: tuple[str, ...]
    review_state: str
    quality_grade: str | None
    locale: str | None
    evidence_refs: tuple[str, ...]
    visibility_scope: str
    selection_hash: str | None = None
    selection_text: str | None = None
    facets: Mapping[str, Any] = field(default_factory=dict)


def _contract_failure(code: str, message: str, *, owner: str, **details: Any) -> Failure:
    return typed_knowledge_failure(
        code,
        message,
        owner=owner,
        public_exception=TypedKnowledgeContractError,
        public_message=message,
        **details,
    )


def _validate_review_state(review_state: str, *, object_name: str) -> Failure | None:
    if review_state not in ALLOWED_REVIEW_STATES:
        return _contract_failure(
            "object_contract_invalid",
            f"{object_name}_invalid_review_state:{review_state}",
            owner="typed_knowledge.contracts.review_state",
            field="review_state",
        )
    return None


def _validate_quality_grade(quality_grade: str | None) -> Failure | None:
    if quality_grade is not None and quality_grade not in ALLOWED_QUALITY_GRADES:
        return _contract_failure(
            "object_contract_invalid",
            f"knowledge_item_invalid_quality_grade:{quality_grade}",
            owner="typed_knowledge.contracts.knowledge_item",
            field="quality_grade",
        )
    return None


def _validate_locale(locale: str | None, locale_variants: Mapping[str, str]) -> Failure | None:
    if locale is not None and not locale.strip():
        return _contract_failure("object_contract_invalid", "knowledge_item_invalid_locale", owner="typed_knowledge.contracts.knowledge_item", field="locale")
    if locale_variants and locale is None:
        return _contract_failure("object_contract_invalid", "knowledge_item_locale_variants_require_locale", owner="typed_knowledge.contracts.knowledge_item", field="locale_variants")
    if any(not str(key).strip() or not str(value).strip() for key, value in locale_variants.items()):
        return _contract_failure("object_contract_invalid", "knowledge_item_invalid_locale_variants", owner="typed_knowledge.contracts.knowledge_item", field="locale_variants")
    return None


def _validate_updated_at(updated_at: str | None, *, object_name: str) -> Failure | None:
    if updated_at is not None and not updated_at.strip():
        return _contract_failure("object_contract_invalid", f"{object_name}_invalid_updated_at", owner="typed_knowledge.contracts.updated_at", field="updated_at")
    return None


def try_validate_type_node(node: TypeNode) -> Failure | None:
    if not node.key or not node.project_key:
        return _contract_failure("object_contract_invalid", "type_node_missing_identity", owner="typed_knowledge.contracts.type_node", field="identity")
    if not node.label.strip():
        return _contract_failure("object_contract_invalid", "type_node_missing_label", owner="typed_knowledge.contracts.type_node", field="label")
    return _validate_review_state(node.review_state, object_name="type_node")


def validate_type_node(node: TypeNode) -> None:
    failure = try_validate_type_node(node)
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def try_validate_knowledge_item(item: KnowledgeItem) -> Failure | None:
    if not item.key or not item.project_key:
        return _contract_failure("object_contract_invalid", "knowledge_item_missing_identity", owner="typed_knowledge.contracts.knowledge_item", field="identity")
    if not item.canonical_statement.strip():
        return _contract_failure("object_contract_invalid", "knowledge_item_missing_statement", owner="typed_knowledge.contracts.knowledge_item", field="canonical_statement")
    if not item.primary_type_node_key.strip():
        return _contract_failure("object_contract_invalid", "knowledge_item_missing_primary_type", owner="typed_knowledge.contracts.knowledge_item", field="primary_type_node_key")
    if not item.evidence_refs:
        return _contract_failure("object_contract_invalid", "knowledge_item_missing_provenance", owner="typed_knowledge.contracts.knowledge_item", field="evidence_refs")
    for failure in (
        _validate_quality_grade(item.quality_grade),
        _validate_locale(item.locale, item.locale_variants),
        _validate_updated_at(item.updated_at, object_name="knowledge_item"),
        _validate_review_state(item.review_state, object_name="knowledge_item"),
    ):
        if isinstance(failure, Failure):
            return failure
    return None


def validate_knowledge_item(item: KnowledgeItem) -> None:
    failure = try_validate_knowledge_item(item)
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def try_validate_topic_cluster(cluster: TopicCluster) -> Failure | None:
    if not cluster.key or not cluster.project_key:
        return _contract_failure("object_contract_invalid", "topic_cluster_missing_identity", owner="typed_knowledge.contracts.topic_cluster", field="identity")
    if not cluster.label.strip():
        return _contract_failure("object_contract_invalid", "topic_cluster_missing_label", owner="typed_knowledge.contracts.topic_cluster", field="label")
    return _validate_review_state(cluster.review_state, object_name="topic_cluster")


def validate_topic_cluster(cluster: TopicCluster) -> None:
    failure = try_validate_topic_cluster(cluster)
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def try_validate_booklet(booklet: Booklet) -> Failure | None:
    if not booklet.key or not booklet.project_key:
        return _contract_failure("object_contract_invalid", "booklet_missing_identity", owner="typed_knowledge.contracts.booklet", field="identity")
    if not booklet.title.strip():
        return _contract_failure("object_contract_invalid", "booklet_missing_title", owner="typed_knowledge.contracts.booklet", field="title")
    return _validate_review_state(booklet.review_state, object_name="booklet")


def validate_booklet(booklet: Booklet) -> None:
    failure = try_validate_booklet(booklet)
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def try_validate_relationships(
    *,
    type_nodes: tuple[TypeNode, ...],
    knowledge_items: tuple[KnowledgeItem, ...],
    topic_clusters: tuple[TopicCluster, ...],
    booklets: tuple[Booklet, ...],
) -> Failure | None:
    type_node_keys = {item.key for item in type_nodes}
    knowledge_item_keys = {item.key for item in knowledge_items}
    topic_cluster_keys = {item.key for item in topic_clusters}
    booklet_keys = {item.key for item in booklets}
    type_nodes_by_key = {item.key: item for item in type_nodes}
    topic_clusters_by_key = {item.key: item for item in topic_clusters}
    booklets_by_key = {item.key: item for item in booklets}
    knowledge_items_by_key = {item.key: item for item in knowledge_items}

    for node in type_nodes:
        failure = try_validate_type_node(node)
        if isinstance(failure, Failure):
            return failure
        if node.primary_parent_key and node.primary_parent_key not in type_node_keys:
            return _contract_failure("relationship_contract_invalid", f"type_node_unknown_parent:{node.primary_parent_key}", owner="typed_knowledge.contracts.relationships", relation="primary_parent")
        if node.primary_parent_key:
            parent = type_nodes_by_key[node.primary_parent_key]
            if parent.project_key != node.project_key:
                return _contract_failure("relationship_contract_invalid", f"type_node_cross_project_parent:{node.primary_parent_key}", owner="typed_knowledge.contracts.relationships", relation="primary_parent")

    for item in knowledge_items:
        failure = try_validate_knowledge_item(item)
        if isinstance(failure, Failure):
            return failure
        if item.primary_type_node_key not in type_node_keys:
            return _contract_failure("relationship_contract_invalid", f"knowledge_item_unknown_primary_type:{item.primary_type_node_key}", owner="typed_knowledge.contracts.relationships", relation="primary_type")
        if type_nodes_by_key[item.primary_type_node_key].project_key != item.project_key:
            return _contract_failure("relationship_contract_invalid", f"knowledge_item_cross_project_primary_type:{item.primary_type_node_key}", owner="typed_knowledge.contracts.relationships", relation="primary_type")
        unknown_topic_keys = set(item.topic_cluster_keys) - topic_cluster_keys
        if unknown_topic_keys:
            return _contract_failure("relationship_contract_invalid", f"knowledge_item_unknown_topic_clusters:{sorted(unknown_topic_keys)}", owner="typed_knowledge.contracts.relationships", relation="topic_clusters")
        cross_project_topics = sorted(
            key for key in item.topic_cluster_keys if topic_clusters_by_key[key].project_key != item.project_key
        )
        if cross_project_topics:
            return _contract_failure("relationship_contract_invalid", f"knowledge_item_cross_project_topic_clusters:{cross_project_topics}", owner="typed_knowledge.contracts.relationships", relation="topic_clusters")
        unknown_booklet_keys = set(item.booklet_keys) - booklet_keys
        if unknown_booklet_keys:
            return _contract_failure("relationship_contract_invalid", f"knowledge_item_unknown_booklets:{sorted(unknown_booklet_keys)}", owner="typed_knowledge.contracts.relationships", relation="booklets")
        cross_project_booklets = sorted(key for key in item.booklet_keys if booklets_by_key[key].project_key != item.project_key)
        if cross_project_booklets:
            return _contract_failure("relationship_contract_invalid", f"knowledge_item_cross_project_booklets:{cross_project_booklets}", owner="typed_knowledge.contracts.relationships", relation="booklets")

    for cluster in topic_clusters:
        failure = try_validate_topic_cluster(cluster)
        if isinstance(failure, Failure):
            return failure
        unknown_item_keys = set(cluster.knowledge_item_keys) - knowledge_item_keys
        if unknown_item_keys:
            return _contract_failure("relationship_contract_invalid", f"topic_cluster_unknown_knowledge_items:{sorted(unknown_item_keys)}", owner="typed_knowledge.contracts.relationships", relation="knowledge_items")
        cross_project_items = sorted(
            key for key in cluster.knowledge_item_keys if knowledge_items_by_key[key].project_key != cluster.project_key
        )
        if cross_project_items:
            return _contract_failure("relationship_contract_invalid", f"topic_cluster_cross_project_knowledge_items:{cross_project_items}", owner="typed_knowledge.contracts.relationships", relation="knowledge_items")

    for booklet in booklets:
        failure = try_validate_booklet(booklet)
        if isinstance(failure, Failure):
            return failure
        unknown_type_keys = set(booklet.included_type_node_keys) - type_node_keys
        if unknown_type_keys:
            return _contract_failure("relationship_contract_invalid", f"booklet_unknown_type_nodes:{sorted(unknown_type_keys)}", owner="typed_knowledge.contracts.relationships", relation="type_nodes")
        cross_project_types = sorted(
            key for key in booklet.included_type_node_keys if type_nodes_by_key[key].project_key != booklet.project_key
        )
        if cross_project_types:
            return _contract_failure("relationship_contract_invalid", f"booklet_cross_project_type_nodes:{cross_project_types}", owner="typed_knowledge.contracts.relationships", relation="type_nodes")
        unknown_topic_keys = set(booklet.included_topic_cluster_keys) - topic_cluster_keys
        if unknown_topic_keys:
            return _contract_failure("relationship_contract_invalid", f"booklet_unknown_topic_clusters:{sorted(unknown_topic_keys)}", owner="typed_knowledge.contracts.relationships", relation="topic_clusters")
        cross_project_topics = sorted(
            key
            for key in booklet.included_topic_cluster_keys
            if topic_clusters_by_key[key].project_key != booklet.project_key
        )
        if cross_project_topics:
            return _contract_failure("relationship_contract_invalid", f"booklet_cross_project_topic_clusters:{cross_project_topics}", owner="typed_knowledge.contracts.relationships", relation="topic_clusters")
        unknown_item_keys = set(booklet.included_knowledge_item_keys) - knowledge_item_keys
        if unknown_item_keys:
            return _contract_failure("relationship_contract_invalid", f"booklet_unknown_knowledge_items:{sorted(unknown_item_keys)}", owner="typed_knowledge.contracts.relationships", relation="knowledge_items")
        cross_project_items = sorted(
            key
            for key in booklet.included_knowledge_item_keys
            if knowledge_items_by_key[key].project_key != booklet.project_key
        )
        if cross_project_items:
            return _contract_failure("relationship_contract_invalid", f"booklet_cross_project_knowledge_items:{cross_project_items}", owner="typed_knowledge.contracts.relationships", relation="knowledge_items")

    return None


def validate_relationships(
    *,
    type_nodes: tuple[TypeNode, ...],
    knowledge_items: tuple[KnowledgeItem, ...],
    topic_clusters: tuple[TopicCluster, ...],
    booklets: tuple[Booklet, ...],
) -> None:
    failure = try_validate_relationships(
        type_nodes=type_nodes,
        knowledge_items=knowledge_items,
        topic_clusters=topic_clusters,
        booklets=booklets,
    )
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def build_downstream_contract_draft(
    item: KnowledgeItem,
) -> Annotated[
    DownstreamKnowledgeContractDraft,
    "kit:non-authoritative derived_as=view "
    "fact_source=validated_knowledge_item "
    "witness=test:test_w04_authority_metadata",
]:
    validate_knowledge_item(item)
    visibility_scope = REVIEW_STATE_VISIBILITY_SCOPE[item.review_state]
    return DownstreamKnowledgeContractDraft(
        knowledge_item_key=item.key,
        project_key=item.project_key,
        canonical_statement=item.canonical_statement.strip(),
        primary_type_node_key=item.primary_type_node_key,
        topic_cluster_keys=tuple(item.topic_cluster_keys),
        booklet_keys=tuple(item.booklet_keys),
        review_state=item.review_state,
        quality_grade=item.quality_grade,
        locale=item.locale,
        locale_variants=MappingProxyType(dict(item.locale_variants)),
        evidence_refs=tuple(item.evidence_refs),
        visibility_scope=visibility_scope,
        updated_at=item.updated_at.strip() if item.updated_at is not None else None,
    )


def try_validate_downstream_contract_draft(contract: DownstreamKnowledgeContractDraft) -> Failure | None:
    if not contract.knowledge_item_key or not contract.project_key:
        return _contract_failure("downstream_contract_invalid", "downstream_contract_missing_identity", owner="typed_knowledge.contracts.downstream", field="identity")
    if not contract.canonical_statement.strip():
        return _contract_failure("downstream_contract_invalid", "downstream_contract_missing_statement", owner="typed_knowledge.contracts.downstream", field="canonical_statement")
    if not contract.primary_type_node_key.strip():
        return _contract_failure("downstream_contract_invalid", "downstream_contract_missing_primary_type", owner="typed_knowledge.contracts.downstream", field="primary_type_node_key")
    if not contract.evidence_refs:
        return _contract_failure("downstream_contract_invalid", "downstream_contract_missing_provenance", owner="typed_knowledge.contracts.downstream", field="evidence_refs")
    for failure in (_validate_quality_grade(contract.quality_grade), _validate_locale(contract.locale, contract.locale_variants), _validate_updated_at(contract.updated_at, object_name="downstream_contract"), _validate_review_state(contract.review_state, object_name="downstream_contract")):
        if isinstance(failure, Failure):
            return _contract_failure("downstream_contract_invalid", failure.message, owner="typed_knowledge.contracts.downstream", field=(failure.context or {}).get("field", "contract"))
    expected_scope = REVIEW_STATE_VISIBILITY_SCOPE[contract.review_state]
    if contract.visibility_scope != expected_scope:
        return _contract_failure("downstream_contract_invalid", "downstream_contract_visibility_scope_mismatch", owner="typed_knowledge.contracts.downstream", field="visibility_scope")
    return None


def validate_downstream_contract_draft(contract: DownstreamKnowledgeContractDraft) -> None:
    failure = try_validate_downstream_contract_draft(contract)
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def build_writing_knowledge_handoff(
    contract: DownstreamKnowledgeContractDraft,
    *,
    selection_hash: str | None = None,
    selection_text: str | None = None,
) -> Annotated[
    WritingKnowledgeHandoff,
    "kit:non-authoritative derived_as=view "
    "fact_source=validated_downstream_contract+selection_inputs "
    "witness=test:test_w04_authority_metadata",
]:
    validate_downstream_contract_draft(contract)
    if contract.visibility_scope != VISIBILITY_SCOPE_DOWNSTREAM_READY:
        raise_typed_knowledge_legacy(_contract_failure("writing_handoff_contract_invalid", "writing_handoff_requires_downstream_ready", owner="typed_knowledge.contracts.writing_handoff", field="visibility_scope"))
    normalized_selection_hash = str(selection_hash or "").strip() or None
    normalized_selection_text = str(selection_text or "").strip() or None
    facets = MappingProxyType(
        {
            "primary_type_node_key": contract.primary_type_node_key,
            "topic_cluster_keys": tuple(contract.topic_cluster_keys),
            "booklet_keys": tuple(contract.booklet_keys),
            "quality_grade": contract.quality_grade,
            "locale": contract.locale,
            "review_state": contract.review_state,
            "source_contract_fields": DOWNSTREAM_CONTRACT_FIELDS,
            "consumer_boundary": WRITING_KNOWLEDGE_HANDOFF_CONSUMER_BOUNDARY,
        }
    )
    handoff = WritingKnowledgeHandoff(
        contract_version=WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
        knowledge_item_key=contract.knowledge_item_key,
        project_key=contract.project_key,
        canonical_statement=contract.canonical_statement.strip(),
        primary_type_node_key=contract.primary_type_node_key,
        topic_cluster_keys=tuple(contract.topic_cluster_keys),
        booklet_keys=tuple(contract.booklet_keys),
        review_state=contract.review_state,
        quality_grade=contract.quality_grade,
        locale=contract.locale,
        evidence_refs=tuple(contract.evidence_refs),
        visibility_scope=contract.visibility_scope,
        selection_hash=normalized_selection_hash,
        selection_text=normalized_selection_text,
        facets=facets,
    )
    validate_writing_knowledge_handoff(handoff)
    return handoff


def try_validate_writing_knowledge_handoff(handoff: WritingKnowledgeHandoff) -> Failure | None:
    if handoff.contract_version != WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION:
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_contract_version_mismatch", owner="typed_knowledge.contracts.writing_handoff", field="contract_version")
    if not handoff.knowledge_item_key or not handoff.project_key:
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_missing_identity", owner="typed_knowledge.contracts.writing_handoff", field="identity")
    if not handoff.canonical_statement.strip():
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_missing_statement", owner="typed_knowledge.contracts.writing_handoff", field="canonical_statement")
    if not handoff.primary_type_node_key.strip():
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_missing_primary_type", owner="typed_knowledge.contracts.writing_handoff", field="primary_type_node_key")
    if not handoff.evidence_refs:
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_missing_provenance", owner="typed_knowledge.contracts.writing_handoff", field="evidence_refs")
    if handoff.visibility_scope != VISIBILITY_SCOPE_DOWNSTREAM_READY:
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_requires_downstream_ready", owner="typed_knowledge.contracts.writing_handoff", field="visibility_scope")
    if handoff.selection_hash is not None and not handoff.selection_hash.strip():
        return _contract_failure("writing_handoff_contract_invalid", "writing_handoff_invalid_selection_hash", owner="typed_knowledge.contracts.writing_handoff", field="selection_hash")
    for failure in (_validate_quality_grade(handoff.quality_grade), _validate_locale(handoff.locale, {}), _validate_review_state(handoff.review_state, object_name="writing_handoff")):
        if isinstance(failure, Failure):
            return _contract_failure("writing_handoff_contract_invalid", failure.message, owner="typed_knowledge.contracts.writing_handoff", field=(failure.context or {}).get("field", "handoff"))
    return None


def validate_writing_knowledge_handoff(handoff: WritingKnowledgeHandoff) -> None:
    failure = try_validate_writing_knowledge_handoff(handoff)
    if isinstance(failure, Failure):
        raise_typed_knowledge_legacy(failure)


def serialize_writing_knowledge_handoff(handoff: WritingKnowledgeHandoff) -> dict[str, Any]:
    validate_writing_knowledge_handoff(handoff)
    return {field: _json_safe(getattr(handoff, field)) for field in WRITING_KNOWLEDGE_HANDOFF_FIELDS}


def parse_writing_knowledge_handoff_payload(payload: Mapping[str, Any]) -> WritingKnowledgeHandoff:
    if not isinstance(payload, Mapping):
        raise_typed_knowledge_legacy(_contract_failure("writing_handoff_contract_invalid", "writing_handoff_payload_not_mapping", owner="typed_knowledge.contracts.writing_handoff", field="payload"))
    handoff = WritingKnowledgeHandoff(
        contract_version=str(payload.get("contract_version") or ""),
        knowledge_item_key=str(payload.get("knowledge_item_key") or ""),
        project_key=str(payload.get("project_key") or ""),
        canonical_statement=str(payload.get("canonical_statement") or ""),
        primary_type_node_key=str(payload.get("primary_type_node_key") or ""),
        topic_cluster_keys=_tuple_of_nonblank_strings(payload.get("topic_cluster_keys"), "topic_cluster_keys"),
        booklet_keys=_tuple_of_nonblank_strings(payload.get("booklet_keys"), "booklet_keys"),
        review_state=str(payload.get("review_state") or ""),
        quality_grade=_optional_string(payload.get("quality_grade")),
        locale=_optional_string(payload.get("locale")),
        evidence_refs=_tuple_of_nonblank_strings(payload.get("evidence_refs"), "evidence_refs"),
        visibility_scope=str(payload.get("visibility_scope") or ""),
        selection_hash=_optional_string(payload.get("selection_hash")),
        selection_text=_optional_string(payload.get("selection_text")),
        facets=dict(payload.get("facets") or {}) if isinstance(payload.get("facets") or {}, Mapping) else {},
    )
    validate_writing_knowledge_handoff(handoff)
    return handoff


def try_parse_writing_knowledge_handoff_payload(
    payload: Mapping[str, Any],
) -> WritingKnowledgeHandoff | Failure:
    try:
        return parse_writing_knowledge_handoff_payload(payload)
    except TypedKnowledgeContractError as exc:
        return _contract_failure(
            "writing_handoff_contract_invalid",
            str(exc),
            owner="typed_knowledge.contracts.writing_handoff",
            field="payload",
        )


def build_writing_knowledge_context_envelope(
    handoffs: tuple[WritingKnowledgeHandoff, ...],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=validated_writing_handoffs "
    "witness=test:test_w04_authority_metadata",
]:
    if not handoffs:
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_missing_handoffs", owner="typed_knowledge.contracts.writing_context", field="handoffs"))
    envelope = {
        "contract_version": WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION,
        "source": "typed_knowledge",
        "consumer": "writing.keyword_card",
        "handoffs": [serialize_writing_knowledge_handoff(handoff) for handoff in handoffs],
        "boundary": _json_safe(WRITING_KNOWLEDGE_HANDOFF_CONSUMER_BOUNDARY),
    }
    validate_writing_knowledge_context_envelope(envelope)
    return envelope


def validate_writing_knowledge_context_envelope(envelope: Mapping[str, Any]) -> None:
    _parse_writing_knowledge_context_envelope(envelope)


def try_validate_writing_knowledge_context_envelope(envelope: Mapping[str, Any]) -> Failure | None:
    try:
        _parse_writing_knowledge_context_envelope(envelope)
    except TypedKnowledgeContractError as exc:
        return _contract_failure(
            "writing_context_contract_invalid",
            str(exc),
            owner="typed_knowledge.contracts.writing_context",
            field="envelope",
        )
    return None


def parse_writing_knowledge_context_envelope(envelope: Mapping[str, Any]) -> tuple[WritingKnowledgeHandoff, ...]:
    return _parse_writing_knowledge_context_envelope(envelope)


def try_parse_writing_knowledge_context_envelope(
    envelope: Mapping[str, Any],
) -> tuple[WritingKnowledgeHandoff, ...] | Failure:
    try:
        return _parse_writing_knowledge_context_envelope(envelope)
    except TypedKnowledgeContractError as exc:
        return _contract_failure(
            "writing_context_contract_invalid",
            str(exc),
            owner="typed_knowledge.contracts.writing_context",
            field="envelope",
        )


def _parse_writing_knowledge_context_envelope(envelope: Mapping[str, Any]) -> tuple[WritingKnowledgeHandoff, ...]:
    if not isinstance(envelope, Mapping):
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_not_mapping", owner="typed_knowledge.contracts.writing_context", field="envelope"))
    if envelope.get("contract_version") != WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION:
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_version_mismatch", owner="typed_knowledge.contracts.writing_context", field="contract_version"))
    if envelope.get("source") != "typed_knowledge":
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_source_mismatch", owner="typed_knowledge.contracts.writing_context", field="source"))
    if envelope.get("consumer") != "writing.keyword_card":
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_consumer_mismatch", owner="typed_knowledge.contracts.writing_context", field="consumer"))
    boundary = envelope.get("boundary")
    if not isinstance(boundary, Mapping):
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_missing_boundary", owner="typed_knowledge.contracts.writing_context", field="boundary"))
    if boundary.get("card_source_type") != "resource":
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_card_source_type_mismatch", owner="typed_knowledge.contracts.writing_context", field="card_source_type"))
    raw_handoffs = envelope.get("handoffs")
    if not isinstance(raw_handoffs, list) or not raw_handoffs:
        raise_typed_knowledge_legacy(_contract_failure("writing_context_contract_invalid", "writing_context_envelope_missing_handoffs", owner="typed_knowledge.contracts.writing_context", field="handoffs"))
    return tuple(parse_writing_knowledge_handoff_payload(item) for item in raw_handoffs)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _tuple_of_nonblank_strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise_typed_knowledge_legacy(_contract_failure("writing_handoff_contract_invalid", f"writing_handoff_invalid_{field_name}", owner="typed_knowledge.contracts.writing_handoff", field=field_name))
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise_typed_knowledge_legacy(_contract_failure("writing_handoff_contract_invalid", f"writing_handoff_invalid_{field_name}", owner="typed_knowledge.contracts.writing_handoff", field=field_name))
        normalized.append(item.strip())
    return tuple(normalized)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def try_apply_review_state_transition(*, current_state: str, target_state: str, actor: str) -> str | Failure:
    for failure in (_validate_review_state(current_state, object_name="governance_current"), _validate_review_state(target_state, object_name="governance_target")):
        if isinstance(failure, Failure):
            return _contract_failure("governance_transition_invalid", failure.message, owner="typed_knowledge.contracts.governance", field="review_state")
    if actor not in ALLOWED_GOVERNANCE_ACTORS:
        return _contract_failure("governance_transition_invalid", f"governance_unknown_actor:{actor}", owner="typed_knowledge.contracts.governance", field="actor")
    if current_state == REVIEW_STATE_DEPRECATED and target_state != REVIEW_STATE_DEPRECATED:
        return _contract_failure("governance_transition_invalid", "governance_transition_from_deprecated_forbidden", owner="typed_knowledge.contracts.governance", field="transition")
    if actor == ACTOR_AUTOMATION and target_state in {REVIEW_STATE_HUMAN_CONFIRMED, REVIEW_STATE_DEPRECATED}:
        return _contract_failure("governance_transition_invalid", "governance_transition_requires_human", owner="typed_knowledge.contracts.governance", field="actor")
    return target_state


def apply_review_state_transition(*, current_state: str, target_state: str, actor: str) -> str:
    result = try_apply_review_state_transition(current_state=current_state, target_state=target_state, actor=actor)
    if isinstance(result, Failure):
        raise_typed_knowledge_legacy(result)
    return result
