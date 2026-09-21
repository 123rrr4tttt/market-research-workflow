#!/usr/bin/env python3
"""Bounded Contract14 wrapper for deterministic search-quality generators.

The legacy generators default to deleted automation-run locations.  This
wrapper supplies explicit successor output paths and rebinding only in memory;
it never changes production source or starts a service.  All network socket
operations are denied while the selected generator executes.
"""

from __future__ import annotations

import argparse
import importlib.util
import socket
import ssl  # preload before network guard; ssl.SSLSocket subclasses socket.socket
from pathlib import Path

_SSL_PRELOADED = ssl.OPENSSL_VERSION

REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED_ROOT = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")  # noqa: TRY003
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _NetworkDenied:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection
        self._getaddrinfo = socket.getaddrinfo

        def denied(*_args, **_kwargs):
            raise RuntimeError("CONTRACT14_NETWORK_BLOCKED")

        socket.socket = denied  # type: ignore[assignment]
        socket.create_connection = denied  # type: ignore[assignment]
        socket.getaddrinfo = denied  # type: ignore[assignment]
        return self

    def __exit__(self, *_exc):
        socket.socket = self._socket  # type: ignore[assignment]
        socket.create_connection = self._create_connection  # type: ignore[assignment]
        socket.getaddrinfo = self._getaddrinfo  # type: ignore[assignment]
        return False


def run(
    stage: str,
    out_dir: Path,
    trace_path: Path | None,
    embedding_path: Path | None,
    wave55_path: Path | None,
) -> None:
    scripts = REPO_ROOT / "ops" / "search-lab" / "scripts"
    if stage == "trace":
        module = _load("contract14_search_provider_trace", scripts / "search_provider_trace_contract.py")
        with _NetworkDenied():
            out_dir.mkdir(parents=True, exist_ok=True)
            contract = module.build_contract()
            target = out_dir / "search_provider_trace_contract.json"
            target.write_text(
                module.json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(module.json.dumps({"status": "passed", "out": str(target)}, sort_keys=True))
            return
    if stage == "embedding":
        module = _load("contract14_wave55_embedding", scripts / "wave55_live_embedding_provider_gate.py")
        with _NetworkDenied():
            contract = module.build_contract()
            module.write_outputs(out_dir, contract)
            print(module.json.dumps({"status": contract["status"], "out_dir": str(out_dir)}, sort_keys=True))
            if contract["status"] != "passed":
                raise SystemExit(1)
            return
    if stage == "wave55":
        if trace_path is None or embedding_path is None:
            raise ValueError("wave55 requires --trace-path and --embedding-path")  # noqa: TRY003
        module = _load("contract14_wave55_search_quality", scripts / "wave55_oss_node_search_quality_gate.py")
        with _NetworkDenied():
            module.OPEN_SEARCH_TRACE = trace_path
            module.LIVE_EMBEDDING_PROVIDER_GATE = embedding_path
            contract = module.build_contract()
            module.write_outputs(out_dir, contract)
            print(module.json.dumps({"status": contract["status"], "out_dir": str(out_dir)}, sort_keys=True))
            if contract["status"] != "passed":
                raise SystemExit(1)
            return
    if stage == "wave57":
        if wave55_path is None:
            raise ValueError("wave57 requires --wave55-path")  # noqa: TRY003
        module = _load(
            "contract14_wave57_public_corpus",
            scripts / "wave57_oss_node_public_corpus_semantic_relevance_gate.py",
        )
        with _NetworkDenied():
            module.WAVE55_SEARCH_QUALITY_ARTIFACT = wave55_path
            contract = module.build_contract()
            module.write_outputs(out_dir, contract)
            print(module.json.dumps({"status": contract["status"], "out_dir": str(out_dir)}, sort_keys=True))
            if contract["status"] != "passed":
                raise SystemExit(1)
            return
    raise ValueError(f"unknown stage: {stage}")  # noqa: TRY003


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("trace", "embedding", "wave55", "wave57"), required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--trace-path")
    parser.add_argument("--embedding-path")
    parser.add_argument("--wave55-path")
    args = parser.parse_args()
    run(
        args.stage,
        Path(args.out_dir).resolve(),
        Path(args.trace_path).resolve() if args.trace_path else None,
        Path(args.embedding_path).resolve() if args.embedding_path else None,
        Path(args.wave55_path).resolve() if args.wave55_path else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
