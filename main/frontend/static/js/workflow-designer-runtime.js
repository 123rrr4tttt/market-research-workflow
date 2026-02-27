(function () {
  const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function classifyRuntimeError(error) {
    const status = Number(error && error.httpStatus ? error.httpStatus : 0);
    if (status === 401 || status === 403) return "auth";
    if (RETRYABLE_STATUS.has(status)) return "retryable";
    const message = String((error && error.message) || "").toLowerCase();
    if (message.includes("timeout") || message.includes("network")) return "retryable";
    return "fatal";
  }

  async function withRetry(requestFn, options) {
    const maxRetries = Number(options && options.maxRetries != null ? options.maxRetries : 2);
    const baseDelayMs = Number(options && options.baseDelayMs != null ? options.baseDelayMs : 350);
    const diagnostics = [];

    let attempt = 0;
    while (attempt <= maxRetries) {
      try {
        const data = await requestFn();
        return { ok: true, data, attempts: attempt + 1, diagnostics };
      } catch (error) {
        const kind = classifyRuntimeError(error);
        diagnostics.push({
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
  };
})();
