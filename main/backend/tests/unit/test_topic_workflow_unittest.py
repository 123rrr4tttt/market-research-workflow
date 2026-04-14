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


if __name__ == "__main__":
    unittest.main()
