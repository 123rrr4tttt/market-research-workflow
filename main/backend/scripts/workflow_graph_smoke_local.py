#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.workflow_graph import compiler, runtime


@dataclass
class SmokeCase:
    name: str
    dsl: dict[str, Any]
    run_input: dict[str, Any]


def _graph(nodes: list[dict[str, Any]], edges: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "version": "1.0",
        "nodes": nodes,
        "edges": [{"from": s, "to": t} for s, t in edges],
    }


def build_cases() -> list[SmokeCase]:
    return [
        SmokeCase(
            "01_vector_only",
            _graph(
                [
                    {
                        "node_id": "n1",
                        "node_type": "vector_search",
                        "config": {
                            "input_vars": [{"name": "query", "source": "input", "required": True}],
                            "top_k": 2,
                            "output_vars": [{"name": "hits"}],
                        },
                    }
                ],
                [],
            ),
            {"query": "market"},
        ),
        SmokeCase(
            "02_llm_only",
            _graph(
                [
                    {
                        "node_id": "n1",
                        "node_type": "llm_call",
                        "config": {
                            "input_vars": [{"name": "prompt", "source": "input", "required": True}],
                            "prompt_template": "{prompt}",
                            "model": "gpt-4.1-mini",
                            "output_vars": [{"name": "text"}],
                        },
                    }
                ],
                [],
            ),
            {"prompt": "hello"},
        ),
        SmokeCase(
            "03_vector_to_llm",
            _graph(
                [
                    {
                        "node_id": "vec",
                        "node_type": "vector_search",
                        "config": {
                            "input_vars": [{"name": "query", "source": "input", "required": True}],
                            "output_vars": [{"name": "query"}],
                        },
                    },
                    {
                        "node_id": "llm",
                        "node_type": "llm_call",
                        "config": {
                            "input_vars": [{"name": "prompt", "source": "node_output", "from_node": "vec", "from_key": "query"}],
                            "prompt_template": "{prompt}",
                            "output_vars": [{"name": "text"}],
                        },
                    },
                ],
                [("vec", "llm")],
            ),
            {"query": "ca lottery"},
        ),
        SmokeCase(
            "04_join_two",
            _graph(
                [
                    {"node_id": "a", "node_type": "vector_search", "config": {"query": "a"}},
                    {"node_id": "b", "node_type": "vector_search", "config": {"query": "b"}},
                    {"node_id": "j", "node_type": "join", "config": {}},
                ],
                [("a", "j"), ("b", "j")],
            ),
            {},
        ),
        SmokeCase(
            "05_expression_input",
            _graph(
                [
                    {
                        "node_id": "n1",
                        "node_type": "llm_call",
                        "config": {
                            "input_vars": [{"name": "prompt", "source": "expression", "expr": "={{$input.query}}", "required": True}],
                            "prompt_template": "{prompt}",
                        },
                    }
                ],
                [],
            ),
            {"query": "expression smoke"},
        ),
        SmokeCase(
            "06_constant_input",
            _graph(
                [
                    {
                        "node_id": "n1",
                        "node_type": "llm_call",
                        "config": {
                            "input_vars": [{"name": "prompt", "source": "constant", "default_value": "hello constant"}],
                            "prompt_template": "{prompt}",
                        },
                    }
                ],
                [],
            ),
            {},
        ),
        SmokeCase(
            "07_multihop_chain",
            _graph(
                [
                    {"node_id": "n1", "node_type": "vector_search", "config": {"query": "seed", "output_vars": [{"name": "query"}]}},
                    {
                        "node_id": "n2",
                        "node_type": "llm_call",
                        "config": {
                            "input_vars": [{"name": "prompt", "source": "node_output", "from_node": "n1", "from_key": "query"}],
                            "prompt_template": "{prompt}",
                            "output_vars": [{"name": "text"}],
                        },
                    },
                    {"node_id": "n3", "node_type": "join", "config": {}},
                ],
                [("n1", "n2"), ("n2", "n3")],
            ),
            {},
        ),
        SmokeCase(
            "08_full_chain",
            _graph(
                [
                    {"node_id": "in", "node_type": "vector_search", "config": {"input_vars": [{"name": "query", "source": "input"}], "output_vars": [{"name": "query"}]}},
                    {"node_id": "ctx", "node_type": "vector_search", "config": {"query": "context", "output_vars": [{"name": "query"}]}},
                    {
                        "node_id": "llm",
                        "node_type": "llm_call",
                        "config": {
                            "input_vars": [
                                {"name": "prompt", "source": "node_output", "from_node": "in", "from_key": "query"},
                                {"name": "extra", "source": "node_output", "from_node": "ctx", "from_key": "query"},
                            ],
                            "prompt_template": "{prompt}\n{extra}",
                            "output_vars": [{"name": "text"}],
                        },
                    },
                    {"node_id": "out", "node_type": "join", "config": {}},
                ],
                [("in", "llm"), ("ctx", "llm"), ("llm", "out")],
            ),
            {"query": "full chain"},
        ),
    ]


def main() -> int:
    failed: list[str] = []
    for idx, case in enumerate(build_cases(), start=1):
        graph_id = f"smoke-{idx:02d}"
        compiler.compile({"graph_id": graph_id, "dsl": case.dsl})
        result = runtime.run({"graph_id": graph_id, "input": case.run_input})
        status = str(result.get("status") or "")
        if status != "succeeded":
            failed.append(case.name)
            print(f"[FAIL] {case.name}: {json.dumps(result, ensure_ascii=False)}")
        else:
            print(f"[PASS] {case.name} run_id={result.get('run_id')}")
    if failed:
        print(f"\nSMOKE FAILED: {len(failed)} case(s): {', '.join(failed)}")
        return 1
    print("\nSMOKE PASSED: all 8 cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
