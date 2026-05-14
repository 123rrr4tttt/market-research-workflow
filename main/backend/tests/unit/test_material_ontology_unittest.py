from __future__ import annotations

import pytest

from app.services.agent_runtime.material_ontology import (
    EXTERNAL_DISCOVERY,
    EXTERNAL_INGEST,
    INTERNAL_EXISTING,
    INTERNAL_GENERATED,
    SOURCE_CATALOG,
    capability_material_category,
    classify_material_intent,
)

pytestmark = pytest.mark.unit


def test_material_ontology_distinguishes_existing_project_materials_from_source_catalog() -> None:
    existing = classify_material_intent("项目库里已有资料有哪些")
    assert existing.category == INTERNAL_EXISTING
    assert existing.scope == "internal"
    assert existing.material_state == "existing"

    catalog = classify_material_intent("当前有哪些来源库 item")
    assert catalog.category == SOURCE_CATALOG
    assert catalog.material_state == "catalog"


def test_material_ontology_routes_supplement_and_writing_contexts() -> None:
    supplement = classify_material_intent("帮我补充资料")
    assert supplement.category == EXTERNAL_DISCOVERY
    assert supplement.scope == "mixed"
    assert supplement.material_state == "to_collect"

    abstract_supplement = classify_material_intent("帮我搜集一些机器人资料")
    assert abstract_supplement.category == EXTERNAL_DISCOVERY
    assert abstract_supplement.scope == "mixed"
    assert abstract_supplement.material_state == "to_collect"

    reference_supplement = classify_material_intent("帮我补充参考来源")
    assert reference_supplement.category == EXTERNAL_DISCOVERY
    assert reference_supplement.scope == "external"
    assert reference_supplement.material_state == "to_collect"

    writing_internal = classify_material_intent("写作时帮我补充资料")
    assert writing_internal.category == INTERNAL_EXISTING
    assert writing_internal.work_context == "writing"

    writing_search = classify_material_intent("写作的时候帮我搜索一些资料")
    assert writing_search.category == INTERNAL_EXISTING
    assert writing_search.scope == "internal"
    assert writing_search.work_context == "writing"

    writing_text_context = classify_material_intent("这段正文需要补一些已有数据")
    assert writing_text_context.category == INTERNAL_EXISTING
    assert writing_text_context.scope == "internal"
    assert writing_text_context.work_context == "writing"

    writing_collected_context = classify_material_intent("论文里先用已经采集的数据补证据")
    assert writing_collected_context.category == INTERNAL_EXISTING
    assert writing_collected_context.scope == "internal"

    writing_existing_reference_context = classify_material_intent("这段正文先用项目库中既有参考来源补证据")
    assert writing_existing_reference_context.category == INTERNAL_EXISTING
    assert writing_existing_reference_context.scope == "internal"

    writing_collected_abstract = classify_material_intent("这段文字用已入库资料补一些事实")
    assert writing_collected_abstract.category == INTERNAL_EXISTING
    assert writing_collected_abstract.scope == "internal"
    assert writing_collected_abstract.work_context == "writing"

    writing_gap_escalation = classify_material_intent("这段正文已有资料不足，帮我再找参考来源")
    assert writing_gap_escalation.category == EXTERNAL_DISCOVERY
    assert writing_gap_escalation.scope == "mixed"
    assert writing_gap_escalation.work_context == "writing"

    writing_outside_abstract = classify_material_intent("选区里需要补一点站外公开来源")
    assert writing_outside_abstract.category == EXTERNAL_DISCOVERY
    assert writing_outside_abstract.scope == "external"
    assert writing_outside_abstract.work_context == "writing"

    writing_external = classify_material_intent("写作时帮我补充外部资料")
    assert writing_external.category == EXTERNAL_DISCOVERY
    assert writing_external.work_context == "writing"

    writing_external_ingest = classify_material_intent("写作时帮我补充外部资料并入库")
    assert writing_external_ingest.category == EXTERNAL_INGEST
    assert writing_external_ingest.risk == "write_external"


def test_capability_material_categories_are_shared_with_ui_contract() -> None:
    assert capability_material_category("project.context.bundle") == INTERNAL_EXISTING
    assert capability_material_category("source_library.item.list") == SOURCE_CATALOG
    assert capability_material_category("source.web.search") == EXTERNAL_DISCOVERY
    assert capability_material_category("ingest.source_library.run") == EXTERNAL_INGEST
    assert capability_material_category("ingest.url_pool.submit") == EXTERNAL_INGEST
    assert capability_material_category("ingest.url_pool.status") == INTERNAL_EXISTING
    assert capability_material_category("source.history.read") == INTERNAL_EXISTING
    assert capability_material_category("agent_long_task.stage.update") == INTERNAL_GENERATED
