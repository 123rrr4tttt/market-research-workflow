from dataclasses import dataclass
from ..core.failure import Failure, FailureFamily

"""Project config `functorial-kit.json` — exact version literal, relative paths."""
CONFIG_VERSION: str
config_failures: FailureFamily
@dataclass(frozen=True, slots=True)
class KitConfig:
    core_paths: tuple[str, ...]
    shell_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    registries_dir: str
    sketches: str
    baseline: str | None = ...


def parse_config(text: str) -> KitConfig | Failure:
    ...
