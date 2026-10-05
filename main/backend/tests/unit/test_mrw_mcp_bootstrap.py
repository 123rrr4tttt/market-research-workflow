import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "mrw_mcp_server.py"
PYTHON = Path(sys.executable)


def test_stdio_server_starts_without_caller_pythonpath() -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    tools_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

    with tempfile.TemporaryDirectory() as temporary_dir:
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONPATH"
        }
        env.pop("MRW_BACKEND", None)
        completed = subprocess.run(
            [str(PYTHON), str(SCRIPT)],
            cwd=temporary_dir,
            env=env,
            input=json.dumps(initialize) + "\n" + json.dumps(tools_list) + "\n",
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout.endswith("\n")

    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [message["id"] for message in messages] == [1, 2]
    assert all(message["jsonrpc"] == "2.0" for message in messages)
    assert "result" in messages[0]

    tools = messages[1]["result"]["tools"]
    assert len(tools) > 0
    assert all({"name", "inputSchema"} <= set(tool) for tool in tools)
