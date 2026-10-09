from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.extraction import topic_workflow as workflow


class TopicWorkflowUnitTest(unittest.TestCase):
    def test_run_topic_extraction_workflow_uses_injected_extractor_and_fallback(self):
        first = ("operator roadmap " * 90).strip()
        second = ("operator launch entity expansion " * 90).strip()
        text = f"{first}\n\n{second}"
        seen_texts: list[str] = []

        def fake_topic_extractor(topic: str, chunk_text: str) -> dict[str, object]:
            seen_texts.append(chunk_text)
            if "launch entity expansion" in chunk_text:
                return {
                    "entities": [{"text": "Acme", "type": "ORG"}],
                    "relations": [],
                    "facts": [{"fact_type": topic, "value": "detected"}],
                    "topics": [topic],
                    "signals": {"path": "fallback"},
                    "confidence": 0.82,
                    "source_excerpt": chunk_text[:120],
                }
            return workflow.empty_topic_structured()

        result = workflow.run_topic_extraction_workflow(
            extraction_app=None,
            text=text,
            topics=["company"],
            extracted_data={"entities_relations": {"entities": [{"text": "Acme", "type": "ORG"}], "relations": []}},
            dictionaries={"company_nouns": ["operator"], "predicates": [], "modifiers": [], "components": []},
            max_selected_chunks=1,
            fallback_max_chunks=2,
            topic_extractor=fake_topic_extractor,
        )

        company = ((result.get("results") or {}).get("company")) or {}
        diagnostics = ((result.get("diagnostics") or {}).get("topics") or {}).get("company") or {}
        self.assertTrue(workflow.topic_has_data(company))
        self.assertEqual((company.get("entities") or [])[0].get("text"), "Acme")
        self.assertTrue(bool(diagnostics.get("fallback_used")))
        self.assertGreaterEqual(len(seen_texts), 2)

    def test_topic_merge_preserves_invalid_item_and_confidence_semantics(self):
        invalid_item = object()
        opaque_value = object()
        mixed_fact: dict[object, object] = {
            "fact_type": "mixed",
            1: opaque_value,
        }
        valid_entity: dict[object, object] = {
            "text": "Acme",
            "type": "ORG",
            1: opaque_value,
        }
        merged = workflow.merge_topic_structured(
            {
                "entities": [invalid_item, valid_entity],
                "facts": [mixed_fact],
                "confidence": 0.8,
            },
            {
                "entities": [invalid_item, valid_entity],
                "facts": [mixed_fact],
                "confidence": "bad",
            },
        )

        self.assertEqual(merged["entities"], [invalid_item, valid_entity])
        self.assertIs(merged["entities"][1], valid_entity)
        self.assertEqual(merged["facts"], [mixed_fact])
        self.assertIs(merged["facts"][0], mixed_fact)
        self.assertIs(merged["facts"][0][1], opaque_value)
        self.assertEqual(merged["confidence"], 0.0)

        with self.assertRaisesRegex(TypeError, "^topic collection is not iterable: object$"):
            workflow.merge_topic_structured({"topics": object()}, {})


if __name__ == "__main__":
    unittest.main()
