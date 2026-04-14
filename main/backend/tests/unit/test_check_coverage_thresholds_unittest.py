from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_coverage_thresholds.py"
    spec = importlib.util.spec_from_file_location("check_coverage_thresholds", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load check_coverage_thresholds module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_accumulate_normalizes_non_prefixed_paths(tmp_path):
    module = _load_module()
    coverage_file = tmp_path / "coverage.xml"
    coverage_file.write_text(
        """<?xml version='1.0'?>
<coverage>
  <packages>
    <package name='app'>
      <classes>
        <class filename='contracts/api.py'>
          <lines>
            <line number='1' hits='1'/>
            <line number='2' hits='0'/>
          </lines>
        </class>
        <class filename='api/other.py'>
          <lines>
            <line number='1' hits='1'/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        encoding="utf-8",
    )

    core, other = module.accumulate(coverage_file, ["app/contracts/api.py"])
    assert core.total == 2
    assert core.covered == 1
    assert other.total == 1
    assert other.covered == 1


def test_main_returns_code_2_for_invalid_xml(tmp_path, capsys, monkeypatch):
    module = _load_module()
    broken = tmp_path / "broken.xml"
    broken.write_text("<coverage><broken>", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_coverage_thresholds.py",
            "--coverage-file",
            str(broken),
            "--core-paths",
            "app/contracts/api.py",
        ],
    )

    code = module.main()
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid coverage xml" in captured.err
