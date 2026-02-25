(function () {
  function qs(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value ?? "");
    return div.innerHTML;
  }

  function formatNumber(value) {
    if (value === null || value === undefined || value === "") return "-";
    const num = Number(value);
    if (!Number.isFinite(num)) return escapeHtml(value);
    return new Intl.NumberFormat("zh-CN").format(num);
  }

  function setStatus(id, message, kind) {
    const el = qs(id);
    if (!el) return;
    const statusKind = kind || "loading";
    const icons = {
      loading: "refresh-cw",
      error: "alert-circle",
      success: "check-circle-2",
    };
    const iconName = icons[statusKind] || "info";
    el.className = `status ${statusKind}`;
    el.innerHTML = `<i data-lucide="${iconName}" class="status-icon"></i> <span>${escapeHtml(message)}</span>`;
    if (window.lucide) {
      window.lucide.createIcons({
        attrs: {
          class: ["lucide-icon"],
        },
        nameAttr: "data-lucide",
      });
    }
  }

  function setLoading(id, message) {
    setStatus(id, message || "加载中...", "loading");
  }

  function setError(id, message) {
    setStatus(id, message || "请求失败", "error");
  }

  function setSuccess(id, message) {
    setStatus(id, message || "操作成功", "success");
  }

  function setEmpty(id, message) {
    const el = qs(id);
    if (!el) return;
    el.className = "empty";
    el.innerHTML = escapeHtml(message || "暂无数据");
  }

  function toggleDisabled(ids, disabled) {
    (ids || []).forEach((id) => {
      const el = qs(id);
      if (el) el.disabled = !!disabled;
    });
  }

  function toDateTime(isoValue) {
    if (!isoValue) return "-";
    try {
      return new Date(isoValue).toLocaleString("zh-CN");
    } catch {
      return String(isoValue);
    }
  }

  // 自动初始化图标
  function initIcons() {
    if (window.lucide) {
      window.lucide.createIcons();
    } else {
      // 如果 lucide 还没加载，等一下
      setTimeout(initIcons, 100);
    }
  }

  window.addEventListener("DOMContentLoaded", initIcons);

  window.UICore = {
    qs,
    escapeHtml,
    formatNumber,
    setLoading,
    setError,
    setSuccess,
    setEmpty,
    toggleDisabled,
    toDateTime,
  };
})();
