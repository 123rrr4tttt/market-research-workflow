"""Focused witnesses for resource-pool compatibility and defect lifts."""

from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.services.resource_pool import (
    open_source_source_presets,
    search_contract_discovery,
    search_template_service,
    site_entries,
    unified_search,
)


def test_latest_service_b_resource_pool_failure_lifts() -> None:
    modules = (
        open_source_source_presets,
        search_contract_discovery,
        search_template_service,
        site_entries,
        unified_search,
    )
    for module in modules:
        failure = module._contract_failure(
            "scope_invalid",
            "resource pool test failure",
            operation="test",
            site=f"resource_pool.{module.__name__.rsplit('.', 1)[-1]}",
        )
        with pytest.raises(ValueError, match="^resource pool test failure$"):
            module._raise_contract_failure(failure)

        malformed = Failure("other.family", "bad", "malformed", {})
        with pytest.raises(TypeError, match="^resource pool failure lift context is incomplete or inconsistent$"):
            module._raise_contract_failure(malformed)
