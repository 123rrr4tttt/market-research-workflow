from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from collections.abc import Callable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import JsonValue as PydanticJSONValue


def register_ui_routes(
    app: FastAPI,
    *,
    usa_map_path: Path,
) -> None:
    def _ui_route(
        path: str,
        *,
        response_class: type[Response] | None = None,
    ) -> Callable[[Callable[..., Response]], Callable[..., Response]]:
        def register(handler: Callable[..., Response]) -> Callable[..., Response]:
            if response_class is None:
                app.get(path)(handler)
            else:
                app.get(path, response_class=response_class)(handler)
            return handler

        return register

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

    def _archived_entry_response() -> HTMLResponse:
        return HTMLResponse(
            content=(
                "<!doctype html><html><head><meta charset='utf-8'/>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
                "<title>Historical Entry Archived</title></head>"
                "<body style='font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif; padding:24px;'>"
                "<h2>历史页面入口已归档</h2>"
                "<p>当前实例仅提供 modern 前端入口。</p>"
                "<p><a href='/'>进入 modern 前端</a></p>"
                "</body></html>"
            ),
            status_code=410,
        )

    def _merge_route_target(target: str, request: Request) -> str:
        base = target.strip()
        try:
            parsed = urlsplit(base)
        except Exception:
            return base
        merged: list[tuple[str, str]] = []
        merged.extend(parse_qsl(parsed.query, keep_blank_values=True))
        for key, value in request.query_params.multi_items():
            merged.append((key, value))

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

    def _modern_entry_redirect(target: str, request: Request) -> RedirectResponse | None:
        base = _modern_frontend_base()
        if not base:
            return None
        modern_target = _merge_route_target(target, request)
        encoded = modern_target.lstrip("/")
        return RedirectResponse(url=f"{base}/#{quote(encoded)}", status_code=302)

    def _redirect_or_archive(request: Request, *, route_target: str):
        modern = _modern_entry_redirect(route_target, request)
        if modern is not None:
            return modern
        return _archived_entry_response()

    @_ui_route("/", response_class=RedirectResponse)
    def index(request: Request):
        """Root redirects to app shell"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return _archived_entry_response()

    @_ui_route("/index.html", response_class=RedirectResponse)
    def index_html(request: Request):
        """Legacy index redirects to app shell"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return _archived_entry_response()

    @_ui_route("/ingest.html", response_class=HTMLResponse)
    def ingest_page(request: Request):
        """Ingest page (采集入口) - loaded in app iframe"""
        return _redirect_or_archive(
            request=request,
            route_target="ingest.html",
        )

    @_ui_route("/settings.html", response_class=HTMLResponse)
    def settings_page(request: Request):
        return _redirect_or_archive(
            request=request,
            route_target="settings.html",
        )

    @_ui_route("/admin.html", response_class=HTMLResponse)
    def admin_page(request: Request):
        return _redirect_or_archive(
            request=request,
            route_target="admin.html",
        )

    @_ui_route("/dashboard.html", response_class=HTMLResponse)
    def dashboard_page(request: Request):
        """数据可视化仪表盘页面"""
        try:
            return _redirect_or_archive(
                request=request,
                route_target="dashboard.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load dashboard.html: {e}")
            raise

    @_ui_route("/workflow-designer.html", response_class=HTMLResponse)
    def workflow_designer_page(request: Request):
        """图形化工作流编排页面（用户设计 -> 抽象层 -> 主干模块）"""
        return _redirect_or_archive(
            request=request,
            route_target="workflow-designer.html",
        )

    @_ui_route("/topic-dashboard.html", response_class=HTMLResponse)
    def topic_dashboard_page(request: Request):
        """专题结果页（公司/商品/电商经营）"""
        return _redirect_or_archive(
            request=request,
            route_target="topic-dashboard.html",
        )

    @_ui_route("/dashboard")
    def dashboard_redirect(request: Request):
        """重定向 /dashboard 到 /dashboard.html"""
        return RedirectResponse(url="/dashboard.html", status_code=301)

    @_ui_route("/app.html", response_class=HTMLResponse)
    def app_page(request: Request):
        """主应用页面（带侧边栏）"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return _archived_entry_response()

    @_ui_route("/app", response_class=HTMLResponse)
    def app_redirect(request: Request):
        """重定向 /app 到 /app.html"""
        modern = _modern_frontend_redirect(request)
        if modern is not None:
            return modern
        return _archived_entry_response()

    @_ui_route("/data-dashboard.html", response_class=HTMLResponse)
    def data_dashboard_page(request: Request):
        """数据仪表盘页面（市场数据与舆论数据）"""
        return _redirect_or_archive(
            request=request,
            route_target="data-dashboard.html",
        )

    @_ui_route("/backend-dashboard.html", response_class=HTMLResponse)
    def backend_dashboard_page(request: Request):
        """后端数据仪表盘页面（系统监控）"""
        return _redirect_or_archive(
            request=request,
            route_target="backend-dashboard.html",
        )

    @_ui_route("/policy-dashboard.html", response_class=RedirectResponse)
    def policy_dashboard_page(request: Request):
        """Redirect to policy-visualization.html (merged)"""
        return RedirectResponse(url="/policy-visualization.html", status_code=302)

    @_ui_route("/policy-state-detail.html", response_class=HTMLResponse)
    def policy_state_detail_page(request: Request):
        """州级政策详情页面"""
        return _redirect_or_archive(
            request=request,
            route_target="policy-state-detail.html",
        )

    @_ui_route("/policy-tracking.html", response_class=HTMLResponse)
    def policy_tracking_page(request: Request):
        """政策可视化页面"""
        return _redirect_or_archive(
            request=request,
            route_target="policy-tracking.html",
        )

    @_ui_route("/market-data-visualization.html", response_class=HTMLResponse)
    def market_data_visualization_page(request: Request):
        """市场数据可视化页面"""
        try:
            return _redirect_or_archive(
                request=request,
                route_target="market-data-visualization.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load market-data-visualization.html: {e}")
            raise

    @_ui_route("/social-media-visualization.html", response_class=HTMLResponse)
    def social_media_visualization_page(request: Request):
        """社交媒体数据可视化页面"""
        try:
            return _redirect_or_archive(
                request=request,
                route_target="social-media-visualization.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load social-media-visualization.html: {e}")
            raise

    @_ui_route("/policy-visualization.html", response_class=HTMLResponse)
    def policy_visualization_page(request: Request):
        """政策可视化页面"""
        try:
            return _redirect_or_archive(
                request=request,
                route_target="policy-visualization.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load policy-visualization.html: {e}")
            raise

    @_ui_route("/graph.html", response_class=HTMLResponse)
    def graph_page(request: Request):
        """Unified graph visualization page (policy/social/market)"""
        try:
            return _redirect_or_archive(
                request=request,
                route_target="graph.html",
            )
        except Exception as e:
            logging.getLogger("app").error(f"Failed to load graph.html: {e}")
            raise

    @_ui_route("/policy-graph.html", response_class=RedirectResponse)
    def policy_graph_page(request: Request):
        """Redirect to unified graph page"""
        compat_target = _merge_route_target("/graph.html?type=policy", request)
        modern = _modern_entry_redirect("graph.html?type=policy", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target=compat_target)

    @_ui_route("/social-media-graph.html", response_class=RedirectResponse)
    def social_media_graph_page(request: Request):
        """Redirect to unified graph page"""
        compat_target = _merge_route_target("/graph.html?type=social", request)
        modern = _modern_entry_redirect("graph.html?type=social", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target=compat_target)

    @_ui_route("/market-graph.html", response_class=RedirectResponse)
    @_ui_route("/market-data-graph.html", response_class=RedirectResponse)
    def market_graph_page(request: Request):
        """Redirect to unified graph page"""
        compat_target = _merge_route_target("/graph.html?type=market", request)
        modern = _modern_entry_redirect("graph.html?type=market", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target=compat_target)

    @_ui_route("/project-management.html", response_class=HTMLResponse)
    def project_management_page(request: Request):
        """项目管理页面"""
        return _redirect_or_archive(
            request=request,
            route_target="project-management.html",
        )

    @_ui_route("/process-management.html", response_class=HTMLResponse)
    def process_management_page(request: Request):
        """进程管理页面"""
        return _redirect_or_archive(
            request=request,
            route_target="process-management.html",
        )

    @_ui_route("/raw-data-processing.html", response_class=HTMLResponse)
    def raw_data_processing_page(request: Request):
        """流程视角-数据处理页面（Raw Data直入库）"""
        return _redirect_or_archive(
            request=request,
            route_target="raw-data-processing.html",
        )

    @_ui_route("/source-library-management.html", response_class=RedirectResponse)
    def source_library_management_redirect(request: Request):
        """Redirect to unified resource pool management (source-library tab)"""
        return RedirectResponse(url="/resource-pool-management.html#source-library", status_code=302)

    @_ui_route("/resource-pool-management.html", response_class=HTMLResponse)
    def resource_pool_management_page(request: Request):
        """信息资源库管理页面"""
        return _redirect_or_archive(
            request=request,
            route_target="resource-pool-management.html",
        )

    @_ui_route("/dashboard", response_class=HTMLResponse)
    def dashboard_alias(request: Request):
        """兼容 dashboard 无后缀入口"""
        modern = _modern_entry_redirect("dashboard.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target="dashboard.html")

    @_ui_route("/process-management")
    def process_management_alias(request: Request):
        modern = _modern_entry_redirect("process-management.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target="process-management.html")

    @_ui_route("/workflow-designer")
    def workflow_designer_alias(request: Request):
        modern = _modern_entry_redirect("workflow-designer.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(
            request=request,
            route_target="workflow-designer.html",
        )

    @_ui_route("/resource-pool-management")
    def resource_pool_management_alias(request: Request):
        modern = _modern_entry_redirect("resource-pool-management.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(
            request=request,
            route_target="resource-pool-management.html",
        )

    @_ui_route("/project-management")
    def project_management_alias(request: Request):
        modern = _modern_entry_redirect("project-management.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(
            request=request,
            route_target="project-management.html",
        )

    @_ui_route("/raw-data-processing")
    def raw_data_processing_alias(request: Request):
        modern = _modern_entry_redirect("raw-data-processing.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(
            request=request,
            route_target="raw-data-processing.html",
        )

    @_ui_route("/raw-data")
    def raw_data_alias(request: Request):
        return raw_data_processing_alias(request)

    @_ui_route("/admin")
    def admin_alias(request: Request):
        modern = _modern_entry_redirect("admin.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target="admin.html")

    @_ui_route("/settings")
    def settings_alias(request: Request):
        modern = _modern_entry_redirect("settings.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target="settings.html")

    @_ui_route("/graph")
    def graph_alias(request: Request):
        modern = _modern_entry_redirect("graph.html", request)
        if modern is not None:
            return modern
        return _redirect_or_archive(request=request, route_target="graph.html")

    registered_ui_handlers = (
        index,
        index_html,
        ingest_page,
        settings_page,
        admin_page,
        dashboard_page,
        workflow_designer_page,
        topic_dashboard_page,
        dashboard_redirect,
        app_page,
        app_redirect,
        data_dashboard_page,
        backend_dashboard_page,
        policy_dashboard_page,
        policy_state_detail_page,
        policy_tracking_page,
        market_data_visualization_page,
        social_media_visualization_page,
        policy_visualization_page,
        graph_page,
        policy_graph_page,
        social_media_graph_page,
        market_graph_page,
        project_management_page,
        process_management_page,
        raw_data_processing_page,
        source_library_management_redirect,
        resource_pool_management_page,
        dashboard_alias,
        process_management_alias,
        workflow_designer_alias,
        resource_pool_management_alias,
        project_management_alias,
        raw_data_processing_alias,
        raw_data_alias,
        admin_alias,
        settings_alias,
        graph_alias,
    )
    if not all(callable(handler) for handler in registered_ui_handlers):
        raise TypeError("UI route registration produced a non-callable handler")


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

    get_usa_map = app.get(
        "/api/v1/maps/usa",
        response_class=JSONResponse,
        response_model=dict[str, PydanticJSONValue],
    )(get_usa_map)
