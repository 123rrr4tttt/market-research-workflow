#!/usr/bin/env python3
from pathlib import Path

DOC = Path("main/backend/docs/implementation/R8_1_D_ACCEPTANCE.md")
required_tokens = [
    "SPDX SBOM",
    "验签失败阻断发布",
    "secret scanning",
    "dependency scanning",
    "image scanning",
    "最小权限复核",
]

if not DOC.exists():
    raise SystemExit(f"missing doc: {DOC}")

text = DOC.read_text(encoding="utf-8")
missing = [t for t in required_tokens if t not in text]
if missing:
    raise SystemExit("missing tokens: " + ", ".join(missing))

print("R8.1-D verification passed")
