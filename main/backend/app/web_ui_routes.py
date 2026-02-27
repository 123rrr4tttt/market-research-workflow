from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlencode

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
    def _modern_frontend_redirect(request: Request) -> RedirectResponse | None:
        """Redirect shell entry routes to modern frontend when enabled."""
        base = str(os.getenv("MODERN_FRONTEND_URL") or "").strip().rstrip("/")
        if not base:
            return None
        query = dict(request.query_params)
        target = f"{base}/"
        if query:
            target = f"{target}?{urlencode(query)}"
        return RedirectResponse(url=target, status_code=302)

    @app.get("/", response_class=RedirectResponse)
    def index(request: Request):
        """Root redirects to app shell"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return RedirectResponse(url="/app.html", status_code=302)

    @app.get("/index.html", response_class=RedirectResponse)
    def index_html(request: Request):
        """Legacy index redirects to app shell"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return RedirectResponse(url="/app.html", status_code=302)

    @app.get("/ingest.html", response_class=HTMLResponse)
    def ingest_page(request: Request):
        """Ingest page (采集入口) - loaded in app iframe"""
        return templates.TemplateResponse("ingest.html", {"request": request})

    @app.get("/settings.html", response_class=HTMLResponse)
    def settings_page(request: Request):
        return templates.TemplateResponse("settings.html", {"request": request})

    @app.get("/admin.html", response_class=HTMLResponse)
    def admin_page(request: Request):
        return templates.TemplateResponse("admin.html", {"request": request})

    @app.get("/dashboard.html", response_class=HTMLResponse)
    def dashboard_page(request: Request):
        """数据可视化仪表盘页面"""
        try:
            return templates.TemplateResponse("dashboard.html", {"request": request})
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load dashboard.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"Dashboard file exists: {(template_dir / 'dashboard.html').exists()}")
            raise

    @app.get("/workflow-designer.html", response_class=HTMLResponse)
    def workflow_designer_page(request: Request):
        """图形化工作流编排页面（用户设计 -> 抽象层 -> 主干模块）"""
        return templates.TemplateResponse("workflow-designer.html", {"request": request})

    @app.get("/topic-dashboard.html", response_class=HTMLResponse)
    def topic_dashboard_page(request: Request):
        """专题结果页（公司/商品/电商经营）"""
        return templates.TemplateResponse("topic-dashboard.html", {"request": request})

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_redirect(request: Request):
        """重定向 /dashboard 到 /dashboard.html"""
        return RedirectResponse(url="/dashboard.html", status_code=301)

    @app.get("/app.html", response_class=HTMLResponse)
    def app_page(request: Request):
        """主应用页面（带侧边栏）"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return templates.TemplateResponse("app.html", {"request": request})

    @app.get("/app", response_class=HTMLResponse)
    def app_redirect(request: Request):
        """重定向 /app 到 /app.html"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return RedirectResponse(url="/app.html", status_code=301)

    @app.get("/data-dashboard.html", response_class=HTMLResponse)
    def data_dashboard_page(request: Request):
        """数据仪表盘页面（市场数据与舆论数据）"""
        return templates.TemplateResponse("data-dashboard.html", {"request": request})

    @app.get("/backend-dashboard.html", response_class=HTMLResponse)
    def backend_dashboard_page(request: Request):
        """后端数据仪表盘页面（系统监控）"""
        return templates.TemplateResponse("backend-dashboard.html", {"request": request})

    @app.get("/policy-dashboard.html", response_class=RedirectResponse)
    def policy_dashboard_page(request: Request):
        """Redirect to policy-visualization.html (merged)"""
        return RedirectResponse(url="/policy-visualization.html", status_code=302)

    @app.get("/policy-state-detail.html", response_class=HTMLResponse)
    def policy_state_detail_page(request: Request):
        """州级政策详情页面"""
        return templates.TemplateResponse("policy-state-detail.html", {"request": request})

    @app.get("/policy-tracking.html", response_class=HTMLResponse)
    def policy_tracking_page(request: Request):
        """政策追踪页面"""
        return templates.TemplateResponse("policy-tracking.html", {"request": request})

    @app.get("/market-data-visualization.html", response_class=HTMLResponse)
    def market_data_visualization_page(request: Request):
        """市场数据可视化页面"""
        try:
            return templates.TemplateResponse("market-data-visualization.html", {"request": request})
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load market-data-visualization.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"File exists: {(template_dir / 'market-data-visualization.html').exists()}")
            raise

    @app.get("/social-media-visualization.html", response_class=HTMLResponse)
    def social_media_visualization_page(request: Request):
        """社交媒体数据可视化页面"""
        try:
            return templates.TemplateResponse("social-media-visualization.html", {"request": request})
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load social-media-visualization.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"File exists: {(template_dir / 'social-media-visualization.html').exists()}")
            raise

    @app.get("/policy-visualization.html", response_class=HTMLResponse)
    def policy_visualization_page(request: Request):
        """政策可视化页面"""
        try:
            return templates.TemplateResponse("policy-visualization.html", {"request": request})
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load policy-visualization.html: {e}")
            logging.getLogger("app").error(f"Template directory: {template_dir}")
            logging.getLogger("app").error(f"File exists: {(template_dir / 'policy-visualization.html').exists()}")
            raise

    @app.get("/graph.html", response_class=HTMLResponse)
    def graph_page(request: Request):
        """Unified graph visualization page (policy/social/market)"""
        try:
            return templates.TemplateResponse("graph.html", {"request": request})
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load graph.html: {e}")
            raise

    @app.get("/policy-graph.html", response_class=RedirectResponse)
    def policy_graph_page(request: Request):
        """Redirect to unified graph page"""
        return RedirectResponse(url="/graph.html?type=policy", status_code=302)

    @app.get("/social-media-graph.html", response_class=RedirectResponse)
    def social_media_graph_page(request: Request):
        """Redirect to unified graph page"""
        return RedirectResponse(url="/graph.html?type=social", status_code=302)

    @app.get("/project-management.html", response_class=HTMLResponse)
    def project_management_page(request: Request):
        """项目管理页面"""
        return templates.TemplateResponse("project-management.html", {"request": request})

    @app.get("/process-management.html", response_class=HTMLResponse)
    def process_management_page(request: Request):
        """进程管理页面"""
        return templates.TemplateResponse("process-management.html", {"request": request})

    @app.get("/raw-data-processing.html", response_class=HTMLResponse)
    def raw_data_processing_page(request: Request):
        """流程视角-数据处理页面（Raw Data直入库）"""
        return templates.TemplateResponse("raw-data-processing.html", {"request": request})

    @app.get("/source-library-management.html", response_class=RedirectResponse)
    def source_library_management_redirect(request: Request):
        """Redirect to unified resource pool management (source-library tab)"""
        return RedirectResponse(url="/resource-pool-management.html#source-library", status_code=302)

    @app.get("/resource-pool-management.html", response_class=HTMLResponse)
    def resource_pool_management_page(request: Request):
        """信息资源库管理页面"""
        return templates.TemplateResponse("resource-pool-management.html", {"request": request})

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
