from dataclasses import dataclass
from pathlib import Path
from .config import KitConfig
from .scan import Violation

"""Effect shell for the architecture gates: reads the project, runs the pure scan, builds a test class."""
@dataclass(frozen=True, slots=True)
class ProjectScan:
    config: KitConfig
    violations: tuple[Violation, ...]
    baseline: tuple[str, ...]
    ...


def scan_project(root: str | Path) -> ProjectScan:
    ...

def architecture_gate_tests(root: str | Path) -> type:
    """Return a pytest test class with one test per gate. KIT_ARCH_BASELINE_WRITE=1 rewrites the baseline."""
    ...
