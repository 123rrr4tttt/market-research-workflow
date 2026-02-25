from __future__ import annotations

from .chains import (
    PolicyClassification,
    build_policy_classification_chain,
    build_policy_summary_chain,
)


_CLASSIFICATION_CHAIN = build_policy_classification_chain()
_SUMMARY_CHAIN = build_policy_summary_chain()


def classify_policy_text(document: str) -> PolicyClassification:
    return _CLASSIFICATION_CHAIN.invoke({"document": document})


def summarize_policy_text(document: str) -> str:
    return _SUMMARY_CHAIN.invoke({"document": document})


def batch_classify(documents: list[str]) -> list[PolicyClassification]:
    return list(_CLASSIFICATION_CHAIN.batch([{"document": doc} for doc in documents]))


def batch_summarize(documents: list[str]) -> list[str]:
    return list(_SUMMARY_CHAIN.batch([{"document": doc} for doc in documents]))


