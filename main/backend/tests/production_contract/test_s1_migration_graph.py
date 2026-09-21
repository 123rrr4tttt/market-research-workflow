from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATION_FILE = (
    BACKEND_DIR
    / "migrations"
    / "versions"
    / "20260905_000001_merge_release_heads.py"
)
REVISION = "20260905_000001"
PARENTS = ("20260525_000001", "20260831_000002")


def _script_directory() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(config)


def test_merge_revision_is_sole_head() -> None:
    script = _script_directory()

    assert script.get_heads() == [REVISION]


def test_merge_revision_points_to_both_release_heads() -> None:
    script = _script_directory()
    revision = script.get_revision(REVISION)

    assert revision.down_revision == PARENTS
    assert revision.branch_labels == set()


def test_merge_migration_is_parseable_no_op() -> None:
    source = MIGRATION_FILE.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(MIGRATION_FILE))

    function_bodies = {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert set(function_bodies) >= {"upgrade", "downgrade"}

    for name in ("upgrade", "downgrade"):
        function = next(
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        )
        assert len(function.body) == 2
        docstring = ast.get_docstring(function)
        assert isinstance(docstring, str)
        assert isinstance(function.body[-1], ast.Pass)
