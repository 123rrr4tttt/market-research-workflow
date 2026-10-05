import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "mrw_mcp_server.py"
PYTHON = Path(sys.executable)


def _request(request_id: int, method: str, params: dict | None = None) -> str:
    message: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return json.dumps(message)


def _run_stdio_session(*calls: dict) -> list[dict]:
    initialize = {"protocolVersion": "2024-11-05"}
    messages = [
        _request(1, "initialize", initialize),
        _request(2, "tools/list"),
    ]
    for index, call in enumerate(calls, start=3):
        messages.append(_request(index, "tools/call", call))

    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env.pop("MRW_BACKEND", None)
    env["agent_session_db_store_enabled"] = "false"
    with tempfile.TemporaryDirectory() as temporary_dir:
        completed = subprocess.run(
            [str(PYTHON), str(SCRIPT)],
            cwd=temporary_dir,
            env=env,
            input="\n".join(messages) + "\n",
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return [json.loads(line) for line in completed.stdout.splitlines()]


def test_stdio_projection_annotates_read_write_and_stays_unbound() -> None:
    responses = _run_stdio_session()
    assert [response["id"] for response in responses] == [1, 2]
    assert responses[0]["result"]["hostAuthorization"] == {
        "status": "unbound",
        "reason": "trusted_host_binding_unavailable",
    }

    tools = {tool["name"]: tool for tool in responses[1]["result"]["tools"]}
    assert "skill.search" in tools
    assert "skill.load" in tools
    assert "writing.document.create" in tools

    assert tools["skill.search"]["annotations"]["readOnlyHint"] is True
    assert tools["skill.load"]["annotations"]["readOnlyHint"] is True
    assert tools["writing.document.create"]["annotations"]["readOnlyHint"] is False
    # permission=allow does not imply read-only: these write tools are allowed but
    # still annotated readOnlyHint=False from their spec.risk.
    assert (
        tools["agent_investigation.leads.append"]["annotations"]["readOnlyHint"]
        is False
    )
    assert tools["ingest.url_pool.submit"]["annotations"]["readOnlyHint"] is False

    # Functorial composition is not fabricated by the stdio projection.
    assert not {"create_motif", "create_workflow", "run_workflow"} & set(tools)


def test_functorial_calls_are_unsupported_not_scheduled() -> None:
    responses = _run_stdio_session(
        {
            "name": "create_motif",
            "arguments": {"motif_id": "m", "name": "m", "composition": []},
        },
        {
            "name": "create_workflow",
            "arguments": {"workflow_id": "w", "name": "w", "steps": []},
        },
        {
            "name": "run_workflow",
            "arguments": {"workflow_id": "w", "project_key": "project_a"},
        },
    )
    results = [response["result"] for response in responses[2:]]
    assert all(result["isError"] is True for result in results)
    assert [result["structuredContent"]["code"] for result in results] == [
        "unsupported",
        "unsupported",
        "unsupported",
    ]
    for result in results:
        assert "contract_version" not in result["structuredContent"]
        assert "session_id" not in result["structuredContent"]


def test_scoped_and_write_calls_fail_closed_without_host_binding() -> None:
    responses = _run_stdio_session(
        {"name": "writing.document.create", "arguments": {"title": "demo"}},
        {"name": "task.cancel", "arguments": {}},
        {
            "name": "writing.document.create",
            "arguments": {"project_key": "project_a", "title": "demo"},
        },
        {"name": "project.summary.read", "arguments": {"session_id": "sess-1"}},
        {"name": "project.summary.read", "arguments": {}},
    )
    results = [response["result"] for response in responses[2:]]
    assert all(result["isError"] is True for result in results)
    structured = [result["structuredContent"] for result in results]
    assert [item["code"] for item in structured] == [
        "authorization_required",
        "authorization_required",
        "scope_required",
        "scope_required",
        "scope_required",
    ]
    assert all(item["approval_required"] is True for item in structured)
    assert all(
        item["host_authorization"]["status"] == "unbound" for item in structured
    )
    # zero effect: denied calls carry no executed-tool payload.
    for item in structured:
        assert not {"contract_version", "session_id", "result"} & set(item)


def test_public_registry_discovery_is_the_only_unbound_call_success() -> None:
    responses = _run_stdio_session(
        {
            "name": "skill.search",
            "arguments": {"query": "workflow", "include_write_skills": False},
        },
        {
            "name": "skill.load",
            "arguments": {"skill_id": "project_retrieval.current"},
        },
        {"name": "skill.search", "arguments": {"query": "x", "project_key": "project_a"}},
    )
    allowed = responses[2]["result"]
    assert allowed["isError"] is False
    assert allowed["structuredContent"]["contract_version"] == "skill.search.v1"

    loaded = responses[3]["result"]
    assert loaded["isError"] is False
    assert loaded["structuredContent"]["contract_version"] == "skill.load.v1"

    rejected = responses[4]["result"]
    assert rejected["isError"] is True
    assert rejected["structuredContent"]["code"] == "scope_required"
