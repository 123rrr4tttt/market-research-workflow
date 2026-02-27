(function () {
  const MODULE_REGISTRY = {
    search_market: {
      module_key: "search_market",
      title: "市场搜索",
      handler: "ingest.market",
      category: "search",
      input_types: ["query"],
      output_types: ["documents"],
      cardinality: "many",
      output_fields: ["url", "title", "content", "published_at"],
      required_input_fields: ["keywords"],
      default_params: { keywords: [], limit: 20, enable_extraction: true },
    },
    search_policy: {
      module_key: "search_policy",
      title: "政策搜索",
      handler: "ingest.policy",
      category: "search",
      input_types: ["query"],
      output_types: ["documents"],
      cardinality: "many",
      output_fields: ["url", "title", "content", "published_at", "state"],
      required_input_fields: ["source_hint"],
      default_params: { source_hint: "", state: "" },
    },
    search_social: {
      module_key: "search_social",
      title: "舆情搜索",
      handler: "ingest.social_sentiment",
      category: "search",
      input_types: ["query"],
      output_types: ["documents"],
      cardinality: "many",
      output_fields: ["url", "title", "content", "platform", "sentiment"],
      required_input_fields: ["keywords"],
      default_params: { keywords: [], limit: 20, enable_extraction: true },
    },
    search_news: {
      module_key: "search_news",
      title: "新闻搜索",
      handler: "ingest.google_news",
      category: "search",
      input_types: ["query"],
      output_types: ["documents"],
      cardinality: "many",
      output_fields: ["url", "title", "content", "published_at", "source"],
      required_input_fields: ["keywords"],
      default_params: { keywords: [], limit: 20 },
    },
    search_reddit: {
      module_key: "search_reddit",
      title: "社区搜索",
      handler: "ingest.reddit",
      category: "search",
      input_types: ["query"],
      output_types: ["documents"],
      cardinality: "many",
      output_fields: ["url", "title", "content", "subreddit"],
      required_input_fields: ["subreddit"],
      default_params: { subreddit: "Lottery", limit: 20 },
    },
    store_documents: {
      module_key: "store_documents",
      title: "入库",
      handler: "builtin.store",
      category: "store",
      input_types: ["documents"],
      output_types: ["documents"],
      cardinality: "many",
      output_fields: ["url", "title", "content", "published_at"],
      required_input_fields: ["url", "title"],
      default_params: {},
    },
    llm_extract: {
      module_key: "llm_extract",
      title: "LLM提取",
      handler: "builtin.llm_extract",
      category: "llm",
      input_types: ["documents"],
      output_types: ["extracted_data"],
      cardinality: "many",
      output_fields: ["summary", "entities", "topics", "confidence"],
      required_input_fields: ["content"],
      default_params: { enabled: true, provider: "auto" },
    },
    aggregate_topic: {
      module_key: "aggregate_topic",
      title: "主题聚合",
      handler: "builtin.aggregate_topic",
      category: "llm",
      input_types: ["extracted_data", "documents"],
      output_types: ["extracted_data"],
      cardinality: "many",
      output_fields: ["summary", "entities", "topics", "confidence"],
      required_input_fields: [],
      default_params: {},
    },
    viz_trend: {
      module_key: "viz_trend",
      title: "趋势看板",
      handler: "builtin.viz_trend",
      category: "viz",
      input_types: ["extracted_data", "documents"],
      output_types: ["visualization"],
      cardinality: "one",
      output_fields: ["series", "legend"],
      required_input_fields: ["summary"],
      default_params: { layout: "trend" },
    },
    viz_timeline: {
      module_key: "viz_timeline",
      title: "时间线看板",
      handler: "builtin.viz_timeline",
      category: "viz",
      input_types: ["documents", "extracted_data"],
      output_types: ["visualization"],
      cardinality: "one",
      output_fields: ["events"],
      required_input_fields: ["published_at"],
      default_params: { layout: "timeline" },
    },
    viz_graph: {
      module_key: "viz_graph",
      title: "图谱看板",
      handler: "builtin.viz_graph",
      category: "viz",
      input_types: ["extracted_data", "documents"],
      output_types: ["visualization"],
      cardinality: "one",
      output_fields: ["nodes", "edges"],
      required_input_fields: ["entities"],
      default_params: { layout: "graph" },
    },
    adapter: {
      module_key: "adapter",
      title: "接口适配器",
      handler: "builtin.adapter",
      category: "adapter",
      input_types: ["documents", "extracted_data", "visualization"],
      output_types: ["documents", "extracted_data", "visualization"],
      cardinality: "many",
      output_fields: [],
      required_input_fields: [],
      default_params: { count_rule: "many_to_many", field_map: [] },
    },
    branch_condition: {
      module_key: "branch_condition",
      title: "条件分支",
      handler: "builtin.branch_condition",
      category: "branch",
      input_types: ["documents", "extracted_data"],
      output_types: ["documents", "extracted_data"],
      cardinality: "many",
      output_fields: [],
      required_input_fields: [],
      default_params: {
        field: "sentiment",
        operator: "contains",
        value: "positive",
        branch_mode: "two_way",
      },
    },
  };
  const DEFAULT_NODE_POSITION = Object.freeze({ x: 120, y: 120 });
  const EDGE_COUNT_RULES = new Set(["one_to_one", "one_to_many", "many_to_one", "many_to_many"]);
  const HANDLE_OUTPUT_PATTERN = /\b(out|output|source)\b/i;
  const HANDLE_INPUT_PATTERN = /\b(in|input|target)\b/i;

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function isPlainObject(value) {
    return Object.prototype.toString.call(value) === "[object Object]";
  }

  function inferFieldType(value) {
    if (Array.isArray(value)) return "array";
    if (value === null) return "null";
    if (typeof value === "boolean") return "boolean";
    if (typeof value === "number") return "number";
    if (typeof value === "object") return "object";
    return "string";
  }

  function resolveModuleDefinition(moduleLike) {
    if (typeof moduleLike === "string") return MODULE_REGISTRY[moduleLike] || null;
    if (isPlainObject(moduleLike)) return moduleLike;
    return null;
  }

  function normalizeFieldType(typeLike, fallbackValue, enumValues) {
    if (typeof typeLike === "string" && typeLike.trim()) return typeLike.trim();
    if (Array.isArray(enumValues) && enumValues.length) return inferFieldType(enumValues[0]);
    const inferred = inferFieldType(fallbackValue);
    return inferred === "null" ? "string" : inferred;
  }

  function normalizeInputFields(moduleLike) {
    const moduleDef = resolveModuleDefinition(moduleLike);
    if (!moduleDef) return {};
    const defaults = isPlainObject(moduleDef.default_params) ? moduleDef.default_params : {};
    const requiredFields = Array.isArray(moduleDef.required_input_fields) ? moduleDef.required_input_fields : [];
    const requiredSet = new Set(requiredFields.map((item) => String(item)));
    const rawInputFields = isPlainObject(moduleDef.input_fields) ? moduleDef.input_fields : {};

    const fieldNames = [];
    const added = new Set();
    const pushField = function (name) {
      const key = String(name || "");
      if (!key || added.has(key)) return;
      added.add(key);
      fieldNames.push(key);
    };

    Object.keys(defaults).forEach(pushField);
    Object.keys(rawInputFields).forEach(pushField);
    requiredSet.forEach(pushField);

    const schema = {};
    fieldNames.forEach((fieldName) => {
      const defaultFromModule = Object.prototype.hasOwnProperty.call(defaults, fieldName) ? clone(defaults[fieldName]) : null;
      const rawField = rawInputFields[fieldName];
      const fieldDef = isPlainObject(rawField) ? clone(rawField) : {};
      const enumValues = Array.isArray(fieldDef.enum) ? clone(fieldDef.enum) : null;
      const hasDefault = Object.prototype.hasOwnProperty.call(fieldDef, "default");
      const normalizedDefault = hasDefault ? clone(fieldDef.default) : defaultFromModule;
      const normalized = Object.assign({}, fieldDef, {
        type: normalizeFieldType(fieldDef.type, normalizedDefault, enumValues),
        required: typeof fieldDef.required === "boolean" ? fieldDef.required : requiredSet.has(fieldName),
        default: normalizedDefault,
      });
      if (enumValues && enumValues.length) normalized.enum = enumValues;
      else delete normalized.enum;
      schema[fieldName] = normalized;
    });
    return schema;
  }

  function getRenderableInputFields(moduleLike) {
    const normalized = normalizeInputFields(moduleLike);
    return Object.keys(normalized).map((fieldName) => {
      const field = normalized[fieldName];
      return {
        key: fieldName,
        type: field.type,
        required: Boolean(field.required),
        default: clone(field.default),
        enum: Array.isArray(field.enum) ? clone(field.enum) : [],
      };
    });
  }

  function castParamValueByType(value, type) {
    if (value === undefined) return undefined;
    if (value === null) return null;
    if (type === "boolean") {
      if (typeof value === "boolean") return value;
      if (typeof value === "number") return value !== 0;
      const text = String(value).trim().toLowerCase();
      if (["true", "1", "yes", "on"].includes(text)) return true;
      if (["false", "0", "no", "off", ""].includes(text)) return false;
      return Boolean(value);
    }
    if (type === "number") {
      if (typeof value === "number") return Number.isFinite(value) ? value : null;
      const parsed = Number(String(value).trim());
      return Number.isFinite(parsed) ? parsed : null;
    }
    if (type === "array") {
      if (Array.isArray(value)) return clone(value);
      if (typeof value === "string") {
        const trimmed = value.trim();
        if (!trimmed) return [];
        if ((trimmed.startsWith("[") && trimmed.endsWith("]")) || (trimmed.startsWith("{") && trimmed.endsWith("}"))) {
          try {
            const parsed = JSON.parse(trimmed);
            if (Array.isArray(parsed)) return parsed;
          } catch (err) {
            // ignore parse error and fallback to split
          }
        }
        return trimmed.split(/[\n,]/g).map((x) => x.trim()).filter(Boolean);
      }
      return [clone(value)];
    }
    if (type === "object") {
      if (isPlainObject(value)) return clone(value);
      if (typeof value === "string") {
        const trimmed = value.trim();
        if (!trimmed) return {};
        try {
          const parsed = JSON.parse(trimmed);
          return isPlainObject(parsed) ? parsed : {};
        } catch (err) {
          return {};
        }
      }
      return {};
    }
    if (type === "string") return String(value);
    return clone(value);
  }

  function coerceParamValue(value, fieldMeta) {
    const meta = isPlainObject(fieldMeta) ? fieldMeta : {};
    const hasDefault = Object.prototype.hasOwnProperty.call(meta, "default");
    const fallback = hasDefault ? clone(meta.default) : null;
    const resolvedType = normalizeFieldType(meta.type, fallback, meta.enum);
    const hasInput = value !== undefined;
    const casted = castParamValueByType(hasInput ? value : fallback, resolvedType);
    if (Array.isArray(meta.enum) && meta.enum.length) {
      return meta.enum.includes(casted) ? casted : fallback;
    }
    return casted;
  }

  function mergeModuleParams(moduleLike, params, options) {
    const moduleDef = resolveModuleDefinition(moduleLike);
    const inputParams = isPlainObject(params) ? params : {};
    const opts = isPlainObject(options) ? options : {};
    if (!moduleDef) return clone(inputParams);

    const normalizedFields = normalizeInputFields(moduleDef);
    const defaults = isPlainObject(moduleDef.default_params) ? clone(moduleDef.default_params) : {};
    const merged = {};
    const knownKeys = new Set(Object.keys(defaults).concat(Object.keys(normalizedFields)));

    knownKeys.forEach((fieldName) => {
      const fieldMeta = normalizedFields[fieldName] || {
        type: inferFieldType(defaults[fieldName]),
        required: false,
        default: Object.prototype.hasOwnProperty.call(defaults, fieldName) ? clone(defaults[fieldName]) : null,
      };
      const hasInput = Object.prototype.hasOwnProperty.call(inputParams, fieldName);
      merged[fieldName] = coerceParamValue(hasInput ? inputParams[fieldName] : undefined, fieldMeta);
    });

    if (opts.includeUnknown !== false) {
      Object.keys(inputParams).forEach((fieldName) => {
        if (knownKeys.has(fieldName)) return;
        merged[fieldName] = clone(inputParams[fieldName]);
      });
    }
    return merged;
  }

  function getModuleFieldMetadata(moduleLike) {
    const normalized = normalizeInputFields(moduleLike);
    const metadata = {};
    Object.keys(normalized).forEach((fieldName) => {
      const field = normalized[fieldName];
      metadata[fieldName] = {
        type: field.type,
        required: Boolean(field.required),
        default: clone(field.default),
        enum: Array.isArray(field.enum) ? clone(field.enum) : [],
      };
    });
    return metadata;
  }

  function hydrateModuleSchemas(registry) {
    Object.keys(registry).forEach((moduleKey) => {
      const def = registry[moduleKey];
      if (!isPlainObject(def)) return;
      def.input_fields = normalizeInputFields(def);
    });
  }

  hydrateModuleSchemas(MODULE_REGISTRY);

  function stableStringify(value) {
    if (value === null || value === undefined) return String(value);
    if (typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }

  function hashString(input) {
    let hash = 0x811c9dc5;
    for (let i = 0; i < input.length; i += 1) {
      hash ^= input.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(36);
  }

  function generateStableId(prefix, seed) {
    const normalizedPrefix = String(prefix || "id")
      .replace(/[^a-zA-Z0-9_]/g, "_")
      .replace(/^_+|_+$/g, "") || "id";
    const normalizedSeed = typeof seed === "string" ? seed : stableStringify(seed);
    return `${normalizedPrefix}_${hashString(normalizedSeed)}`;
  }

  function resolveNodeTitle(moduleKey, def, opts) {
    const candidates = [opts && opts.title, opts && opts.label, def && def.title, moduleKey];
    for (const candidate of candidates) {
      if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
    }
    return String(moduleKey || "node");
  }

  function normalizePosition(position, fallbackPosition) {
    const fallback = fallbackPosition || DEFAULT_NODE_POSITION;
    const x = Number(position && position.x);
    const y = Number(position && position.y);
    if (Number.isFinite(x) && Number.isFinite(y)) return { x, y };
    return { x: Number(fallback.x) || DEFAULT_NODE_POSITION.x, y: Number(fallback.y) || DEFAULT_NODE_POSITION.y };
  }

  function buildNodeFromModule(moduleKey, options) {
    const opts = options && typeof options === "object" ? options : {};
    const def = MODULE_REGISTRY[moduleKey];
    if (!def) return null;
    const inputParams = isPlainObject(opts.params) ? clone(opts.params) : {};
    const resolvedDataType = String(opts.data_type || opts.globalDataType || "market_info").trim() || "market_info";

    return {
      id: opts.id || generateStableId(`n_${moduleKey}`, { moduleKey, opts }),
      module_key: moduleKey,
      title: resolveNodeTitle(moduleKey, def, opts),
      data_type: resolvedDataType,
      params: mergeModuleParams(def, inputParams),
      position: normalizePosition(opts.position, opts.fallbackPosition),
    };
  }

  function inferSearchModule(searchModuleValue) {
    const mapping = {
      market: "search_market",
      policy: "search_policy",
      social: "search_social",
      news: "search_news",
      reddit: "search_reddit",
    };
    return mapping[searchModuleValue] || "search_market";
  }

  function inferVizModule(vizModuleValue) {
    const mapping = {
      trend: "viz_trend",
      timeline: "viz_timeline",
      graph: "viz_graph",
    };
    return mapping[vizModuleValue] || "viz_trend";
  }

  function parseKeywords(raw) {
    return String(raw || "")
      .split(/[\n,]/g)
      .map((x) => x.trim())
      .filter(Boolean);
  }

  function createDefaultDesign(input) {
    const searchModuleKey = inferSearchModule(input.searchModule);
    const vizModuleKey = inferVizModule(input.vizModule);
    const keywords = parseKeywords(input.queryText);
    const limit = Math.max(1, Number(input.limit || 20));

    const searchDef = MODULE_REGISTRY[searchModuleKey];
    const searchParams = clone(searchDef.default_params);
    if (searchModuleKey === "search_reddit") {
      searchParams.subreddit = keywords[0] || searchParams.subreddit;
    } else if (searchModuleKey === "search_policy") {
      searchParams.source_hint = keywords[0] || "";
      searchParams.state = input.state || "";
    } else {
      searchParams.keywords = keywords;
      searchParams.limit = limit;
    }

    const llmEnabled = input.llmEnabled !== false;
    const llmParams = {
      enabled: llmEnabled,
      provider: input.llmProvider || "auto",
      data_type: input.globalDataType || "market_info",
    };

    const nodes = [
      {
        id: "n_search",
        module_key: searchModuleKey,
        title: searchDef.title,
        data_type: input.globalDataType || "market_info",
        params: searchParams,
        position: { x: 36, y: 120 },
      },
      {
        id: "n_store",
        module_key: "store_documents",
        title: "入库",
        data_type: input.globalDataType || "market_info",
        params: {},
        position: { x: 280, y: 120 },
      },
      {
        id: "n_llm",
        module_key: "llm_extract",
        title: "LLM提取",
        data_type: input.globalDataType || "market_info",
        params: llmParams,
        position: { x: 524, y: 120 },
      },
      {
        id: "n_viz",
        module_key: vizModuleKey,
        title: MODULE_REGISTRY[vizModuleKey].title,
        data_type: input.globalDataType || "market_info",
        params: { layout: input.vizModule || "trend" },
        position: { x: 768, y: 120 },
      },
    ];

    const edges = [
      { id: "e1", source: "n_search", target: "n_store", mapping: { count_rule: "many_to_many", field_map: [] } },
      { id: "e2", source: "n_store", target: "n_llm", mapping: { count_rule: "many_to_many", field_map: [] } },
      { id: "e3", source: "n_llm", target: "n_viz", mapping: { count_rule: "many_to_one", field_map: [] } },
    ];

    return {
      global_data_type: input.globalDataType || "market_info",
      llm_policy: input.llmProvider || "auto",
      visualization_module: input.vizModule || "trend",
      nodes,
      edges,
      diagnostics: [],
    };
  }

  function applyGlobalType(design, globalType, nodeOverrides) {
    const normalized = String(globalType || "market_info").trim() || "market_info";
    design.global_data_type = normalized;
    const overrides = nodeOverrides && typeof nodeOverrides === "object" ? nodeOverrides : {};
    design.nodes.forEach((node) => {
      const overrideType = overrides[node.id];
      node.data_type = overrideType ? String(overrideType) : normalized;
      if (!node.params || typeof node.params !== "object") node.params = {};
      node.params.data_type = node.data_type;
    });
    return design;
  }

  function detectCycle(design) {
    const graph = new Map();
    design.nodes.forEach((n) => graph.set(n.id, []));
    design.edges.forEach((e) => {
      if (graph.has(e.source)) graph.get(e.source).push(e.target);
    });

    const visiting = new Set();
    const visited = new Set();

    function dfs(nodeId) {
      if (visiting.has(nodeId)) return true;
      if (visited.has(nodeId)) return false;
      visiting.add(nodeId);
      const next = graph.get(nodeId) || [];
      for (const target of next) {
        if (dfs(target)) return true;
      }
      visiting.delete(nodeId);
      visited.add(nodeId);
      return false;
    }

    for (const nodeId of graph.keys()) {
      if (dfs(nodeId)) return true;
    }
    return false;
  }

  function createDiagnosticsBucket() {
    return { errors: [], warnings: [], info: [] };
  }

  function appendDiagnostic(bucket, level, payload) {
    if (!bucket[level]) return;
    bucket[level].push(payload);
  }

  function dedupeDiagnostics(list) {
    return list.filter((item, index, arr) => {
      return arr.findIndex((x) => x.kind === item.kind && x.node_id === item.node_id && x.edge_id === item.edge_id && x.message === item.message) === index;
    });
  }

  function mergeDiagnostics(left, right) {
    const merged = createDiagnosticsBucket();
    merged.errors = dedupeDiagnostics((left && left.errors ? left.errors : []).concat(right && right.errors ? right.errors : []));
    merged.warnings = dedupeDiagnostics((left && left.warnings ? left.warnings : []).concat(right && right.warnings ? right.warnings : []));
    merged.info = dedupeDiagnostics((left && left.info ? left.info : []).concat(right && right.info ? right.info : []));
    return merged;
  }

  function getHandleString(edgeLike, key) {
    if (!edgeLike || typeof edgeLike !== "object") return "";
    const camel = key === "source" ? "sourceHandle" : "targetHandle";
    const snake = key === "source" ? "source_handle" : "target_handle";
    return String(edgeLike[camel] || edgeLike[snake] || "").trim();
  }

  function parseHandle(handle) {
    const normalized = String(handle || "").trim();
    if (!normalized) return { raw: "", direction: "", dataType: "" };
    const parts = normalized.split(/[:|/]/g).map((item) => item.trim()).filter(Boolean);
    let direction = "";
    let dataType = "";
    parts.forEach((part) => {
      if (!direction && HANDLE_OUTPUT_PATTERN.test(part)) direction = "output";
      if (!direction && HANDLE_INPUT_PATTERN.test(part)) direction = "input";
    });
    if (parts.length >= 2) {
      const candidate = parts[parts.length - 1];
      if (!HANDLE_OUTPUT_PATTERN.test(candidate) && !HANDLE_INPUT_PATTERN.test(candidate)) dataType = candidate;
    }
    return { raw: normalized, direction, dataType };
  }

  function hasPath(graph, fromId, toId) {
    const queue = [fromId];
    const visited = new Set();
    while (queue.length) {
      const nodeId = queue.shift();
      if (nodeId === toId) return true;
      if (visited.has(nodeId)) continue;
      visited.add(nodeId);
      const next = graph.get(nodeId) || [];
      next.forEach((item) => {
        if (!visited.has(item)) queue.push(item);
      });
    }
    return false;
  }

  function isConnectionAllowed(design, sourceId, targetId, options) {
    const opts = options && typeof options === "object" ? options : {};
    const result = { allowed: true, code: "ok", message: "" };
    const nodes = Array.isArray(design && design.nodes) ? design.nodes : [];
    const edges = Array.isArray(design && design.edges) ? design.edges : [];
    const source = String(sourceId || "");
    const target = String(targetId || "");
    const sourceHandle = String(opts.sourceHandle || "");
    const targetHandle = String(opts.targetHandle || "");
    const ignoreEdgeId = String(opts.ignoreEdgeId || "");
    const requireHandles = opts.requireHandles === true;
    const disallowCycles = opts.allowCycle !== true;

    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    if (!nodeMap.has(source) || !nodeMap.has(target)) {
      result.allowed = false;
      result.code = "invalid_node";
      result.message = "连线节点不存在";
      return opts.withReason ? result : result.allowed;
    }
    if (source === target && opts.allowSelfLoop !== true) {
      result.allowed = false;
      result.code = "self_loop";
      result.message = "不允许节点自连接";
      return opts.withReason ? result : result.allowed;
    }

    const duplicate = edges.some((edge) => {
      if (!edge || edge.id === ignoreEdgeId) return false;
      if (edge.source !== source || edge.target !== target) return false;
      if (sourceHandle || targetHandle) {
        const existedSourceHandle = getHandleString(edge, "source");
        const existedTargetHandle = getHandleString(edge, "target");
        return existedSourceHandle === sourceHandle && existedTargetHandle === targetHandle;
      }
      return true;
    });
    if (duplicate && opts.allowDuplicate !== true) {
      result.allowed = false;
      result.code = "duplicate";
      result.message = "重复连线";
      return opts.withReason ? result : result.allowed;
    }

    const sourceNode = nodeMap.get(source);
    const targetNode = nodeMap.get(target);
    const sourceDef = MODULE_REGISTRY[sourceNode.module_key];
    const targetDef = MODULE_REGISTRY[targetNode.module_key];
    if (!sourceDef || !targetDef) {
      result.allowed = false;
      result.code = "unknown_module";
      result.message = "节点模块不存在";
      return opts.withReason ? result : result.allowed;
    }

    const parsedSourceHandle = parseHandle(sourceHandle);
    const parsedTargetHandle = parseHandle(targetHandle);
    if (requireHandles && (!parsedSourceHandle.raw || !parsedTargetHandle.raw)) {
      result.allowed = false;
      result.code = "missing_handle";
      result.message = "连线必须指定源/目标句柄";
      return opts.withReason ? result : result.allowed;
    }
    if (parsedSourceHandle.direction === "input") {
      result.allowed = false;
      result.code = "invalid_direction";
      result.message = "源句柄必须是输出方向";
      return opts.withReason ? result : result.allowed;
    }
    if (parsedTargetHandle.direction === "output") {
      result.allowed = false;
      result.code = "invalid_direction";
      result.message = "目标句柄必须是输入方向";
      return opts.withReason ? result : result.allowed;
    }

    const sourceTypes = parsedSourceHandle.dataType ? [parsedSourceHandle.dataType] : sourceDef.output_types;
    const targetTypes = parsedTargetHandle.dataType ? [parsedTargetHandle.dataType] : targetDef.input_types;
    const isAdapterTarget = targetDef.category === "adapter";
    const typeCompatible = sourceTypes.some((x) => targetTypes.includes(x));
    if (!typeCompatible && !isAdapterTarget) {
      result.allowed = false;
      result.code = "type_mismatch";
      result.message = `类型不兼容: ${sourceNode.title} -> ${targetNode.title}`;
      return opts.withReason ? result : result.allowed;
    }
    if (parsedSourceHandle.dataType && !sourceDef.output_types.includes(parsedSourceHandle.dataType)) {
      result.allowed = false;
      result.code = "source_handle_type_mismatch";
      result.message = `源句柄类型不合法: ${parsedSourceHandle.dataType}`;
      return opts.withReason ? result : result.allowed;
    }
    if (parsedTargetHandle.dataType && !targetDef.input_types.includes(parsedTargetHandle.dataType) && !isAdapterTarget) {
      result.allowed = false;
      result.code = "target_handle_type_mismatch";
      result.message = `目标句柄类型不合法: ${parsedTargetHandle.dataType}`;
      return opts.withReason ? result : result.allowed;
    }

    if (disallowCycles) {
      const graph = new Map();
      nodes.forEach((node) => graph.set(node.id, []));
      edges.forEach((edge) => {
        if (!edge || edge.id === ignoreEdgeId) return;
        if (graph.has(edge.source)) graph.get(edge.source).push(edge.target);
      });
      if (graph.has(source)) graph.get(source).push(target);
      if (hasPath(graph, target, source)) {
        result.allowed = false;
        result.code = "cycle";
        result.message = "连线方向将导致环路";
        return opts.withReason ? result : result.allowed;
      }
    }

    return opts.withReason ? result : result.allowed;
  }

  function validateDesign(design) {
    const diagnostics = createDiagnosticsBucket();
    const nodeMap = new Map(design.nodes.map((n) => [n.id, n]));

    if (!design.nodes.length) {
      appendDiagnostic(diagnostics, "errors", { kind: "compile_error", message: "没有可执行节点" });
    }

    design.nodes.forEach((node) => {
      if (!MODULE_REGISTRY[node.module_key]) {
        appendDiagnostic(diagnostics, "errors", {
          kind: "compile_error",
          node_id: node.id,
          message: `节点 ${node.title || node.id} 使用了未注册模块: ${node.module_key}`,
        });
      }
    });

    design.edges.forEach((edge) => {
      if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) {
        appendDiagnostic(diagnostics, "errors", { kind: "compile_error", edge_id: edge.id, message: "连线存在无效节点引用" });
        return;
      }
      const connectionCheck = isConnectionAllowed(design, edge.source, edge.target, {
        withReason: true,
        ignoreEdgeId: edge.id,
        sourceHandle: getHandleString(edge, "source"),
        targetHandle: getHandleString(edge, "target"),
      });
      if (!connectionCheck.allowed) {
        appendDiagnostic(diagnostics, "errors", { kind: "compile_error", edge_id: edge.id, message: connectionCheck.message });
      }
      const countRule = edge && edge.mapping && edge.mapping.count_rule;
      if (!EDGE_COUNT_RULES.has(countRule)) {
        appendDiagnostic(diagnostics, "errors", {
          kind: "compile_error",
          edge_id: edge.id,
          message: `连线 ${edge.id} 的 count_rule 不合法: ${countRule}`,
        });
      }

      const sourceNode = nodeMap.get(edge.source);
      const targetNode = nodeMap.get(edge.target);
      const sourceDef = MODULE_REGISTRY[sourceNode.module_key];
      const targetDef = MODULE_REGISTRY[targetNode.module_key];
      if (!sourceDef || !targetDef) {
        appendDiagnostic(diagnostics, "errors", { kind: "compile_error", edge_id: edge.id, message: "节点模块不存在" });
      }
    });

    if (detectCycle(design)) {
      appendDiagnostic(diagnostics, "errors", { kind: "compile_error", message: "检测到环路，无法执行" });
    }

    const incoming = new Map();
    const outgoing = new Map();
    design.nodes.forEach((n) => incoming.set(n.id, 0));
    design.nodes.forEach((n) => outgoing.set(n.id, 0));
    design.edges.forEach((e) => {
      if (incoming.has(e.target)) incoming.set(e.target, incoming.get(e.target) + 1);
      if (outgoing.has(e.source)) outgoing.set(e.source, outgoing.get(e.source) + 1);
    });

    design.nodes.forEach((node) => {
      const def = MODULE_REGISTRY[node.module_key];
      if (!def) return;
      if (def.category !== "search" && def.category !== "adapter" && (incoming.get(node.id) || 0) === 0) {
        appendDiagnostic(diagnostics, "errors", { kind: "compile_error", node_id: node.id, message: `节点 ${node.title} 缺少输入连线` });
      }
      if (def.category === "branch" && (outgoing.get(node.id) || 0) < 2) {
        appendDiagnostic(diagnostics, "errors", { kind: "compile_error", node_id: node.id, message: `条件分支节点 ${node.title} 至少需要两条输出连线` });
      }
      if (def.category !== "viz" && (outgoing.get(node.id) || 0) === 0) {
        appendDiagnostic(diagnostics, "warnings", { kind: "compile_warning", node_id: node.id, message: `节点 ${node.title} 没有下游连线` });
      }
    });

    appendDiagnostic(diagnostics, "info", {
      kind: "compile_info",
      message: `节点数 ${design.nodes.length}，连线数 ${design.edges.length}`,
    });

    const compileErrors = dedupeDiagnostics(diagnostics.errors.filter((item) => item.kind === "compile_error"));
    return {
      errors: dedupeDiagnostics(diagnostics.errors),
      warnings: dedupeDiagnostics(diagnostics.warnings),
      info: dedupeDiagnostics(diagnostics.info),
      compile_errors: compileErrors,
    };
  }

  function sanitizeSteps(design) {
    const steps = [];
    const diagnostics = [];
    design.nodes.forEach((node) => {
      const def = MODULE_REGISTRY[node.module_key];
      if (!def) {
        diagnostics.push({
          kind: "compile_error",
          node_id: node.id,
          message: `节点 ${node.title || node.id} 使用了未注册模块: ${node.module_key}`,
        });
        return;
      }
      if (def.handler.startsWith("builtin.")) return;
      steps.push({
        handler: def.handler,
        params: node.params || {},
        enabled: true,
        name: node.title || def.title,
      });
    });
    return { steps, diagnostics };
  }

  function insertConditionBranchNode(design, opts) {
    const next = clone(design);
    const sourceNodeId = opts && opts.sourceNodeId ? String(opts.sourceNodeId) : "";
    const trueTargetId = opts && opts.trueTargetId ? String(opts.trueTargetId) : "";
    const falseTargetId = opts && opts.falseTargetId ? String(opts.falseTargetId) : "";

    const nodeIds = new Set(next.nodes.map((n) => n.id));
    if (!sourceNodeId || !nodeIds.has(sourceNodeId)) return next;
    if (!trueTargetId || !nodeIds.has(trueTargetId)) return next;
    if (!falseTargetId || !nodeIds.has(falseTargetId)) return next;
    if (trueTargetId === falseTargetId) return next;

    const branchId = `n_branch_${Date.now()}`;
    const branchNode = buildNodeFromModule("branch_condition", {
      id: branchId,
      data_type: next.global_data_type || "market_info",
      position: { x: 520, y: 260 },
      params: {
        field: (opts && opts.field) || "sentiment",
        operator: (opts && opts.operator) || "contains",
        value: (opts && opts.value) || "positive",
        branch_mode: "two_way",
      },
    });
    if (!branchNode) return next;
    next.nodes.push(branchNode);

    const directEdgeIndex = next.edges.findIndex((e) => e.source === sourceNodeId && (e.target === trueTargetId || e.target === falseTargetId));
    if (directEdgeIndex >= 0) {
      next.edges.splice(directEdgeIndex, 1);
    }

    next.edges.push({
      id: `e_${Date.now()}_in`,
      source: sourceNodeId,
      target: branchId,
      mapping: { count_rule: "many_to_many", field_map: [] },
    });
    next.edges.push({
      id: `e_${Date.now()}_true`,
      source: branchId,
      target: trueTargetId,
      mapping: { count_rule: "many_to_many", field_map: [] },
      branch: "true",
    });
    next.edges.push({
      id: `e_${Date.now()}_false`,
      source: branchId,
      target: falseTargetId,
      mapping: { count_rule: "many_to_many", field_map: [] },
      branch: "false",
    });
    return next;
  }

  function compileDesign(design, options) {
    const validation = validateDesign(design);
    const compileErrors = validation.compile_errors || [];

    const sanitized = sanitizeSteps(design);
    const sanitizedDiagnostics = {
      errors: dedupeDiagnostics((sanitized.diagnostics || []).filter((d) => d.kind === "compile_error")),
      warnings: [],
      info: [],
    };
    const combinedDiagnostics = mergeDiagnostics(validation, sanitizedDiagnostics);
    const combinedCompileErrors = dedupeDiagnostics((combinedDiagnostics.errors || []).filter((d) => d.kind === "compile_error"));

    const board_layout = {
      layout: options.layout || design.visualization_module || "trend",
      auto_interface: true,
      data_flow: ["documents", "extracted_data", "visualization"],
      design: {
        global_data_type: design.global_data_type || "market_info",
        node_overrides: options.node_overrides || {},
        llm_policy: design.llm_policy || "auto",
        visualization_module: design.visualization_module || options.layout || "trend",
      },
      graph: {
        nodes: design.nodes,
        edges: design.edges,
      },
      edge_mappings: options.edge_mappings || [],
      adapter_nodes: options.adapter_nodes || [],
      diagnostics: combinedDiagnostics,
    };

    return {
      workflow_name: options.workflow_name || "workflow_visual_builder",
      steps: sanitized.steps,
      board_layout,
      diagnostics: combinedDiagnostics,
      compile_errors: dedupeDiagnostics((compileErrors || []).concat(combinedCompileErrors || [])),
    };
  }

  function getModuleSchema(moduleKey) {
    const key = String(moduleKey || "").trim();
    if (!key || !MODULE_REGISTRY[key]) return null;
    const def = MODULE_REGISTRY[key];
    return {
      module_key: def.module_key,
      title: def.title,
      category: def.category,
      input_types: clone(def.input_types || []),
      output_types: clone(def.output_types || []),
      required_input_fields: clone(def.required_input_fields || []),
      input_fields: normalizeInputFields(def),
      default_params: clone(def.default_params || {}),
    };
  }

  function getNodeOutputFields(node) {
    if (!node || !node.module_key) return [];
    const def = MODULE_REGISTRY[node.module_key];
    if (!def || !Array.isArray(def.output_fields)) return [];
    return def.output_fields
      .map((field) => String(field || "").trim())
      .filter(Boolean);
  }

  function getUpstreamVisibleNodeIds(design, nodeId, options) {
    const opts = isPlainObject(options) ? options : {};
    const includeSelf = opts.includeSelf === true;
    const nodes = Array.isArray(design && design.nodes) ? design.nodes : [];
    const edges = Array.isArray(design && design.edges) ? design.edges : [];
    const targetId = String(nodeId || "");
    if (!targetId) return [];

    const nodeIdSet = new Set(nodes.map((node) => node.id));
    if (!nodeIdSet.has(targetId)) return [];

    const incoming = new Map();
    nodes.forEach((node) => incoming.set(node.id, []));
    edges.forEach((edge) => {
      if (!edge) return;
      if (!incoming.has(edge.target) || !nodeIdSet.has(edge.source)) return;
      incoming.get(edge.target).push(edge.source);
    });

    const visited = new Set();
    const queue = [targetId];
    while (queue.length) {
      const current = queue.shift();
      const sources = incoming.get(current) || [];
      sources.forEach((sourceId) => {
        if (visited.has(sourceId)) return;
        visited.add(sourceId);
        queue.push(sourceId);
      });
    }

    if (includeSelf) visited.add(targetId);
    return nodes.map((node) => node.id).filter((id) => visited.has(id));
  }

  function filterUpstreamVisibleNodes(design, nodeId, options) {
    const upstreamIds = new Set(getUpstreamVisibleNodeIds(design, nodeId, options));
    const nodes = Array.isArray(design && design.nodes) ? design.nodes : [];
    return nodes.filter((node) => upstreamIds.has(node.id)).map((node) => clone(node));
  }

  function getVariableReferenceSuggestions(design, nodeId, options) {
    const opts = isPlainObject(options) ? options : {};
    const includeSelf = opts.includeSelf === true;
    const keyword = String(opts.keyword || "").trim().toLowerCase();
    const visibleIds = getUpstreamVisibleNodeIds(design, nodeId, { includeSelf });
    const nodes = Array.isArray(design && design.nodes) ? design.nodes : [];
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const suggestions = [];

    visibleIds.forEach((visibleNodeId) => {
      const node = nodeMap.get(visibleNodeId);
      if (!node) return;
      const outputFields = getNodeOutputFields(node);
      outputFields.forEach((field) => {
        const expression = `{{${visibleNodeId}.${field}}}`;
        const item = {
          expression,
          node_id: visibleNodeId,
          node_title: node.title || visibleNodeId,
          field,
          label: `${node.title || visibleNodeId}.${field}`,
        };
        if (!keyword) {
          suggestions.push(item);
          return;
        }
        const searchText = `${item.expression} ${item.label}`.toLowerCase();
        if (searchText.includes(keyword)) suggestions.push(item);
      });
    });

    return suggestions;
  }

  function validateVariableExpressions(expressionLike, design) {
    const input = String(expressionLike || "");
    const nodes = Array.isArray(design && design.nodes) ? design.nodes : [];
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const errors = [];
    const references = [];

    let depth = 0;
    for (let i = 0; i < input.length - 1; i += 1) {
      const pair = input.slice(i, i + 2);
      if (pair === "{{") {
        depth += 1;
        i += 1;
        continue;
      }
      if (pair === "}}") {
        if (depth <= 0) {
          errors.push({ kind: "unclosed", message: "存在未匹配的关闭标记 }}" });
          break;
        }
        depth -= 1;
        i += 1;
      }
    }
    if (depth > 0) errors.push({ kind: "unclosed", message: "存在未闭合变量表达式 {{" });

    const pattern = /\{\{\s*([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_]+)\s*\}\}/g;
    let match;
    while ((match = pattern.exec(input)) !== null) {
      const nodeId = match[1];
      const field = match[2];
      const node = nodeMap.get(nodeId);
      references.push({ expression: match[0], node_id: nodeId, field, start: match.index });
      if (!node) {
        errors.push({ kind: "unknown_node", node_id: nodeId, message: `未知节点: ${nodeId}` });
        continue;
      }
      const outputFields = getNodeOutputFields(node);
      if (!outputFields.includes(field)) {
        errors.push({ kind: "unknown_field", node_id: nodeId, field, message: `未知字段: ${nodeId}.${field}` });
      }
    }

    return {
      valid: errors.length === 0,
      errors: dedupeDiagnostics(errors),
      references,
    };
  }

  const MODULE_FIELD_METADATA = {};
  Object.keys(MODULE_REGISTRY).forEach((moduleKey) => {
    MODULE_FIELD_METADATA[moduleKey] = getModuleFieldMetadata(moduleKey);
  });

  window.WorkflowDesignerCore = {
    MODULE_REGISTRY,
    MODULE_FIELD_METADATA,
    buildNodeFromModule,
    createDefaultDesign,
    applyGlobalType,
    isConnectionAllowed,
    validateDesign,
    compileDesign,
    getModuleSchema,
    normalizeInputFields,
    getRenderableInputFields,
    getModuleFieldMetadata,
    castParamValueByType,
    coerceParamValue,
    mergeModuleParams,
    parseKeywords,
    insertConditionBranchNode,
    generateStableId,
    getUpstreamVisibleNodeIds,
    filterUpstreamVisibleNodes,
    getVariableReferenceSuggestions,
    validateVariableExpressions,
  };
})();
