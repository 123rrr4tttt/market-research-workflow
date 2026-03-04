from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.main import app as backend_app
    from app.services.graph.models import Graph, GraphEdge, GraphNode

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _ok_doc(doc_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=doc_id,
        extracted_data={
            "sentiment": {"topic": "robotics"},
            "market": {"state": "CA", "game": "Powerball", "report_date": "2025-01-01"},
            "policy": {"state": "CA", "policy_type": "regulation"},
            "company_structured": {"entities": [{"text": "Acme", "type": "company"}], "topics": ["company"]},
            "product_structured": {"entities": [{"text": "RoboArm", "type": "product"}], "topics": ["product"]},
            "operation_structured": {"entities": [{"text": "Amazon", "type": "platform"}], "topics": ["operation"]},
            "entities_relations": {"entities": [{"text": "Acme", "type": "ORG"}], "relations": []},
        },
        publish_date=datetime(2025, 1, 1).date(),
        created_at=datetime(2025, 1, 1),
        state="CA",
        title=f"doc-{doc_id}",
        status="published",
        summary="summary",
        uri=f"https://example.com/{doc_id}",
        source=None,
        doc_type="market_info",
    )


class _FakeResult:
    def __init__(self, docs):
        self._docs = docs

    def scalars(self):
        return self

    def all(self):
        return self._docs


class _FakeSession:
    def __init__(self, docs):
        self._docs = docs

    def execute(self, _query):  # noqa: ANN001
        return _FakeResult(self._docs)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False


class _FakeBindProject:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False


def _social_graph() -> Graph:
    post = GraphNode(type="Post", id="1", properties={})
    keyword = GraphNode(type="Keyword", id="k1", properties={})
    entity = GraphNode(type="Entity", id="e1", properties={})
    topic = GraphNode(type="Topic", id="t1", properties={})
    tag = GraphNode(type="SentimentTag", id="s1", properties={})
    user = GraphNode(type="User", id="u1", properties={})
    sub = GraphNode(type="Subreddit", id="r1", properties={})
    g = Graph(
        nodes={
            "Post:1": post,
            "Keyword:k1": keyword,
            "Entity:e1": entity,
            "Topic:t1": topic,
            "SentimentTag:s1": tag,
            "User:u1": user,
            "Subreddit:r1": sub,
        },
        edges=[
            GraphEdge(type="MENTIONS_KEYWORD", from_node=post, to_node=keyword, properties={}),
            GraphEdge(type="MENTIONS_ENTITY", from_node=post, to_node=entity, properties={}),
            GraphEdge(type="HAS_TOPIC", from_node=post, to_node=topic, properties={}),
        ],
        schema_version="v1",
    )
    return g


def _market_graph() -> Graph:
    market = GraphNode(type="MarketData", id="1", properties={})
    state = GraphNode(type="State", id="CA", properties={})
    seg = GraphNode(type="Segment", id="powerball", properties={})
    entity = GraphNode(type="Entity", id="e1", properties={})
    return Graph(
        nodes={
            "MarketData:1": market,
            "State:CA": state,
            "Segment:powerball": seg,
            "Entity:e1": entity,
        },
        edges=[
            GraphEdge(type="IN_STATE", from_node=market, to_node=state, properties={}),
            GraphEdge(type="HAS_SEGMENT", from_node=market, to_node=seg, properties={}),
            GraphEdge(type="MENTIONS_ENTITY", from_node=market, to_node=entity, properties={}),
        ],
        schema_version="v1",
    )


def _policy_graph() -> Graph:
    policy = GraphNode(type="Policy", id="1", properties={})
    state = GraphNode(type="State", id="CA", properties={})
    ptype = GraphNode(type="PolicyType", id="regulation", properties={})
    keypoint = GraphNode(type="KeyPoint", id="k1", properties={})
    entity = GraphNode(type="Entity", id="e1", properties={})
    return Graph(
        nodes={
            "Policy:1": policy,
            "State:CA": state,
            "PolicyType:regulation": ptype,
            "KeyPoint:k1": keypoint,
            "Entity:e1": entity,
        },
        edges=[
            GraphEdge(type="APPLIES_TO_STATE", from_node=policy, to_node=state, properties={}),
            GraphEdge(type="HAS_TYPE", from_node=policy, to_node=ptype, properties={}),
            GraphEdge(type="HAS_KEYPOINT", from_node=policy, to_node=keypoint, properties={}),
            GraphEdge(type="MENTIONS_ENTITY", from_node=policy, to_node=entity, properties={}),
        ],
        schema_version="v1",
    )


class _FakeMarketAdapter:
    def to_normalized(self, _doc):  # noqa: ANN001
        return SimpleNamespace(stat_id=1)


class _FakePolicyAdapter:
    def to_normalized(self, doc):  # noqa: ANN001
        return SimpleNamespace(
            doc_id=doc.id,
            state="CA",
            policy_type="regulation",
            publish_date=datetime(2025, 1, 1),
        )


class AdminGraphStandardizationIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"admin graph integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "admin-graph-std"}

    def _patch_common(self):
        docs = [_ok_doc(1)]
        return [
            patch("app.api.admin.SessionLocal", return_value=_FakeSession(docs)),
            patch("app.api.admin.bind_project", return_value=_FakeBindProject()),
            patch("app.services.graph.adapters.normalize_document", side_effect=lambda doc: SimpleNamespace(doc_id=doc.id)),
            patch("app.services.graph.builder.build_graph", side_effect=lambda posts: _social_graph()),
            patch("app.services.graph.builder.build_topic_subgraph", side_effect=lambda g, _topic: g),
            patch("app.services.graph.adapters.market.MarketAdapter", return_value=_FakeMarketAdapter()),
            patch("app.services.graph.builder.build_market_graph", side_effect=lambda items: _market_graph()),
            patch("app.services.graph.adapters.policy.PolicyAdapter", return_value=_FakePolicyAdapter()),
            patch("app.services.graph.builder.build_policy_graph", side_effect=lambda items: _policy_graph()),
        ]

    @staticmethod
    def _fake_augment(graph, _documents, topic_scope=None):  # noqa: ANN001
        market_node = graph.nodes.get("MarketData:1")
        if market_node is None:
            return
        topic_tag = GraphNode(type="TopicTag", id="tag1", properties={"label": "tag"})
        graph.nodes["TopicTag:tag1"] = topic_tag
        graph.edges.append(GraphEdge(type="HAS_TOPIC_TAG", from_node=market_node, to_node=topic_tag, properties={}))

        mapping = {
            "company": "CompanyEntity",
            "product": "ProductEntity",
            "operation": "OperationEntity",
        }
        scopes = [topic_scope] if topic_scope else ["company", "product", "operation"]
        for scope in scopes:
            node_type = mapping[scope]
            node_id = f"{scope}-1"
            node_key = f"{node_type}:{node_id}"
            node = GraphNode(type=node_type, id=node_id, properties={})
            graph.nodes[node_key] = node
            graph.edges.append(GraphEdge(type=f"HAS_{scope.upper()}_ENTITY", from_node=market_node, to_node=node, properties={}))

    @staticmethod
    def _assert_contract(body: dict):
        assert body.get("status") == "ok"
        data = body.get("data")
        assert isinstance(data, dict)
        assert set(data.keys()) == {"graph_schema_version", "nodes", "edges"}
        assert data["graph_schema_version"] == "v1"
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def _mock_graph_db_graph_for_path(self, path: str) -> Graph:
        if "/content-graph" in path:
            return _social_graph()
        if "/policy-graph" in path:
            return _policy_graph()
        if "/market-graph" in path:
            graph = _market_graph()
            parsed = parse_qs(urlparse(path).query)
            view = (parsed.get("view") or [None])[0]
            topic_scope = (parsed.get("topic_scope") or [None])[0]
            if view == "market_deep_entities" or topic_scope:
                self._fake_augment(graph, [], topic_scope=topic_scope)
            return graph
        return Graph()

    def _call(self, path: str, *, graph_db_graph: Graph | None = None, graph_db_read_error: Exception | None = None):
        patches = self._patch_common()
        with patch("app.api.admin._augment_market_graph_with_topic_structured", side_effect=self._fake_augment):
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
                if graph_db_read_error is not None:
                    with patch(
                        "app.services.graph.persistence.graph_node_reader.GraphNodeReader.load_graph",
                        side_effect=graph_db_read_error,
                    ):
                        return self.client.get(path, headers=self.headers)
                with patch(
                    "app.services.graph.persistence.graph_node_reader.GraphNodeReader.load_graph",
                    return_value=(
                        graph_db_graph if graph_db_graph is not None else self._mock_graph_db_graph_for_path(path)
                    ),
                ):
                    return self.client.get(path, headers=self.headers)

    def test_admin_graph_endpoints_response_contract_stable(self):
        for path in (
            "/api/v1/admin/content-graph?limit=20",
            "/api/v1/admin/market-graph?limit=20",
            "/api/v1/admin/policy-graph?limit=20",
        ):
            resp = self._call(path)
            self.assertEqual(resp.status_code, 200, msg=f"path={path} body={resp.text}")
            self._assert_contract(resp.json())

    def test_admin_content_graph_node_types_whitelist(self):
        allowed = {"Post", "Keyword", "Entity", "Topic", "SentimentTag", "User", "Subreddit"}
        resp = self._call("/api/v1/admin/content-graph?limit=20")
        body = resp.json()
        self._assert_contract(body)
        data = body["data"]
        node_types = {str(n.get("type")) for n in data["nodes"]}
        self.assertTrue(node_types.issubset(allowed), msg=f"unexpected node types: {node_types - allowed}")
        for edge in data["edges"]:
            self.assertIn(edge["from"]["type"], allowed)
            self.assertIn(edge["to"]["type"], allowed)

    def test_admin_market_graph_base_node_types_whitelist(self):
        allowed = {"MarketData", "State", "Segment", "Entity"}
        resp = self._call("/api/v1/admin/market-graph?limit=20")
        body = resp.json()
        self._assert_contract(body)
        data = body["data"]
        node_types = {str(n.get("type")) for n in data["nodes"]}
        self.assertTrue(node_types.issubset(allowed), msg=f"unexpected node types: {node_types - allowed}")
        for edge in data["edges"]:
            self.assertIn(edge["from"]["type"], allowed)
            self.assertIn(edge["to"]["type"], allowed)

    def test_admin_market_graph_deep_entities_disjunction_keeps_contract(self):
        allowed = {
            "MarketData", "State", "Segment", "Entity", "TopicTag",
            "CompanyEntity", "CompanyBrand", "CompanyUnit", "CompanyPartner", "CompanyChannel",
            "ProductEntity", "ProductModel", "ProductCategory", "ProductBrand", "ProductComponent", "ProductScenario",
            "OperationEntity", "OperationPlatform", "OperationStore", "OperationChannel", "OperationMetric", "OperationStrategy", "OperationRegion", "OperationPeriod",
        }
        resp = self._call("/api/v1/admin/market-graph?view=market_deep_entities&limit=20")
        body = resp.json()
        self._assert_contract(body)
        data = body["data"]
        node_types = {str(n.get("type")) for n in data["nodes"]}
        self.assertTrue(node_types.issubset(allowed), msg=f"unexpected node types: {node_types - allowed}")
        self.assertIn("TopicTag", node_types)
        for edge in data["edges"]:
            self.assertIn(edge["from"]["type"], allowed)
            self.assertIn(edge["to"]["type"], allowed)

    def test_admin_market_graph_topic_scope_node_types_expected(self):
        expected = {
            "company": "Company",
            "product": "Product",
            "operation": "Operation",
        }
        for scope, prefix in expected.items():
            resp = self._call(f"/api/v1/admin/market-graph?topic_scope={scope}&limit=20")
            body = resp.json()
            self._assert_contract(body)
            types = {str(n.get("type")) for n in body["data"]["nodes"]}
            self.assertTrue(any(t.startswith(prefix) for t in types), msg=f"scope={scope} types={types}")
            disallowed_prefixes = {"Company", "Product", "Operation"} - {prefix}
            self.assertFalse(any(any(t.startswith(p) for p in disallowed_prefixes) for t in types), msg=f"scope={scope} types={types}")

    def test_admin_graph_edges_refer_existing_nodes(self):
        paths = (
            "/api/v1/admin/content-graph?limit=20",
            "/api/v1/admin/market-graph?view=market_deep_entities&limit=20",
            "/api/v1/admin/policy-graph?limit=20",
        )
        for path in paths:
            resp = self._call(path)
            body = resp.json()
            self._assert_contract(body)
            data = body["data"]
            node_index = {(str(n.get("type")), str(n.get("id"))) for n in data["nodes"]}
            for edge in data["edges"]:
                from_node = edge.get("from") or {}
                to_node = edge.get("to") or {}
                from_key = (str(from_node.get("type", "")), str(from_node.get("id", "")))
                to_key = (str(to_node.get("type", "")), str(to_node.get("id", "")))
                self.assertTrue(from_key[0] and from_key[1], msg=f"path={path} edge={edge}")
                self.assertTrue(to_key[0] and to_key[1], msg=f"path={path} edge={edge}")
                self.assertIn(from_key, node_index, msg=f"path={path} missing from={from_key}")
                self.assertIn(to_key, node_index, msg=f"path={path} missing to={to_key}")

    def test_admin_graph_endpoint_is_read_only_no_graph_db_write(self):
        with patch("app.settings.config.settings.graph_db_write_mode", "on"), patch(
            "app.settings.config.settings.graph_db_read_mode", "db_primary"
        ), patch("app.services.graph.persistence.graph_node_writer.GraphNodeWriter.persist_graph_nodes") as persist_mock:
            resp = self._call("/api/v1/admin/content-graph?limit=20")
            self.assertEqual(resp.status_code, 200, msg=resp.text)
            self._assert_contract(resp.json())
            self.assertFalse(persist_mock.called)

    def test_admin_graph_forced_db_primary_reads_graph_db_nodes(self):
        canary_graph = Graph(
            nodes={"Post:canary-1": GraphNode(type="Post", id="canary-1", properties={"label": "canary"})},
            edges=[],
            schema_version="v1",
        )
        with patch("app.settings.config.settings.graph_db_write_mode", "off"), patch(
            "app.settings.config.settings.graph_db_read_mode", "db_primary"
        ):
            resp = self._call("/api/v1/admin/content-graph?limit=20", graph_db_graph=canary_graph)
            self.assertEqual(resp.status_code, 200, msg=resp.text)
            body = resp.json()
            self._assert_contract(body)
            node_ids = {str(n.get("id")) for n in body["data"]["nodes"]}
            self.assertIn("canary-1", node_ids)
            self.assertEqual(len(body["data"]["edges"]), 0)

    def test_admin_graph_db_primary_read_error_returns_empty_graph_not_a_fallback(self):
        with patch("app.settings.config.settings.graph_db_write_mode", "off"), patch(
            "app.settings.config.settings.graph_db_read_mode", "db_primary"
        ):
            resp = self._call(
                "/api/v1/admin/content-graph?limit=20",
                graph_db_read_error=RuntimeError("graph_db read failed"),
            )
            body = resp.json()
            self.assertEqual(resp.status_code, 200, msg=resp.text)
            self._assert_contract(body)
            node_ids = {str(n.get("id")) for n in body.get("data", {}).get("nodes", [])}
            self.assertFalse("1" in node_ids, msg=f"unexpected A-fallback node under db-primary read error: {body}")
            self.assertEqual(len(body.get("data", {}).get("nodes", [])), 0)
            self.assertEqual(len(body.get("data", {}).get("edges", [])), 0)

    def test_admin_graph_db_primary_empty_graph_does_not_backfill_a_nodes(self):
        empty_graph = Graph(nodes={}, edges=[], schema_version="v1")
        with patch("app.settings.config.settings.graph_db_write_mode", "off"), patch(
            "app.settings.config.settings.graph_db_read_mode", "db_primary"
        ):
            resp = self._call("/api/v1/admin/content-graph?limit=20", graph_db_graph=empty_graph)
            body = resp.json()
            if resp.status_code == 200 and body.get("status") == "ok":
                node_ids = {str(n.get("id")) for n in body.get("data", {}).get("nodes", [])}
                self.assertFalse("1" in node_ids, msg=f"unexpected A backfill when graph_db is empty: {body}")
            else:
                self.assertNotEqual(resp.status_code, 200, msg=f"unexpected status for db-primary empty graph: {body}")


if __name__ == "__main__":
    unittest.main()
