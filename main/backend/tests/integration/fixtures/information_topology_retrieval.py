"""Small structural fixture; it contains no research findings."""
from app.services.information_topology.contracts import BoundRef, ElementRef
from app.services.information_topology.modules.retrieval import DomainVocabulary


def vocabulary(project_key="it-retrieval"):
    source = BoundRef(ElementRef(project_key, "retrieval", "brief", "source", "analysis-brief"), "brief-r1", "brief-digest")
    return DomainVocabulary("结构测试域", ("现场", "行动者"), ("管理",), ("制度",),
                            ("背景",), ("来源池A",), ("A", "B", "C", "D"), source)


def source_bundle():
    graph = {
        "证据口径": 2, "线索ID": "clue:test:1", "轮次": "run:test:1",
        "现场": "现场:test", "生成日": "2026-09-24",
        "节点": [
            {"节点ID": "现场:test", "类型": "现场", "名称": "测试现场"},
            {"节点ID": "行动者:test", "类型": "行动者", "名称": "测试行动者"},
        ],
        "边": [{"边ID": "e:test:1", "边类型": "管理", "从": "行动者:test", "到": "现场:test",
                "大纲节": "背景", "关系类": ["线索链", "证据网"], "池": ["来源池A"],
                "证据ID": ["ev:test:1"],
                "判断": "仅用于结构往返", "范围": "测试范围", "判断版本": "v1"}],
        "证据": [{"证据ID": "ev:test:1", "名称": "测试材料标题", "边ID": "e:test:1",
                   "材料ID": "item:test:1", "档": "A", "打架": "否", "作用": "支持",
                   "原文定位": "第1段", "原文摘录": "测试原文", "适用范围": "测试范围",
                   "推论说明": "结构测试", "证明对象": "事实关系", "来源角色": "直接记录",
                   "独立组": "src:test", "上游材料ID": [], "冲突证据ID": []}],
        "线索": [{"线索ID": "clue:test:1", "轮次": "run:test:1", "现场": "现场:test",
                   "名称": "线索链：测试现场",
                   "链状态": "开", "下一跳": "继续查证", "顺序": ["行动者:test", "e:test:1", "行动者:test"]}],
    }
    return {
        "namespace": "retrieval",
        "source_revision": "folder-r1",
        "domain_vocabulary": {"域名": "结构测试域", "节点类型": ["现场", "行动者"],
                              "边类型": ["管理"], "问题意识视角": ["制度"],
                              "大纲节": ["背景"], "池": ["来源池A"], "档": ["A", "B", "C", "D"]},
        "domain_source_ref": {"ref": {"project_key": "it-retrieval", "module_id": "retrieval",
                                       "namespace": "brief", "type_id": "source", "local_id": "analysis-brief"},
                              "observed_revision": "brief-r1", "content_digest": "brief-digest"},
        "graph": graph,
        "materials": [{"材料ID": "item:test:1", "标题": "测试材料标题", "档": "A"}],
        "source_routes": [{"route_id": "route:test:1", "pool": "来源池A", "status": "planned"}],
        "keyword_plans": [{"plan_id": "query:test:1", "kind": "query", "expression": "测试查询式",
                            "execution_status": "not_executed", "source_route_id": "route:test:1"}],
        "attempts": [{"attempt_id": "attempt:test:1", "query_id": "query:test:1",
                       "round_id": "run:test:1", "clue_key": "clue:test:1", "executed_at": "2026-09-24T00:00:00Z",
                       "tool": "fixture", "actual_query": "测试查询式", "result": "访问失败",
                       "source_ids": [], "material_ids": [], "next_step": "停止", "result_note": "结构样例",
                       "raw_return_location": ""}],
        "source_registry": [], "candidates": [], "gaps": [],
        "report_body": "报告原文由报告 owner 保管。",
        "report_ref": {"path": "报告.md", "revision": "report-r1"},
        "original_files": {"来源池.md": "# 原始来源路线\nroute:test:1\n",
                           "初始关键词池.md": "query:test:1\t测试查询式\n"},
    }
