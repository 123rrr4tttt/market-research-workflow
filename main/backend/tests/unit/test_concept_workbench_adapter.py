from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from app.services.crawlers_mgmt import workbench


@pytest.fixture
def configured(monkeypatch, tmp_path):
    sdk = tmp_path / "sdk"
    (sdk / "concept_workbench").mkdir(parents=True)
    (sdk / "concept_workbench" / "cli.py").write_text("# original CLI\n")
    for method in workbench.METHOD_DEFINITIONS:
        directory = sdk / "skills" / method["id"]
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"# {method['title']}\n")
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setenv(workbench.SDK_ROOT_ENV, str(sdk))
    monkeypatch.setenv(workbench.TARGETS_ENV, json.dumps({"mrw": {"root": str(target), "project_key": "project_a", "label": "MRW"}}))
    monkeypatch.setattr(workbench, "_functorial_kit_available", lambda: True)
    return sdk, target


def test_module_is_project_bound_and_observation_has_no_effect(configured, monkeypatch):
    monkeypatch.setattr(workbench, "_run_subprocess", lambda *args: pytest.fail("directory must not execute"))
    module = workbench.workbench_module("project_a")
    assert module["available"] is True
    assert module["targets"] == [{"id": "mrw", "label": "MRW"}]
    assert len(module["methods"]) == 9
    assert not workbench.workbench_module("project_b")["available"]
    configured[1].rmdir()
    assert not workbench.workbench_module("project_a")["available"]


@pytest.mark.parametrize("operation", [entry["id"] for entry in workbench.OPERATION_DEFINITIONS])
def test_operations_invoke_original_cli_and_preserve_results(configured, monkeypatch, operation):
    observed = []
    def invoke(argv, env):
        observed.append((argv, env))
        return subprocess.CompletedProcess(argv, 7, '{"original":true}', "original failure")
    monkeypatch.setattr(workbench, "_run_subprocess", invoke)
    arguments = {"target_id": "mrw"}
    if operation in {"scan", "materials"}:
        arguments["paths"] = ["source.py"]
    result = workbench.run_workbench(operation, arguments, "project_a")
    assert result == {"exit_code": 7, "stdout": '{"original":true}', "stderr": "original failure", "report": {"original": True}}
    argv, env = observed[0]
    assert argv[:5] == [workbench.sys.executable, "-B", "-m", "concept_workbench.cli", operation]
    assert str(configured[1]) in argv or f"--root={configured[1]}" in argv
    assert env["PYTHONPATH"].split(workbench.os.pathsep)[0] == str(configured[0])
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


@pytest.mark.parametrize("arguments,project", [
    ({"target_id": "mrw", "root": "/"}, "project_a"),
    ({"target_id": "mrw", "argv": []}, "project_a"),
    ({"target_id": "mrw"}, "project_b"),
    ({"target_id": "unknown"}, "project_a"),
    ({"target_id": "mrw", "catalog": "../outside.py"}, "project_a"),
    ({"target_id": "mrw", "catalog": "--help"}, "project_a"),
])
def test_invalid_requests_have_zero_effect(configured, monkeypatch, arguments, project):
    monkeypatch.setattr(workbench, "_run_subprocess", lambda *args: pytest.fail("invalid request executed"))
    with pytest.raises(ValueError):
        workbench.run_workbench("check", arguments, project)


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "--help", "source\x00.py", "source\n.py", "link.py"])
def test_scan_paths_reject_escape_and_flag_injection(configured, monkeypatch, path, tmp_path):
    (configured[1] / "link.py").symlink_to(tmp_path / "outside.py")
    monkeypatch.setattr(workbench, "_run_subprocess", lambda *args: pytest.fail("invalid path executed"))
    with pytest.raises(ValueError):
        workbench.run_workbench("scan", {"target_id": "mrw", "paths": [path]}, "project_a")


def test_method_reads_actual_bytes_and_rejects_escape(configured):
    source = configured[0] / "skills" / "workbench-authoring" / "SKILL.md"
    result = workbench.read_workbench_method("workbench-authoring")
    assert result["content_text"] == source.read_text()
    assert result["content_digest"] == hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        workbench.read_workbench_method("workbench-authoring", "../functorial-construction/SKILL.md")
    with pytest.raises(ValueError):
        workbench.read_workbench_method("unknown")
    source.write_bytes(b"x" * (workbench.MAX_METHOD_FILE_BYTES + 1))
    with pytest.raises(ValueError):
        workbench.read_workbench_method("workbench-authoring")


def test_transport_errors_keep_failure_and_serializable_output(configured, monkeypatch):
    def timeout(*args):
        raise subprocess.TimeoutExpired("original CLI", 300, output=b"partial", stderr=b"timeout")
    monkeypatch.setattr(workbench, "_run_subprocess", timeout)
    result = workbench.run_workbench("check", {"target_id": "mrw"}, "project_a")
    assert result["exit_code"] == 124
    assert result["stdout"] == "partial"
    json.dumps(result)
    def unavailable(*args):
        raise OSError("CLI transport unavailable")
    monkeypatch.setattr(workbench, "_run_subprocess", unavailable)
    assert workbench.run_workbench("check", {"target_id": "mrw"}, "project_a")["exit_code"] == 127
