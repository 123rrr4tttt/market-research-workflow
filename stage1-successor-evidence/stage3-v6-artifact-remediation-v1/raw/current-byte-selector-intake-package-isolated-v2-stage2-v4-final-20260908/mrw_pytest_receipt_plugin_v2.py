"""Capture the exact nodeids collected by the receipt run."""
import json
import os
from pathlib import Path


def pytest_collection_finish(session):
    output = Path(os.environ["MRW_PYTEST_NODEIDS_PATH"])
    output.write_text(
        json.dumps([item.nodeid for item in session.items], ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
