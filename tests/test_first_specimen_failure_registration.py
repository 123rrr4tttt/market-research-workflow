from __future__ import annotations

import ast
import json
from pathlib import Path

from app.successor_runtime.capabilities.first_specimen_interpreters import (
    InterpreterFailure,
)
from app.successor_runtime.substrate.postgres.first_specimen_handlers import (
    FirstSpecimenHandlerError,
    FirstSpecimenInterpreterFailure,
)
from mrw_functorial_kit.core.first_specimen_semantics import (
    first_specimen_handler_failures,
)


ROOT = Path(__file__).resolve().parents[1]
HANDLER_SOURCE = (
    ROOT
    / "main/backend/app/successor_runtime/substrate/postgres/first_specimen_handlers.py"
)


class MissingLocalFailureCode(AssertionError):
    pass


def _local_class_failure_codes() -> dict[str, str]:
    module = ast.parse(HANDLER_SOURCE.read_text(encoding="utf-8"))
    class_nodes = {
        statement.name: statement
        for statement in module.body
        if isinstance(statement, ast.ClassDef)
    }

    def is_exception_class(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name in seen or name not in class_nodes:
            return False
        for base in class_nodes[name].bases:
            base_name = base.id if isinstance(base, ast.Name) else None
            if base_name in {"BaseException", "Exception", "RuntimeError"}:
                return True
            if base_name and is_exception_class(base_name, seen | {name}):
                return True
        return False

    codes: dict[str, str] = {}
    for statement in module.body:
        if not isinstance(statement, ast.ClassDef):
            continue
        if not statement.name.startswith("FirstSpecimen") or not is_exception_class(
            statement.name
        ):
            continue
        for class_statement in statement.body:
            if not isinstance(class_statement, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "failure_code"
                for target in class_statement.targets
            ):
                continue
            code = ast.literal_eval(class_statement.value)
            assert isinstance(code, str)
            codes[statement.name] = code
            break
        else:
            raise MissingLocalFailureCode
    return codes


def test_INVARIANT__first_specimen_failure_codes_match_runtime_classes() -> None:
    class_codes = _local_class_failure_codes()
    assert len(first_specimen_handler_failures.codes) == len(set(class_codes.values()))
    assert set(first_specimen_handler_failures.codes) == set(class_codes.values())


def test_INVARIANT__first_specimen_failure_family_matches_registry_and_governance() -> None:
    failures = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert registered["first_specimen.handler_failure"] == (
        first_specimen_handler_failures.codes
    )

    governance = json.loads(
        (ROOT / "docs/governance/failure-family-map.v1.json").read_text(encoding="utf-8")
    )["priority_order"]
    first_specimen_map = next(
        entry
        for entry in governance
        if entry.get("proposed_family") == "first_specimen.handler_failure"
    )
    assert tuple(first_specimen_map["registered_codes"]) == (
        first_specimen_handler_failures.codes
    )


def test_REFLECTION__first_specimen_error_classes_expose_registered_codes() -> None:
    handler_module = __import__(
        FirstSpecimenHandlerError.__module__,
        fromlist=[FirstSpecimenHandlerError.__name__],
    )
    for class_name, code in _local_class_failure_codes().items():
        runtime_class = getattr(handler_module, class_name)
        assert runtime_class.failure_code == code
        assert code in first_specimen_handler_failures.codes


def test_FAILURE_PRESERVED__capability_interpreter_code_remains_passthrough() -> None:
    capability_code = "INVALID_EVIDENCE_QUALIFICATION"
    capability_failure = InterpreterFailure(
        code=capability_code,
        message="qualification identity drift",
    )
    wrapped = FirstSpecimenInterpreterFailure(
        code=capability_failure.code,
        message=capability_failure.message,
    )

    assert FirstSpecimenInterpreterFailure.failure_code == (
        "first_specimen_handler_contract_invalid"
    )
    assert wrapped.failure_code == capability_code
    assert capability_code not in first_specimen_handler_failures.codes
