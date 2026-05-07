from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.document_queries import (
    policy_effective_date_expr,
    policy_has_data_condition,
    policy_state_condition,
    policy_time_expr,
    policy_type_condition,
    policy_type_order_expr,
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
        ]
        for expr in expressions:
            self.assertTrue(hasattr(expr, "compile"))


if __name__ == "__main__":
    unittest.main()
