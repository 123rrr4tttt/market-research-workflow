from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from main.ops.production_contract.fixture_recovery_tools import (  # noqa: E402
    RECEIPT_SCHEMA_VERSION,
    FixturePathResolver,
    PlannedCommand,
    RecoveryReceipt,
    RecoveryRequest,
    RecoveryToolError,
    build_cli,
    main,
    plan_recovery,
    redact_secrets,
)


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "recovery-fixture"
    for directory in ("data", "backups", "migrations", "migration_journal", "images", "configs"):
        (root / directory).mkdir(parents=True)

    (root / "data" / "default.sqlite").write_bytes(b"database-fixture")
    (root / "data" / "recovered.sqlite").write_bytes(b"old-database-fixture")
    (root / "backups" / "default.sqlite.fixture").write_bytes(b"backup-fixture")
    (root / "backups" / "recovered.sqlite.fixture").write_bytes(b"recovery-backup-fixture")
    (root / "migrations" / "default.forward.sql").write_text("CREATE TABLE fixture(id);")
    (root / "images" / "current.manifest.fixture").write_text("image=current\n")
    (root / "images" / "previous.manifest.fixture").write_text("image=previous\n")
    (root / "configs" / "app.current.fixture").write_text("setting=current\n")
    (root / "configs" / "app.previous.fixture").write_text("setting=previous\n")
    return root


def _request(operation: str, root: Path, **overrides: object) -> RecoveryRequest:
    return RecoveryRequest(
        operation=operation,  # type: ignore[arg-type]
        fixture_root=root,
        **overrides,
    )


@pytest.mark.parametrize(
    "operation",
    [
        "backup",
        "restore",
        "migration_forward",
        "migration_failure_recovery",
        "image_rollback",
        "config_rollback",
    ],
)
def test_all_operations_return_fixture_dry_run_receipt(operation: str, fixture_root: Path) -> None:
    receipt = plan_recovery(_request(operation, fixture_root))

    assert isinstance(receipt, RecoveryReceipt)
    assert receipt.schema_version == RECEIPT_SCHEMA_VERSION
    assert receipt.operation == operation
    assert receipt.target_class == "fixture"
    assert receipt.result == "planned_dry_run_fixture"
    assert receipt.authority is False
    assert receipt.executed is False
    assert len(receipt.input_digest) == 64
    assert len(receipt.receipt_digest) == 64
    assert [command.order for command in receipt.planned_commands] == list(
        range(1, len(receipt.planned_commands) + 1)
    )
    assert all(isinstance(command, PlannedCommand) for command in receipt.planned_commands)
    assert json.loads(json.dumps(receipt.to_dict())) == receipt.to_dict()


def test_receipt_is_idempotent_for_the_same_fixture(fixture_root: Path) -> None:
    request = _request("migration_failure_recovery", fixture_root)
    first = plan_recovery(request)
    second = plan_recovery(request)

    assert first == second
    assert first.receipt_digest == second.receipt_digest
    assert first.to_dict() == second.to_dict()


def test_migration_plan_is_ordered_and_does_not_claim_execution(fixture_root: Path) -> None:
    receipt = plan_recovery(
        _request("migration_failure_recovery", fixture_root, failure_kind="index_conflict")
    )
    intents = [command.intent for command in receipt.planned_commands]

    assert intents.index("apply migration to fixture journal") < intents.index(
        "inject migration failure"
    )
    assert intents.index("inject migration failure") < intents.index(
        "record migration failure"
    )
    assert intents.index("record migration failure") < intents.index(
        "restore recovery fixture snapshot"
    )
    assert intents.index("restore recovery fixture snapshot") < intents.index(
        "verify migration recovery"
    )
    assert any(command.command[0] == "fixture.migrate.forward" for command in receipt.planned_commands)
    assert any(
        command.command[0] == "fixture.migration.fail" for command in receipt.planned_commands
    )
    assert any(
        command.command[0] == "fixture.migration.verify_recovery"
        for command in receipt.planned_commands
    )
    assert all(not command.command[0].startswith("docker") for command in receipt.planned_commands)
    assert receipt.executed is False


def test_rollback_plans_prepare_instead_of_claiming_a_swap(fixture_root: Path) -> None:
    image = plan_recovery(_request("image_rollback", fixture_root))
    config = plan_recovery(_request("config_rollback", fixture_root))

    for receipt in (image, config):
        assert receipt.planned_commands[-1].command[0] == (
            "fixture.rollback.image.prepare"
            if receipt.operation == "image_rollback"
            else "fixture.rollback.config.prepare"
        )
        assert all("swap" not in item for command in receipt.planned_commands for item in command.command)
        assert receipt.result == "planned_dry_run_fixture"


def test_path_resolver_rejects_escape_and_nonexistent_parent(fixture_root: Path) -> None:
    resolver = FixturePathResolver(fixture_root)

    with pytest.raises(RecoveryToolError, match="relative path"):
        resolver.resolve("../outside.sqlite")
    with pytest.raises(RecoveryToolError, match="does not exist"):
        resolver.resolve("data/missing.sqlite")
    with pytest.raises(RecoveryToolError, match="fixture parent does not exist"):
        resolver.resolve("missing-dir/output.sqlite", must_exist=False)


def test_path_resolver_rejects_root_and_child_symlinks(
    fixture_root: Path, tmp_path: Path
) -> None:
    child = fixture_root / "data" / "linked.sqlite"
    child.symlink_to(fixture_root / "data" / "default.sqlite")
    resolver = FixturePathResolver(fixture_root)

    with pytest.raises(RecoveryToolError, match="symlinked fixture path"):
        resolver.resolve("data/linked.sqlite")

    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(fixture_root, target_is_directory=True)
    with pytest.raises(RecoveryToolError, match="fixture root must not be a symlink"):
        plan_recovery(_request("backup", linked_root))


@pytest.mark.parametrize(
    ("context", "message"),
    [
        ({"api_key": "fixture-placeholder"}, "secret-bearing parameter"),
        ({"nested": {"database_url": "postgresql://fixture/db"}}, "endpoint-bearing parameter"),
    ],
)
def test_real_endpoint_and_secret_parameters_are_rejected(
    fixture_root: Path, context: dict[str, object], message: str
) -> None:
    with pytest.raises(RecoveryToolError, match=message):
        plan_recovery(_request("backup", fixture_root, context=context))


def test_secret_redaction_is_log_safe() -> None:
    redacted = redact_secrets(
        {"api_key": "fixture-value", "nested": {"password": "fixture-value"}, "name": "fixture"}
    )

    assert redacted == {
        "api_key": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
        "name": "fixture",
    }


def test_cli_requires_dry_run_and_fixture(fixture_root: Path) -> None:
    parser = build_cli()
    with pytest.raises(SystemExit):
        parser.parse_args(["--fixture", "--fixture-root", str(fixture_root), "--operation", "backup"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--dry-run", "--fixture-root", str(fixture_root), "--operation", "backup"])


def test_cli_success_and_rejection_emit_non_executing_receipts(
    fixture_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "--dry-run",
            "--fixture",
            "--fixture-root",
            str(fixture_root),
            "--operation",
            "backup",
        ]
    )
    success = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert success["result"] == "planned_dry_run_fixture"
    assert success["authority"] is False
    assert success["executed"] is False

    exit_code = main(
        [
            "--dry-run",
            "--fixture",
            "--fixture-root",
            "/definitely/not/a/fixture",
            "--operation",
            "backup",
        ]
    )
    rejection = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert rejection["result"] == "rejected"
    assert rejection["authority"] is False
    assert rejection["executed"] is False
