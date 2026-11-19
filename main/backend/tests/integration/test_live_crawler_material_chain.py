from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest


pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SOURCE_SCOPE = "dedicated localhost HTTP source; one generated path; no follow links"


@contextmanager
def _dedicated_http_source(run_token: str) -> Iterator[str]:
    source_path = f"/live-crawler-{run_token}"
    body = (
        "<!doctype html><html><head><title>Live Crawler Material</title></head>"
        f"<body><main>Live crawler material body {run_token}</main></body></html>"
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path != source_path:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(server.server_address[1])
        yield f"http://127.0.0.1:{port}{source_path}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name) or default).strip()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provider_job_id(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = str(payload.get("provider_job_id") or "").strip()
    if direct:
        return direct
    for key in ("terminal_output", "legacy_result", "result", "raw"):
        nested = _provider_job_id(payload.get(key))
        if nested:
            return nested
    return ""


def _status(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = [payload]
    for key in ("terminal_output", "legacy_result", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for item in candidates:
        value = str(item.get("status") or "").strip().lower()
        if value:
            return value
    return ""


def _find_mapping(
    payload: object,
    key: str,
    *,
    required_key: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, dict) and (required_key is None or required_key in value):
            return value
        for nested in payload.values():
            found = _find_mapping(nested, key, required_key=required_key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for nested in payload:
            found = _find_mapping(nested, key, required_key=required_key)
            if found is not None:
                return found
    return None


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    response = client.request(
        method,
        path,
        headers=headers,
        json=json_payload,
        params=params,
        timeout=20.0,
    )
    assert response.status_code < 400, f"{method} {path} failed: HTTP {response.status_code} {response.text}"
    return response


def test_live_source_url_crawler_to_material_and_graph_readback() -> None:
    enabled = str(os.getenv("MRW_LIVE_CRAWLER_CHAIN") or "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        pytest.skip("live crawler chain requires MRW_LIVE_CRAWLER_CHAIN=1")

    backend_base_url = _env("MRW_LIVE_CRAWLER_BASE_URL", "http://127.0.0.1:18086")
    scrapyd_base_url = _env("MRW_LIVE_CRAWLER_SCRAPYD_BASE_URL", "http://127.0.0.1:16886")
    project_key = _env("MRW_LIVE_CRAWLER_PROJECT_KEY", "completion_test")
    bootstrap_python = _env(
        "MRW_LIVE_CRAWLER_BOOTSTRAP_PYTHON",
        str(Path(sys.executable).resolve()),
    )
    app_site_packages = next(
        (path for path in sys.path if str(path).rstrip("/").endswith("site-packages")),
        "",
    )
    run_token = uuid.uuid4().hex[:10]
    crawler_key = f"live_crawler_{run_token}"
    channel_key = f"crawler.{crawler_key}"
    item_key = f"crawler.{crawler_key}.default"

    from app.services.crawlers.providers.scrapy import ScrapyCrawlerProvider

    headers = {"X-Project-Key": project_key}
    with (
        _dedicated_http_source(run_token) as target_url,
        httpx.Client(base_url=backend_base_url, headers=headers) as client,
    ):
        health = _request(client, "GET", "/api/v1/health")
        health_payload = health.json()
        assert health_payload.get("status") == "ok"

        imported = _request(
            client,
            "POST",
            "/api/v1/crawler/projects/import",
            json_payload={
                "project_key": crawler_key,
                "name": f"Live crawler chain {run_token}",
                "description": _SOURCE_SCOPE,
                "source_type": "manifest",
                "source_uri": target_url,
                "provider": "scrapyd",
                "enable_now": True,
                "manifest": {
                    "scrapy_project": crawler_key,
                    "spider": "example",
                    "allowed_domains": ["127.0.0.1"],
                },
                "metadata": {"source_scope": _SOURCE_SCOPE},
            },
        ).json()["data"]
        assert imported["provider"] == "scrapyd"

        deployed = _request(
            client,
            "POST",
            f"/api/v1/crawler/projects/{crawler_key}/deploy",
            json_payload={
                "async_mode": True,
                "requested_version": imported["current_version"],
            },
        ).json()["data"]
        assert deployed["run"]["external_provider"] == "scrapyd"
        assert deployed["task_id"]
        deploy_run_id = int(deployed["run"]["id"])

        channel = None
        item = None
        registration_deadline = time.time() + 45
        while time.time() < registration_deadline:
            channels = _request(
                client,
                "GET",
                "/api/v1/source_library/channels",
                params={"scope": "project", "project_key": project_key},
            ).json()["data"]["items"]
            channel = next((x for x in channels if x.get("channel_key") == channel_key), None)
            items = _request(
                client,
                "GET",
                "/api/v1/source_library/items",
                params={"scope": "project", "project_key": project_key},
            ).json()["data"]["items"]
            item = next((x for x in items if x.get("item_key") == item_key), None)
            if channel and item:
                break
            time.sleep(0.5)
        assert channel is not None and channel.get("provider_type") == "scrapy"
        assert item is not None and item.get("params", {}).get("spider") == "example"
        assert item.get("params", {}).get("output_ingest", {}).get("enabled") is True

        deploy_deadline = time.time() + 45
        deploy_readback: dict[str, Any] = {}
        while time.time() < deploy_deadline:
            deploy_readback = _request(
                client,
                "GET",
                f"/api/v1/crawler/deploy-runs/{deploy_run_id}",
            ).json()["data"]
            if deploy_readback.get("status") in {"registered", "succeeded", "failed"}:
                break
            time.sleep(0.5)
        assert deploy_readback.get("status") == "registered", deploy_readback
        assert deploy_readback.get("finished_at")

        bootstrap_code = "\n".join(
            [
                "import sys",
                f"sys.path.insert(0, {app_site_packages!r})",
                f"sys.path.insert(0, {str(_REPO_ROOT / 'src')!r})",
                f"sys.path.insert(0, {str(_REPO_ROOT / 'main' / 'backend')!r})",
                "import json",
                "from app.services.crawlers.scrapyd_bootstrap import ensure_bootstrap_project_deployed",
                "from app.services.crawlers.scrapyd_client import ScrapydClient",
                f"client = ScrapydClient(base_url={scrapyd_base_url!r})",
                "print(json.dumps(ensure_bootstrap_project_deployed("
                f"client, project={crawler_key!r}, spider='example')))",
            ]
        )
        bootstrap = subprocess.run(
            [bootstrap_python, "-I", "-c", bootstrap_code],
            cwd=_REPO_ROOT,
            env={
                **os.environ,
                "PYTHONPATH": "src:main/backend",
                "SCRAPYD_BASE_URL": scrapyd_base_url,
                "CRAWLER_LAZY_START_SCRAPYD": "0",
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert bootstrap.returncode == 0, (
            f"bootstrap deploy failed: code={bootstrap.returncode} "
            f"stdout={bootstrap.stdout[-1000:]} stderr={bootstrap.stderr[-1000:]}"
        )
        assert json.loads(bootstrap.stdout.splitlines()[-1])["project"] == crawler_key

        submitted_payload = _request(
            client,
            "POST",
            "/api/v1/ingest/source-library/run",
            json_payload={
                "project_key": project_key,
                "item_key": item_key,
                "async_mode": False,
                "override_params": {
                    "arguments": {"urls": target_url},
                    "scrapy_project": crawler_key,
                    "spider": "example",
                },
            },
        ).json()["data"]
        submitted_status = _status(submitted_payload)
        job_id = _provider_job_id(submitted_payload)
        assert job_id, f"provider job id missing from response: {submitted_payload}"
        assert submitted_status == "completed", submitted_payload
        ingested = _find_mapping(submitted_payload, "output_ingest", required_key="status")
        assert ingested is not None, submitted_payload
        assert ingested["status"] == "ingested", ingested
        assert ingested["raw_item_count"] >= 1
        assert ingested["import_result"]["inserted"] == 1

        provider = ScrapyCrawlerProvider(base_url=scrapyd_base_url)
        observations: list[dict[str, Any]] = []
        provider_status = ""
        started_at = time.time()
        terminal_deadline = started_at + 120
        while time.time() < terminal_deadline:
            polled = provider.poll(
                external_job_id=job_id,
                project=crawler_key,
                spider="example",
            )
            provider_status = str(polled.get("provider_status") or "").lower()
            observations.append(
                {
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                    "provider_status": provider_status,
                }
            )
            if provider_status in {"completed", "failed", "cancelled"}:
                break
            time.sleep(1.0)
        assert provider_status == "completed", f"provider did not complete: {observations}"

        materials = _request(
            client,
            "POST",
            "/api/v1/admin/materials/list",
            json_payload={"search": target_url, "page": 1, "page_size": 20},
        ).json()["data"]["items"]
        assert materials, "material readback did not return the crawled URL"
        material = materials[0]
        assert material["uri"] == target_url

        detail = _request(client, "GET", f"/api/v1/admin/materials/{material['id']}").json()["data"]
        assert detail["uri"] == material["uri"]
        assert f"Live crawler material body {run_token}" in str(detail.get("content") or "")

        topology = _request(
            client,
            "POST",
            "/api/v1/information-topology/resolve",
            json_payload={
                "refs": [
                    {
                        "project_key": project_key,
                        "module_id": "materials",
                        "namespace": "materials",
                        "type_id": "material",
                        "local_id": str(material["id"]),
                    }
                ]
            },
        ).json()["data"]
        assert topology["total"] == 1
        graph_ref = topology["items"][0]["ref"]
        assert graph_ref == {
            "project_key": project_key,
            "module_id": "materials",
            "namespace": "materials",
            "type_id": "material",
            "local_id": str(material["id"]),
        }

        from sqlalchemy import select

        from app.models.base import SessionLocal
        from app.models.entities import Material
        from app.services.projects.context import bind_project

        with bind_project(project_key):
            with SessionLocal() as session:
                persisted = session.execute(select(Material).where(Material.id == int(material["id"]))).scalar_one()
                assert persisted.uri == target_url
                assert f"Live crawler material body {run_token}" in str(persisted.content or "")

    source_fingerprint = {
        "contract": "live_crawler_material_chain.v1",
        "source_scope": _SOURCE_SCOPE,
        "source_url": target_url,
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "bootstrap_python": bootstrap_python,
        "backend_base_url": backend_base_url,
        "scrapyd_base_url": scrapyd_base_url,
        "project_key": project_key,
        "crawler_project": crawler_key,
        "deploy_run_id": deploy_run_id,
        "deploy_run_status": deploy_readback["status"],
        "provider_job_id": job_id,
        "material_id": material["id"],
        "material_body_sha256": hashlib.sha256(str(detail.get("content") or "").encode("utf-8")).hexdigest(),
        "graph_ref": graph_ref,
        "provider_observations": observations,
        "ingest_status": ingested["status"],
        "raw_item_count": ingested["raw_item_count"],
        "source_files": {
            str(path): _sha256_file(_REPO_ROOT / path)
            for path in (
                "main/backend/app/services/crawlers/providers/scrapy.py",
                "main/backend/app/services/crawlers/scrapyd_client.py",
                "main/backend/app/services/crawlers/scrapyd_result_ingest.py",
                "main/backend/app/services/ingest/raw_import.py",
                "main/backend/app/services/source_library/runner.py",
            )
        },
    }
    assert source_fingerprint["git_head"]
    evidence_path = _REPO_ROOT / "run" / "logs" / f"live-crawler-chain-evidence-{run_token}.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(source_fingerprint, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
