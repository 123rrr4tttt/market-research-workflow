from __future__ import annotations

from ...contracts.schemas.writing import (
    PrimaryWritingLoopStage,
    WritingBaselineCapability,
    WritingBaselineDeltaMatrix,
    WritingPrimaryLoopCheckpoint,
    WritingPrimaryLoopState,
)

_CANONICAL_PRIMARY_LOOP: tuple[PrimaryWritingLoopStage, ...] = (
    "document_ready",
    "editing",
    "saved",
    "context_loaded",
    "citation_applied",
    "action_executed",
    "write_back_ready",
)


def build_wave_a_baseline_matrix() -> WritingBaselineDeltaMatrix:
    return WritingBaselineDeltaMatrix(
        contract_version="writing.wave_c.e8.v1",
        capabilities=[
            WritingBaselineCapability(
                capability_id="document_lifecycle",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["api/writing.py", "services/writing/document_service.py"],
                notes="Open/create/read/patch/autosave/version conflict path already exists.",
            ),
            WritingBaselineCapability(
                capability_id="evidence_lookup_keyword_cards",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["api/writing.py", "services/writing/keyword_card_service.py"],
                notes="Selection-driven keyword-card retrieval is already available.",
            ),
            WritingBaselineCapability(
                capability_id="citation_acceptance",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["api/writing.py", "services/writing/citation_service.py"],
                notes="Citation upsert/list is already wired for writing documents.",
            ),
            WritingBaselineCapability(
                capability_id="llm_action_dispatch_and_audit",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["api/writing.py", "services/writing/llm_action_service.py"],
                notes="Action dispatch/history/detail contract already exists.",
            ),
            WritingBaselineCapability(
                capability_id="markdown_export_with_citation_rebuild",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["api/writing.py", "services/writing/document_service.py", "services/writing/citation_service.py"],
                notes="Markdown export already rebuilds references from accepted citations.",
            ),
            WritingBaselineCapability(
                capability_id="graph_context_adapter_boundary",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["contracts/schemas/writing.py", "services/writing/keyword_card_service.py"],
                notes="Graph context is consumed via writing adapter boundary and remains optional.",
            ),
            WritingBaselineCapability(
                capability_id="cross_theme_dependency_merge_gate",
                designed=True,
                implemented=True,
                still_open=False,
                owner_modules=["contracts/schemas/writing.py", "services/writing/primary_loop_service.py"],
                notes="Writing tracks graph/llm/frontend dependency topology as consume-only boundaries.",
            ),
            WritingBaselineCapability(
                capability_id="non_markdown_export_adapters",
                designed=True,
                implemented=False,
                still_open=True,
                owner_modules=["api/writing.py"],
                notes="Non-Markdown export is intentionally staged after Wave-A.",
            ),
        ],
        non_goals=[
            "Do not redesign graph storage or graph editing architecture in Wave-A.",
            "Do not replace writing API with generalized workflow/agent orchestration in Wave-A.",
            "Do not treat docx/latex export as implemented in Wave-A.",
        ],
        repo_reality="Writing page and writing API already exist; Wave-A freezes contract boundaries instead of rebuilding from zero.",
    )


def evaluate_primary_loop_state(checkpoint: WritingPrimaryLoopCheckpoint) -> WritingPrimaryLoopState:
    completed: list[PrimaryWritingLoopStage] = []
    if checkpoint.document_id is not None:
        completed.append("document_ready")
    if checkpoint.has_markdown_body:
        completed.append("editing")
    if checkpoint.saved_version is not None:
        completed.append("saved")
    if checkpoint.has_context_cards:
        completed.append("context_loaded")
    if checkpoint.has_accepted_citation:
        completed.append("citation_applied")
    if checkpoint.llm_action_invoked:
        completed.append("action_executed")
    if checkpoint.has_write_back_candidate:
        completed.append("write_back_ready")

    ordering_violations: list[str] = []
    next_required_stage: PrimaryWritingLoopStage | None = None
    for index, stage in enumerate(_CANONICAL_PRIMARY_LOOP):
        if stage in completed:
            continue
        next_required_stage = stage
        for later in _CANONICAL_PRIMARY_LOOP[index + 1 :]:
            if later in completed:
                ordering_violations.append(f"{later}_before_{stage}")
        break

    no_graph_happy_path_complete = next_required_stage is None and not checkpoint.graph_context_attached
    graph_contract_ok = not checkpoint.graph_context_attached or str(checkpoint.graph_handoff_contract_version or "").startswith("graph_handoff.v")
    llm_consumer_ok = str(checkpoint.llm_consumer or "writing.llm_action").strip() == "writing.llm_action"
    frontend_ok = bool(str(checkpoint.frontend_surface or "").strip())
    cross_theme_dependency_gate = {
        "contract_version": "writing.cross_theme_gate.e8.v1",
        "topology": ["writing<->graph", "writing<->llm", "writing<->frontend"],
        "graph": {
            "attached": checkpoint.graph_context_attached,
            "handoff_contract_version": checkpoint.graph_handoff_contract_version,
            "status": "ready" if graph_contract_ok else "blocked",
            "boundary": "writing consumes graph context adapter only",
        },
        "llm": {
            "consumer": checkpoint.llm_consumer or "writing.llm_action",
            "status": "ready" if llm_consumer_ok else "blocked",
            "boundary": "writing consumes llm platform routing/audit only",
        },
        "frontend": {
            "surface": checkpoint.frontend_surface,
            "status": "ready" if frontend_ok else "blocked",
            "boundary": "writing backend does not own frontend topology refactor",
        },
        "passed": graph_contract_ok and llm_consumer_ok and frontend_ok,
    }
    return WritingPrimaryLoopState(
        stages=completed,
        next_required_stage=next_required_stage,
        always_on_layers=["core_document_loop", "evidence_context", "citation_handling", "llm_action", "write_back"],
        optional_layers=["graph_context_adapter"],
        no_graph_happy_path_complete=no_graph_happy_path_complete,
        selection_level_entry_supported=True,
        document_level_entry_supported=True,
        ordering_violations=ordering_violations,
        cross_theme_dependency_gate=cross_theme_dependency_gate,
    )
