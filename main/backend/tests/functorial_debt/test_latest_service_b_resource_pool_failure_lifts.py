"""Focused witnesses for resource-pool compatibility and defect lifts."""

from __future__ import annotations

import pytest
from app.services.resource_pool import (
    open_source_source_presets,
    search_contract_discovery,
    search_template_service,
    site_entries,
    unified_search,
)
from functorial_kit import Failure


def test_latest_service_b_resource_pool_failure_lifts() -> None:
    modules = (
        open_source_source_presets,
        search_contract_discovery,
        search_template_service,
        site_entries,
        unified_search,
    )
    for module in modules:
        contract_failure = (
            site_entries.resource_pool_contract_failure
            if module is site_entries
            else module._contract_failure
        )
        raise_failure = (
            site_entries.raise_resource_pool_contract_legacy
            if module is site_entries
            else module._raise_contract_failure
        )
        failure = contract_failure(
            "scope_invalid",
            "resource pool test failure",
            operation="test",
            site=f"resource_pool.{module.__name__.rsplit('.', 1)[-1]}",
        )
        with pytest.raises(ValueError, match="^resource pool test failure$"):
            raise_failure(failure)

        malformed = Failure("other.family", "bad", "malformed", {})
        with pytest.raises(TypeError, match="^resource pool failure lift context is incomplete or inconsistent$"):
            raise_failure(malformed)

    type_failure = site_entries.resource_pool_contract_failure(
        "record_field_type_invalid",
        "batch index is not numeric",
        operation="test",
        site="resource_pool.auto_classify.batch_index",
        public_exception=TypeError,
    )
    with pytest.raises(TypeError, match="^batch index is not numeric$"):
        site_entries.raise_resource_pool_contract_legacy(type_failure, exception_type=TypeError)
