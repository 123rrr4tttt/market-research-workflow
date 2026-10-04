#!/usr/bin/env python3
"""Check manifest-backed navigation without weakening migrated-file checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_docs_root_migration_manifest.py"
SPEC = importlib.util.spec_from_file_location("check_docs_root_migration_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class ManifestNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.manifest = self.repo / "docs/architecture/latest-dev-docs-entry-manifest.json"
        self.root_readme = "docs/architecture/README.md"
        self.target_readme = "docs/architecture/topic/README.md"
        self.source = "development/latest-dev-docs/topic/A_ARCHITECTURE"
        self.source_file = f"{self.source}/note.md"
        self.target_file = "docs/architecture/topic/note.md"
        self.entry = {
            "id": "architecture-topic",
            "classification": "architecture",
            "source": self.source,
            "source_role": "explicit-architecture-tree",
            "target": self.target_readme,
            "target_root": "docs/architecture/topic",
            "shim": self.target_readme,
            "compatibility_entry": self.source_file,
            "status": "content_moved_batch",
            "moved_files": [{
                "source": self.source_file,
                "target": self.target_file,
                "compatibility_entry": self.source_file,
                "authority": "target_authoritative",
                "source_status": "compatibility_shim",
            }],
        }
        self.data = {
            "schema": checker.EXPECTED_SCHEMA,
            "root": "docs/architecture",
            "entries": [self.entry],
            "navigation_promotions": [{
                "id": "topic-navigation",
                "status": "navigation_promoted",
                "root_readme": self.root_readme,
                "navigation_section": "Original Navigation",
                "entries": [{
                    "target_root": "docs/architecture/topic",
                    "target": self.target_readme,
                    "compatibility_entry": self.source_file,
                    "manifest_entry_ids": [self.entry["id"]],
                    "partial_boundary": "Target owns moved content; source is a compatibility shim.",
                }],
            }],
        }
        self.write(self.root_readme,
                   "# Navigation\n[Manifest](latest-dev-docs-entry-manifest.json)\n"
                   "[Topic](topic/README.md)\n")
        self.write(self.target_readme, "# Topic\n[Manifest](../latest-dev-docs-entry-manifest.json)\n")
        self.write(self.source_file, f"Compatibility shim: {self.target_file}\n")
        self.write(self.target_file, f"Content moved from {self.source_file}\n")
        self.save_manifest()

    def write(self, relative: str, text: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def save_manifest(self) -> None:
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def messages(self) -> list[str]:
        problems, count = checker.validate_manifest(self.repo, self.manifest)
        self.assertEqual(count, 1)
        return [problem.message for problem in problems]

    def test_owning_manifest_links_replace_repeated_metadata(self) -> None:
        self.assertEqual(self.messages(), [])

    def test_filename_and_wrong_manifest_links_do_not_replace_metadata(self) -> None:
        self.write("docs/architecture/topic/latest-dev-docs-entry-manifest.json", "{}")
        variants = [
            "latest-dev-docs-entry-manifest.json",
            "[Manifest](latest-dev-docs-entry-manifest.json)",
            "[Manifest](https://example.org/latest-dev-docs-entry-manifest.json)",
            "`[Manifest](../latest-dev-docs-entry-manifest.json)`",
            "```md\n[Manifest](../latest-dev-docs-entry-manifest.json)\n```",
            "<!-- [Manifest](../latest-dev-docs-entry-manifest.json) -->",
            "![Manifest](../latest-dev-docs-entry-manifest.json)",
            "    [Manifest](../latest-dev-docs-entry-manifest.json)",
        ]
        for text in variants:
            with self.subTest(text=text):
                self.write(self.target_readme, text)
                self.assertTrue(any("does not mention moved path" in message for message in self.messages()))

    def test_wrong_root_manifest_link_does_not_replace_promotion_metadata(self) -> None:
        self.write(self.root_readme,
                   "[Manifest](missing/latest-dev-docs-entry-manifest.json)\n[Topic](topic/README.md)")
        self.assertTrue(any("navigation promotion id is not mentioned" in message for message in self.messages()))

    def test_missing_moved_target_still_fails(self) -> None:
        (self.repo / self.target_file).unlink()
        self.assertIn("moved file target is missing", self.messages())

    def test_content_shim_manifest_link_still_checks_compatibility_file(self) -> None:
        self.entry["status"] = "content_shim"
        del self.entry["moved_files"]
        self.save_manifest()
        self.assertEqual(self.messages(), [])
        (self.repo / self.source_file).unlink()
        self.assertIn("content_shim compatibility_entry does not exist", self.messages())

    def test_missing_source_shim_still_fails(self) -> None:
        (self.repo / self.source_file).unlink()
        self.assertIn("moved file source compatibility shim is missing", self.messages())

    def test_invalid_target_metadata_still_fails(self) -> None:
        self.write(self.target_file, "# A file without migration metadata\n")
        messages = self.messages()
        self.assertTrue(any("moved target does not mention compatibility source" in message for message in messages))
        self.assertIn("moved target must identify content moved status", messages)

    def test_invalid_owner_and_classification_still_fail(self) -> None:
        self.entry["classification"] = "development"
        self.entry["moved_files"][0]["authority"] = "source_authoritative"
        self.save_manifest()
        messages = self.messages()
        self.assertIn("entry classification does not match root", messages)
        self.assertIn("moved file authority must be target_authoritative", messages)

    def test_promotion_target_requires_real_navigation_link(self) -> None:
        for reference in (
            self.target_readme,
            "[Topic](missing/README.md)",
            "`[Topic](topic/README.md)`",
            "<!-- [Topic](topic/README.md) -->",
        ):
            with self.subTest(reference=reference):
                self.write(self.root_readme,
                           "[Manifest](latest-dev-docs-entry-manifest.json)\n" + reference)
                self.assertIn(f"navigation README does not link target: {self.target_readme}", self.messages())

    def test_promotion_unknown_id_still_fails(self) -> None:
        self.data["navigation_promotions"][0]["entries"][0]["manifest_entry_ids"] = ["missing-id"]
        self.save_manifest()
        self.assertIn("navigation references unknown entry id: missing-id", self.messages())

    def test_original_explicit_metadata_without_manifest_link_still_passes(self) -> None:
        self.write(self.target_readme, "\n".join([
            "Content moved; content shim", self.source, self.source_file, self.target_file,
            self.target_readme, self.entry["target_root"],
        ]))
        self.write(self.root_readme, "\n".join([
            self.manifest.name, "Original Navigation", "topic-navigation", self.entry["id"],
            self.entry["target_root"], self.target_readme, self.source_file,
        ]))
        self.assertEqual(self.messages(), [])

    def test_non_object_manifest_is_reported(self) -> None:
        self.manifest.write_text("[]", encoding="utf-8")
        problems, count = checker.validate_manifest(self.repo, self.manifest)
        self.assertEqual(count, 0)
        self.assertEqual([problem.message for problem in problems], ["manifest must be an object"])


if __name__ == "__main__":
    unittest.main()
