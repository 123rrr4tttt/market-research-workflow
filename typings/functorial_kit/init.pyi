from pathlib import Path

"""`python -m functorial_kit init <dir>` — scaffold a project that runs the gates and one example law suite."""
def scaffold_files(package: str, kit_spec: str) -> dict[str, str]:
    ...

def write_scaffold(directory: str | Path, package: str = ..., kit_spec: str = ...) -> list[str]:
    ...
