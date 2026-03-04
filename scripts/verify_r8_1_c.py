#!/usr/bin/env python3
from pathlib import Path

DOC = Path("main/backend/docs/implementation/R8_1_C_ACCEPTANCE.md")
required_tokens = [
    "业务 SLI + RED + USE",
    "burn_rate > 14",
    "burn_rate > 6",
    "http.method",
    "service.name",
]

if not DOC.exists():
    raise SystemExit(f"missing doc: {DOC}")

text = DOC.read_text(encoding="utf-8")
missing = [t for t in required_tokens if t not in text]
if missing:
    raise SystemExit("missing tokens: " + ", ".join(missing))

print("R8.1-C verification passed")
