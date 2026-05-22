from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.document_queries import (
    document_json_iso_date_expr,
    policy_effective_date_expr,
    policy_has_data_condition,
    policy_state_condition,
    policy_time_expr,
    policy_type_condition,
    policy_type_order_expr,
    prompt_time_density_time_expr,
)


class PolicyFiltersUnitTestCase(unittest.TestCase):
    def test_policy_query_helpers_return_sql_expressions(self) -> None:
        expressions = [
            policy_effective_date_expr(),
            policy_time_expr(),
            policy_has_data_condition(),
            policy_state_condition("CA"),
            policy_type_condition("licensing"),
            policy_type_order_expr(),
            document_json_iso_date_expr("source_time"),
            prompt_time_density_time_expr(),
        ]
        for expr in expressions:
            self.assertTrue(hasattr(expr, "compile"))

    def test_policy_time_expr_includes_explicit_effective_and_source_time(self) -> None:
        compiled = str(policy_time_expr().compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("effective_time", compiled)
        self.assertIn("source_time", compiled)

    def test_prompt_time_density_time_expr_is_exposed_from_document_queries(self) -> None:
        compiled = str(prompt_time_density_time_expr().compile(compile_kwargs={"literal_binds": True}))

        self.assertIn("effective_time", compiled)
        self.assertIn("source_time", compiled)
        self.assertIn("effective_date", compiled)


if __name__ == "__main__":
    unittest.main()
