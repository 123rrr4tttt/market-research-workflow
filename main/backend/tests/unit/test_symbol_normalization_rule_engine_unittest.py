from __future__ import annotations

import unittest

import pytest

from app.services.graph.symbol_normalization import (
    BaseSymbolRule,
    RuleRegistry,
    SymbolRuleExecutor,
    normalize_symbol,
)

pytestmark = pytest.mark.unit


class _AppendARule(BaseSymbolRule):
    rule_id = "append_a"

    def apply(self, value: str, context=None) -> str:
        return f"{value}|A"


class _WrapRule(BaseSymbolRule):
    rule_id = "wrap"

    def apply(self, value: str, context=None) -> str:
        return f"<{value}>"


class SymbolNormalizationRuleEngineUnitTestCase(unittest.TestCase):
    def test_rule_registry_register_and_duplicate_guard(self):
        registry = RuleRegistry()
        registry.register(_AppendARule.rule_id, _AppendARule)

        self.assertTrue(registry.has("append_a"))
        self.assertEqual(registry.available_rule_ids(), ("append_a",))
        self.assertEqual(registry.create("append_a").apply("x"), "x|A")

        with self.assertRaises(ValueError):
            registry.register(_AppendARule.rule_id, _AppendARule)

    def test_executor_respects_rule_chain_order(self):
        registry = RuleRegistry()
        registry.register(_AppendARule.rule_id, _AppendARule)
        registry.register(_WrapRule.rule_id, _WrapRule)

        executor = SymbolRuleExecutor(registry=registry)
        self.assertEqual(executor.normalize("core", rule_ids=["append_a", "wrap"]), "<core|A>")
        self.assertEqual(executor.normalize("core", rule_ids=["wrap", "append_a"]), "<core>|A")

    def test_default_normalization_is_idempotent(self):
        raw = "  ＡＩ，研究-计划  "

        first = normalize_symbol(raw)
        second = normalize_symbol(first)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
