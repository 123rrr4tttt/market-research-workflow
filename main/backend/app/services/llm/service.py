from __future__ import annotations

from .chains import (
    PolicyClassification,
    build_policy_classification_chain,
    build_policy_summary_chain,
)


_CLASSIFICATION_CHAIN = None
_SUMMARY_CHAIN = None


def _get_classification_chain():
    global _CLASSIFICATION_CHAIN
    if _CLASSIFICATION_CHAIN is None:
        _CLASSIFICATION_CHAIN = build_policy_classification_chain()
    return _CLASSIFICATION_CHAIN


def _get_summary_chain():
    global _SUMMARY_CHAIN
    if _SUMMARY_CHAIN is None:
        _SUMMARY_CHAIN = build_policy_summary_chain()
    return _SUMMARY_CHAIN


def classify_policy_text(document: str) -> PolicyClassification:
    return _get_classification_chain().invoke({"document": document})


def summarize_policy_text(document: str) -> str:
    return _get_summary_chain().invoke({"document": document})


def batch_classify(documents: list[str]) -> list[PolicyClassification]:
    return list(_get_classification_chain().batch([{"document": doc} for doc in documents]))


def batch_summarize(documents: list[str]) -> list[str]:
    return list(_get_summary_chain().batch([{"document": doc} for doc in documents]))


