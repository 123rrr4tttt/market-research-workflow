from pathlib import Path

from scripts.check_successor_runtime_dependencies import check


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_successor_runtime_dependency_direction_is_fail_closed() -> None:
    root = Path(__file__).resolve().parents[2] / "app/successor_runtime"
    report = check(root)
    assert report["ok"], report["violations"]
    assert report["files_checked"] > 0


def test_lint_rejects_inner_layer_importing_outer_layer(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "language/program.py",
        "class Program:\n    pass\n",
    )
    _write(
        tmp_path,
        "research/domain.py",
        "from app.successor_runtime.language.program import Program\n",
    )
    report = check(tmp_path)
    assert any(item["code"] == "LAYER_DIRECTION" for item in report["violations"])


def test_lint_scans_function_local_inner_layer_importing_outer_layer(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "language/program.py",
        "def helper() -> None:\n"
        "    from app.successor_runtime.runtime.ports import Port\n",
    )
    report = check(tmp_path)
    assert any(item["code"] == "LAYER_DIRECTION" for item in report["violations"])
    assert report["function_local_imports_scanned"] >= 1


def test_lint_accepts_allowed_runtime_to_pure_layers_direction(tmp_path: Path) -> None:
    _write(tmp_path, "research/object_types.py", "class ObjectType:\n    pass\n")
    _write(
        tmp_path,
        "language/program.py",
        "from app.successor_runtime.research.object_types import ObjectType\n"
        "class Program:\n    pass\n",
    )
    _write(
        tmp_path,
        "capabilities/contracts.py",
        "from app.successor_runtime.language.program import Program\n"
        "class Contract:\n    pass\n",
    )
    _write(
        tmp_path,
        "runtime/ports.py",
        "from app.successor_runtime.capabilities.contracts import Contract\n"
        "class Port:\n    pass\n",
    )
    report = check(tmp_path)
    assert report["ok"], report["violations"]


def test_lint_rejects_runtime_importing_effect_facility_directly(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "runtime/executor.py",
        "from app.successor_runtime.substrate.postgres.work_items import WorkItem\n",
    )
    report = check(tmp_path)
    assert any(item["code"] == "RUNTIME_ONLY_PORTS" for item in report["violations"])


def test_lint_rejects_module_import_cycle(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "language/a.py",
        "from app.successor_runtime.language.b import helper\n",
    )
    _write(
        tmp_path,
        "language/b.py",
        "from app.successor_runtime.language.a import helper\n",
    )
    report = check(tmp_path)
    assert any(item["code"] == "IMPORT_CYCLE" for item in report["violations"])


def test_lint_rejects_capability_direct_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "capabilities/contracts.py",
        "class OperationContract:\n    pass\n",
    )
    _write(tmp_path, "capabilities/alpha.py", "from .beta import helper\n")
    _write(tmp_path, "capabilities/beta.py", "def helper():\n    return 1\n")
    report = check(tmp_path)
    assert any(
        item["code"] == "CAPABILITY_DIRECT_IMPORT" for item in report["violations"]
    )


def test_lint_rejects_function_local_capability_direct_import(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "capabilities/contracts.py",
        "class OperationContract:\n    pass\n",
    )
    _write(
        tmp_path,
        "capabilities/alpha.py",
        "def load():\n    from .beta import helper\n",
    )
    _write(tmp_path, "capabilities/beta.py", "def helper():\n    return 1\n")
    report = check(tmp_path)
    assert any(
        item["code"] == "CAPABILITY_DIRECT_IMPORT" for item in report["violations"]
    )
    assert report["function_local_imports_scanned"] >= 1


def test_lint_allows_public_capability_shared_modules(tmp_path: Path) -> None:
    for name in (
        "contracts",
        "profiles",
        "catalog",
        "checksum",
        "codecs",
        "ingest_c7_common",
        "c8_common",
    ):
        _write(tmp_path, f"capabilities/{name}.py", "VALUE = 1\n")
    _write(
        tmp_path,
        "capabilities/alpha.py",
        "from .contracts import OperationContract\n"
        "from .profiles import AuthorityProfile\n"
        "from .catalog import build_catalog\n"
        "from .checksum import content_digest\n"
        "from .codecs import dataclass_codec\n",
    )
    report = check(tmp_path)
    assert report["ok"], report["violations"]


def test_lint_allows_family_common_c8_module(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "capabilities/c8_common.py",
        "class ReadHandle:\n    pass\n",
    )
    _write(
        tmp_path,
        "capabilities/c8_writing.py",
        "from .c8_common import ReadHandle\n",
    )
    report = check(tmp_path)
    assert report["ok"], report["violations"]


def test_lint_allows_family_common_c7_contract_module(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "capabilities/ingest_c7_common.py",
        "class CommitIntent:\n    pass\n",
    )
    _write(
        tmp_path,
        "capabilities/ingest_c7_program.py",
        "from .ingest_c7_common import CommitIntent\nclass Program:\n    pass\n",
    )
    report = check(tmp_path)
    assert report["ok"], report["violations"]


def test_lint_rejects_duplicate_canonical_class_owner(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "capabilities/alpha.py",
        'kind = "alpha.op.v1"\n'
        '_authority_profile(kind, canonical_owner="SharedLedger")\n',
    )
    _write(
        tmp_path,
        "capabilities/beta.py",
        'kind = "beta.op.v1"\n'
        '_authority_profile(kind, canonical_owner="SharedLedger")\n',
    )
    report = check(tmp_path)
    assert any(
        item["code"] == "DUPLICATE_CANONICAL_CLASS_OWNER"
        for item in report["violations"]
    )


def test_lint_accepts_typed_runtime_work_items_root_schema(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "runtime/assignments.py",
        "class RuntimeAssignment:\n    pass\n",
    )
    _write(
        tmp_path,
        "runtime/work_items.py",
        "from app.successor_runtime.runtime.assignments import RuntimeAssignment\n"
        "class WorkItemRoot:\n"
        "    assignment: RuntimeAssignment\n",
    )
    report = check(tmp_path)
    assert report["ok"], report["violations"]


def test_lint_rejects_runtime_work_items_importing_substrate(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "runtime/work_items.py",
        "from app.successor_runtime.substrate.postgres.work_items import WorkItem\n",
    )
    report = check(tmp_path)
    assert any(item["code"] == "RUNTIME_ONLY_PORTS" for item in report["violations"])
