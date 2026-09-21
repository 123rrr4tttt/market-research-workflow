"""Kit registration projection for FirstSpecimen PostgreSQL handler failures."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


FirstSpecimenHandlerFailureCode = Literal[
    "first_specimen_handler_contract_invalid",
    "first_specimen_operation_unsupported",
    "first_specimen_semantic_product_invalid",
    "first_specimen_replay_projection_invalid",
    "first_specimen_activation_binding_invalid",
    "first_specimen_handler_binding_invalid",
    "first_specimen_output_write_invalid",
    "first_specimen_output_readback_invalid",
]

first_specimen_handler_failures = define_failure_family(
    "first_specimen.handler_failure",
    get_args(FirstSpecimenHandlerFailureCode),
)


__all__ = ["first_specimen_handler_failures"]
