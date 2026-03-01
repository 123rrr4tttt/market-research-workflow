from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .scrapyd_client import ScrapydClient


_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAPPED_PROJECTS: set[str] = set()


def is_missing_project_schedule_error(response: dict[str, Any], *, project: str) -> bool:
    status = str(response.get("status") or "").strip().lower()
    if status not in {"error", "failed"}:
        return False
    message = str(response.get("message") or response.get("error") or response.get("reason") or "").strip().lower()
    if not message:
        return False
    if "project" not in message:
        return False
    missing_markers = ("not found", "does not exist", "unknown project", "no such project")
    if not any(marker in message for marker in missing_markers):
        return False
    project_name = str(project or "").strip().lower()
    return not project_name or project_name in message


def is_missing_spider_schedule_error(response: dict[str, Any], *, spider: str) -> bool:
    status = str(response.get("status") or "").strip().lower()
    if status not in {"error", "failed"}:
        return False
    message = str(response.get("message") or response.get("error") or response.get("reason") or "").strip().lower()
    if not message or "spider" not in message:
        return False
    missing_markers = ("not found", "does not exist", "unknown spider", "no such spider")
    if not any(marker in message for marker in missing_markers):
        return False
    spider_name = str(spider or "").strip().lower()
    return not spider_name or spider_name in message


def is_bad_egg_schedule_error(response: dict[str, Any]) -> bool:
    status = str(response.get("status") or "").strip().lower()
    if status not in {"error", "failed"}:
        return False
    message = str(response.get("message") or response.get("error") or response.get("reason") or "").strip().lower()
    if not message:
        return False
    return "badeggerror" in message or "bad egg" in message


def is_bootstrap_recoverable_schedule_error(
    response: dict[str, Any],
    *,
    project: str,
    spider: str,
) -> bool:
    return (
        is_missing_project_schedule_error(response, project=project)
        or is_missing_spider_schedule_error(response, spider=spider)
        or is_bad_egg_schedule_error(response)
    )


def _is_valid_python_package_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""))


def _to_class_name(raw: str) -> str:
    tokens = [x for x in re.split(r"[^A-Za-z0-9]+", raw or "") if x]
    if not tokens:
        return "GenericUrlSpider"
    return "".join(token[:1].upper() + token[1:] for token in tokens) + "Spider"


def _build_minimal_scrapy_egg(*, project: str, spider: str) -> bytes:
    project_name = str(project or "").strip()
    spider_name = str(spider or "").strip() or "default"
    if not _is_valid_python_package_name(project_name):
        raise ValueError(
            f"scrapyd bootstrap requires python-package-compatible project name, got: {project_name!r}"
        )

    class_name = _to_class_name(spider_name)
    settings_text = """BOT_NAME = "bootstrap_crawler"
SPIDER_MODULES = ["{project}.spiders"]
NEWSPIDER_MODULE = "{project}.spiders"
ROBOTSTXT_OBEY = False
LOG_ENABLED = False
""".format(project=project_name)
    spider_text = """import scrapy


class {class_name}(scrapy.Spider):
    name = {spider_name!r}

    def start_requests(self):
        raw_urls = self._collect_urls()
        if not raw_urls:
            return
        for url in raw_urls:
            if not url.startswith(("http://", "https://")):
                continue
            yield scrapy.Request(url=url, callback=self.parse)

    def _collect_urls(self):
        values = []
        for key in ("url", "urls", "start_url", "start_urls"):
            raw = getattr(self, key, None)
            if not raw:
                continue
            if isinstance(raw, str):
                values.extend(raw.replace(",", "\\n").splitlines())
            elif isinstance(raw, (list, tuple)):
                values.extend(raw)
            else:
                values.append(str(raw))
        seen = set()
        out = []
        for value in values:
            u = str(value or "").strip()
            if not u:
                continue
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def parse(self, response):
        title = response.css("title::text").get()
        text = " ".join(response.css("body *::text").getall()).strip()
        yield {{
            "url": response.url,
            "status": response.status,
            "title": title,
            "text": text[:20000],
        }}
""".format(
        class_name=class_name,
        spider_name=spider_name,
    )
    files = {
        f"{project_name}/__init__.py": "__all__ = []\n",
        f"{project_name}/settings.py": settings_text,
        f"{project_name}/spiders/__init__.py": "__all__ = []\n",
        f"{project_name}/spiders/bootstrap.py": spider_text,
    }
    setup_py = """from setuptools import setup, find_packages

setup(
    name={project_name!r},
    version="0.0.1",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    entry_points={{"scrapy": ["settings = {project_name}.settings"]}},
)
""".format(project_name=project_name)
    with tempfile.TemporaryDirectory(prefix=f"scrapyd-bootstrap-{project_name}-") as tmp_dir:
        root = Path(tmp_dir)
        for name, content in files.items():
            file_path = root / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        (root / "setup.py").write_text(setup_py, encoding="utf-8")
        dist_dir = root / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        proc = subprocess.run(
            [sys.executable, "setup.py", "bdist_egg", "-d", str(dist_dir)],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ValueError(
                "failed to build bootstrap egg: "
                f"code={proc.returncode}, stdout={proc.stdout[-500:]}, stderr={proc.stderr[-500:]}"
            )
        eggs = sorted(dist_dir.glob("*.egg"))
        if not eggs:
            raise ValueError("bootstrap egg build produced no .egg artifact")
        return eggs[-1].read_bytes()


def ensure_bootstrap_project_deployed(
    client: ScrapydClient,
    *,
    project: str,
    spider: str,
) -> dict[str, Any]:
    normalized_project = str(project or "").strip()
    if not normalized_project:
        raise ValueError("bootstrap deploy requires project")

    cache_key = normalized_project.lower()
    with _BOOTSTRAP_LOCK:
        if cache_key in _BOOTSTRAPPED_PROJECTS:
            return {"status": "cached", "project": normalized_project}

        egg = _build_minimal_scrapy_egg(project=normalized_project, spider=spider)
        version = f"bootstrap-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        metadata = {"source": "crawler_lazy_bootstrap", "spider": str(spider or "").strip()}
        response = client.add_version(
            project=normalized_project,
            version=version,
            egg_bytes=egg,
            metadata=metadata,
        )
        status = str(response.get("status") or "unknown").strip().lower()
        if status not in {"ok", "queued"}:
            raise ValueError(f"scrapyd bootstrap addversion failed: {response}")
        _BOOTSTRAPPED_PROJECTS.add(cache_key)
        return {"status": status, "project": normalized_project, "version": version, "raw": response}


__all__ = [
    "is_bootstrap_recoverable_schedule_error",
    "is_bad_egg_schedule_error",
    "is_missing_spider_schedule_error",
    "is_missing_project_schedule_error",
    "ensure_bootstrap_project_deployed",
]
