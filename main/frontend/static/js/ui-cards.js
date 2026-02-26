(function () {
  'use strict';

  function esc(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  function renderChips(items, opts) {
    const list = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!list.length) return (opts && opts.emptyHtml) || '';
    const cls = (opts && opts.className) || 'chip';
    return list.map((item) => `<span class="${cls}">${esc(item)}</span>`).join('');
  }

  function renderInfoGrid(items) {
    const rows = Array.isArray(items) ? items : [];
    return `<div class="info-grid">${
      rows.map((it) => `<div class="info-item"><label>${esc(it.label || '-')}</label><div class="value">${it.html != null ? it.html : esc(it.value ?? '-')}</div></div>`).join('')
    }</div>`;
  }

  function renderList(items, opts) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return `<div style="color:#64748b;">${esc((opts && opts.emptyText) || '无')}</div>`;
    const itemHtml = list.map((it) => `<li>${it && it.html != null ? it.html : esc(it)}</li>`).join('');
    return `<ul style="margin:0;padding-left:18px;">${itemHtml}</ul>`;
  }

  function renderSectionCard(section) {
    const title = section?.title ? `<div style="font-weight:700;color:#0f172a;margin-bottom:10px;">${esc(section.title)}</div>` : '';
    const blocks = [];
    if (section?.metrics && section.metrics.length) blocks.push(renderInfoGrid(section.metrics));
    if (section?.chipGroups) {
      for (const group of section.chipGroups) {
        blocks.push(
          `<div style="margin-top:12px;"><label style="display:block;color:#64748b;font-size:12px;margin-bottom:6px;">${esc(group.label || '')}</label><div style="display:flex;flex-wrap:wrap;gap:6px;">${renderChips(group.items, { emptyHtml: '<span style=\"color:#64748b;\">无</span>' })}</div></div>`
        );
      }
    }
    if (section?.lists) {
      for (const group of section.lists) {
        blocks.push(
          `<div style="margin-top:12px;"><label style="display:block;color:#64748b;font-size:12px;margin-bottom:6px;">${esc(group.label || '')}</label>${renderList(group.items, { emptyText: group.emptyText || '无' })}</div>`
        );
      }
    }
    return `<div class="extracted-card" style="${section?.compact ? '' : 'margin-top:12px;'}${section?.style || ''}">${title}${blocks.join('')}</div>`;
  }

  window.UICards = {
    esc,
    renderChips,
    renderInfoGrid,
    renderList,
    renderSectionCard,
  };
})();

