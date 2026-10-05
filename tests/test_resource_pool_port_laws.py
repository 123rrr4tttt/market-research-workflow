from __future__ import annotations

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws

class InMemoryHttpFetchPort:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch_html(self, url: str, **_: object) -> tuple[str, object]:
        self.urls.append(url)
        return f"<html>{url}</html>", {
            "text": f"<html>{url}</html>",
            "content": f"<html>{url}</html>".encode(),
            "headers": {"content-type": "text/html"},
            "status_code": 200,
            "final_url": url,
        }


class InMemoryOfficialAccessPort:
    def __init__(self) -> None:
        self.params: list[dict[str, object]] = []

    def handle(
        self,
        params: dict[str, object],
        project_key: str | None,
    ) -> dict[str, object]:
        self.params.append(dict(params))
        return {
            "project_key": project_key,
            "request_count": len(self.params),
            "provider_key": params.get("provider_key"),
        }


_fetch_idempotent: Idempotent[InMemoryHttpFetchPort] = Idempotent(
    "fetch same url is deterministic",
    lambda port: port.fetch_html("https://example.com")[0],
)
_fetch_ordered: Ordered[InMemoryHttpFetchPort] = Ordered(
    "url request order is preserved",
    first=lambda port: port.fetch_html("https://first.example"),
    second=lambda port: port.fetch_html("https://second.example"),
    observe=lambda port: list(port.urls),
    commutes=False,
)
_fetch_spec: PortLawSpec[InMemoryHttpFetchPort] = PortLawSpec(
    idempotent=[_fetch_idempotent], ordered=[_fetch_ordered]
)
TestHttpFetchPort = port_laws("HttpFetchPort", InMemoryHttpFetchPort, _fetch_spec)

_official_idempotent: Idempotent[InMemoryOfficialAccessPort] = Idempotent(
    "handle official request is deterministic",
    lambda port: port.handle({"provider_key": "arxiv"}, None)["provider_key"],
)
_official_ordered: Ordered[InMemoryOfficialAccessPort] = Ordered(
    "official request order is preserved",
    first=lambda port: port.handle({"provider_key": "first"}, None),
    second=lambda port: port.handle({"provider_key": "second"}, None),
    observe=lambda port: [row["provider_key"] for row in port.params],
    commutes=False,
)
_official_spec: PortLawSpec[InMemoryOfficialAccessPort] = PortLawSpec(
    idempotent=[_official_idempotent], ordered=[_official_ordered]
)
TestOfficialAccessPort = port_laws(
    "OfficialAccessPort", InMemoryOfficialAccessPort, _official_spec
)
