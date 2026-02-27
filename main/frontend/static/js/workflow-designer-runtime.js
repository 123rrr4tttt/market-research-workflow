(function () {
  const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);
  const RUNTIME_NODE_ID = "__runtime__";

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function classifyRuntimeError(error) {
    const status = Number(error && error.httpStatus ? error.httpStatus : 0);
    if (status === 401 || status === 403) return "auth";
    if (RETRYABLE_STATUS.has(status)) return "retryable";
    const message = String((error && error.message) || "").toLowerCase();
    if (message.includes("timeout") || message.includes("timed out")) return "retryable";
    return "fatal";
  }

  function normalizeStatusValue(value) {
    const text = String(value == null ? "" : value).toLowerCase();
    if (!text) return "idle";
    if (["ok", "done", "success", "completed", "complete", "passed"].includes(text)) return "success";
    if (["running", "in_progress", "in-progress", "processing", "started"].includes(text)) return "running";
    if (["error", "failed", "fail", "fatal", "timeout", "cancelled", "canceled"].includes(text)) return "error";
    if (["skipped", "skip", "ignored"].includes(text)) return "skipped";
    if (["idle", "pending", "queued", "unknown"].includes(text)) return "idle";
    return "idle";
  }

  function toNodeStatus(item, context) {
    if (!item || typeof item !== "object") return null;
    const nodeId = item.node_id || item.nodeId || item.id || item.key || item.name || RUNTIME_NODE_ID;
    const nodeName = item.node_name || item.nodeName || item.name || context.defaultNodeName || "Runtime";
    const status = normalizeStatusValue(item.status || item.state || item.result || item.outcome);
    const message = item.message || item.error || item.reason || "";
    const startedAt = item.started_at || item.startedAt || null;
    const finishedAt = item.finished_at || item.finishedAt || null;
    const diagnostics = Array.isArray(item.diagnostics)
      ? item.diagnostics
      : Array.isArray(item.timeline)
      ? item.timeline
      : [];

    return {
      node_id: String(nodeId),
      node_name: String(nodeName),
      status,
      message: message ? String(message) : "",
      started_at: startedAt,
      finished_at: finishedAt,
      diagnostics,
      raw: item,
    };
  }

  function toNodeStatuses(list, context) {
    if (!Array.isArray(list)) return [];
    return list.map((item) => toNodeStatus(item, context)).filter(Boolean);
  }

  function extractPayload(response) {
    if (response && typeof response === "object" && response.data && typeof response.data === "object") {
      return response.data;
    }
    return response && typeof response === "object" ? response : {};
  }

  function normalizeRuntimeDiagnostics(response, context) {
    const normalizedContext = context && typeof context === "object" ? context : {};
    const payload = extractPayload(response);
    const timelineSource =
      (payload.diagnostics && Array.isArray(payload.diagnostics.timeline) && payload.diagnostics.timeline) ||
      (response && response.diagnostics && Array.isArray(response.diagnostics.timeline) && response.diagnostics.timeline) ||
      (Array.isArray(payload.diagnostics) && payload.diagnostics) ||
      (Array.isArray(response && response.diagnostics) && response.diagnostics) ||
      (Array.isArray(payload.timeline) && payload.timeline) ||
      [];

    let nodeStatuses = [];
    if (Array.isArray(payload.node_statuses)) {
      nodeStatuses = toNodeStatuses(payload.node_statuses, normalizedContext);
    } else if (Array.isArray(payload.nodeStatuses)) {
      nodeStatuses = toNodeStatuses(payload.nodeStatuses, normalizedContext);
    } else if (Array.isArray(payload.node_results)) {
      nodeStatuses = toNodeStatuses(payload.node_results, normalizedContext);
    } else if (Array.isArray(payload.nodeResults)) {
      nodeStatuses = toNodeStatuses(payload.nodeResults, normalizedContext);
    } else if (Array.isArray(payload.nodes)) {
      nodeStatuses = toNodeStatuses(payload.nodes, normalizedContext);
    } else if (payload.node_status_map && typeof payload.node_status_map === "object") {
      nodeStatuses = Object.keys(payload.node_status_map).map((nodeId) =>
        toNodeStatus(
          {
            node_id: nodeId,
            status: payload.node_status_map[nodeId],
          },
          normalizedContext
        )
      );
    }

    if (!nodeStatuses.length) {
      const fallbackStatus = payload.error || response.error ? "error" : normalizeStatusValue(payload.status || response.status);
      nodeStatuses = [
        toNodeStatus(
          {
            node_id: normalizedContext.nodeId || normalizedContext.workflowName || RUNTIME_NODE_ID,
            node_name: normalizedContext.nodeName || normalizedContext.workflowName || "Runtime",
            status: fallbackStatus,
            message:
              payload.error ||
              (response && response.error) ||
              (timelineSource[0] && timelineSource[0].message) ||
              "",
            diagnostics: timelineSource,
          },
          normalizedContext
        ),
      ].filter(Boolean);
    }

    return {
      node_statuses: nodeStatuses,
      diagnostics: {
        timeline: timelineSource,
      },
      raw: response,
      context: normalizedContext,
    };
  }

  async function withRetry(requestFn, options) {
    const maxRetries = Number(options && options.maxRetries != null ? options.maxRetries : 2);
    const baseDelayMs = Number(options && options.baseDelayMs != null ? options.baseDelayMs : 350);
    const diagnostics = [];
    diagnostics.timeline = diagnostics;

    let attempt = 0;
    while (attempt <= maxRetries) {
      try {
        const data = await requestFn();
        return { ok: true, data, attempts: attempt + 1, diagnostics };
      } catch (error) {
        const kind = classifyRuntimeError(error);
        diagnostics.timeline.push({
          kind: "runtime_api_error",
          phase: "runtime",
          attempt: attempt + 1,
          http_status: error && error.httpStatus ? error.httpStatus : 0,
          code: error && error.code ? error.code : "REQUEST_FAILED",
          message: error && error.message ? String(error.message) : "请求失败",
        });

        if (kind !== "retryable" || attempt >= maxRetries) {
          return { ok: false, error, attempts: attempt + 1, diagnostics };
        }

        const waitMs = baseDelayMs * (attempt + 1);
        await sleep(waitMs);
      }
      attempt += 1;
    }

    return {
      ok: false,
      error: new Error("Unexpected runtime retry state"),
      attempts: maxRetries + 1,
      diagnostics,
    };
  }

  async function loadTemplate(workflowName) {
    return window.MarketApp.fetchJSON(`/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/template`);
  }

  async function saveTemplate(workflowName, payload) {
    return window.MarketApp.fetchJSON(`/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/template`, {
      method: "POST",
      body: payload,
    });
  }

  async function deleteTemplate(workflowName, projectKey) {
    const query = `?project_key=${encodeURIComponent(projectKey || "")}`;
    return window.MarketApp.fetchJSON(`/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/template${query}`, {
      method: "DELETE",
    });
  }

  async function runWorkflow(workflowName, payload, options) {
    return withRetry(
      () =>
        window.MarketApp.fetchJSON(`/api/v1/project-customization/workflows/${encodeURIComponent(workflowName)}/run`, {
          method: "POST",
          body: payload,
        }),
      options || {}
    );
  }

  window.WorkflowDesignerRuntime = {
    withRetry,
    loadTemplate,
    saveTemplate,
    deleteTemplate,
    runWorkflow,
    normalizeRuntimeDiagnostics,
  };
})();
