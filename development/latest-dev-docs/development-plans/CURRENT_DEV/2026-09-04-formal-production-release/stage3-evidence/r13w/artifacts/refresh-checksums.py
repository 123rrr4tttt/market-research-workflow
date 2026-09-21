#!/usr/bin/env python3
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parent
excluded = {
    root / "SHA256SUMS",
    root / "logs/finalize-evidence.log",
    root / "logs/checksums-verify.log",
    root / "metadata/checksums-verify.exit",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


paths = sorted(path for path in root.rglob("*") if path.is_file() and path not in excluded)
(root / "SHA256SUMS").write_text(
    "\n".join(f"{digest(path)}  {path.relative_to(root).as_posix()}" for path in paths) + "\n"
)
