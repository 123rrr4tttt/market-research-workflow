(function () {
  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizeFieldMap(fieldMap) {
    if (!Array.isArray(fieldMap)) return [];
    return fieldMap
      .filter((x) => x && typeof x === "object")
      .map((x) => ({
        from: String(x.from || "").trim(),
        to: String(x.to || "").trim(),
        default: Object.prototype.hasOwnProperty.call(x, "default") ? x.default : "",
      }))
      .filter((x) => x.to);
  }

  function detectInterfaceGaps(design, registry) {
    const nodeMap = new Map(design.nodes.map((n) => [n.id, n]));
    const gaps = [];

    for (const edge of design.edges) {
      const sourceNode = nodeMap.get(edge.source);
      const targetNode = nodeMap.get(edge.target);
      if (!sourceNode || !targetNode) continue;
      const sourceDef = registry[sourceNode.module_key];
      const targetDef = registry[targetNode.module_key];
      if (!sourceDef || !targetDef) continue;

      const mapping = edge.mapping && typeof edge.mapping === "object" ? edge.mapping : {};
      const fieldMap = normalizeFieldMap(mapping.field_map);

      if (sourceDef.cardinality !== targetDef.cardinality && !mapping.count_rule) {
        gaps.push({
          edge_id: edge.id,
          type: "count_mismatch",
          source: sourceNode.title,
          target: targetNode.title,
          message: `数量不匹配: ${sourceDef.cardinality} -> ${targetDef.cardinality}`,
        });
      }

      const sourceFields = Array.isArray(sourceDef.output_fields) ? sourceDef.output_fields : [];
      const requiredFields = Array.isArray(targetDef.required_input_fields) ? targetDef.required_input_fields : [];
      const mappedTargets = new Set(fieldMap.map((m) => m.to));
      const missing = requiredFields.filter((f) => !sourceFields.includes(f) && !mappedTargets.has(f));
      if (missing.length) {
        gaps.push({
          edge_id: edge.id,
          type: "field_mismatch",
          source: sourceNode.title,
          target: targetNode.title,
          missing,
          message: `字段缺失: ${missing.join(", ")}`,
        });
      }
    }

    return gaps;
  }

  function ensureEdgeMapping(edge) {
    if (!edge.mapping || typeof edge.mapping !== "object") {
      edge.mapping = { count_rule: "", field_map: [] };
    }
    if (!Array.isArray(edge.mapping.field_map)) edge.mapping.field_map = [];
    return edge.mapping;
  }

  function quickFixGap(design, gap, registry) {
    const next = clone(design);
    const edge = next.edges.find((e) => e.id === gap.edge_id);
    if (!edge) return next;
    const mapping = ensureEdgeMapping(edge);

    if (gap.type === "count_mismatch" && !mapping.count_rule) {
      mapping.count_rule = "many_to_many";
    }

    if (gap.type === "field_mismatch") {
      const nodeMap = new Map(next.nodes.map((n) => [n.id, n]));
      const sourceNode = nodeMap.get(edge.source);
      const sourceDef = sourceNode ? registry[sourceNode.module_key] : null;
      const sourceFields = sourceDef && Array.isArray(sourceDef.output_fields) ? sourceDef.output_fields : [];
      const current = normalizeFieldMap(mapping.field_map);
      const usedTargets = new Set(current.map((m) => m.to));

      for (const targetField of gap.missing || []) {
        if (usedTargets.has(targetField)) continue;
        if (sourceFields.includes(targetField)) {
          current.push({ from: targetField, to: targetField, default: "" });
        } else {
          current.push({ from: "", to: targetField, default: "" });
        }
      }
      mapping.field_map = current;
    }

    return next;
  }

  function promoteEdgeToAdapter(design, edgeId) {
    const next = clone(design);
    const edgeIndex = next.edges.findIndex((e) => e.id === edgeId);
    if (edgeIndex < 0) return next;

    const edge = next.edges[edgeIndex];
    const adapterId = `adapter_${Date.now()}`;
    const adapterNode = {
      id: adapterId,
      module_key: "adapter",
      title: "接口适配器",
      data_type: "market_info",
      params: {
        count_rule: edge.mapping && edge.mapping.count_rule ? edge.mapping.count_rule : "many_to_many",
        field_map: normalizeFieldMap(edge.mapping && edge.mapping.field_map),
      },
    };

    next.nodes.push(adapterNode);
    next.edges.splice(edgeIndex, 1);
    next.edges.push({
      id: `e_${Date.now()}_a`,
      source: edge.source,
      target: adapterId,
      mapping: { count_rule: "many_to_many", field_map: [] },
    });
    next.edges.push({
      id: `e_${Date.now()}_b`,
      source: adapterId,
      target: edge.target,
      mapping: {
        count_rule: adapterNode.params.count_rule,
        field_map: adapterNode.params.field_map,
      },
    });

    return next;
  }

  function collectEdgeMappings(design) {
    return (design.edges || []).map((edge) => ({
      edge_id: edge.id,
      source: edge.source,
      target: edge.target,
      count_rule: edge.mapping && edge.mapping.count_rule ? edge.mapping.count_rule : "",
      field_map: normalizeFieldMap(edge.mapping && edge.mapping.field_map),
    }));
  }

  function collectAdapterNodes(design) {
    return (design.nodes || [])
      .filter((node) => node.module_key === "adapter")
      .map((node) => ({
        node_id: node.id,
        mode: "adapter",
        params: node.params || {},
      }));
  }

  window.WorkflowDesignerMapping = {
    detectInterfaceGaps,
    quickFixGap,
    promoteEdgeToAdapter,
    collectEdgeMappings,
    collectAdapterNodes,
    normalizeFieldMap,
  };
})();
