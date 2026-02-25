(function () {
  const STORAGE_KEY = "market_project_key";
  const nativeFetch = window.fetch.bind(window);

  function normalizeProjectKey(raw) {
    let key = String(raw || "").trim().toLowerCase();
    key = key.replace(/[^a-z0-9_]+/g, "_");
    key = key.replace(/_+/g, "_").replace(/^_+|_+$/g, "");
    return key || "default";
  }

  function getProjectKey() {
    const fromQuery = new URLSearchParams(window.location.search).get("project_key");
    if (fromQuery) {
      const key = normalizeProjectKey(fromQuery);
      localStorage.setItem(STORAGE_KEY, key);
      return key;
    }
    return normalizeProjectKey(localStorage.getItem(STORAGE_KEY) || "default");
  }

  function withProjectKey(inputUrl) {
    const url = new URL(String(inputUrl), window.location.origin);
    if (url.origin === window.location.origin) {
      url.searchParams.set("project_key", getProjectKey());
    }
    return url.toString();
  }

  function buildProjectHeaders(headersLike) {
    const headers = new Headers(headersLike || {});
    headers.set("X-Project-Key", getProjectKey());
    return headers;
  }

  function fetchWithProject(input, init) {
    if (input instanceof Request) {
      const headers = buildProjectHeaders(init && init.headers ? init.headers : input.headers);
      const requestUrl = withProjectKey(input.url);
      const source = input.clone();
      const method = (init && init.method) || input.method || "GET";
      const nextInit = {
        method,
        headers,
        body: init && Object.prototype.hasOwnProperty.call(init, "body") ? init.body : (["GET", "HEAD"].includes(method.toUpperCase()) ? undefined : source.body),
        cache: (init && init.cache) || input.cache,
        credentials: (init && init.credentials) || input.credentials,
        integrity: (init && init.integrity) || input.integrity,
        keepalive: (init && init.keepalive) || input.keepalive,
        mode: (init && init.mode) || input.mode,
        redirect: (init && init.redirect) || input.redirect,
        referrer: (init && init.referrer) || input.referrer,
        referrerPolicy: (init && init.referrerPolicy) || input.referrerPolicy,
        signal: (init && init.signal) || input.signal,
      };
      return nativeFetch(requestUrl, nextInit);
    }
    const nextInit = init ? { ...init } : {};
    nextInit.headers = buildProjectHeaders(nextInit.headers);
    return nativeFetch(withProjectKey(input), nextInit);
  }

  function buildApiError(response, payload, fallbackMessage) {
    const fromEnvelope = payload && payload.error ? payload.error : null;
    const err = new Error(
      fromEnvelope && fromEnvelope.message
        ? fromEnvelope.message
        : fallbackMessage || `HTTP ${response ? response.status : 0}`
    );
    err.httpStatus = response ? response.status : 0;
    err.code = fromEnvelope && fromEnvelope.code ? fromEnvelope.code : "HTTP_ERROR";
    err.details = fromEnvelope && fromEnvelope.details ? fromEnvelope.details : {};
    err.raw = payload;
    return err;
  }

  async function parseResponseJSON(response) {
    try {
      return await response.json();
    } catch (err) {
      if (!response.ok) {
        throw buildApiError(response, null, `HTTP ${response.status}: failed to parse error response`);
      }
      throw new Error("Invalid JSON response");
    }
  }

  function isEnvelope(payload) {
    return !!(payload && typeof payload === "object" && "status" in payload && "data" in payload && "meta" in payload);
  }

  async function requestFull(method, url, options) {
    const opts = options ? { ...options } : {};
    const headers = new Headers(opts.headers || {});
    if (opts.body != null && !headers.has("Content-Type") && !(opts.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    let body = opts.body;
    if (body != null && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Blob) && !(body instanceof ArrayBuffer) && !(body instanceof URLSearchParams)) {
      body = JSON.stringify(body);
    }
    const response = await fetchWithProject(url, {
      ...opts,
      method,
      headers,
      body,
    });
    const payload = await parseResponseJSON(response);

    if (!response.ok) {
      throw buildApiError(response, payload, `HTTP ${response.status}`);
    }

    if (isEnvelope(payload)) {
      if (payload.status === "error") {
        throw buildApiError(response, payload, `${payload.error && payload.error.message ? payload.error.message : "Request failed"}`);
      }
      return payload;
    }

    return {
      status: "ok",
      data: payload,
      error: null,
      meta: {},
    };
  }

  async function request(method, url, options) {
    const envelope = await requestFull(method, url, options);
    return envelope.data;
  }

  const api = {
    request,
    requestFull,
    get(url, options) {
      return request("GET", url, options);
    },
    getFull(url, options) {
      return requestFull("GET", url, options);
    },
    post(url, body, options) {
      return request("POST", url, { ...(options || {}), body });
    },
    put(url, body, options) {
      return request("PUT", url, { ...(options || {}), body });
    },
    delete(url, options) {
      return request("DELETE", url, options);
    },
  };

  async function fetchJSON(input, init) {
    if (typeof input === "string") {
      return api.request((init && init.method) || "GET", input, init);
    }
    if (input instanceof Request) {
      const response = await fetchWithProject(input, init);
      const payload = await parseResponseJSON(response);
      if (!response.ok) {
        throw buildApiError(response, payload, `HTTP ${response.status}`);
      }
      if (isEnvelope(payload)) {
        if (payload.status === "error") {
          throw buildApiError(response, payload, "Request failed");
        }
        return payload.data;
      }
      return payload;
    }
    return api.request("GET", String(input), init);
  }

  function navigateInShell(page) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: "navigate", page }, "*");
      return;
    }
    window.location.href = page;
  }

  function forceLoadTheme() {
    if (!document.querySelector('link[href*="app-theme.css"]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/static/css/app-theme.css?v=" + Date.now();
      document.head.appendChild(link);
    }
  }

  function markIframeState() {
    forceLoadTheme();
    if (window.self !== window.top) {
      document.body.classList.add("in-iframe");
      document.body.classList.add("iframe-mode");
    }
  }

  window.fetch = fetchWithProject;
  window.MarketApp = {
    normalizeProjectKey,
    getProjectKey,
    withProjectKey,
    fetchJSON,
    navigateInShell,
    api,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", markIframeState, { once: true });
  } else {
    markIframeState();
  }
})();
