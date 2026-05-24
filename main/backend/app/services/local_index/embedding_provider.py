from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Iterable, Protocol


LOCAL_LIVE_EMBEDDING_PROVIDER_ID = "repo_local_token_hashing"
LOCAL_LIVE_EMBEDDING_MODEL = "repo-local-token-hashing-v1"
LOCAL_LIVE_EMBEDDING_MODEL_VERSION = "2026-05-23.wave56"
LOCAL_LIVE_VECTOR_VERSION = "repo-local-live-v2"
DEFAULT_LOCAL_LIVE_EMBEDDING_DIM = 512


class LocalEmbeddingProvider(Protocol):
    provider_id: str
    model: str
    model_version: str
    vector_version: str
    embedding_dim: int
    network_required: bool

    def embed_text(self, text: str) -> list[float]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        ...

    def metadata(self) -> dict[str, object]:
        ...

    def readback(self, texts: Iterable[str]) -> dict[str, object]:
        ...


@dataclass(frozen=True)
class EmbeddingVectorReadback:
    text_digest: str
    vector_digest: str
    embedding_dim: int
    norm: float
    non_zero_dimensions: int

    def to_dict(self) -> dict[str, object]:
        return {
            "text_digest": self.text_digest,
            "vector_digest": self.vector_digest,
            "embedding_dim": self.embedding_dim,
            "norm": self.norm,
            "non_zero_dimensions": self.non_zero_dimensions,
        }


class RepoLocalHashingEmbeddingProvider:
    """Executable local embedding provider for repo-local vector gates.

    This provider is intentionally dependency-free and network-free. It is not a
    production semantic model; it gives the local vector path a real provider
    boundary with deterministic vectors, provenance, and readback.
    """

    provider_id = LOCAL_LIVE_EMBEDDING_PROVIDER_ID
    model = LOCAL_LIVE_EMBEDDING_MODEL
    model_version = LOCAL_LIVE_EMBEDDING_MODEL_VERSION
    vector_version = LOCAL_LIVE_VECTOR_VERSION
    network_required = False

    def __init__(self, embedding_dim: int = DEFAULT_LOCAL_LIVE_EMBEDDING_DIM) -> None:
        if embedding_dim < 8:
            raise ValueError("embedding_dim must be at least 8")
        self.embedding_dim = int(embedding_dim)

    def embed_text(self, text: str) -> list[float]:
        values = [0.0 for _ in range(self.embedding_dim)]
        for feature, weight in _weighted_features(text):
            digest = hashlib.sha256(feature.encode("utf-8", errors="replace")).digest()
            index = int.from_bytes(digest[:4], "big") % self.embedding_dim
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign * weight
        return _normalize(values)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def metadata(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "provider_family": "repo_local",
            "model": self.model,
            "model_version": self.model_version,
            "embedding_dim": self.embedding_dim,
            "vector_version": self.vector_version,
            "network_required": self.network_required,
        }

    def readback(self, texts: Iterable[str]) -> dict[str, object]:
        rows = [_vector_readback(str(text or ""), self.embed_text(str(text or ""))) for text in texts]
        failures: list[str] = []
        if not rows:
            failures.append("no_texts_embedded")
        for index, row in enumerate(rows, start=1):
            if row.embedding_dim != self.embedding_dim:
                failures.append(f"row_{index}:embedding_dim_mismatch")
            if row.non_zero_dimensions <= 0:
                failures.append(f"row_{index}:zero_vector")
            if not 0.999 <= row.norm <= 1.001:
                failures.append(f"row_{index}:vector_norm_not_unit")
        return {
            **self.metadata(),
            "status": "passed" if not failures else "failed",
            "executable": True,
            "live_provider_verified": not failures,
            "vector_count": len(rows),
            "vectors": [row.to_dict() for row in rows],
            "failures": failures,
        }


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
_ALIAS_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("robotics", ("robotic", "robotics", "robot", "robots", "automation", "autonomous", "embodied")),
    (
        "commercialization",
        ("commercial", "commercialization", "market", "revenue", "business", "deployment", "rollout", "adoption"),
    ),
    (
        "policy",
        (
            "policy",
            "regulation",
            "regulatory",
            "government",
            "grant",
            "grants",
            "funding",
            "subsidy",
            "subsidies",
            "incentive",
            "incentives",
            "procurement",
            "program",
            "public",
            "tender",
            "tenders",
        ),
    ),
    (
        "agriculture",
        (
            "agriculture",
            "agricultural",
            "commodity",
            "commodities",
            "crop",
            "crops",
            "farm",
            "farmer",
            "farming",
            "harvest",
            "futures",
            "insurance",
            "coverage",
            "risk",
            "volatility",
        ),
    ),
    (
        "energy",
        (
            "energy",
            "renewable",
            "renewables",
            "storage",
            "battery",
            "batteries",
            "grid",
            "procurement",
            "resilience",
            "infrastructure",
        ),
    ),
    ("safety", ("safety", "worker", "workers", "inspection", "inspections", "compliance", "hazard", "hazards")),
    ("event_ticketing", ("festival", "ticket", "tickets", "ticketing", "venue", "venues", "staff", "staffing")),
)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))


def _weighted_features(text: str) -> list[tuple[str, float]]:
    tokens = _tokenize(text)
    features: list[tuple[str, float]] = [(f"tok:{token}", 1.0) for token in tokens]
    features.extend((f"bigram:{left}_{right}", 1.65) for left, right in zip(tokens, tokens[1:]))
    for token in tokens:
        if len(token) >= 5 and token.isascii():
            for index in range(0, len(token) - 3):
                features.append((f"char4:{token[index:index + 4]}", 0.25))
    token_set = set(tokens)
    for canonical, aliases in _ALIAS_GROUPS:
        if token_set.intersection(aliases):
            features.append((f"alias:{canonical}", 0.55))
    return features or [("empty", 1.0)]


def _tokenize(text: str) -> list[str]:
    return [_normalize_token(match.group(0)) for match in _TOKEN_RE.finditer(str(text or "").lower())]


def _normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return [0.0 for _ in values]
    return [round(value / norm, 8) for value in values]


def _vector_readback(text: str, vector: list[float]) -> EmbeddingVectorReadback:
    text_digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    encoded = ",".join(f"{value:.8f}" for value in vector)
    vector_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    norm = math.sqrt(sum(value * value for value in vector))
    return EmbeddingVectorReadback(
        text_digest=text_digest,
        vector_digest=vector_digest,
        embedding_dim=len(vector),
        norm=round(norm, 6),
        non_zero_dimensions=sum(1 for value in vector if abs(value) > 0.0),
    )
