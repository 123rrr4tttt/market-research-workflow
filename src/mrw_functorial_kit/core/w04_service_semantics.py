"""Kit projection for W04 service failure families."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


ClueChainFailureCode = Literal[
    "input_invalid",
    "provider_result_invalid",
    "chain_not_found",
    "object_not_found",
    "chain_closed",
    "graph_projection_invalid",
]

DocumentQueryFailureCode = Literal[
    "filter_invalid",
    "sort_invalid",
    "statement_invalid",
    "result_envelope_invalid",
    "document_not_found",
]

GraphBackfillFailureCode = Literal["transaction_failed"]

SearchFailureCode = Literal[
    "backend_unavailable",
    "embedding_failed",
    "vector_search_failed",
    "global_vector_object_invalid",
    "evidence_hit_invalid",
    "retrieval_run_invalid",
]

TypedKnowledgeContractFailureCode = Literal[
    "object_contract_invalid",
    "relationship_contract_invalid",
    "downstream_contract_invalid",
    "writing_handoff_contract_invalid",
    "writing_context_contract_invalid",
    "governance_transition_invalid",
]

WorkflowGraphFailureCode = Literal[
    "contract_invalid",
    "integrity_invalid",
    "object_not_found",
    "revision_conflict",
    "executor_not_registered",
    "required_input_missing",
    "store_unavailable",
]

WritingFailureCode = Literal[
    "document_not_found",
    "version_conflict",
    "card_not_found",
    "action_not_found",
    "action_execution_failed",
]


clue_chain_failures = define_failure_family(
    "clue_chain.failure",
    get_args(ClueChainFailureCode),
)
document_query_failures = define_failure_family(
    "document_query.failure",
    get_args(DocumentQueryFailureCode),
)
graph_backfill_failures = define_failure_family(
    "graph.backfill.failure",
    get_args(GraphBackfillFailureCode),
)
search_failures = define_failure_family(
    "search.failure",
    get_args(SearchFailureCode),
)
typed_knowledge_contract_failures = define_failure_family(
    "typed_knowledge.contract_failure",
    get_args(TypedKnowledgeContractFailureCode),
)
workflow_graph_failures = define_failure_family(
    "workflow_graph.failure",
    get_args(WorkflowGraphFailureCode),
)
writing_failures = define_failure_family(
    "writing.failure",
    get_args(WritingFailureCode),
)


__all__ = [
    "clue_chain_failures",
    "document_query_failures",
    "graph_backfill_failures",
    "search_failures",
    "typed_knowledge_contract_failures",
    "workflow_graph_failures",
    "writing_failures",
]
