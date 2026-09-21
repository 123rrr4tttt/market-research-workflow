from __future__ import annotations

import json
from pathlib import Path

from functorial_kit import architecture_gate_tests
from functorial_kit.contributions_cli import main as contributions_main


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "contributions" / "c8_graph_projection_catalog.py"

TestArchitecture = architecture_gate_tests(ROOT)


def test_contribution_projection_is_current(capsys) -> None:
    status = contributions_main(["check", "--catalog", str(CATALOG), "--root", str(ROOT)])

    assert status == 0
    report = json.loads(capsys.readouterr().out)
    assert report["command"] == "contributions check"
    assert report["clean"] is True
    assert report["changed_paths"] == []
