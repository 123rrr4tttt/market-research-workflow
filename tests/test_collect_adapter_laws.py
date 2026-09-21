from __future__ import annotations

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws

from app.services.collect_runtime.contracts import CollectRequest, CollectResult


class InMemoryCollectAdapter:
    def __init__(self) -> None:
        self.requests: list[CollectRequest] = []

    def run(self, request: CollectRequest) -> CollectResult:
        self.requests.append(request)
        return CollectResult(
            channel=request.channel,
            status="completed",
            inserted=len(request.query_terms),
            meta={"query_terms": list(request.query_terms)},
        )


TestCollectAdapter = port_laws(
    "CollectAdapter",
    InMemoryCollectAdapter,
    PortLawSpec(
        idempotent=[
            Idempotent(
                "run is deterministic",
                lambda adapter: adapter.run(
                    CollectRequest(channel="search.market", query_terms=["a"])
                ).meta,
            )
        ],
        ordered=[
            Ordered(
                "request order is preserved",
                first=lambda adapter: adapter.run(
                    CollectRequest(channel="search.market", query_terms=["first"])
                ),
                second=lambda adapter: adapter.run(
                    CollectRequest(channel="search.market", query_terms=["second"])
                ),
                observe=lambda adapter: [r.query_terms for r in adapter.requests],
                commutes=False,
            )
        ],
    ),
)
