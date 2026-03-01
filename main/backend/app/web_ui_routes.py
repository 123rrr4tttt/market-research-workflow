from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


def register_ui_routes(
    app: FastAPI,
    *,
    templates: Jinja2Templates,
    template_dir: Path,
    usa_map_path: Path,
) -> None:
    def _modern_frontend_base() -> str:
        explicit = str(os.getenv("MODERN_FRONTEND_URL") or "").strip().rstrip("/")
        if explicit:
            return explicit
        enable_default = str(os.getenv("ENABLE_DEFAULT_MODERN_FRONTEND", "1")).strip().lower()
        if enable_default in {"0", "false", "no", "off"}:
            return ""
        host = str(os.getenv("MODERN_FRONTEND_HOST") or "127.0.0.1").strip()
        port = str(os.getenv("MODERN_FRONTEND_PORT") or "5173").strip()
        if not host or not port:
            return ""
        return f"http://{host}:{port}"

    def _modern_frontend_redirect(request: Request) -> RedirectResponse | None:
        """Redirect shell entry routes to modern frontend when enabled."""
        base = _modern_frontend_base()
        if not base:
            return None
        query = dict(request.query_params)
        target = f"{base}/"
        if query:
            target = f"{target}?{urlencode(query)}"
        return RedirectResponse(url=target, status_code=302)

    def _should_use_legacy(request: Request) -> bool:
        # Keep an emergency fallback path when explicitly requested.
        legacy = request.query_params.get("legacy")
        return str(legacy).lower() in {"1", "true", "yes", "on", "legacy"}

    def _build_legacy_target(target: str, request: Request) -> str:
        base = target.strip()
        try:
            parsed = urlsplit(base)
        except Exception:
            return base
        merged = []
        merged.extend(parse_qsl(parsed.query, keep_blank_values=True))
        merged.extend([(k, v) for k, v in request.query_params.multi_items()])

        # keep query ordering stable while preserving repeated params
        unique: list[tuple[str, str]] = []
        seen: dict[str, str] = {}
        for key, value in merged:
            if key not in seen:
                unique.append((key, value))
                seen[key] = value

        rebuilt = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(unique),
                parsed.fragment,
            )
        )
        return rebuilt

    def _modern_frontend_redirect_with_hash(target: str, request: Request) -> RedirectResponse | None:
        base = _modern_frontend_base()
        if not base:
            return None
        modern_target = _build_legacy_target(target, request)
        encoded = modern_target.lstrip("/")
        return RedirectResponse(url=f"{base}/#{quote(encoded)}", status_code=302)

    def _render_or_forward(request: Request, template_name: str, *, route_target: str):
        if _should_use_legacy(request):
            return templates.TemplateResponse(template_name, {"request": request})
        modern = _modern_frontend_redirect_with_hash(route_target, request)
        if modern is not None:
            return modern
        return templates.TemplateResponse(template_name, {"request": request})

    @app.get("/", response_class=RedirectResponse)
    def index(request: Request):
        """Root redirects to app shell"""
        if _should_use_legacy(request):
            return RedirectResponse(url="/app.html?legacy=1", status_code=302)
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return RedirectResponse(url="/app.html", status_code=302)

    @app.get("/index.html", response_class=RedirectResponse)
    def index_html(request: Request):
        """Legacy index redirects to app shell"""
        if _should_use_legacy(request):
            return RedirectResponse(url="/app.html?legacy=1", status_code=302)
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return RedirectResponse(url="/app.html", status_code=302)

    @app.get("/ingest.html", response_class=HTMLResponse)
    def ingest_page(request: Request):
        """Ingest page (采集入口) - loaded in app iframe"""
        return _render_or_forward(
            request=request,
            template_name="ingest.html",
            route_target="ingest.html",
        )

    @app.get("/settings.html", response_class=HTMLResponse)
    def settings_page(request: Request):
        return _render_or_forward(
            request=request,
            template_name="settings.html",
            route_target="settings.html",
        )

    @app.get("/admin.html", response_class=HTMLResponse)
    def admin_page(request: Request):
        return _render_or_forward(
            request=request,
            template_name="admin.html",
            route_target="admin.html",
        )

    @app.get("/dashboard.html", response_class=HTMLResponse)
    def dashboard_page(request: Request):
        """数据可视化仪表盘页面"""
        try:
            return _render_or_forward(
                request=request,
                template_name="dashboard.html",
                route_target="dashboard.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load dashboard.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"Dashboard file exists: {(template_dir / 'dashboard.html').exists()}")
            raise

    @app.get("/workflow-designer.html", response_class=HTMLResponse)
    def workflow_designer_page(request: Request):
        """图形化工作流编排页面（用户设计 -> 抽象层 -> 主干模块）"""
        return _render_or_forward(
            request=request,
            template_name="workflow-designer.html",
            route_target="workflow-designer.html",
        )

    @app.get("/topic-dashboard.html", response_class=HTMLResponse)
    def topic_dashboard_page(request: Request):
        """专题结果页（公司/商品/电商经营）"""
        return _render_or_forward(
            request=request,
            template_name="topic-dashboard.html",
            route_target="topic-dashboard.html",
        )

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_redirect(request: Request):
        """重定向 /dashboard 到 /dashboard.html"""
        return RedirectResponse(url="/dashboard.html", status_code=301)

    @app.get("/app.html", response_class=HTMLResponse)
    def app_page(request: Request):
        """主应用页面（带侧边栏）"""
        if _should_use_legacy(request):
            return templates.TemplateResponse("app.html", {"request": request})
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return templates.TemplateResponse("app.html", {"request": request})

    @app.get("/app", response_class=HTMLResponse)
    def app_redirect(request: Request):
        """重定向 /app 到 /app.html"""
        if _should_use_legacy(request):
            return RedirectResponse(url="/app.html?legacy=1", status_code=301)
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return RedirectResponse(url="/app.html", status_code=301)

    @app.get("/data-dashboard.html", response_class=HTMLResponse)
    def data_dashboard_page(request: Request):
        """数据仪表盘页面（市场数据与舆论数据）"""
        return _render_or_forward(
            request=request,
            template_name="data-dashboard.html",
            route_target="data-dashboard.html",
        )

    @app.get("/backend-dashboard.html", response_class=HTMLResponse)
    def backend_dashboard_page(request: Request):
        """后端数据仪表盘页面（系统监控）"""
        return _render_or_forward(
            request=request,
            template_name="backend-dashboard.html",
            route_target="backend-dashboard.html",
        )

    @app.get("/policy-dashboard.html", response_class=RedirectResponse)
    def policy_dashboard_page(request: Request):
        """Redirect to policy-visualization.html (merged)"""
        return RedirectResponse(url="/policy-visualization.html", status_code=302)

    @app.get("/policy-state-detail.html", response_class=HTMLResponse)
    def policy_state_detail_page(request: Request):
        """州级政策详情页面"""
        return _render_or_forward(
            request=request,
            template_name="policy-state-detail.html",
            route_target="policy-state-detail.html",
        )

    @app.get("/policy-tracking.html", response_class=HTMLResponse)
    def policy_tracking_page(request: Request):
        """政策追踪页面"""
        return _render_or_forward(
            request=request,
            template_name="policy-tracking.html",
            route_target="policy-tracking.html",
        )

    @app.get("/market-data-visualization.html", response_class=HTMLResponse)
    def market_data_visualization_page(request: Request):
        """市场数据可视化页面"""
        try:
            return _render_or_forward(
                request=request,
                template_name="market-data-visualization.html",
                route_target="market-data-visualization.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load market-data-visualization.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"File exists: {(template_dir / 'market-data-visualization.html').exists()}")
            raise

    @app.get("/social-media-visualization.html", response_class=HTMLResponse)
    def social_media_visualization_page(request: Request):
        """社交媒体数据可视化页面"""
        try:
            return _render_or_forward(
                request=request,
                template_name="social-media-visualization.html",
                route_target="social-media-visualization.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load social-media-visualization.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"File exists: {(template_dir / 'social-media-visualization.html').exists()}")
            raise

    @app.get("/policy-visualization.html", response_class=HTMLResponse)
    def policy_visualization_page(request: Request):
        """政策可视化页面"""
        try:
            return _render_or_forward(
                request=request,
                template_name="policy-visualization.html",
                route_target="policy-visualization.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load policy-visualization.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"File exists: {(template_dir / 'policy-visualization.html').exists()}")
            raise

    @app.get("/graph.html", response_class=HTMLResponse)
    def graph_page(request: Request):
        """Unified graph visualization page (policy/social/market)"""
        try:
            return _render_or_forward(
                request=request,
                template_name="graph.html",
                route_target="graph.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load graph.html: {e}")
            raise

    @app.get("/policy-graph.html", response_class=RedirectResponse)
    def policy_graph_page(request: Request):
        """Redirect to unified graph page"""
        legacy_target = _build_legacy_target("/graph.html?type=policy", request)
        if _should_use_legacy(request):
            return RedirectResponse(url=legacy_target, status_code=302)
        modern = _modern_frontend_redirect_with_hash("graph.html?type=policy", request)
        if modern is not None:
            return modern
        return RedirectResponse(url=legacy_target, status_code=302)

    @app.get("/social-media-graph.html", response_class=RedirectResponse)
    def social_media_graph_page(request: Request):
        """Redirect to unified graph page"""
        legacy_target = _build_legacy_target("/graph.html?type=social", request)
        if _should_use_legacy(request):
            return RedirectResponse(url=legacy_target, status_code=302)
        modern = _modern_frontend_redirect_with_hash("graph.html?type=social", request)
        if modern is not None:
            return modern
        return RedirectResponse(url=legacy_target, status_code=302)

    @app.get("/market-graph.html", response_class=RedirectResponse)
    @app.get("/market-data-graph.html", response_class=RedirectResponse)
    def market_graph_page(request: Request):
        """Redirect to unified graph page"""
        legacy_target = _build_legacy_target("/graph.html?type=market", request)
        if _should_use_legacy(request):
            return RedirectResponse(url=legacy_target, status_code=302)
        modern = _modern_frontend_redirect_with_hash("graph.html?type=market", request)
        if modern is not None:
            return modern
        return RedirectResponse(url=legacy_target, status_code=302)

    @app.get("/project-management.html", response_class=HTMLResponse)
    def project_management_page(request: Request):
        """项目管理页面"""
        return _render_or_forward(
            request=request,
            template_name="project-management.html",
            route_target="project-management.html",
        )

    @app.get("/process-management.html", response_class=HTMLResponse)
    def process_management_page(request: Request):
        """进程管理页面"""
        return _render_or_forward(
            request=request,
            template_name="process-management.html",
            route_target="process-management.html",
        )

    @app.get("/raw-data-processing.html", response_class=HTMLResponse)
    def raw_data_processing_page(request: Request):
        """流程视角-数据处理页面（Raw Data直入库）"""
        return _render_or_forward(
            request=request,
            template_name="raw-data-processing.html",
            route_target="raw-data-processing.html",
        )

    @app.get("/source-library-management.html", response_class=RedirectResponse)
    def source_library_management_redirect(request: Request):
        """Redirect to unified resource pool management (source-library tab)"""
        return RedirectResponse(url="/resource-pool-management.html#source-library", status_code=302)

    @app.get("/resource-pool-management.html", response_class=HTMLResponse)
    def resource_pool_management_page(request: Request):
        """信息资源库管理页面"""
        return _render_or_forward(
            request=request,
            template_name="resource-pool-management.html",
            route_target="resource-pool-management.html",
        )

    @app.get("/dashboard")
    def dashboard_alias(request: Request):
        """兼容 dashboard 无后缀入口"""
        modern = _modern_frontend_redirect_with_hash("dashboard.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(request=request, template_name="dashboard.html", route_target="dashboard.html")

    @app.get("/process-management")
    def process_management_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("process-management.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(request=request, template_name="process-management.html", route_target="process-management.html")

    @app.get("/workflow-designer")
    def workflow_designer_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("workflow-designer.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(
            request=request,
            template_name="workflow-designer.html",
            route_target="workflow-designer.html",
        )

    @app.get("/resource-pool-management")
    def resource_pool_management_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("resource-pool-management.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(
            request=request,
            template_name="resource-pool-management.html",
            route_target="resource-pool-management.html",
        )

    @app.get("/project-management")
    def project_management_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("project-management.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(
            request=request,
            template_name="project-management.html",
            route_target="project-management.html",
        )

    @app.get("/raw-data-processing")
    def raw_data_processing_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("raw-data-processing.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(
            request=request,
            template_name="raw-data-processing.html",
            route_target="raw-data-processing.html",
        )

    @app.get("/raw-data")
    def raw_data_alias(request: Request):
        return raw_data_processing_alias(request)

    @app.get("/admin")
    def admin_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("admin.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(request=request, template_name="admin.html", route_target="admin.html")

    @app.get("/settings")
    def settings_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("settings.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(request=request, template_name="settings.html", route_target="settings.html")

    @app.get("/graph")
    def graph_alias(request: Request):
        modern = _modern_frontend_redirect_with_hash("graph.html", request)
        if modern is not None:
            return modern
        return _render_or_forward(request=request, template_name="graph.html", route_target="graph.html")


    @app.get("/api/v1/maps/usa")
    def get_usa_map() -> JSONResponse:
        """提供美国地图GeoJSON供前端使用。"""
        if not usa_map_path.exists():
            raise HTTPException(status_code=404, detail="USA map resource not found")
        try:
            with usa_map_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return JSONResponse(content=data)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="USA map resource invalid") from exc
