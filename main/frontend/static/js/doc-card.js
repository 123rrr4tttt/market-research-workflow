/**
 * Shared document card renderer - same as graph page (social-media-graph) post modal.
 * Used by: admin, data-dashboard, social-media-visualization, social-media-graph.
 */
(function () {
  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  function renderGraphExtractedCard(extractedData, optEscape, labels) {
    const extracted = extractedData && typeof extractedData === "object" ? extractedData : {};
    if (Object.keys(extracted).length === 0) return "";
    const esc = optEscape || escapeHtml;
    const nodeL = (labels?.nodeLabels || labels?.node_labels || {});
    const fieldL = (labels?.fieldLabels || labels?.field_labels || {});
    const L = {
      node: (key, d) => nodeL[key] || d,
      field: (key, d) => fieldL[key] || nodeL[key.charAt(0).toUpperCase() + key.slice(1)] || d,
    };
    const sentiment = extracted.sentiment || {};

    // entities: top-level or from entities_relations
    const entRel = extracted.entities_relations || {};
    const entList = Array.isArray(extracted.entities)
      ? extracted.entities
      : Array.isArray(entRel.entities)
        ? entRel.entities
        : Array.isArray(entRel.nodes)
          ? entRel.nodes
          : [];
    const keywords = Array.isArray(extracted.keywords)
      ? extracted.keywords
      : Array.isArray(sentiment.keywords)
        ? sentiment.keywords
        : [];

    let html = '<div class="extracted-card">';

    // Platform info
    if (
      extracted.platform ||
      extracted.username ||
      extracted.subreddit ||
      extracted.likes !== undefined ||
      extracted.comments !== undefined
    ) {
      html += `<div class="extracted-section"><h3>📱 ${L.field("platform", "平台")}信息</h3><div class="info-grid">`;
      if (extracted.platform) html += `<div class="info-item"><label>${L.field("platform", "平台")}</label><div class="value">${esc(extracted.platform)}</div></div>`;
      if (extracted.username) html += `<div class="info-item"><label>用户名</label><div class="value">${esc(extracted.username)}</div></div>`;
      if (extracted.subreddit) html += `<div class="info-item"><label>Subreddit</label><div class="value">r/${esc(extracted.subreddit)}</div></div>`;
      if (extracted.likes !== undefined && extracted.likes !== null) html += `<div class="info-item"><label>点赞数</label><div class="value">${extracted.likes}</div></div>`;
      if (extracted.comments !== undefined && extracted.comments !== null) html += `<div class="info-item"><label>评论数</label><div class="value">${extracted.comments}</div></div>`;
      html += "</div></div>";
    }

    // Topic (graph node)
    const topic = sentiment.topic || extracted.topic || "";
    if (topic) {
      html += `<div class="extracted-section"><h3>🎯 ${L.node("Topic", "主题")}（图谱节点）</h3>`;
      html += `<div class="info-item" style="background:#eff6ff;border-color:#3b82f6;"><label>${L.node("Topic", "主题")}</label><div class="value" style="font-size:16px;color:#1e40af;font-weight:600;">${esc(topic)}</div></div>`;
      html += "</div>";
    }

    // Keywords (graph node)
    if (keywords.length > 0) {
      html += `<div class="extracted-section"><h3>🔑 ${L.node("Keyword", "关键词")}（图谱节点）</h3><div class="tag-list">`;
      keywords.forEach((kw) => {
        html += `<span class="tag-item" style="background:#dbeafe;color:#1e40af;border-color:#93c5fd;">${esc(String(kw))}</span>`;
      });
      html += "</div></div>";
    }

    // Entities (graph node)
    if (entList.length > 0) {
      html += `<div class="extracted-section"><h3>🏷️ ${L.node("Entity", "实体")}（图谱节点）</h3><div class="tag-list">`;
      entList.forEach((e) => {
        const name = (e.canonical_name || e.text || e.name || "").trim();
        const typ = e.type || "UNKNOWN";
        if (name) html += `<span class="tag-item" style="background:#dcfce7;color:#166534;border-color:#86efac;" title="类型:${esc(typ)}">${esc(name)}</span>`;
      });
      html += "</div></div>";
    }

    // Sentiment
    const sentTags = sentiment.sentiment_tags || [];
    const keyPhrases = sentiment.key_phrases || [];
    const emotionWords = sentiment.emotion_words || [];
    if (
      sentiment.sentiment_orientation ||
      sentTags.length > 0 ||
      keyPhrases.length > 0 ||
      emotionWords.length > 0
    ) {
      html += '<div class="extracted-section"><h3>💬 情感分析</h3><div class="info-grid">';
      if (sentiment.sentiment_orientation) {
        const o = sentiment.sentiment_orientation;
        const labelMap = { positive: "正面", negative: "负面", neutral: "中性" };
        html += `<div class="info-item"><label>情感倾向</label><div class="value"><span class="badge ${o}">${labelMap[o] || o}</span></div></div>`;
      }
      html += "</div>";
      if (sentTags.length > 0) {
        html += `<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">${L.node("SentimentTag", "情感标签")}（图谱节点）</label><div class="tag-list">`;
        sentTags.forEach((t) => (html += `<span class="tag-item" style="background:#fce7f3;color:#9f1239;border-color:#f9a8d4;">${esc(t)}</span>`));
        html += "</div></div>";
      }
      if (keyPhrases.length > 0) {
        html += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">关键短语</label><div class="tag-list">';
        keyPhrases.forEach((p) => (html += `<span class="tag-item">${esc(p)}</span>`));
        html += "</div></div>";
      }
      if (emotionWords.length > 0) {
        html += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">情感词汇</label><div class="tag-list">';
        emotionWords.forEach((w) => (html += `<span class="tag-item">${esc(w)}</span>`));
        html += "</div></div>";
      }
      html += "</div>";
    }

    // Market (for market docs)
    if (extracted.market && Object.keys(extracted.market).length > 0) {
      const m = extracted.market;
      html += `<div class="extracted-section"><h3>📊 ${L.node("MarketData", "市场数据")}</h3><div class="info-grid">`;
      if (m.state) html += `<div class="info-item"><label>${L.field("state", "州")}</label><div class="value">${esc(m.state)}</div></div>`;
      if (m.game) html += `<div class="info-item"><label>${L.field("game", "游戏")}</label><div class="value">${esc(m.game)}</div></div>`;
      if (m.segment && !m.game) html += `<div class="info-item"><label>${L.field("segment", "品类")}</label><div class="value">${esc(m.segment)}</div></div>`;
      if (m.sales_volume != null) html += `<div class="info-item"><label>${L.field("sales_volume", "销售额")}</label><div class="value">$${Number(m.sales_volume).toLocaleString()}</div></div>`;
      if (m.revenue != null) html += `<div class="info-item"><label>${L.field("revenue", "收入")}</label><div class="value">$${Number(m.revenue).toLocaleString()}</div></div>`;
      html += "</div></div>";
    }

    // Policy (for policy docs)
    if (extracted.policy && Object.keys(extracted.policy).length > 0) {
      const p = extracted.policy;
      html += `<div class="extracted-section"><h3>📜 ${L.node("Policy", "政策")}信息</h3><div class="info-grid">`;
      if (p.title) html += `<div class="info-item"><label>${L.field("title", "标题")}</label><div class="value">${esc(p.title)}</div></div>`;
      if (p.state) html += `<div class="info-item"><label>${L.field("state", "州")}</label><div class="value">${esc(p.state)}</div></div>`;
      if (p.status) html += `<div class="info-item"><label>${L.field("status", "状态")}</label><div class="value">${esc(p.status)}</div></div>`;
      html += "</div></div>";
    }

    // Entity relations (for policy/market)
    const relList = Array.isArray(entRel.relations)
      ? entRel.relations
      : Array.isArray(entRel.edges)
        ? entRel.edges
        : [];
    // Graph edges/nodes (generic graph payload)
    const graph = extracted.graph || extracted.graph_data || {};
    const graphEdges =
      (Array.isArray(graph.edges) && graph.edges) ||
      (Array.isArray(extracted.graph_edges) && extracted.graph_edges) ||
      (Array.isArray(extracted.edges) && extracted.edges) ||
      [];
    const graphNodes =
      (Array.isArray(graph.nodes) && graph.nodes) ||
      (Array.isArray(extracted.graph_nodes) && extracted.graph_nodes) ||
      (Array.isArray(extracted.nodes) && extracted.nodes) ||
      [];
    if (relList.length > 0) {
      html += '<div class="extracted-section"><h3>🔗 实体关系</h3><div class="relation-list">';
      relList.forEach((r) => {
        const subj = r.subject || r.subject_text || "";
        const pred = r.predicate || "";
        const obj = r.object || r.object_text || "";
        if (subj || pred || obj) html += `<div class="relation-item">${esc(subj)} <strong>${esc(pred)}</strong> ${esc(obj)}</div>`;
      });
      html += "</div></div>";
    }

    // Generic graph nodes/edges
    if (graphNodes.length > 0 || graphEdges.length > 0) {
      html += '<div class="extracted-section"><h3>🕸️ 图谱</h3>';
      if (graphNodes.length > 0) {
        html += '<div style="margin-bottom:8px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">节点</label><div class="tag-list">';
        graphNodes.slice(0, 60).forEach((n) => {
          const name = n.label || n.name || n.id || "";
          const typ = n.type || n.kind || "";
          html += `<span class="tag-item" style="background:#eef2ff;color:#312e81;border-color:#c7d2fe;" title="${esc(typ)}">${esc(String(name))}</span>`;
        });
        if (graphNodes.length > 60) html += `<span class="tag-item" style="background:#f1f5f9;color:#475569;">+${graphNodes.length - 60}</span>`;
        html += "</div></div>";
      }
      if (graphEdges.length > 0) {
        html += '<div><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">边</label><div class="relation-list">';
        graphEdges.slice(0, 60).forEach((e) => {
          const src = e.source || e.src || e.from || "";
          const tgt = e.target || e.tgt || e.to || "";
          const rel = e.label || e.relation || e.pred || "";
          html += `<div class="relation-item">${esc(src)} <strong>${esc(rel || "→")}</strong> ${esc(tgt)}</div>`;
        });
        if (graphEdges.length > 60) html += `<div class="relation-item muted">... 还有 ${graphEdges.length - 60} 条</div>`;
        html += "</div></div>";
      }
      html += "</div>";
    }

    html += "</div>";
    return html;
  }

  window.renderGraphExtractedCard = renderGraphExtractedCard;
})();
