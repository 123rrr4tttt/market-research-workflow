from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


ROLLBACK_SCRIPT = Path(__file__).resolve().parents[3] / "ops" / "rollback.sh"


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "rollback-fixture"
    (root / "configs").mkdir(parents=True)
    (root / "configs" / "app.current.fixture").write_text("setting=current\n")
    (root / "configs" / "app.previous.fixture").write_text("setting=previous\n")
    return root


def _dry_run(
    fixture_root: Path,
    *arguments: str,
    hook_file: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if hook_file is not None:
        env["OPS_HOOK_FILE"] = str(hook_file)
    else:
        env.pop("OPS_HOOK_FILE", None)
    return subprocess.run(
        ["bash", str(ROLLBACK_SCRIPT), "dry-run", *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _plan(fixture_root: Path) -> dict[str, object]:
    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--operation",
        "config_rollback",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_dry_run_generates_nonexecuting_fixture_receipt(fixture_root: Path) -> None:
    receipt = _plan(fixture_root)

    assert receipt["schema_version"] == "ops.production_contract.recovery-receipt.v1"
    assert receipt["operation"] == "config_rollback"
    assert receipt["target_class"] == "fixture"
    assert receipt["result"] == "planned_dry_run_fixture"
    assert receipt["authority"] is False
    assert receipt["executed"] is False
    assert receipt["planned_commands"][-1]["command"][0] == "fixture.rollback.config.prepare"
    assert all(
        command["command"][0].startswith("fixture.")
        for command in receipt["planned_commands"]
    )
    assert all(
        Path(argument).is_relative_to(fixture_root)
        for command in receipt["planned_commands"]
        for argument in command["command"][1:]
        if "/" in argument
    )


def test_dry_run_reads_and_revalidates_the_same_receipt(fixture_root: Path) -> None:
    generated = _plan(fixture_root)
    receipt_file = fixture_root / "plan-receipt.json"
    receipt_file.write_text(json.dumps(generated), encoding="utf-8")

    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--plan-receipt",
        str(receipt_file),
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == generated


def test_dry_run_does_not_source_operations_hook(fixture_root: Path, tmp_path: Path) -> None:
    hook_marker = tmp_path / "hook-was-sourced"
    hook_file = tmp_path / "operations-hook.sh"
    hook_file.write_text(f"touch '{hook_marker}'\n", encoding="utf-8")

    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--operation",
        "config_rollback",
        hook_file=hook_file,
    )

    assert result.returncode == 0, result.stderr
    assert hook_marker.exists() is False


@pytest.mark.parametrize("missing", ["--dry-run", "--fixture"])
def test_dry_run_requires_explicit_fixture_only_markers(
    fixture_root: Path, missing: str
) -> None:
    arguments = [
        "--fixture-root",
        str(fixture_root),
        "--operation",
        "config_rollback",
    ]
    if missing == "--dry-run":
        arguments = ["--fixture", *arguments]
    else:
        arguments = ["--dry-run", *arguments]

    result = _dry_run(fixture_root, *arguments)

    assert result.returncode == 2
    rejection = json.loads(result.stdout)
    assert rejection["result"] == "rejected"
    assert rejection["authority"] is False
    assert rejection["executed"] is False


@pytest.mark.parametrize("artifact_id", ["http://production.example", "api-key-value"])
def test_production_endpoint_and_secret_like_parameters_fail_closed(
    fixture_root: Path, artifact_id: str
) -> None:
    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--operation",
        "config_rollback",
        "--artifact-id",
        artifact_id,
    )

    assert result.returncode == 2
    rejection = json.loads(result.stdout)
    assert rejection["result"] == "rejected"
    assert rejection["authority"] is False
    assert rejection["executed"] is False


def test_read_receipt_rejects_non_fixture_and_nonexecuting_markers_are_required(
    fixture_root: Path,
) -> None:
    receipt = _plan(fixture_root)
    receipt["planned_commands"][0]["command"][0] = "docker.rollback.restore"
    receipt_file = fixture_root / "invalid-verb.json"
    receipt_file.write_text(json.dumps(receipt), encoding="utf-8")

    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--plan-receipt",
        str(receipt_file),
    )

    assert result.returncode == 2
    rejection = json.loads(result.stdout)
    assert rejection["result"] == "rejected"
    assert rejection["authority"] is False
    assert rejection["executed"] is False


def test_read_receipt_rejects_path_outside_fixture_root(fixture_root: Path) -> None:
    receipt = _plan(fixture_root)
    receipt["planned_commands"][0]["command"][1] = "/production/config/app.current"
    receipt_file = fixture_root / "outside-boundary.json"
    receipt_file.write_text(json.dumps(receipt), encoding="utf-8")

    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--plan-receipt",
        str(receipt_file),
    )

    assert result.returncode == 2
    rejection = json.loads(result.stdout)
    assert rejection["result"] == "rejected"
    assert rejection["authority"] is False
    assert rejection["executed"] is False


def test_read_receipt_rejects_live_endpoint_intent(fixture_root: Path) -> None:
    receipt = _plan(fixture_root)
    receipt["planned_commands"][0]["intent"] = "contact https://production.example/rollback"
    receipt_file = fixture_root / "live-intent.json"
    receipt_file.write_text(json.dumps(receipt), encoding="utf-8")

    result = _dry_run(
        fixture_root,
        "--dry-run",
        "--fixture",
        "--fixture-root",
        str(fixture_root),
        "--plan-receipt",
        str(receipt_file),
    )

    assert result.returncode == 2
    rejection = json.loads(result.stdout)
    assert rejection["result"] == "rejected"
    assert rejection["authority"] is False
    assert rejection["executed"] is False


def test_existing_snapshot_and_rollback_commands_remain_documented() -> None:
    usage = subprocess.run(
        ["bash", str(ROLLBACK_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert usage.returncode == 1
    assert "snapshot" in usage.stdout
    assert "rollback [snapshot_id]" in usage.stdout
    assert "--no-restart" in usage.stdout
