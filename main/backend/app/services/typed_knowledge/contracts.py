from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Mapping

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
)
DOWNSTREAM_CONSUMER_FACETS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "search": ("project_key", "primary_type_node_key", "topic_cluster_keys", "booklet_keys", "quality_grade"),
        "graph": ("knowledge_item_key", "primary_type_node_key", "topic_cluster_keys", "review_state"),
        "writing": ("knowledge_item_key", "canonical_statement", "evidence_refs", "locale", "quality_grade"),
        "reporting": ("project_key", "topic_cluster_keys", "booklet_keys", "quality_grade", "review_state"),
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


def _validate_review_state(review_state: str, *, object_name: str) -> None:
    if review_state not in ALLOWED_REVIEW_STATES:
        raise TypedKnowledgeContractError(f"{object_name}_invalid_review_state:{review_state}")


def _validate_quality_grade(quality_grade: str | None) -> None:
    if quality_grade is None:
        return
    if quality_grade not in ALLOWED_QUALITY_GRADES:
        raise TypedKnowledgeContractError(f"knowledge_item_invalid_quality_grade:{quality_grade}")


def _validate_locale(locale: str | None, locale_variants: Mapping[str, str]) -> None:
    if locale is not None and not locale.strip():
        raise TypedKnowledgeContractError("knowledge_item_invalid_locale")
    if not locale_variants:
        return
    if locale is None:
        raise TypedKnowledgeContractError("knowledge_item_locale_variants_require_locale")
    for key, value in locale_variants.items():
        if not key.strip() or not str(value).strip():
            raise TypedKnowledgeContractError("knowledge_item_invalid_locale_variants")


def validate_type_node(node: TypeNode) -> None:
    if not node.key or not node.project_key:
        raise TypedKnowledgeContractError("type_node_missing_identity")
    if not node.label.strip():
        raise TypedKnowledgeContractError("type_node_missing_label")
    _validate_review_state(node.review_state, object_name="type_node")


def validate_knowledge_item(item: KnowledgeItem) -> None:
    if not item.key or not item.project_key:
        raise TypedKnowledgeContractError("knowledge_item_missing_identity")
    if not item.canonical_statement.strip():
        raise TypedKnowledgeContractError("knowledge_item_missing_statement")
    if not item.primary_type_node_key.strip():
        raise TypedKnowledgeContractError("knowledge_item_missing_primary_type")
    if not item.evidence_refs:
        raise TypedKnowledgeContractError("knowledge_item_missing_provenance")
    _validate_quality_grade(item.quality_grade)
    _validate_locale(item.locale, item.locale_variants)
    _validate_review_state(item.review_state, object_name="knowledge_item")


def validate_topic_cluster(cluster: TopicCluster) -> None:
    if not cluster.key or not cluster.project_key:
        raise TypedKnowledgeContractError("topic_cluster_missing_identity")
    if not cluster.label.strip():
        raise TypedKnowledgeContractError("topic_cluster_missing_label")
    _validate_review_state(cluster.review_state, object_name="topic_cluster")


def validate_booklet(booklet: Booklet) -> None:
    if not booklet.key or not booklet.project_key:
        raise TypedKnowledgeContractError("booklet_missing_identity")
    if not booklet.title.strip():
        raise TypedKnowledgeContractError("booklet_missing_title")
    _validate_review_state(booklet.review_state, object_name="booklet")


def validate_relationships(
    *,
    type_nodes: tuple[TypeNode, ...],
    knowledge_items: tuple[KnowledgeItem, ...],
    topic_clusters: tuple[TopicCluster, ...],
    booklets: tuple[Booklet, ...],
) -> None:
    type_node_keys = {item.key for item in type_nodes}
    knowledge_item_keys = {item.key for item in knowledge_items}
    topic_cluster_keys = {item.key for item in topic_clusters}
    booklet_keys = {item.key for item in booklets}
    type_nodes_by_key = {item.key: item for item in type_nodes}
    topic_clusters_by_key = {item.key: item for item in topic_clusters}
    booklets_by_key = {item.key: item for item in booklets}
    knowledge_items_by_key = {item.key: item for item in knowledge_items}

    for node in type_nodes:
        validate_type_node(node)
        if node.primary_parent_key and node.primary_parent_key not in type_node_keys:
            raise TypedKnowledgeContractError(f"type_node_unknown_parent:{node.primary_parent_key}")
        if node.primary_parent_key:
            parent = type_nodes_by_key[node.primary_parent_key]
            if parent.project_key != node.project_key:
                raise TypedKnowledgeContractError(f"type_node_cross_project_parent:{node.primary_parent_key}")

    for item in knowledge_items:
        validate_knowledge_item(item)
        if item.primary_type_node_key not in type_node_keys:
            raise TypedKnowledgeContractError(f"knowledge_item_unknown_primary_type:{item.primary_type_node_key}")
        if type_nodes_by_key[item.primary_type_node_key].project_key != item.project_key:
            raise TypedKnowledgeContractError(
                f"knowledge_item_cross_project_primary_type:{item.primary_type_node_key}"
            )
        unknown_topic_keys = set(item.topic_cluster_keys) - topic_cluster_keys
        if unknown_topic_keys:
            raise TypedKnowledgeContractError(f"knowledge_item_unknown_topic_clusters:{sorted(unknown_topic_keys)}")
        cross_project_topics = sorted(
            key for key in item.topic_cluster_keys if topic_clusters_by_key[key].project_key != item.project_key
        )
        if cross_project_topics:
            raise TypedKnowledgeContractError(f"knowledge_item_cross_project_topic_clusters:{cross_project_topics}")
        unknown_booklet_keys = set(item.booklet_keys) - booklet_keys
        if unknown_booklet_keys:
            raise TypedKnowledgeContractError(f"knowledge_item_unknown_booklets:{sorted(unknown_booklet_keys)}")
        cross_project_booklets = sorted(key for key in item.booklet_keys if booklets_by_key[key].project_key != item.project_key)
        if cross_project_booklets:
            raise TypedKnowledgeContractError(f"knowledge_item_cross_project_booklets:{cross_project_booklets}")

    for cluster in topic_clusters:
        validate_topic_cluster(cluster)
        unknown_item_keys = set(cluster.knowledge_item_keys) - knowledge_item_keys
        if unknown_item_keys:
            raise TypedKnowledgeContractError(f"topic_cluster_unknown_knowledge_items:{sorted(unknown_item_keys)}")
        cross_project_items = sorted(
            key for key in cluster.knowledge_item_keys if knowledge_items_by_key[key].project_key != cluster.project_key
        )
        if cross_project_items:
            raise TypedKnowledgeContractError(f"topic_cluster_cross_project_knowledge_items:{cross_project_items}")

    for booklet in booklets:
        validate_booklet(booklet)
        unknown_type_keys = set(booklet.included_type_node_keys) - type_node_keys
        if unknown_type_keys:
            raise TypedKnowledgeContractError(f"booklet_unknown_type_nodes:{sorted(unknown_type_keys)}")
        cross_project_types = sorted(
            key for key in booklet.included_type_node_keys if type_nodes_by_key[key].project_key != booklet.project_key
        )
        if cross_project_types:
            raise TypedKnowledgeContractError(f"booklet_cross_project_type_nodes:{cross_project_types}")
        unknown_topic_keys = set(booklet.included_topic_cluster_keys) - topic_cluster_keys
        if unknown_topic_keys:
            raise TypedKnowledgeContractError(f"booklet_unknown_topic_clusters:{sorted(unknown_topic_keys)}")
        cross_project_topics = sorted(
            key
            for key in booklet.included_topic_cluster_keys
            if topic_clusters_by_key[key].project_key != booklet.project_key
        )
        if cross_project_topics:
            raise TypedKnowledgeContractError(f"booklet_cross_project_topic_clusters:{cross_project_topics}")
        unknown_item_keys = set(booklet.included_knowledge_item_keys) - knowledge_item_keys
        if unknown_item_keys:
            raise TypedKnowledgeContractError(f"booklet_unknown_knowledge_items:{sorted(unknown_item_keys)}")
        cross_project_items = sorted(
            key
            for key in booklet.included_knowledge_item_keys
            if knowledge_items_by_key[key].project_key != booklet.project_key
        )
        if cross_project_items:
            raise TypedKnowledgeContractError(f"booklet_cross_project_knowledge_items:{cross_project_items}")


def build_downstream_contract_draft(item: KnowledgeItem) -> DownstreamKnowledgeContractDraft:
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
    )


def validate_downstream_contract_draft(contract: DownstreamKnowledgeContractDraft) -> None:
    if not contract.knowledge_item_key or not contract.project_key:
        raise TypedKnowledgeContractError("downstream_contract_missing_identity")
    if not contract.canonical_statement.strip():
        raise TypedKnowledgeContractError("downstream_contract_missing_statement")
    if not contract.primary_type_node_key.strip():
        raise TypedKnowledgeContractError("downstream_contract_missing_primary_type")
    if not contract.evidence_refs:
        raise TypedKnowledgeContractError("downstream_contract_missing_provenance")
    _validate_quality_grade(contract.quality_grade)
    _validate_locale(contract.locale, contract.locale_variants)
    _validate_review_state(contract.review_state, object_name="downstream_contract")
    expected_scope = REVIEW_STATE_VISIBILITY_SCOPE[contract.review_state]
    if contract.visibility_scope != expected_scope:
        raise TypedKnowledgeContractError("downstream_contract_visibility_scope_mismatch")


def apply_review_state_transition(*, current_state: str, target_state: str, actor: str) -> str:
    _validate_review_state(current_state, object_name="governance_current")
    _validate_review_state(target_state, object_name="governance_target")
    if actor not in ALLOWED_GOVERNANCE_ACTORS:
        raise TypedKnowledgeContractError(f"governance_unknown_actor:{actor}")
    if current_state == REVIEW_STATE_DEPRECATED and target_state != REVIEW_STATE_DEPRECATED:
        raise TypedKnowledgeContractError("governance_transition_from_deprecated_forbidden")
    if actor == ACTOR_AUTOMATION and target_state in {REVIEW_STATE_HUMAN_CONFIRMED, REVIEW_STATE_DEPRECATED}:
        raise TypedKnowledgeContractError("governance_transition_requires_human")
    return target_state
