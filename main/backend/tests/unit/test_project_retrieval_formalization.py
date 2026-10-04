from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

from app.services.information_topology.modules.retrieval import validate_evidence_v2
from app.services.project_retrieval.formalization import formalize_document


BODY = "水务机构的年度记录指出，供水收费收入用于维护输配水设施。该记录只覆盖本报告年度。"
EXCERPT = "供水收费收入用于维护输配水设施"


def payload() -> dict:
    return {
        "project_key": "hk_water_investigation",
        "run_id": "retrieval-run:1",
        "plan_id": "retrieval-plan:1",
        "route_id": "route:finance",
        "query_id": "query:03",
        "candidate_id": "candidate:1",
        "document_id": 19,
        "title": "年度记录",
        "url": "https://example.invalid/annual",
        "body": BODY,
        "body_digest": sha256(BODY.encode("utf-8")).hexdigest(),
        "document_updated_at": "2026-09-26T10:00:00Z",
        "domain_vocabulary": {
            "域名": "香港水资源与水治理",
            "节点类型": ["现场", "制度安排", "货币流", "技术物"],
            "边类型": ["分配", "依赖"],
            "大纲节": ["1", "3"],
            "池": ["A", "B"],
            "档": ["A", "B", "C", "D"],
        },
        "query": {"query_id": "query:03", "route_id": "route:finance", "expression": "收费 收入 维护"},
        # This route intentionally does not list 现场.  A clue scene is a
        # profile requirement and may use any node type in the bound domain
        # vocabulary; claim endpoint types remain domain-validated.
        "source_route": {
            "route_id": "route:finance", "pool": "A", "outline_sections": ["1", "3"],
            "node_types": ["货币流", "制度安排"], "target_edges": ["分配"],
        },
    }


def response() -> dict:
    return {
        "status": "proposed",
        "proposal": {
            "nodes": [
                {"local_key": "scene", "name": "年度记录现场", "type_id": "node:现场"},
                {"local_key": "revenue", "name": "供水收费收入", "type_id": "node:货币流"},
                {"local_key": "maintenance", "name": "设施维护安排", "type_id": "node:制度安排"},
            ],
            "judgment": {
                "from_key": "revenue", "to_key": "maintenance", "edge_type": "分配",
                "judgment": "供水收费收入被分配到输配水设施维护。", "scope": "该机构本报告年度",
                "outline_section": "1", "pools": ["A"], "relation_classes": ["证据网"],
            },
            "evidence": {
                "original_location": "document.body 第一句", "original_excerpt": EXCERPT,
                "grade": "B", "conflict": False, "effect": "支持",
                "applicable_scope": "该机构本报告年度", "inference_note": "原文直接说明收入用途。",
                "proves": "事实关系", "source_role": "机构自报", "independence_group": "document:19",
            },
            "clue": {"name": "收费收入的维护用途", "scene_key": "scene"},
        },
        "gaps": ["该记录未说明分配比例"],
    }


def test_formalize_document_returns_profile_validated_proposal_with_source_provenance():
    captured: list[str] = []

    def invoke(prompt: str):
        captured.append(prompt)
        return SimpleNamespace(content=response())

    result = formalize_document(payload(), model_invoke=invoke)

    assert result["status"] == "proposed"
    assert len(captured) == 1 and BODY in captured[0]
    proposal = result["proposal"]
    assert proposal["clue"]["scene_key"] == "scene"
    assert proposal["provenance"] == {
        "project_key": "hk_water_investigation", "plan_id": "retrieval-plan:1",
        "route_id": "route:finance", "query_id": "query:03", "candidate_id": "candidate:1",
        "document_id": "19", "document_url": "https://example.invalid/annual",
        "document_updated_at": "2026-09-26T10:00:00Z",
        "body_digest": sha256(BODY.encode("utf-8")).hexdigest(), "run_id": "retrieval-run:1",
    }
    assert validate_evidence_v2(proposal["evidence"]) is None
    assert result["gaps"] == ["该记录未说明分配比例"]


def test_formalize_document_returns_no_claim_without_synthesizing_a_proposal():
    result = formalize_document(
        payload(), model_invoke=lambda _: {"status": "no_claim", "gaps": ["正文没有可核实关系"]})

    assert result == {"status": "no_claim", "gaps": ["正文没有可核实关系"]}


def test_formalize_document_retries_unparseable_output_then_validates_result():
    prompts: list[str] = []

    def invoke(prompt: str):
        prompts.append(prompt)
        if len(prompts) == 1:
            return '{"status":"no_claim","gaps":["待核实"]}\nextra text'
        return {"status": "no_claim", "gaps": ["正文不能支持该关系"]}

    result = formalize_document(payload(), model_invoke=invoke)

    assert len(prompts) == 2
    assert result == {"status": "no_claim", "gaps": ["正文不能支持该关系"]}


def test_formalize_document_retries_invalid_claim_shape_without_accepting_it():
    prompts: list[str] = []

    def invoke(prompt: str):
        prompts.append(prompt)
        if len(prompts) == 1:
            return {"status": "no_claim", "proposal": response()["proposal"], "gaps": ["待核实"]}
        return {"status": "no_claim", "gaps": ["正文不能支持该关系"]}

    result = formalize_document(payload(), model_invoke=invoke)

    assert len(prompts) == 2
    assert "response" in prompts[1]
    assert result == {"status": "no_claim", "gaps": ["正文不能支持该关系"]}


def test_formalize_document_fails_explicitly_when_provider_is_unavailable():
    def unavailable(_: str):
        raise RuntimeError

    result = formalize_document(payload(), model_invoke=unavailable)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORMALIZATION_PROVIDER_FAILED"


def test_formalize_document_rejects_a_non_verbatim_quote():
    invalid = response()
    invalid["proposal"]["evidence"]["original_excerpt"] = "模型改写过的引文"

    result = formalize_document(payload(), model_invoke=lambda _: invalid)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORMALIZATION_PROPOSAL_INVALID"
    assert result["error"]["context"]["path"] == "response.proposal.evidence.original_excerpt"


def test_formalize_document_rejects_route_classification_drift():
    invalid = response()
    invalid["proposal"]["judgment"]["edge_type"] = "依赖"

    result = formalize_document(payload(), model_invoke=lambda _: invalid)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORMALIZATION_PROPOSAL_INVALID"
    assert result["error"]["context"]["path"] == "response.proposal.judgment.edge_type"


def test_formalize_document_rejects_evidence_v2_role_drift():
    invalid = response()
    invalid["proposal"]["evidence"]["source_role"] = "官方来源"

    result = formalize_document(payload(), model_invoke=lambda _: invalid)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORMALIZATION_PROPOSAL_INVALID"
    assert result["error"]["context"]["path"] == "response.proposal.evidence"


def test_formalize_document_rejects_clue_without_a_scene_node():
    invalid = response()
    invalid["proposal"]["nodes"] = [node for node in invalid["proposal"]["nodes"] if node["local_key"] != "scene"]

    result = formalize_document(payload(), model_invoke=lambda _: invalid)

    assert result["status"] == "failed"
    assert result["error"]["context"]["path"] == "response.proposal.clue.scene_key"


def test_formalize_document_rejects_body_identity_drift_before_calling_model():
    invalid_payload = deepcopy(payload())
    invalid_payload["body_digest"] = "0" * 64
    called = False

    def invoke(_: str):
        nonlocal called
        called = True
        return response()

    result = formalize_document(invalid_payload, model_invoke=invoke)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORMALIZATION_INPUT_INVALID"
    assert result["error"]["context"]["path"] == "document.body_digest"
    assert called is False
