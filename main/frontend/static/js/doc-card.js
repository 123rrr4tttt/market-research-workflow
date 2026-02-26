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
    const U = window.UICards || null;
    const renderInfoGridFromPairs = (pairs) => {
      const rows = (pairs || []).filter(Boolean).map((p) => ({ label: p.label, html: p.html, value: p.value }));
      if (!rows.length) return '<div class="info-grid"></div>';
      return U?.renderInfoGrid ? U.renderInfoGrid(rows) : `<div class="info-grid">${
        rows.map(r => `<div class="info-item"><label>${esc(r.label || '-')}</label><div class="value">${r.html != null ? r.html : esc(r.value ?? '-')}</div></div>`).join('')
      }</div>`;
    };
    const renderTagList = (items, styleHtml) => {
      const vals = (items || []).filter(Boolean);
      if (!vals.length) return '<div class="tag-list"></div>';
      if (U?.renderChips && !styleHtml) return `<div class="tag-list">${U.renderChips(vals.map(v => String(v)), { className: 'tag-item' })}</div>`;
      return `<div class="tag-list">${vals.map(v => styleHtml ? styleHtml(v) : `<span class="tag-item">${esc(String(v))}</span>`).join('')}</div>`;
    };
    const renderRelationList = (items, formatter) => {
      const vals = (items || []).filter(Boolean);
      if (!vals.length) return '<div class="relation-list"></div>';
      return `<div class="relation-list">${vals.map(v => formatter(v)).join('')}</div>`;
    };

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
      html += `<div class="extracted-section"><h3>📱 ${L.field("platform", "平台")}信息</h3>`;
      html += renderInfoGridFromPairs([
        extracted.platform ? { label: L.field("platform", "平台"), value: extracted.platform } : null,
        extracted.username ? { label: "用户名", value: extracted.username } : null,
        extracted.subreddit ? { label: "Subreddit", html: `r/${esc(extracted.subreddit)}` } : null,
        (extracted.likes !== undefined && extracted.likes !== null) ? { label: "点赞数", value: extracted.likes } : null,
        (extracted.comments !== undefined && extracted.comments !== null) ? { label: "评论数", value: extracted.comments } : null,
      ]);
      html += "</div>";
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
      html += `<div class="extracted-section"><h3>🔑 ${L.node("Keyword", "关键词")}（图谱节点）</h3>`;
      html += renderTagList(keywords, (kw) => `<span class="tag-item" style="background:#dbeafe;color:#1e40af;border-color:#93c5fd;">${esc(String(kw))}</span>`);
      html += "</div>";
    }

    // Entities (graph node)
    if (entList.length > 0) {
      html += `<div class="extracted-section"><h3>🏷️ ${L.node("Entity", "实体")}（图谱节点）</h3>`;
      html += renderTagList(entList, (e) => {
        const name = (e.canonical_name || e.text || e.name || "").trim();
        const typ = e.type || "UNKNOWN";
        return name ? `<span class="tag-item" style="background:#dcfce7;color:#166534;border-color:#86efac;" title="类型:${esc(typ)}">${esc(name)}</span>` : '';
      });
      html += "</div>";
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
      html += '<div class="extracted-section"><h3>💬 情感分析</h3>';
      html += renderInfoGridFromPairs([
        sentiment.sentiment_orientation ? {
          label: '情感倾向',
          html: (() => {
            const o = sentiment.sentiment_orientation;
            const labelMap = { positive: "正面", negative: "负面", neutral: "中性" };
            return `<span class="badge ${o}">${labelMap[o] || o}</span>`;
          })()
        } : null,
      ]);
      if (sentTags.length > 0) {
        html += `<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">${L.node("SentimentTag", "情感标签")}（图谱节点）</label>`;
        html += renderTagList(sentTags, (t) => `<span class="tag-item" style="background:#fce7f3;color:#9f1239;border-color:#f9a8d4;">${esc(t)}</span>`);
        html += "</div>";
      }
      if (keyPhrases.length > 0) {
        html += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">关键短语</label>';
        html += renderTagList(keyPhrases);
        html += "</div>";
      }
      if (emotionWords.length > 0) {
        html += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">情感词汇</label>';
        html += renderTagList(emotionWords);
        html += "</div>";
      }
      html += "</div>";
    }

    // Market (for market docs)
    if (extracted.market && Object.keys(extracted.market).length > 0) {
      const m = extracted.market;
      html += `<div class="extracted-section"><h3>📊 ${L.node("MarketData", "市场数据")}</h3>`;
      html += renderInfoGridFromPairs([
        m.state ? { label: L.field("state", "州"), value: m.state } : null,
        m.game ? { label: L.field("game", "游戏"), value: m.game } : null,
        (m.segment && !m.game) ? { label: L.field("segment", "品类"), value: m.segment } : null,
        (m.sales_volume != null) ? { label: L.field("sales_volume", "销售额"), html: `$${Number(m.sales_volume).toLocaleString()}` } : null,
        (m.revenue != null) ? { label: L.field("revenue", "收入"), html: `$${Number(m.revenue).toLocaleString()}` } : null,
      ]);
      html += "</div>";
    }

    // Policy (for policy docs)
    if (extracted.policy && Object.keys(extracted.policy).length > 0) {
      const p = extracted.policy;
      html += `<div class="extracted-section"><h3>📜 ${L.node("Policy", "政策")}信息</h3>`;
      html += renderInfoGridFromPairs([
        p.title ? { label: L.field("title", "标题"), value: p.title } : null,
        p.state ? { label: L.field("state", "州"), value: p.state } : null,
        p.status ? { label: L.field("status", "状态"), value: p.status } : null,
      ]);
      html += "</div>";
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

    function renderTopicStructuredBlock(fieldKey, title, icon) {
      const td = extracted[fieldKey];
      if (!td || typeof td !== 'object') return '';
      const entities = Array.isArray(td.entities) ? td.entities : [];
      const relations = Array.isArray(td.relations) ? td.relations : [];
      const facts = Array.isArray(td.facts) ? td.facts : [];
      const topics2 = Array.isArray(td.topics) ? td.topics : [];
      const signals = td.signals && typeof td.signals === 'object' ? td.signals : {};
      const confidence = Number(td.confidence || 0);
      const sourceExcerpt = String(td.source_excerpt || '');
      const hasAny = entities.length || relations.length || facts.length || topics2.length || Object.keys(signals).length;
      if (!hasAny) return '';

      let sec = `<div class="extracted-section"><h3>${icon} ${esc(title)}</h3>`;
      sec += renderInfoGridFromPairs([
        { label: '实体数', value: entities.length },
        { label: '关系数', value: relations.length },
        { label: '事实数', value: facts.length },
        { label: '主题数', value: topics2.length },
        confidence ? { label: '置信度', value: confidence.toFixed(2) } : null,
      ]);

      if (entities.length) {
        sec += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">专题实体</label>';
        sec += renderTagList(
          entities.slice(0, 80),
          (e) => {
            const name = String(e?.text || e?.name || '').trim();
            const typ = String(e?.type || '').trim();
            if (!name) return '';
            return `<span class="tag-item" style="background:#fff7ed;color:#9a3412;border-color:#fdba74;" title="类型:${esc(typ || 'unknown')}">${esc(name)}${typ ? ` · ${esc(typ)}` : ''}</span>`;
          }
        );
        sec += '</div>';
      }
      if (relations.length) {
        sec += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">专题关系</label>';
        sec += renderRelationList(relations.slice(0, 30), (r) => {
          const subj = r.subject || r.subject_text || '';
          const pred = r.predicate || '';
          const obj = r.object || r.object_text || '';
          return (subj || pred || obj) ? `<div class="relation-item">${esc(subj)} <strong>${esc(pred)}</strong> ${esc(obj)}</div>` : '';
        });
        sec += '</div>';
      }
      if (facts.length) {
        sec += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">专题事实</label>';
        sec += renderTagList(
          facts.slice(0, 40),
          (f) => {
            const factType = String(f?.fact_type || 'fact').trim();
            const preview = Object.entries(f || {})
              .filter(([k]) => k !== 'fact_type')
              .slice(0, 2)
              .map(([k, v]) => `${k}:${String(v)}`)
              .join(' | ');
            return `<span class="tag-item" style="background:#eef2ff;color:#312e81;border-color:#c7d2fe;" title="${esc(JSON.stringify(f))}">${esc(factType)}${preview ? ` · ${esc(preview)}` : ''}</span>`;
          }
        );
        sec += '</div>';
      }
      if (topics2.length) {
        sec += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">专题主题</label>';
        sec += renderTagList(topics2, (t) => `<span class="tag-item" style="background:#faf5ff;color:#6b21a8;border-color:#d8b4fe;">${esc(String(t))}</span>`);
        sec += '</div>';
      }
      if (Object.keys(signals).length) {
        sec += '<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">专题信号</label>';
        sec += renderInfoGridFromPairs(Object.entries(signals).slice(0, 12).map(([k, v]) => ({ label: k, value: (typeof v === 'object' ? JSON.stringify(v) : String(v)) })));
        sec += '</div>';
      }
      if (sourceExcerpt) {
        sec += `<div style="margin-top:12px;"><label style="display:block;font-size:12px;color:#6b7280;margin-bottom:6px;font-weight:500;">证据片段</label><div class="content-preview" style="max-height:120px;">${esc(sourceExcerpt)}</div></div>`;
      }
      sec += '</div>';
      return sec;
    }
    if (relList.length > 0) {
      html += '<div class="extracted-section"><h3>🔗 实体关系</h3>';
      html += renderRelationList(relList, (r) => {
        const subj = r.subject || r.subject_text || "";
        const pred = r.predicate || "";
        const obj = r.object || r.object_text || "";
        return (subj || pred || obj) ? `<div class="relation-item">${esc(subj)} <strong>${esc(pred)}</strong> ${esc(obj)}</div>` : '';
      });
      html += "</div>";
    }

    // Topic structured overlays (company / product / operation)
    html += renderTopicStructuredBlock("company_structured", "公司专题结构化", "🏢");
    html += renderTopicStructuredBlock("product_structured", "商品专题结构化", "📦");
    html += renderTopicStructuredBlock("operation_structured", "电商/经营专题结构化", "🛒");

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

  function enhanceExtractedCardTabs(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const cards = Array.from(scope.querySelectorAll('.extracted-card'));
    cards.forEach((card) => {
      if (!card || card.dataset.tabified === '1') return;
      const sections = Array.from(card.querySelectorAll(':scope > .extracted-section'));
      if (!sections.length) return;

      const groups = {
        base: [],
        company: [],
        product: [],
        operation: [],
      };
      const classify = (sec) => {
        const title = (sec.querySelector('h3')?.textContent || '').trim();
        if (title.includes('公司专题结构化')) return 'company';
        if (title.includes('商品专题结构化')) return 'product';
        if (title.includes('电商/经营专题结构化')) return 'operation';
        return 'base';
      };
      sections.forEach((sec) => groups[classify(sec)].push(sec));
      if (!groups.company.length && !groups.product.length && !groups.operation.length) return;

      const tabs = [
        { key: 'base', label: '基础' },
        { key: 'company', label: '公司' },
        { key: 'product', label: '商品' },
        { key: 'operation', label: '电商/经营' },
      ];
      const tabNav = document.createElement('div');
      tabNav.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 12px 0;';

      const panelWrap = document.createElement('div');
      const panelMap = new Map();
      tabs.forEach((tab, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = tab.label;
        btn.dataset.tab = tab.key;
        btn.style.cssText = 'padding:6px 12px;border-radius:8px;border:1px solid #d1d5db;background:#f8fafc;color:#334155;font-size:12px;font-weight:600;cursor:pointer;';
        if (idx === 0) {
          btn.dataset.active = '1';
          btn.style.background = '#2563eb';
          btn.style.color = '#fff';
          btn.style.borderColor = '#2563eb';
        }
        tabNav.appendChild(btn);

        const panel = document.createElement('div');
        panel.dataset.tabPanel = tab.key;
        panel.style.display = idx === 0 ? 'block' : 'none';
        if (groups[tab.key].length) {
          groups[tab.key].forEach((sec) => panel.appendChild(sec));
        } else {
          const empty = document.createElement('div');
          empty.style.cssText = 'color:#64748b;font-size:12px;padding:8px 2px;';
          empty.textContent = `暂无${tab.label}专题结构化数据`;
          panel.appendChild(empty);
        }
        panelWrap.appendChild(panel);
        panelMap.set(tab.key, panel);
      });

      tabNav.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-tab]');
        if (!btn) return;
        const key = btn.dataset.tab;
        tabNav.querySelectorAll('button[data-tab]').forEach((b) => {
          const active = b === btn;
          b.dataset.active = active ? '1' : '0';
          b.style.background = active ? '#2563eb' : '#f8fafc';
          b.style.color = active ? '#fff' : '#334155';
          b.style.borderColor = active ? '#2563eb' : '#d1d5db';
        });
        panelMap.forEach((panel, panelKey) => { panel.style.display = panelKey === key ? 'block' : 'none'; });
      });

      card.prepend(panelWrap);
      card.prepend(tabNav);
      card.dataset.tabified = '1';
    });
  }

  window.renderGraphExtractedCard = renderGraphExtractedCard;
  window.enhanceExtractedCardTabs = enhanceExtractedCardTabs;
})();
