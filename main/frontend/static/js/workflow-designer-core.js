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

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
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

  function validateDesign(design) {
    const diagnostics = [];
    const nodeMap = new Map(design.nodes.map((n) => [n.id, n]));

    if (!design.nodes.length) {
      diagnostics.push({ kind: "compile_error", message: "没有可执行节点" });
    }

    design.edges.forEach((edge) => {
      if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) {
        diagnostics.push({ kind: "compile_error", edge_id: edge.id, message: "连线存在无效节点引用" });
        return;
      }
      if (edge.source === edge.target) {
        diagnostics.push({ kind: "compile_error", edge_id: edge.id, message: "不允许节点自连接" });
      }

      const sourceNode = nodeMap.get(edge.source);
      const targetNode = nodeMap.get(edge.target);
      const sourceDef = MODULE_REGISTRY[sourceNode.module_key];
      const targetDef = MODULE_REGISTRY[targetNode.module_key];
      if (!sourceDef || !targetDef) {
        diagnostics.push({ kind: "compile_error", edge_id: edge.id, message: "节点模块不存在" });
        return;
      }

      const typeCompatible = sourceDef.output_types.some((x) => targetDef.input_types.includes(x));
      if (!typeCompatible && targetDef.category !== "adapter") {
        diagnostics.push({
          kind: "compile_error",
          edge_id: edge.id,
          message: `类型不兼容: ${sourceNode.title} -> ${targetNode.title}`,
        });
      }
    });

    if (detectCycle(design)) {
      diagnostics.push({ kind: "compile_error", message: "检测到环路，无法执行" });
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
        diagnostics.push({ kind: "compile_error", node_id: node.id, message: `节点 ${node.title} 缺少输入连线` });
      }
      if (def.category === "branch" && (outgoing.get(node.id) || 0) < 2) {
        diagnostics.push({ kind: "compile_error", node_id: node.id, message: `条件分支节点 ${node.title} 至少需要两条输出连线` });
      }
    });

    return diagnostics;
  }

  function sanitizeSteps(design) {
    const steps = [];
    design.nodes.forEach((node) => {
      const def = MODULE_REGISTRY[node.module_key];
      if (!def) return;
      if (def.handler.startsWith("builtin.")) return;
      steps.push({
        handler: def.handler,
        params: node.params || {},
        enabled: true,
        name: node.title || def.title,
      });
    });
    return steps;
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
    next.nodes.push({
      id: branchId,
      module_key: "branch_condition",
      title: "条件分支",
      data_type: next.global_data_type || "market_info",
      position: { x: 520, y: 260 },
      params: {
        field: (opts && opts.field) || "sentiment",
        operator: (opts && opts.operator) || "contains",
        value: (opts && opts.value) || "positive",
        branch_mode: "two_way",
      },
    });

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
    const diagnostics = validateDesign(design);
    const compileErrors = diagnostics.filter((d) => d.kind === "compile_error");

    const steps = sanitizeSteps(design);

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
      diagnostics,
    };

    return {
      workflow_name: options.workflow_name || "workflow_visual_builder",
      steps,
      board_layout,
      diagnostics,
      compile_errors: compileErrors,
    };
  }

  window.WorkflowDesignerCore = {
    MODULE_REGISTRY,
    createDefaultDesign,
    applyGlobalType,
    validateDesign,
    compileDesign,
    parseKeywords,
    insertConditionBranchNode,
  };
})();
