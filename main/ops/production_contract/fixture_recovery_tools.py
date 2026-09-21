"""Fixture-only planning for production recovery workflows.

Every public planner is a dry-run.  It may read the caller-selected fixture
directory, but it never starts services, mutates fixtures, contacts an
endpoint, or claims authority over staging/production resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlsplit
from enum import StrEnum


RECEIPT_SCHEMA_VERSION: Final = "ops.production_contract.recovery-receipt.v1"
TARGET_CLASS: Final = "fixture"
DRY_RUN_RESULT: Final = "planned_dry_run_fixture"
_ARTIFACT_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SECRET_KEY_PATTERN: Final = re.compile(
    r"(?:secret|password|passwd|passphrase|token|api[_-]?key|"
    r"access[_-]?key|private[_-]?key|credential|authorization|bearer)",
    re.IGNORECASE,
)
_ENDPOINT_KEY_PATTERN: Final = re.compile(
    r"(?:endpoint|database[_-]?url|service[_-]?url|host(?:name)?)", re.IGNORECASE
)
_SECRET_VALUE_PATTERN: Final = re.compile(
    r"(?:^|\s)(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,})", re.IGNORECASE
)
_NETWORK_SCHEMES: Final = frozenset(
    {"http", "https", "ws", "wss", "postgres", "postgresql", "mysql", "redis", "amqp", "tcp"}
)
_OPERATIONS: Final = (
    "backup",
    "restore",
    "migration_forward",
    "migration_failure_recovery",
    "image_rollback",
    "config_rollback",
)


class RecoveryFailureReason(StrEnum):
    SECRET_PARAMETER = "secret-bearing parameter is forbidden"
    ENDPOINT_PARAMETER = "endpoint-bearing parameter is forbidden"
    SECRET_VALUE = "secret-like value is forbidden"
    NETWORK_ENDPOINT = "network endpoint is forbidden"
    INVALID_ARTIFACT_ID = "invalid fixture artifact id"
    ROOT_SYMLINK = "fixture root must not be a symlink"
    ROOT_MISSING = "fixture root does not exist"
    ROOT_NOT_DIRECTORY = "fixture root must be a directory"
    PATH_ESCAPE = "path escapes the fixture root"
    RELATIVE_PATH_REQUIRED = "relative path must stay inside the fixture root"
    SYMLINK_FORBIDDEN = "symlinked fixture path is forbidden"
    PATH_MISSING = "fixture path does not exist"
    PARENT_MISSING = "fixture parent does not exist"
    UNSUPPORTED_OPERATION = "unsupported operation"


@dataclass(frozen=True)
class RecoveryToolError(ValueError):
    """Raised when a request violates the fixture-only contract."""

    reason: RecoveryFailureReason
    location: str = ""

    def __str__(self) -> str:
        if not self.location:
            return self.reason.value
        return f"{self.reason.value}: {self.location}"


def _policy_error(
    reason: RecoveryFailureReason, location: str = ""
) -> RecoveryToolError:
    return RecoveryToolError(reason, location)


@dataclass(frozen=True, slots=True)
class PlannedCommand:
    """A semantic command; receiving it does not execute anything."""

    order: int
    intent: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveryReceipt:
    """Typed fixture dry-run receipt shared by all recovery planners."""

    schema_version: str
    receipt_digest: str
    operation: str
    input_digest: str
    target_class: str
    planned_commands: tuple[PlannedCommand, ...]
    result: str
    authority: bool
    executed: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["planned_commands"] = [
            {**command, "command": list(command["command"])}
            for command in value["planned_commands"]
        ]
        return value


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    """Inputs for one fixture recovery plan."""

    operation: Literal[
        "backup",
        "restore",
        "migration_forward",
        "migration_failure_recovery",
        "image_rollback",
        "config_rollback",
    ]
    fixture_root: Path
    artifact_id: str = "default"
    restore_artifact_id: str = "restored"
    recovery_artifact_id: str = "recovered"
    current_artifact_id: str = "current"
    previous_artifact_id: str = "previous"
    config_name: str = "app"
    failure_kind: str = "constraint_violation"
    context: Mapping[str, object] = field(default_factory=dict)


def redact_secrets(value: object) -> object:
    """Return a JSON-like value safe for logs, without authorizing it."""

    if not isinstance(value, Mapping):
        if isinstance(value, (list, tuple)):
            return [redact_secrets(item) for item in value]
        if isinstance(value, dict) is False and value is not None and not isinstance(
            value, (str, int, float, bool)
        ):
            return repr(value)
        return value

    redacted: dict[object, object] = {}
    for key, item in value.items():
        key_text = str(key)
        if _SECRET_KEY_PATTERN.search(key_text):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = redact_secrets(item)
    return redacted


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _context_digest(context: Mapping[str, object]) -> str:
    return _sha256(_json_ready(redact_secrets(context)))


def _reject_network_context(context: Mapping[str, object]) -> None:
    stack: list[tuple[str, object]] = [(key, item) for key, item in context.items()]

    while stack:
        key, item = stack.pop()
        key_text = str(key)
        if _SECRET_KEY_PATTERN.search(key_text):
            raise _policy_error(RecoveryFailureReason.SECRET_PARAMETER, key_text)
        if _ENDPOINT_KEY_PATTERN.search(key_text):
            raise _policy_error(RecoveryFailureReason.ENDPOINT_PARAMETER, key_text)
        if isinstance(item, Mapping):
            stack.extend((f"{key_text}.{child_key}", child_item) for child_key, child_item in item.items())
            continue
        if isinstance(item, (list, tuple)):
            stack.extend((f"{key_text}[{index}]", child) for index, child in enumerate(item))
            continue
        if not isinstance(item, str):
            continue
        if _SECRET_VALUE_PATTERN.search(item):
            raise _policy_error(RecoveryFailureReason.SECRET_VALUE, key_text)
        scheme = urlsplit(item).scheme.lower()
        if scheme in _NETWORK_SCHEMES:
            raise _policy_error(RecoveryFailureReason.NETWORK_ENDPOINT, key_text)


def _artifact_id(value: str, field_name: str) -> str:
    if not _ARTIFACT_ID_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise _policy_error(RecoveryFailureReason.INVALID_ARTIFACT_ID, field_name)
    return value


class FixturePathResolver:
    """Resolve an explicit fixture root and its allowlisted relative paths."""

    def __init__(self, root: Path) -> None:
        supplied = Path(root).expanduser()
        if supplied.is_symlink():
            raise _policy_error(RecoveryFailureReason.ROOT_SYMLINK)
        try:
            self.root = supplied.resolve(strict=True)
        except OSError as exc:
            raise _policy_error(RecoveryFailureReason.ROOT_MISSING) from exc
        if not self.root.is_dir():
            raise _policy_error(RecoveryFailureReason.ROOT_NOT_DIRECTORY)

    def _reject_escape(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise _policy_error(RecoveryFailureReason.PATH_ESCAPE) from exc

    def resolve(self, relative: str, *, must_exist: bool = True) -> Path:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise _policy_error(RecoveryFailureReason.RELATIVE_PATH_REQUIRED)

        candidate = self.root / relative
        if candidate.is_symlink():
            raise _policy_error(RecoveryFailureReason.SYMLINK_FORBIDDEN, relative)
        for prefix in candidate.parents:
            if prefix != self.root and prefix.is_symlink():
                raise _policy_error(RecoveryFailureReason.SYMLINK_FORBIDDEN, relative)

        if must_exist:
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise _policy_error(RecoveryFailureReason.PATH_MISSING, relative) from exc
            self._reject_escape(resolved)
            return resolved

        parent = candidate.parent
        if parent.is_symlink():
            raise _policy_error(RecoveryFailureReason.SYMLINK_FORBIDDEN, str(parent))
        try:
            resolved_parent = parent.resolve(strict=True)
        except OSError as exc:
            raise _policy_error(RecoveryFailureReason.PARENT_MISSING, str(parent)) from exc
        self._reject_escape(resolved_parent)
        return resolved_parent / candidate.name


def _receipt(
    *,
    request: RecoveryRequest,
    context_digest: str,
    commands: list[PlannedCommand],
) -> RecoveryReceipt:
    without_digest = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "operation": request.operation,
        "input_digest": context_digest,
        "target_class": TARGET_CLASS,
        "planned_commands": [
            {
                "order": command.order,
                "intent": command.intent,
                "command": list(command.command),
            }
            for command in commands
        ],
        "result": DRY_RUN_RESULT,
        "authority": False,
        "executed": False,
    }
    return RecoveryReceipt(
        schema_version=RECEIPT_SCHEMA_VERSION,
        receipt_digest=_sha256(without_digest),
        operation=request.operation,
        input_digest=context_digest,
        target_class=TARGET_CLASS,
        planned_commands=tuple(commands),
        result=DRY_RUN_RESULT,
        authority=False,
        executed=False,
    )


def _backup_commands(resolver: FixturePathResolver, request: RecoveryRequest) -> list[PlannedCommand]:
    source = resolver.resolve(f"data/{request.artifact_id}.sqlite")
    destination = resolver.resolve(
        f"backups/{request.artifact_id}.sqlite.fixture", must_exist=False
    )
    return [
        PlannedCommand(1, "inspect fixture source", ("fixture.read", str(source))),
        PlannedCommand(2, "copy fixture snapshot", ("fixture.copy", str(source), str(destination))),
        PlannedCommand(3, "verify copied digest", ("fixture.verify_digest", str(source), str(destination))),
    ]


def _restore_commands(resolver: FixturePathResolver, request: RecoveryRequest) -> list[PlannedCommand]:
    backup = resolver.resolve(f"backups/{request.artifact_id}.sqlite.fixture")
    target = resolver.resolve(
        f"data/{request.restore_artifact_id}.sqlite", must_exist=False
    )
    return [
        PlannedCommand(1, "inspect fixture backup", ("fixture.read", str(backup))),
        PlannedCommand(2, "verify fixture backup", ("fixture.verify_digest", str(backup))),
        PlannedCommand(3, "restore into fixture target", ("fixture.restore", str(backup), str(target))),
        PlannedCommand(4, "verify restored fixture", ("fixture.verify_restore", str(target))),
    ]


def _migration_forward_commands(
    resolver: FixturePathResolver, request: RecoveryRequest
) -> list[PlannedCommand]:
    script = resolver.resolve(f"migrations/{request.artifact_id}.forward.sql")
    journal = resolver.resolve(
        f"migration_journal/{request.artifact_id}.json", must_exist=False
    )
    return [
        PlannedCommand(1, "inspect migration fixture", ("fixture.read", str(script))),
        PlannedCommand(
            2,
            "apply migration to fixture journal",
            ("fixture.migrate.forward", str(script), str(journal)),
        ),
        PlannedCommand(3, "verify migration journal", ("fixture.verify_journal", str(journal))),
    ]


def _migration_failure_recovery_commands(
    resolver: FixturePathResolver, request: RecoveryRequest
) -> list[PlannedCommand]:
    script = resolver.resolve(f"migrations/{request.artifact_id}.forward.sql")
    journal = resolver.resolve(
        f"migration_journal/{request.artifact_id}.json", must_exist=False
    )
    recovery_backup = resolver.resolve(f"backups/{request.recovery_artifact_id}.sqlite.fixture")
    recovery_target = resolver.resolve(
        f"data/{request.recovery_artifact_id}.sqlite", must_exist=False
    )
    return [
        PlannedCommand(1, "inspect migration fixture", ("fixture.read", str(script))),
        PlannedCommand(
            2,
            "apply migration to fixture journal",
            ("fixture.migrate.forward", str(script), str(journal)),
        ),
        PlannedCommand(
            3,
            "inject migration failure",
            ("fixture.migration.fail", str(journal), request.failure_kind),
        ),
        PlannedCommand(
            4, "record migration failure", ("fixture.migration.record_failure", str(journal))
        ),
        PlannedCommand(
            5,
            "restore recovery fixture snapshot",
            ("fixture.restore", str(recovery_backup), str(recovery_target)),
        ),
        PlannedCommand(
            6,
            "verify migration recovery",
            ("fixture.migration.verify_recovery", str(journal), str(recovery_target)),
        ),
    ]


def _image_rollback_commands(
    resolver: FixturePathResolver, request: RecoveryRequest
) -> list[PlannedCommand]:
    current = resolver.resolve(f"images/{request.current_artifact_id}.manifest.fixture")
    previous = resolver.resolve(f"images/{request.previous_artifact_id}.manifest.fixture")
    return [
        PlannedCommand(1, "inspect current fixture image", ("fixture.read", str(current))),
        PlannedCommand(2, "select previous fixture image", ("fixture.image.select", str(previous))),
        PlannedCommand(
            3,
            "validate previous image manifest",
            ("fixture.verify_manifest", str(previous)),
        ),
        PlannedCommand(
            4,
            "prepare image rollback plan",
            ("fixture.rollback.image.prepare", str(current), str(previous)),
        ),
    ]


def _config_rollback_commands(
    resolver: FixturePathResolver, request: RecoveryRequest
) -> list[PlannedCommand]:
    current = resolver.resolve(f"configs/{request.config_name}.current.fixture")
    previous = resolver.resolve(f"configs/{request.config_name}.previous.fixture")
    return [
        PlannedCommand(1, "inspect current fixture config", ("fixture.read", str(current))),
        PlannedCommand(2, "read previous fixture config", ("fixture.read", str(previous))),
        PlannedCommand(
            3,
            "compare fixture configs",
            ("fixture.config.diff", str(current), str(previous)),
        ),
        PlannedCommand(
            4,
            "prepare config rollback plan",
            ("fixture.rollback.config.prepare", str(current), str(previous)),
        ),
    ]


_PLANNERS: Final = {
    "backup": _backup_commands,
    "restore": _restore_commands,
    "migration_forward": _migration_forward_commands,
    "migration_failure_recovery": _migration_failure_recovery_commands,
    "image_rollback": _image_rollback_commands,
    "config_rollback": _config_rollback_commands,
}


def plan_recovery(request: RecoveryRequest) -> Annotated[
    RecoveryReceipt,
    "kit:non-authoritative derived_as=preflight "
    "fact_source=fixture_recovery_tools "
    "witness=test:test_all_operations_return_fixture_dry_run_receipt",
]:
    """Build an idempotent fixture-only plan without executing commands."""

    if request.operation not in _OPERATIONS:
        raise _policy_error(RecoveryFailureReason.UNSUPPORTED_OPERATION, request.operation)

    _reject_network_context(request.context)
    ids = {
        "artifact_id": request.artifact_id,
        "restore_artifact_id": request.restore_artifact_id,
        "recovery_artifact_id": request.recovery_artifact_id,
        "current_artifact_id": request.current_artifact_id,
        "previous_artifact_id": request.previous_artifact_id,
        "config_name": request.config_name,
        "failure_kind": request.failure_kind,
    }
    for field_name, value in ids.items():
        _artifact_id(value, field_name)

    resolver = FixturePathResolver(request.fixture_root)
    input_payload = {
        "operation": request.operation,
        "fixture_root": str(resolver.root),
        **ids,
        "context": _json_ready(redact_secrets(request.context)),
    }
    input_digest = _sha256(input_payload)
    commands = _PLANNERS[request.operation](resolver, request)
    return _receipt(request=request, context_digest=input_digest, commands=commands)


def build_cli() -> Annotated[
    argparse.ArgumentParser,
    "kit:non-authoritative derived_as=preflight "
    "fact_source=fixture_recovery_tools "
    "witness=test:test_cli_success_and_rejection_emit_non_executing_receipts",
]:
    parser = argparse.ArgumentParser(
        description="Plan a fixture-only recovery operation and print one receipt."
    )
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.add_argument("--fixture", action="store_true", required=True)
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--operation", required=True, choices=_OPERATIONS)
    parser.add_argument("--artifact-id", default="default")
    parser.add_argument("--restore-artifact-id", default="restored")
    parser.add_argument("--recovery-artifact-id", default="recovered")
    parser.add_argument("--current-artifact-id", default="current")
    parser.add_argument("--previous-artifact-id", default="previous")
    parser.add_argument("--config-name", default="app")
    parser.add_argument("--failure-kind", default="constraint_violation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    request = RecoveryRequest(
        operation=args.operation,
        fixture_root=args.fixture_root,
        artifact_id=args.artifact_id,
        restore_artifact_id=args.restore_artifact_id,
        recovery_artifact_id=args.recovery_artifact_id,
        current_artifact_id=args.current_artifact_id,
        previous_artifact_id=args.previous_artifact_id,
        config_name=args.config_name,
        failure_kind=args.failure_kind,
    )
    try:
        receipt = plan_recovery(request)
    except RecoveryToolError as exc:
        print(
            json.dumps(
                {
                    "schema_version": RECEIPT_SCHEMA_VERSION,
                    "operation": request.operation,
                    "result": "rejected",
                    "authority": False,
                    "executed": False,
                    "failure_reason": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
