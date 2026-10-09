from __future__ import annotations

from .chains import (
    PolicyClassification,
    build_policy_classification_chain,
    build_policy_summary_chain,
)


_classification_chain = None
_summary_chain = None


def _get_classification_chain():
    global _classification_chain
    if _classification_chain is None:
        _classification_chain = build_policy_classification_chain()
    return _classification_chain


def _get_summary_chain():
    global _summary_chain
    if _summary_chain is None:
        _summary_chain = build_policy_summary_chain()
    return _summary_chain


def classify_policy_text(document: str) -> PolicyClassification:
    return _get_classification_chain().invoke({"document": document})


def summarize_policy_text(document: str) -> str:
    return _get_summary_chain().invoke({"document": document})


def batch_classify(documents: list[str]) -> list[PolicyClassification]:
    return list(_get_classification_chain().batch([{"document": doc} for doc in documents]))


def batch_summarize(documents: list[str]) -> list[str]:
    return list(_get_summary_chain().batch([{"document": doc} for doc in documents]))

