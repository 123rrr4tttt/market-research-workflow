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

  function getNodeMap(design) {
    return new Map((design.nodes || []).map((n) => [n.id, n]));
  }

  function getEdgeById(design, edgeId) {
    return (design.edges || []).find((e) => e.id === edgeId) || null;
  }

  function getEdgeFieldMap(design, edgeId) {
    const edge = getEdgeById(design, edgeId);
    if (!edge) return [];
    const mapping = edge.mapping && typeof edge.mapping === "object" ? edge.mapping : {};
    return normalizeFieldMap(mapping.field_map);
  }

  function setEdgeFieldMap(design, edgeId, fieldMap) {
    const next = clone(design);
    const edge = getEdgeById(next, edgeId);
    if (!edge) return next;
    const mapping = ensureEdgeMapping(edge);
    mapping.field_map = normalizeFieldMap(fieldMap);
    return next;
  }

  function suggestFieldMap(sourceFields, targetFields, existingFieldMap) {
    const source = Array.isArray(sourceFields) ? sourceFields : [];
    const target = Array.isArray(targetFields) ? targetFields : [];
    const current = normalizeFieldMap(existingFieldMap);
    const usedTargets = new Set(current.map((m) => m.to));

    for (const targetField of target) {
      if (!targetField || usedTargets.has(targetField)) continue;
      if (source.includes(targetField)) {
        current.push({ from: targetField, to: targetField, default: "" });
      } else {
        current.push({ from: "", to: targetField, default: "" });
      }
      usedTargets.add(targetField);
    }

    return current;
  }

  function validateMissingFields(sourceFields, requiredFields, fieldMap) {
    const source = Array.isArray(sourceFields) ? sourceFields : [];
    const required = Array.isArray(requiredFields) ? requiredFields : [];
    const mappedTargets = new Set(normalizeFieldMap(fieldMap).map((m) => m.to));
    return required.filter((f) => !source.includes(f) && !mappedTargets.has(f));
  }

  function getEdgeFieldMappingContext(design, registry, edgeId) {
    const edge = getEdgeById(design, edgeId);
    if (!edge) return null;
    const nodeMap = getNodeMap(design);
    const sourceNode = nodeMap.get(edge.source);
    const targetNode = nodeMap.get(edge.target);
    const sourceDef = sourceNode ? registry[sourceNode.module_key] : null;
    const targetDef = targetNode ? registry[targetNode.module_key] : null;
    if (!sourceDef || !targetDef) return null;
    return {
      edge,
      sourceNode,
      targetNode,
      sourceDef,
      targetDef,
      sourceFields: Array.isArray(sourceDef.output_fields) ? sourceDef.output_fields : [],
      requiredFields: Array.isArray(targetDef.required_input_fields) ? targetDef.required_input_fields : [],
      fieldMap: getEdgeFieldMap(design, edgeId),
    };
  }

  function suggestEdgeFieldMap(design, registry, edgeId) {
    const context = getEdgeFieldMappingContext(design, registry, edgeId);
    if (!context) return getEdgeFieldMap(design, edgeId);
    return suggestFieldMap(context.sourceFields, context.requiredFields, context.fieldMap);
  }

  function validateEdgeMissingFields(design, registry, edgeId) {
    const context = getEdgeFieldMappingContext(design, registry, edgeId);
    if (!context) return [];
    return validateMissingFields(context.sourceFields, context.requiredFields, context.fieldMap);
  }

  function detectInterfaceGaps(design, registry) {
    const nodeMap = getNodeMap(design);
    const gaps = [];

    for (const edge of design.edges) {
      const sourceNode = nodeMap.get(edge.source);
      const targetNode = nodeMap.get(edge.target);
      if (!sourceNode || !targetNode) continue;
      const sourceDef = registry[sourceNode.module_key];
      const targetDef = registry[targetNode.module_key];
      if (!sourceDef || !targetDef) continue;

      const mapping = edge.mapping && typeof edge.mapping === "object" ? edge.mapping : {};

      if (sourceDef.cardinality !== targetDef.cardinality && !mapping.count_rule) {
        gaps.push({
          edge_id: edge.id,
          type: "count_mismatch",
          source: sourceNode.title,
          target: targetNode.title,
          message: `数量不匹配: ${sourceDef.cardinality} -> ${targetDef.cardinality}`,
        });
      }

      const missing = validateEdgeMissingFields(design, registry, edge.id);
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
      mapping.field_map = suggestEdgeFieldMap(next, registry, edge.id);
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

  function severityRank(level) {
    if (level === "high") return 3;
    if (level === "medium") return 2;
    if (level === "low") return 1;
    return 0;
  }

  function mergeSeverity(current, next) {
    return severityRank(next) > severityRank(current) ? next : current;
  }

  function isEmptyDefaultValue(value) {
    if (value === null || value === undefined) return true;
    return String(value).trim() === "";
  }

  function toDefaultCompareKey(value) {
    if (value === undefined) return "__undefined__";
    return JSON.stringify(value);
  }

  function createHighlightRecord() {
    return { severity: "none", conflict_ids: [] };
  }

  function addConflictId(record, conflictId, severity) {
    record.severity = mergeSeverity(record.severity, severity);
    if (!record.conflict_ids.includes(conflictId)) {
      record.conflict_ids.push(conflictId);
    }
  }

  function analyzeFieldMapConflicts(fieldMap) {
    const normalized = normalizeFieldMap(fieldMap);
    const conflicts = [];
    const byIndex = normalized.map(() => createHighlightRecord());
    const byTarget = {};
    const bySource = {};
    const targetEntriesMap = new Map();
    const sourceEntriesMap = new Map();
    let maxSeverity = "none";
    let seq = 0;

    normalized.forEach((entry, index) => {
      if (entry.to) {
        if (!targetEntriesMap.has(entry.to)) targetEntriesMap.set(entry.to, []);
        targetEntriesMap.get(entry.to).push({ index, entry });
      }
      if (entry.from) {
        if (!sourceEntriesMap.has(entry.from)) sourceEntriesMap.set(entry.from, []);
        sourceEntriesMap.get(entry.from).push({ index, entry });
      }
    });

    function ensureTargetHighlight(target) {
      if (!byTarget[target]) byTarget[target] = createHighlightRecord();
      return byTarget[target];
    }

    function ensureSourceHighlight(source) {
      if (!bySource[source]) bySource[source] = createHighlightRecord();
      return bySource[source];
    }

    function registerConflict(conflict) {
      const conflictId = `conflict_${++seq}`;
      const indexes = Array.isArray(conflict.indexes)
        ? Array.from(new Set(conflict.indexes.filter((x) => Number.isInteger(x) && x >= 0)))
        : [];
      const item = {
        id: conflictId,
        type: conflict.type,
        severity: conflict.severity || "medium",
        message: conflict.message || "",
        indexes,
      };
      if (conflict.target) item.target = conflict.target;
      if (conflict.source) item.source = conflict.source;
      if (Array.isArray(conflict.sources)) item.sources = conflict.sources;
      if (Array.isArray(conflict.targets)) item.targets = conflict.targets;

      conflicts.push(item);
      maxSeverity = mergeSeverity(maxSeverity, item.severity);

      indexes.forEach((index) => addConflictId(byIndex[index], conflictId, item.severity));
      if (item.target) addConflictId(ensureTargetHighlight(item.target), conflictId, item.severity);
      if (item.source) addConflictId(ensureSourceHighlight(item.source), conflictId, item.severity);
    }

    targetEntriesMap.forEach((entries, target) => {
      const uniqueSources = Array.from(new Set(entries.map((x) => x.entry.from).filter(Boolean)));
      if (uniqueSources.length > 1) {
        registerConflict({
          type: "target_multi_source_conflict",
          severity: "high",
          target,
          sources: uniqueSources,
          indexes: entries.map((x) => x.index),
          message: `目标字段 ${target} 存在多个来源映射: ${uniqueSources.join(", ")}`,
        });
      }
    });

    sourceEntriesMap.forEach((entries, source) => {
      if (entries.length > 1) {
        const uniqueTargets = Array.from(new Set(entries.map((x) => x.entry.to).filter(Boolean)));
        registerConflict({
          type: "source_duplicate_mapping",
          severity: uniqueTargets.length > 1 ? "high" : "medium",
          source,
          targets: uniqueTargets,
          indexes: entries.map((x) => x.index),
          message: `来源字段 ${source} 被重复映射到目标字段: ${uniqueTargets.join(", ")}`,
        });
      }
    });

    targetEntriesMap.forEach((entries, target) => {
      const sourceIndexes = entries.filter((x) => x.entry.from).map((x) => x.index);
      const defaultEntries = entries.filter((x) => !isEmptyDefaultValue(x.entry.default));

      if (sourceIndexes.length && defaultEntries.length) {
        registerConflict({
          type: "default_override_conflict",
          severity: "medium",
          target,
          indexes: entries.map((x) => x.index),
          message: `目标字段 ${target} 同时存在来源映射和默认值，默认值可能覆盖来源数据`,
        });
      }

      const defaultValues = Array.from(
        new Set(defaultEntries.map((x) => toDefaultCompareKey(x.entry.default)))
      );
      if (defaultValues.length > 1) {
        registerConflict({
          type: "default_value_conflict",
          severity: "high",
          target,
          indexes: defaultEntries.map((x) => x.index),
          message: `目标字段 ${target} 存在多个不同默认值`,
        });
      }
    });

    return {
      severity: maxSeverity,
      conflicts,
      highlight: {
        by_index: byIndex,
        by_target: byTarget,
        by_source: bySource,
      },
      field_map: normalized,
    };
  }

  function getEdgeFieldMapConflictModel(design, edgeId) {
    const edge = getEdgeById(design, edgeId);
    if (!edge) {
      return {
        edge_id: edgeId,
        severity: "none",
        conflicts: [],
        highlight: {
          by_index: [],
          by_target: {},
          by_source: {},
        },
        field_map: [],
      };
    }
    const model = analyzeFieldMapConflicts(getEdgeFieldMap(design, edgeId));
    return {
      edge_id: edge.id,
      severity: model.severity,
      conflicts: model.conflicts,
      highlight: model.highlight,
      field_map: model.field_map,
    };
  }

  function queryEdgeConflicts(design, edgeId) {
    const model = getEdgeFieldMapConflictModel(design, edgeId);
    return {
      edge_id: model.edge_id,
      severity: model.severity,
      conflicts: model.conflicts,
    };
  }

  window.WorkflowDesignerMapping = {
    detectInterfaceGaps,
    quickFixGap,
    promoteEdgeToAdapter,
    collectEdgeMappings,
    collectAdapterNodes,
    normalizeFieldMap,
    getEdgeFieldMap,
    setEdgeFieldMap,
    suggestFieldMap,
    validateMissingFields,
    suggestEdgeFieldMap,
    validateEdgeMissingFields,
    analyzeFieldMapConflicts,
    getEdgeFieldMapConflictModel,
    queryEdgeConflicts,
  };
})();
