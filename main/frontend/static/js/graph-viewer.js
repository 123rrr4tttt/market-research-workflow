/**
 * Unified graph viewer - shared logic for policy, social, market graphs.
 * Config-driven: API path, filters, node colors/symbols, tooltip/click handlers.
 */
(function () {
  'use strict';

  const NODE_COLORS_BY_TYPE = {
    policy: { Policy: '#2563eb', State: '#f59e0b', PolicyType: '#10b981', KeyPoint: '#ec4899', Entity: '#8b5cf6' },
    social: { Post: '#2563eb', Keyword: '#10b981', Entity: '#f59e0b', Topic: '#8b5cf6', SentimentTag: '#ec4899', User: '#64748b', Subreddit: '#14b8a6' },
    market: { MarketData: '#2563eb', State: '#f59e0b', Segment: '#10b981', Game: '#10b981', Entity: '#8b5cf6' }
  };

  const NODE_SYMBOLS_BY_TYPE = {
    policy: { Policy: 'circle', State: 'rect', PolicyType: 'diamond', KeyPoint: 'roundRect', Entity: 'triangle' },
    social: { Post: 'circle', Keyword: 'diamond', Entity: 'rect', Topic: 'triangle', SentimentTag: 'pin', User: 'roundRect', Subreddit: 'arrow' },
    market: { MarketData: 'circle', State: 'rect', Segment: 'diamond', Game: 'diamond', Entity: 'triangle' }
  };

  const API_PATHS = {
    policy: '/api/v1/admin/policy-graph',
    social: '/api/v1/admin/content-graph',
    market: '/api/v1/admin/market-graph'
  };

  const GRAPH_CONFIG_KEYS = {
    policy: { docTypes: 'policy', nodeTypes: 'policy', edgeTypes: 'policy', label: 'policy' },
    social: { docTypes: 'social', nodeTypes: 'social', edgeTypes: 'social', label: 'social' },
    market: { docTypes: 'market', nodeTypes: 'market', edgeTypes: 'market', label: 'market' }
  };

  function nodeKey(node) {
    return `${node.type}:${node.id}`;
  }

  function nodeKeyFromEdge(ep) {
    return `${ep.type}:${ep.id}`;
  }

  function formatLabelText(node, maxLen) {
    const text = node.title || node.name || node.text || node.canonical_name || `节点 ${node.id}`;
    const len = maxLen || (node.type === 'KeyPoint' ? 20 : 24);
    return text.length > len ? `${String(text).slice(0, len)}…` : text;
  }

  function computeNodeSizes(nodes, edges) {
    const degreeMap = new Map();
    edges.forEach(edge => {
      const fromKey = nodeKeyFromEdge(edge.from);
      const toKey = nodeKeyFromEdge(edge.to);
      degreeMap.set(fromKey, (degreeMap.get(fromKey) || 0) + 1);
      degreeMap.set(toKey, (degreeMap.get(toKey) || 0) + 1);
    });
    let minDegree = Infinity, maxDegree = 0;
    nodes.forEach(node => {
      const key = nodeKey(node);
      const deg = degreeMap.get(key) || 0;
      if (deg < minDegree) minDegree = deg;
      if (deg > maxDegree) maxDegree = deg;
    });
    if (minDegree === Infinity) minDegree = 0;
    const degreeRange = Math.max(maxDegree - minDegree, 1);
    return { degreeMap, minDegree, maxDegree, degreeRange };
  }

  function getNodeSize(nodeType, degree, minDegree, degreeRange, rules) {
    const r = rules[nodeType] || { base: 18, max: 38 };
    const normalized = Math.pow(Math.max(degree - minDegree, 0) / degreeRange, 0.5);
    let size = r.base + (r.max - r.base) * normalized;
    if (normalized > 0.7) size = Math.min(r.max, size * (1 + (normalized - 0.7) * 0.4));
    return Math.round(size);
  }

  function buildParams(type, filterValues) {
    const params = new URLSearchParams();
    const projectKey = window.MarketApp?.getProjectKey?.() || '';
    if (projectKey) params.append('project_key', projectKey);
    const limit = Math.min(Math.max(parseInt(filterValues.limit, 10) || 100, 1), 500);
    params.append('limit', String(limit));
    if (filterValues.start_date) params.append('start_date', filterValues.start_date);
    if (filterValues.end_date) params.append('end_date', filterValues.end_date);
    if (type === 'policy') {
      if (filterValues.state) params.append('state', filterValues.state);
      if (filterValues.policy_type) params.append('policy_type', filterValues.policy_type);
    } else if (type === 'social') {
      if (filterValues.platform) params.append('platform', filterValues.platform);
      if (filterValues.topic) params.append('topic', filterValues.topic);
    } else if (type === 'market') {
      if (filterValues.state) params.append('state', filterValues.state);
      if (filterValues.game) params.append('game', filterValues.game);
    }
    return params;
  }

  function transformGraphData(nodes, edges, config) {
    const { nodeColors, nodeSymbols, nodeSizeRules, showLabels } = config;
    const { degreeMap, minDegree, degreeRange } = computeNodeSizes(nodes, edges);

    const echartsNodes = nodes.map(node => {
      const key = nodeKey(node);
      const degree = degreeMap.get(key) || 0;
      const size = getNodeSize(node.type, degree, minDegree, degreeRange, nodeSizeRules);
      const shouldShowLabel = showLabels && size >= 22;
        return {
          id: key,
          name: node.title || node.name || node.text || node.id,
          value: node,  // raw node for click handler
        symbol: nodeSymbols[node.type] || 'circle',
        symbolSize: size,
        itemStyle: { color: nodeColors[node.type] || '#94a3b8' },
        label: {
          show: shouldShowLabel,
          position: 'right',
          formatter: () => formatLabelText(node),
          color: '#1e293b',
          fontSize: 11,
          backgroundColor: shouldShowLabel ? 'rgba(255,255,255,0.85)' : 'transparent',
          padding: shouldShowLabel ? [2, 4] : 0,
          borderRadius: 4
        },
        emphasis: {
          label: {
            show: true,
            color: '#0f172a',
            fontWeight: 600,
            backgroundColor: 'rgba(255,255,255,0.92)',
            padding: [2, 4],
            borderRadius: 4,
            formatter: () => formatLabelText(node)
          }
        }
      };
    });

    const echartsEdges = edges.map(edge => ({
      source: nodeKeyFromEdge(edge.from),
      target: nodeKeyFromEdge(edge.to),
      value: edge,
      lineStyle: {
        width: edge.predicate ? 1.5 : 1,
        color: edge.type === 'POLICY_RELATION' ? '#f97316' : '#cbd5e1',
        curveness: edge.type === 'POLICY_RELATION' ? 0.2 : 0
      },
      label: { show: edge.type === 'POLICY_RELATION', formatter: edge.predicate ? edge.predicate : '' }
    }));

    return { nodes: echartsNodes, edges: echartsEdges };
  }

  function tooltipFormatter(params, _config) {
    if (params.dataType === 'node') {
      const nodeData = params.data.value || {};
      const lines = [`类型: ${nodeData.type}`];
      if (nodeData.title) lines.push(`标题: ${nodeData.title}`);
      if (nodeData.name) lines.push(`名称: ${nodeData.name}`);
      if (nodeData.state) lines.push(`州: ${nodeData.state}`);
      if (nodeData.policy_type) lines.push(`政策类型: ${nodeData.policy_type}`);
      if (nodeData.game) lines.push(`游戏: ${nodeData.game}`);
      if (nodeData.platform) lines.push(`平台: ${nodeData.platform}`);
      if (nodeData.status) lines.push(`状态: ${nodeData.status}`);
      if (nodeData.effective_date) lines.push(`生效日期: ${nodeData.effective_date}`);
      if (nodeData.date) lines.push(`日期: ${nodeData.date}`);
      if (nodeData.revenue != null) lines.push(`收入: ${nodeData.revenue}`);
      if (nodeData.text) lines.push(`内容: ${nodeData.text}`);
      return lines.join('<br/>');
    }
    if (params.dataType === 'edge') {
      const edgeData = params.data.value || {};
      const lines = [`关系: ${edgeData.type}`];
      if (edgeData.predicate) lines.push(`谓词: ${edgeData.predicate}`);
      return lines.join('<br/>');
    }
    return '';
  }

  window.GraphViewer = {
    NODE_COLORS_BY_TYPE,
    NODE_SYMBOLS_BY_TYPE,
    API_PATHS,
    GRAPH_CONFIG_KEYS,
    nodeKey,
    nodeKeyFromEdge,
    formatLabelText,
    computeNodeSizes,
    getNodeSize,
    buildParams,
    transformGraphData,
    tooltipFormatter
  };
})();
