(function () {
  "use strict";

  var API = "/api/v1";
  var TIME_ZONE = "Asia/Shanghai";
  var CATEGORY_OPTIONS = [
    ["HEADQUARTERS_ISSUE", "总行发文"],
    ["RETAIL_ANNOUNCEMENT", "零售条线公告"],
    ["PUBLICATION_RELEASE", "刊物发布"],
    ["BRANCH_ISSUE", "支行发文"],
    ["BRANCH_RECEIVE", "支行收文"],
    ["PUBLIC_STANDARD", "公共发布及规范文件"],
    ["HEADQUARTERS_RECEIVE", "总行收文"],
    ["CORPORATE_ANNOUNCEMENT", "公司条线公告"]
  ];
  var PAGE_TITLES = {
    overview: "总览与每日过程",
    documents: "文档处理",
    approvals: "人工审核",
    cleanup: "清理维护",
    settings: "系统配置"
  };
  var generatedFieldId = 0;
  var STATUS_LABELS = {
    PENDING: "待处理",
    DOWNLOADING: "读取中",
    DECRYPTING: "解密中",
    PARSING: "解析中",
    ANALYZING: "分析中",
    AWAITING_APPROVAL: "待人工审核",
    COMPLETED: "已入库",
    FAILED: "处理失败",
    SKIPPED: "已跳过",
    SUCCESS: "执行成功",
    FAILURE: "执行失败",
    STARTED: "运行中",
    RECEIVED: "已接收",
    RETRY: "等待重试",
    REVOKED: "已撤销",
    RUNNING: "运行中",
    QUEUED: "排队中",
    SUCCESSFUL: "执行成功",
    WARNING: "有异常",
    ERROR: "异常",
    pending: "待审核",
    approved: "已批准",
    rejected: "已拒绝",
    failed: "执行失败",
    deleted: "已清理",
    stale: "文档已变化",
    success: "执行成功",
    started: "运行中",
    received: "已接收",
    retry: "等待重试",
    revoked: "已撤销",
    running: "运行中",
    queued: "排队中",
    warning: "部分异常",
    retrying: "等待重试",
    unavailable: "暂无记录",
    unknown: "状态未知"
  };
  var state = {
    page: "overview",
    date: beijingToday(),
    autoRefresh: true,
    timer: null,
    refreshing: false,
    overview: { daily: null, trend: null, health: null, errors: {}, lastUpdated: null, healthLoadedAt: 0, loading: true },
    documents: { items: [], total: 0, page: 1, pageSize: 20, scope: "day", loading: false, error: "", filters: { q: "", status: "", category: "" } },
    approvals: { items: [], total: 0, details: {}, loading: false, error: "" },
    cleanup: { items: [], total: 0, page: 1, pageSize: 20, status: "", details: {}, loading: false, error: "", task: null },
    settings: { tab: "runtime", config: null, configError: "", configLoading: false, knowledgeBases: [], knowledgeError: "", mappings: [], mappingsError: "", dirty: false, saving: false, loadedConfig: false, loadedKnowledge: false, loadedMappings: false },
    toastTimer: null,
    lastFocus: null
  };

  var els = {};

  function byId(id) { return document.getElementById(id); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function svgEl(tag, attrs) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, String(attrs[key])); });
    return node;
  }

  function iconNode(name, className) {
    var svg = svgEl("svg", { "class": className || "ui-icon", "aria-hidden": "true", focusable: "false" });
    var use = svgEl("use", { href: "/web/icons.svg#" + name });
    svg.appendChild(use);
    return svg;
  }

  function add(parent) {
    for (var i = 1; i < arguments.length; i += 1) {
      if (arguments[i]) parent.appendChild(arguments[i]);
    }
    return parent;
  }

  function button(label, action, className, dataset) {
    var node = el("button", "button" + (className ? " " + className : ""), label);
    node.type = "button";
    node.dataset.action = action;
    Object.keys(dataset || {}).forEach(function (key) { node.dataset[key] = String(dataset[key]); });
    return node;
  }

  function beijingToday() {
    var parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(new Date());
    var values = {};
    parts.forEach(function (part) { values[part.type] = part.value; });
    return values.year + "-" + values.month + "-" + values.day;
  }

  function formatDate(value) {
    if (!value) return "—";
    var date = new Date(value.length === 10 ? value + "T00:00:00+08:00" : value);
    if (isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  }

  function formatTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", { timeZone: TIME_ZONE, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  }

  function prettyNumber(value) {
    if (value === null || value === undefined || value === "") return "—";
    var number = Number(value);
    if (!isFinite(number)) return String(value);
    return new Intl.NumberFormat("zh-CN").format(number);
  }

  function categoryLabel(value) {
    var found = CATEGORY_OPTIONS.filter(function (item) { return item[0] === value; })[0];
    return found ? found[1] : (value || "未分类");
  }

  function statusLabel(value, fallback) {
    var key = value === undefined || value === null ? "" : String(value);
    return STATUS_LABELS[key] || STATUS_LABELS[key.toLowerCase()] || fallback || key || "未知状态";
  }

  function statusTone(value) {
    var key = String(value || "").toLowerCase();
    if (["completed", "success", "succeeded", "deleted", "approved"].indexOf(key) >= 0) return "success";
    if (["failed", "error", "rejected", "stale"].indexOf(key) >= 0) return "danger";
    if (["pending", "awaiting_approval", "started", "received", "retry"].indexOf(key) >= 0) return "warning";
    if (["running", "active", "processing", "progress", "queued"].indexOf(key) >= 0) return "info";
    return "";
  }

  function statusPill(label, value) {
    return el("span", "status-pill" + (statusTone(value) ? " " + statusTone(value) : ""), label || statusLabel(value));
  }

  function createField(labelText, control, help, className) {
    var wrap = el("div", "field" + (className ? " " + className : ""));
    var label = el("label", "", labelText);
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(control.tagName)) {
      if (!control.id) {
        generatedFieldId += 1;
        control.id = "workbench-field-" + generatedFieldId;
      }
      label.htmlFor = control.id;
    }
    add(wrap, label, control);
    if (help) wrap.appendChild(el("p", "field-help", help));
    return wrap;
  }

  function textInput(value, placeholder, type) {
    var input = el("input");
    input.type = type || "text";
    input.value = value === undefined || value === null ? "" : String(value);
    if (placeholder) input.placeholder = placeholder;
    return input;
  }

  function textarea(value, placeholder) {
    var input = el("textarea");
    input.value = value === undefined || value === null ? "" : String(value);
    if (placeholder) input.placeholder = placeholder;
    return input;
  }

  function selectControl(options, selected, placeholder) {
    var select = el("select");
    if (placeholder) {
      var blank = el("option", "", placeholder);
      blank.value = "";
      select.appendChild(blank);
    }
    options.forEach(function (option) {
      var entry = el("option", "", option.label);
      entry.value = String(option.value);
      if (String(option.value) === String(selected === undefined || selected === null ? "" : selected)) entry.selected = true;
      select.appendChild(entry);
    });
    return select;
  }

  function emptyState(title, description, type, retryAction) {
    var wrap = el("div", type === "error" ? "error-state" : (type === "loading" ? "loading-state" : "empty-state"));
    if (type === "loading") wrap.appendChild(el("span", "spinner"));
    wrap.appendChild(el("strong", "", title));
    if (description) wrap.appendChild(el("p", "", description));
    if (retryAction) wrap.appendChild(button("重试", retryAction, "button-small", {}));
    return wrap;
  }

  function pageHeading(title, description, actions) {
    var head = el("div", "page-heading");
    var copy = el("div");
    add(copy, el("h1", "", title), el("p", "", description));
    add(head, copy, actions || null);
    return head;
  }

  function panel(title, description, body, actions) {
    var wrap = el("section", "panel");
    var header = el("header", "panel-header");
    var copy = el("div");
    add(copy, el("h2", "", title));
    if (description) copy.appendChild(el("p", "", description));
    add(header, copy, actions || null);
    add(wrap, header, body);
    return wrap;
  }

  function safeError(error) {
    var message = error && error.message ? String(error.message) : "请求失败，请稍后重试。";
    var secretValues = [];
    document.querySelectorAll("[data-secret='true'], [data-kb-key='api_key'], #new-kb-key").forEach(function (input) {
      if (input.value) secretValues.push(input.value);
    });
    secretValues.forEach(function (secret) {
      if (secret && message.indexOf(secret) >= 0) message = message.split(secret).join("[敏感值已隐藏]");
    });
    return message;
  }

  function findByDataValue(attribute, value, root) {
    var scope = root || document;
    var matches = scope.querySelectorAll("[" + attribute + "]");
    for (var i = 0; i < matches.length; i += 1) {
      if (matches[i].getAttribute(attribute) === String(value)) return matches[i];
    }
    return null;
  }

  function apiErrorMessage(response, payload) {
    var message = "";
    if (payload && typeof payload === "object") {
      message = payload.detail || payload.message || payload.error || "";
      if (typeof message !== "string") message = "";
    }
    if (response.status === 409) return message || "配置版本已变化，请重新载入后再保存。";
    if (response.status === 422) return message || "提交内容不符合要求，请检查后重试。";
    return message || ("服务请求失败（HTTP " + response.status + "）。");
  }

  async function request(path, options) {
    var init = Object.assign({ method: "GET", headers: { "Accept": "application/json" } }, options || {});
    if (init.body && typeof init.body !== "string") {
      init.headers = Object.assign({}, init.headers || {}, { "Content-Type": "application/json" });
      init.body = JSON.stringify(init.body);
    }
    var response;
    try {
      response = await fetch(API + path, init);
    } catch (error) {
      throw new Error("无法连接工作台接口。请检查服务是否启动，再重试。");
    }
    var contentType = response.headers.get("content-type") || "";
    var payload = null;
    if (contentType.indexOf("application/json") >= 0) {
      try { payload = await response.json(); } catch (error) { payload = null; }
    } else if (!response.ok) {
      try { payload = { detail: await response.text() }; } catch (error) { payload = null; }
    }
    if (!response.ok) {
      var apiError = new Error(apiErrorMessage(response, payload));
      apiError.status = response.status;
      throw apiError;
    }
    return payload;
  }

  function toast(message, tone) {
    var region = els.toastRegion;
    var item = el("div", "toast" + (tone ? " " + tone : ""), message);
    region.appendChild(item);
    window.setTimeout(function () { if (item.parentNode) item.parentNode.removeChild(item); }, 4500);
  }

  function setGlobalDate(value) {
    var nextDate = value || beijingToday();
    if (nextDate !== state.date) {
      state.overview.daily = null;
      state.overview.errors.daily = "";
      state.documents.items = [];
      state.documents.page = 1;
    }
    state.date = nextDate;
    if (state.page === "overview") loadOverview(false);
    else if (state.page === "documents") loadDocuments(false);
  }

  function setPage(page) {
    if (!PAGE_TITLES[page]) return;
    state.page = page;
    document.querySelectorAll(".nav-item[data-page]").forEach(function (item) {
      item.classList.toggle("is-active", item.dataset.page === page);
      item.setAttribute("aria-current", item.dataset.page === page ? "page" : "false");
    });
    els.pageTitle.textContent = PAGE_TITLES[page];
    els.globalDate.closest(".date-control").hidden = page !== "overview" && page !== "documents";
    els.sidebar.classList.remove("is-open");
    els.mobileMenu.setAttribute("aria-expanded", "false");
    renderPage();
    if (page === "overview") loadOverview(false);
    if (page === "documents") loadDocuments(false);
    if (page === "approvals") loadApprovals(false);
    if (page === "cleanup") loadCleanup(false);
    if (page === "settings") loadSettings(false);
  }

  function renderPage() {
    if (state.page === "overview") renderOverview();
    else if (state.page === "documents") renderDocuments();
    else if (state.page === "approvals") renderApprovals();
    else if (state.page === "cleanup") renderCleanup();
    else renderSettings();
  }

  function refreshCurrent(manual) {
    if (state.refreshing) return;
    if (state.page === "settings" && state.settings.dirty) return;
    state.refreshing = true;
    var promise;
    if (state.page === "overview") promise = loadOverview(!!manual);
    else if (state.page === "documents") {
      if (isEditingFilter()) { state.refreshing = false; return; }
      promise = loadDocuments(!!manual);
    } else if (state.page === "approvals") promise = loadApprovals(!!manual);
    else if (state.page === "cleanup") promise = loadCleanup(!!manual);
    else promise = loadSettings(!!manual);
    Promise.resolve(promise).finally(function () { state.refreshing = false; });
  }

  function isEditingFilter() {
    var active = document.activeElement;
    return active && active.closest && active.closest(".filter-bar") !== null;
  }

  function toggleAutoRefresh() {
    state.autoRefresh = !state.autoRefresh;
    els.refreshToggle.setAttribute("aria-pressed", state.autoRefresh ? "true" : "false");
    els.refreshLabel.textContent = state.autoRefresh ? "自动刷新 已开启" : "自动刷新 已暂停";
    if (state.autoRefresh) toast("已开启每 15 秒刷新。", "success");
    else toast("自动刷新已暂停，可随时手动刷新。");
  }

  function metricCard(title, value, note, icon, tone) {
    var card = el("article", "metric-card");
    var top = el("div", "metric-top");
    var iconNames = { "＋": "plus", "✓": "check-circle", "!": "alert", "◎": "users" };
    var mark = el("span", "metric-mark " + (tone || ""));
    mark.appendChild(iconNode(iconNames[icon] || "file"));
    add(top, el("span", "", title), mark);
    add(card, top, el("strong", "metric-value", value), el("div", "metric-footer", note));
    return card;
  }

  function runCountsText(counts) {
    if (!counts || typeof counts !== "object") return "";
    var labels = [
      ["imported", "导入"], ["processed", "处理"], ["completed", "入库"],
      ["failed", "失败"], ["skipped", "跳过"], ["deleted", "清理"], ["candidates", "建议"],
      ["submitted", "已提交"], ["submission_errors", "提交失败"], ["updated", "更新"],
      ["awaiting_approval", "待审核"], ["approved", "批准"], ["rejected", "拒绝"]
    ];
    var parts = [];
    labels.forEach(function (item) {
      if (counts[item[0]] !== undefined && counts[item[0]] !== null) parts.push(item[1] + " " + prettyNumber(counts[item[0]]));
    });
    return parts.join(" · ");
  }

  function renderRunList(runs, error) {
    if (error) return emptyState("运行记录暂时不可用", error, "error", "refresh-now");
    var list = el("div", "run-list task-run-list");
    var items = Array.isArray(runs) ? runs.slice() : [];
    if (!items.length) return emptyState("当天暂无持久运行记录", "后台尚未提供当天任务记录；旧有临时日志不会被当作运行记录展示。", "empty");
    items.forEach(function (run) {
      var status = String(run.status || "unknown").toLowerCase();
      var markerTone = ["success", "succeeded", "completed"].indexOf(status) >= 0 ? "success" : (["failed", "error"].indexOf(status) >= 0 ? "failed" : (["running", "started", "pending", "received"].indexOf(status) >= 0 ? "active" : ""));
      var item = el("article", "run-item");
      var marker = el("span", "run-marker" + (markerTone ? " " + markerTone : ""));
      marker.setAttribute("aria-hidden", "true");
      var copy = el("div");
      var title = el("div", "run-title", run.label || run.kind || "后台任务");
      var timeText = formatTime(run.started_at) + (run.finished_at ? " · 完成 " + formatTime(run.finished_at) : "");
      var meta = el("div", "run-meta", statusLabel(run.status, run.status_label) + " · " + timeText + (run.task_id ? " · 任务 " + String(run.task_id).slice(0, 12) : ""));
      add(copy, title, meta);
      if (run.error || run.message) copy.appendChild(el("div", "run-message", run.error || run.message));
      var counts = el("div", "run-counts", runCountsText(run.counts));
      add(item, marker, copy, counts);
      list.appendChild(item);
    });
    return list;
  }

  function renderActivityList(activity) {
    if (!Array.isArray(activity) || !activity.length) return emptyState("暂无文件活动", "每日接口没有返回文件活动记录。", "empty");
    var list = el("div", "run-list activity-list");
    activity.slice(-12).reverse().forEach(function (item) {
      var row = el("article", "run-item");
      var marker = el("span", "run-marker");
      var copy = el("div");
      var title = item.filename || item.label || item.kind || "文件活动";
      var time = item.at || item.created_at || item.updated_at || item.last_processed_at || item.started_at;
      add(copy, el("div", "run-title", title), el("div", "run-meta", statusLabel(item.status, item.status_label) + " · " + formatDateTime(time) + (item.file_id ? " · " + item.file_id : "")));
      if (item.message || item.processing_message || item.error) copy.appendChild(el("div", "run-message", item.error || item.message || item.processing_message));
      add(row, marker, copy, el("span", "run-counts", ""));
      list.appendChild(row);
    });
    return list;
  }

  function chartPointTooltip(items, index) {
    var item = items[index] || {};
    return formatDate(item.date) + "\n新增 " + prettyNumber(item.imported) + " · 入库 " + prettyNumber(item.completed) + " · 失败 " + prettyNumber(item.failed);
  }

  function buildTrendChart(items) {
    var card = el("section", "chart-card");
    var header = el("div", "chart-header");
    var copy = el("div");
    add(copy, el("h2", "", "近 14 日处理趋势"), el("p", "", "按北京时间汇总每天新增、成功入库与失败数量"));
    var legend = el("div", "chart-legend");
    [["新增", ""], ["入库完成", "fail"], ["失败", "danger"]].forEach(function (item) {
      var line = el("span", "legend-item");
      var swatch = el("i", "legend-swatch" + (item[1] === "fail" ? " fail" : ""));
      if (item[1] === "danger") swatch.style.backgroundColor = "#d98d8d";
      add(line, swatch, el("span", "", item[0]));
      legend.appendChild(line);
    });
    add(header, copy, legend);
    card.appendChild(header);
    if (state.overview.errors.trend) {
      card.appendChild(emptyState("趋势接口读取失败", state.overview.errors.trend, "error", "refresh-now"));
      return card;
    }
    if (!Array.isArray(items) || !items.length) {
      card.appendChild(emptyState("暂无趋势数据", "接口尚未返回近 14 日的统计结果。", "empty"));
      return card;
    }
    var svg = svgEl("svg", { "class": "chart-svg", viewBox: "0 0 850 196", role: "img", "aria-label": "近14日新增、入库和失败趋势图" });
    var left = 34;
    var right = 12;
    var top = 14;
    var bottom = 30;
    var width = 850 - left - right;
    var height = 196 - top - bottom;
    var maximum = 1;
    items.forEach(function (item) { maximum = Math.max(maximum, Number(item.imported) || 0, Number(item.completed) || 0, Number(item.failed) || 0); });
    var axisMax = Math.max(1, Math.ceil(maximum / 5) * 5);
    [0, 0.5, 1].forEach(function (ratio) {
      var y = top + height * ratio;
      svg.appendChild(svgEl("line", { x1: left, y1: y, x2: 850 - right, y2: y, "class": "chart-gridline" }));
      var value = Math.round(axisMax * (1 - ratio));
      var label = svgEl("text", { x: left - 8, y: y + 3, "text-anchor": "end", "class": "chart-label" });
      label.textContent = String(value);
      svg.appendChild(label);
    });
    function pointAt(index, key) {
      var x = left + (items.length <= 1 ? width / 2 : index * width / (items.length - 1));
      var value = Number(items[index][key]) || 0;
      var y = top + height - (value / axisMax) * height;
      return { x: x, y: y, value: value };
    }
    function linePath(key) {
      return items.map(function (item, index) {
        var point = pointAt(index, key);
        return (index === 0 ? "M" : "L") + point.x.toFixed(1) + " " + point.y.toFixed(1);
      }).join(" ");
    }
    var firstPoint = pointAt(0, "completed");
    var lastPoint = pointAt(items.length - 1, "completed");
    var area = linePath("completed") + " L" + lastPoint.x.toFixed(1) + " " + (top + height) + " L" + firstPoint.x.toFixed(1) + " " + (top + height) + " Z";
    svg.appendChild(svgEl("path", { d: area, fill: "#3677e8", "fill-opacity": "0.08", stroke: "none" }));
    svg.appendChild(svgEl("path", { d: linePath("imported"), "class": "chart-line-imported" }));
    svg.appendChild(svgEl("path", { d: linePath("completed"), "class": "chart-line-completed" }));
    svg.appendChild(svgEl("path", { d: linePath("failed"), fill: "none", stroke: "#d98d8d", "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round" }));
    items.forEach(function (item, index) {
      if (index % Math.max(1, Math.ceil(items.length / 7)) === 0 || index === items.length - 1) {
        var x = left + (items.length <= 1 ? width / 2 : index * width / (items.length - 1));
        var label = svgEl("text", { x: x, y: 188, "text-anchor": "middle", "class": "chart-label" });
        label.textContent = String(item.date || "").slice(5);
        svg.appendChild(label);
      }
      ["imported", "completed", "failed"].forEach(function (key) {
        var point = pointAt(index, key);
        var dot = svgEl("circle", { cx: point.x, cy: point.y, r: 3.2, fill: key === "imported" ? "#fff" : (key === "completed" ? "#fff" : "#fff"), stroke: key === "imported" ? "#b5c8e8" : (key === "completed" ? "#3677e8" : "#d98d8d"), "stroke-width": 1.5, tabindex: 0, role: "img" });
        var title = svgEl("title", {});
        title.textContent = chartPointTooltip(items, index);
        dot.appendChild(title);
        svg.appendChild(dot);
      });
    });
    var wrap = el("div", "chart-wrap");
    wrap.appendChild(svg);
    card.appendChild(wrap);
    card.appendChild(el("div", "chart-note", "统计口径：数据来自工作台每日与趋势接口；没有返回的数据不会补造。"));
    return card;
  }

  function healthEntry(title, check, note) {
    var wrap = el("div", "health-item");
    var top = el("div", "health-top");
    var label = "状态未知";
    var tone = "";
    var detail = note || "未取得检测结果";
    if (check && typeof check.connected === "boolean") {
      label = check.connected ? "可访问" : "连接失败";
      tone = check.connected ? "success" : "danger";
      detail = check.error || note || (check.connected ? "最近一次检测成功" : "最近一次检测未通过");
    } else if (check && typeof check.success === "boolean") {
      label = check.success ? "可访问" : "连接失败";
      tone = check.success ? "success" : "danger";
      detail = check.error || note || (check.success ? "最近一次检测成功" : "最近一次检测未通过");
    }
    add(top, el("span", "", title), statusPill(label, tone === "success" ? "completed" : (tone === "danger" ? "failed" : "unknown")));
    add(wrap, top, el("p", "", detail));
    return wrap;
  }

  function renderHealthPanel(health, dailySuccess, error) {
    var grid = el("div", "health-grid");
    var apiCheck = dailySuccess ? { connected: true } : null;
    var status = health || {};
    grid.appendChild(healthEntry("工作台接口", apiCheck, apiCheck ? "每日统计请求成功" : "每日统计接口未确认"));
    grid.appendChild(healthEntry("数据库", status.database, "数据库连接检测"));
    grid.appendChild(healthEntry("任务队列", status.celery, "Celery 工作进程检测"));
    grid.appendChild(healthEntry("文件存储", status.storage, status.storage && status.storage.backend === "nas" ? "NAS 挂载目录可读性检测" : "存储连接检测"));
    grid.appendChild(healthEntry("Redis", status.redis, "Redis ping 检测"));
    var wrapper = el("div");
    wrapper.appendChild(grid);
    var note = "状态来自最近一次服务端连接检测。NAS 检测只说明本机挂载目录可访问，不代表底层 NAS 设备在线。";
    if (error) note += " 当前健康接口不可用：" + error;
    wrapper.appendChild(el("p", "health-note", note));
    return wrapper;
  }

  function renderOverview() {
    var root = el("div");
    var day = state.overview.daily;
    var dailySummary = day && day.summary ? day.summary : null;
    var headingActions = el("div", "heading-actions");
    headingActions.appendChild(button("批量处理待处理正文", "open-run", "button-small", { preset: "process_pending" }));
    add(root, pageHeading("每日运行概览", "按北京时间查看 OA 文件处理、人工审核和清理情况。", headingActions));
    var metrics = el("div", "metrics-grid");
    var loadError = state.overview.errors.daily;
    var cards = [
      [state.date === beijingToday() ? "今日新增文件" : "当日新增文件", dailySummary && dailySummary.imported, "所选日期新建的文件记录", "＋", "blue"],
      ["成功入库", dailySummary && dailySummary.completed, "成功写入 Dify，检索索引需完成", "✓", "green"],
      ["处理失败", dailySummary && dailySummary.failed, "需要查看错误并重新处理", "!", "red"],
      ["待人工审核", dailySummary && dailySummary.awaiting_approval, "当前待审核积压，不限所选日期", "◎", "amber"]
    ];
    cards.forEach(function (card) {
      var value = card[1] === undefined || card[1] === null ? "—" : prettyNumber(card[1]);
      var note = loadError ? "统计接口失败，无法确认当前数量" : card[2];
      metrics.appendChild(metricCard(card[0], value, note, card[3], card[4]));
    });
    root.appendChild(metrics);
    if (loadError) root.appendChild(emptyState("每日统计加载失败", loadError, "error", "refresh-now"));
    else if (!day && state.overview.loading) root.appendChild(emptyState("正在读取真实运行数据", "正在请求每日统计接口。", "loading"));
    else if (day && dailySummary && Object.keys(dailySummary).length === 0) root.appendChild(emptyState("该日期暂无汇总数据", "接口没有返回汇总计数。", "empty"));

    root.appendChild(buildTrendChart(state.overview.trend && state.overview.trend.items));

    var runPanelBody = renderRunList(day && day.runs, loadError);
    var runHeaderActions = el("div", "panel-header-actions");
    runHeaderActions.appendChild(el("span", "small subtle", "最后刷新：" + (state.overview.lastUpdated ? formatDateTime(state.overview.lastUpdated) : "尚未成功")));
    var runPanel = panel("当天运行记录", "导入、批量处理、版本扫描与过期/重复扫描。只有持久化任务记录会显示在这里。", runPanelBody, runHeaderActions);
    root.appendChild(runPanel);
    if (day && Array.isArray(day.activity) && day.activity.length) {
      root.appendChild(panel("文件处理动态", "最近 12 条文件阶段活动；完整过程可在文档详情查看。", renderActivityList(day.activity)));
    }

    var lower = el("div", "section-grid section-grid-two");
    var pipelineItems = day && Array.isArray(day.pipeline) ? day.pipeline : [];
    var pipelineGrid = el("div", "pipeline-grid");
    if (pipelineItems.length) {
      pipelineItems.forEach(function (item) {
        var box = el("div", "pipeline-item");
        add(box, el("span", "", item.label || item.key || "处理阶段"), el("strong", "", prettyNumber(item.count)));
        pipelineGrid.appendChild(box);
      });
    }
    var pipelineBody = pipelineItems.length ? pipelineGrid : emptyState("阶段数据暂无", loadError || "每日接口没有返回处理阶段计数。", loadError ? "error" : "empty");
    var pipelinePanel = panel("处理阶段", "各阶段当前文件数量，来自服务端状态统计。", pipelineBody);

    var cleanupBody = el("div", "detail-grid");
    var cleanSummary = [
      ["当日新增清理建议", dailySummary ? dailySummary.cleanup_candidates : undefined],
      ["已执行清理", dailySummary ? dailySummary.deleted : undefined],
      ["当日处理涉及文件", dailySummary ? dailySummary.processed : undefined],
      ["已跳过", dailySummary ? dailySummary.skipped : undefined]
    ];
    cleanSummary.forEach(function (item) {
      var field = el("div", "detail-field");
      add(field, el("strong", "", item[0]), el("span", "", item[1] === undefined || item[1] === null ? (loadError ? "无法确认" : "暂无数据") : prettyNumber(item[1])));
      cleanupBody.appendChild(field);
    });
    var cleanupPanel = panel("清理概览", "默认先生成建议；人工批准后可执行，自动清理规则以系统配置为准。", cleanupBody, button("查看清理建议", "navigate", "button-small", { page: "cleanup" }));
    lower.appendChild(pipelinePanel);
    lower.appendChild(cleanupPanel);
    root.appendChild(lower);

    var healthBody = renderHealthPanel(state.overview.health, !!day, state.overview.errors.health || "");
    root.appendChild(panel("系统连接状态", "接口、数据库、任务队列、存储与 Redis 的实际检测结果。", healthBody, button("重新检测", "refresh-health", "button-small", {})));
    els.mainContent.replaceChildren(root);
  }

  async function loadOverview(manual) {
    var sequence = (state.overview.requestSequence || 0) + 1;
    state.overview.requestSequence = sequence;
    state.overview.loading = true;
    if (!state.overview.daily) renderOverview();
    var dailyPromise = request("/console/daily?date=" + encodeURIComponent(state.date));
    var trendPromise = request("/console/trend?days=14");
    var fetchHealth = !!manual || !state.overview.healthLoadedAt || (Date.now() - state.overview.healthLoadedAt > 60000);
    var promises = [dailyPromise, trendPromise];
    if (fetchHealth) promises.push(request("/system/status"));
    var results = await Promise.allSettled(promises);
    if (sequence !== state.overview.requestSequence) return;
    var now = new Date().toISOString();
    if (results[0].status === "fulfilled") {
      state.overview.daily = results[0].value;
      state.overview.errors.daily = "";
      state.overview.lastUpdated = now;
    } else {
      state.overview.daily = null;
      state.overview.errors.daily = safeError(results[0].reason);
      state.overview.lastUpdated = null;
    }
    if (results[1].status === "fulfilled") {
      state.overview.trend = results[1].value;
      state.overview.errors.trend = "";
    } else {
      state.overview.trend = null;
      state.overview.errors.trend = safeError(results[1].reason);
    }
    if (fetchHealth) {
      state.overview.healthLoadedAt = Date.now();
      if (results[2].status === "fulfilled") {
        state.overview.health = results[2].value;
        state.overview.errors.health = "";
      } else {
        state.overview.health = null;
        state.overview.errors.health = safeError(results[2].reason);
      }
    }
    state.overview.loading = false;
    if (state.page === "overview") renderOverview();
    if (manual) {
      if (state.overview.errors.daily) toast("每日统计刷新失败：" + state.overview.errors.daily, "error");
      else toast("数据已刷新。", "success");
    }
  }

  function fileId(item) {
    return String((item && (item.file_id || item.imagefileid || item.id)) || "");
  }

  function fileName(item) {
    return (item && (item.filename || item.imagefilename || item.name)) || "未命名文件";
  }

  function statusIsRunning(value) {
    return ["DOWNLOADING", "DECRYPTING", "PARSING", "ANALYZING", "RUNNING", "STARTED"].indexOf(String(value || "").toUpperCase()) >= 0;
  }

  function isRetryableDocument(item) {
    var status = String(item && item.status ? item.status : "").toUpperCase();
    return ["PENDING", "FAILED"].indexOf(status) >= 0 && !statusIsRunning(status) && item.is_zw !== false;
  }

  function makeTh(text) { return el("th", "", text); }

  function makeTd(content, className) {
    var cell = el("td", className || "");
    if (typeof content === "string" || typeof content === "number") cell.textContent = String(content);
    else if (content) cell.appendChild(content);
    return cell;
  }

  function tableContainer(headings, rows, minEmpty) {
    if (!rows || !rows.length) return emptyState("暂无符合条件的文档", minEmpty || "请调整关键词或筛选条件。", "empty");
    var wrap = el("div", "table-wrap");
    var table = el("table");
    var thead = el("thead");
    var trh = el("tr");
    headings.forEach(function (heading) { trh.appendChild(makeTh(heading)); });
    thead.appendChild(trh);
    var tbody = el("tbody");
    rows.forEach(function (row) { tbody.appendChild(row); });
    add(table, thead, tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function categoryOptions() {
    return [{ value: "", label: "全部分类" }].concat(CATEGORY_OPTIONS.map(function (item) { return { value: item[0], label: item[1] }; }));
  }

  function documentQuery(page) {
    var params = new URLSearchParams();
    if (state.date && state.documents.scope !== "all") params.set("date", state.date);
    params.set("page", String(page || state.documents.page));
    params.set("page_size", String(state.documents.pageSize));
    if (state.documents.filters.status) params.set("status", state.documents.filters.status);
    if (state.documents.filters.category) params.set("category", state.documents.filters.category);
    if (state.documents.filters.q) params.set("q", state.documents.filters.q);
    return params.toString();
  }

  function renderDocumentFilters() {
    var bar = el("form", "filter-bar");
    bar.addEventListener("submit", function (event) {
      event.preventDefault();
      state.documents.page = 1;
      loadDocuments(false);
    });
    var search = textInput(state.documents.filters.q, "搜索文件名或文件编号");
    search.id = "document-search";
    search.name = "q";
    search.addEventListener("input", function () { state.documents.filters.q = search.value; });
    var searchWrap = createField("关键词", search, "");
    searchWrap.classList.add("search-field");
    var statuses = [
      { value: "", label: "全部状态" },
      { value: "PENDING", label: "待处理" },
      { value: "DOWNLOADING", label: "读取中" },
      { value: "DECRYPTING", label: "解密中" },
      { value: "PARSING", label: "解析中" },
      { value: "ANALYZING", label: "分析中" },
      { value: "AWAITING_APPROVAL", label: "待人工审核" },
      { value: "COMPLETED", label: "已入库" },
      { value: "FAILED", label: "处理失败" },
      { value: "SKIPPED", label: "已跳过" }
    ];
    var status = selectControl(statuses, state.documents.filters.status);
    status.id = "document-status";
    status.addEventListener("change", function () { state.documents.filters.status = status.value; state.documents.page = 1; loadDocuments(false); });
    var category = selectControl(categoryOptions(), state.documents.filters.category);
    category.id = "document-category";
    category.addEventListener("change", function () { state.documents.filters.category = category.value; state.documents.page = 1; loadDocuments(false); });
    var scope = selectControl([{value: "day", label: "所选日期"}, {value: "all", label: "全部历史"}], state.documents.scope);
    scope.id = "document-scope";
    scope.addEventListener("change", function () { state.documents.scope = scope.value; state.documents.page = 1; loadDocuments(false); });
    add(bar, searchWrap, createField("状态", status, ""), createField("业务分类", category, ""), createField("查看范围", scope, ""), button("筛选", "search-documents", "button-primary button-small", {}));
    bar.appendChild(el("p", "filter-note", state.documents.scope === "all" ? "当前查询全部历史文件，顶部统计日期不限制此列表。" : "日期口径：当日同步、处理或处理日志涉及的文件；切换顶部日期后会重新查询。"));
    return bar;
  }

  function renderDocumentRows(items) {
    return items.map(function (item) {
      var id = fileId(item);
      var row = el("tr");
      var file = el("div", "file-cell");
      file.appendChild(el("span", "file-name", fileName(item)));
      file.appendChild(el("span", "file-sub", categoryLabel(item.category_label || item.category) + (id ? " · " + id : "")));
      var status = statusPill(item.status_label || statusLabel(item.status), item.status);
      var currentStep = item.current_step || item.message || "—";
      var processedAt = item.completed_at || item.started_at;
      var actions = el("div", "cell-actions");
      actions.appendChild(button("查看", "document-detail", "button-small", { id: id }));
      actions.appendChild(button("下载", "download-file", "button-small", { id: id }));
      var retry = button("重新处理", "process-file", "button-small button-link", { id: id });
      retry.disabled = !isRetryableDocument(item);
      retry.title = statusIsRunning(item.status) ? "文件正在处理中，不能重复提交" : "仅待处理或失败的正文可重新处理";
      actions.appendChild(retry);
      add(row,
        makeTd(file, "file-cell"),
        makeTd(currentStep),
        makeTd(status),
        makeTd(formatDateTime(processedAt), "nowrap"),
        makeTd(actions)
      );
      return row;
    });
  }

  function renderDocuments() {
    var root = el("div");
    var actions = el("div", "heading-actions");
    actions.appendChild(button("批量处理待处理正文", "open-run", "button-primary button-small", { preset: "process_pending" }));
    add(root, pageHeading("文档处理", "按状态追踪 OA 正文从读取、解析、分析到 Dify 入库的过程。", actions));
    root.appendChild(renderDocumentFilters());
    var body;
    if (state.documents.error) body = emptyState("文档列表加载失败", state.documents.error, "error", "refresh-now");
    else if (state.documents.loading && !state.documents.items.length) body = emptyState("正在读取文档列表", "正在请求真实文件记录。", "loading");
    else body = tableContainer(["文件名 / 分类", "当前阶段", "状态", "最后处理时间", "操作"], renderDocumentRows(state.documents.items), "该日期和筛选条件下没有文件记录。");
    root.appendChild(panel("文件列表", "只显示接口返回的文件记录；“重新处理”仅对待处理或失败的正文开放。", body));
    var totalPages = Math.max(1, Math.ceil((state.documents.total || 0) / state.documents.pageSize));
    var footer = el("div", "table-footer");
    footer.appendChild(el("span", "", "共 " + prettyNumber(state.documents.total) + " 份 · 每页 " + state.documents.pageSize + " 条"));
    var pagination = el("div", "pagination");
    var prev = button("上一页", "documents-page", "button-small", { page: Math.max(1, state.documents.page - 1) });
    prev.disabled = state.documents.page <= 1 || state.documents.loading;
    var next = button("下一页", "documents-page", "button-small", { page: Math.min(totalPages, state.documents.page + 1) });
    next.disabled = state.documents.page >= totalPages || state.documents.loading;
    add(pagination, prev, el("span", "page-count", "第 " + state.documents.page + " / " + totalPages + " 页"), next);
    footer.appendChild(pagination);
    root.appendChild(footer);
    els.mainContent.replaceChildren(root);
  }

  async function loadDocuments(manual) {
    var sequence = (state.documents.requestSequence || 0) + 1;
    state.documents.requestSequence = sequence;
    state.documents.loading = true;
    state.documents.error = "";
    if (state.page === "documents") renderDocuments();
    try {
      var payload = await request("/console/documents?" + documentQuery(state.documents.page));
      if (sequence !== state.documents.requestSequence) return;
      state.documents.items = Array.isArray(payload.items) ? payload.items : [];
      state.documents.total = Number(payload.total) || 0;
      state.documents.page = Number(payload.page) || state.documents.page;
      state.documents.pageSize = Number(payload.page_size) || state.documents.pageSize;
      state.documents.error = "";
      if (manual) toast("文档列表已刷新。", "success");
    } catch (error) {
      if (sequence !== state.documents.requestSequence) return;
      state.documents.items = [];
      state.documents.total = 0;
      state.documents.error = safeError(error);
      if (manual) toast("文档列表刷新失败：" + state.documents.error, "error");
    }
    state.documents.loading = false;
    if (state.page === "documents") renderDocuments();
  }

  function getAnalysis(detail) {
    if (!detail) return {};
    var value = detail.ai_analysis || detail.ai_analysis_result || detail.analysis || {};
    if (typeof value === "string") {
      try { value = JSON.parse(value); } catch (error) { value = { summary: value }; }
    }
    return value && typeof value === "object" ? value : {};
  }

  function firstText(object, keys) {
    for (var i = 0; i < keys.length; i += 1) {
      var value = object ? object[keys[i]] : null;
      if (typeof value === "string" && value.trim()) return value.trim();
      if (typeof value === "number") return String(value);
    }
    return "";
  }

  function analysisSummary(detail) {
    var analysis = getAnalysis(detail);
    return firstText(analysis, ["summary", "document_summary", "content_summary", "摘要", "overview", "abstract", "title"]);
  }

  function analysisReason(detail) {
    var analysis = getAnalysis(detail);
    return firstText(analysis, ["reason", "reasoning", "decision_reason", "add_reason", "rationale", "analysis_reason", "依据", "判断理由", "recommendation"]);
  }

  function analysisConfidence(detail) {
    if (!detail) return null;
    var analysis = getAnalysis(detail);
    var value = detail.ai_confidence_score;
    if (value === undefined || value === null) value = analysis.confidence_score;
    if (value === undefined || value === null) value = analysis.confidence;
    if (value === undefined || value === null) value = analysis.confidenceScore;
    if (value === undefined || value === null) return null;
    var number = Number(value);
    if (!isFinite(number)) return null;
    if (number <= 1) number = number * 100;
    return Math.max(0, Math.min(100, number));
  }

  function documentBody(detail) {
    if (!detail) return "";
    var body = detail.parsed_content || detail.content || detail.body || detail.extracted_text || detail.document_text || detail.text || "";
    return typeof body === "string" ? body : "";
  }

  function detailTarget(detail, item) {
    if (!detail) {
      if (item && item.dataset_id) return "数据集 " + item.dataset_id;
      if (item && item.knowledge_base_id) return "知识库编号 " + item.knowledge_base_id;
      return "目标知识库信息未读取";
    }
    var target = detail.target_knowledge_base;
    if (typeof target === "string" && target) return target;
    if (target && typeof target === "object") {
      var targetName = target.name || target.knowledge_base_name || "";
      var targetDataset = target.dify_dataset_id || target.dataset_id || "";
      if (targetName && targetDataset) return targetName + "（" + targetDataset + "）";
      if (targetName || targetDataset) return targetName || ("数据集 " + targetDataset);
    }
    if (detail.knowledge_base_name) return detail.knowledge_base_name + (detail.dify_dataset_id ? "（" + detail.dify_dataset_id + "）" : "");
    if (detail.dify_dataset_id) return "数据集 " + detail.dify_dataset_id;
    if (detail.dataset_id) return "数据集 " + detail.dataset_id;
    if (item && item.dataset_id) return "数据集 " + item.dataset_id;
    if (detail.knowledge_base_id) return "知识库编号 " + detail.knowledge_base_id;
    if (item && item.knowledge_base_id) return "知识库编号 " + item.knowledge_base_id;
    var status = String((detail && detail.processing_status) || (item && item.status) || "").toUpperCase();
    return status === "AWAITING_APPROVAL" ? "待审批后按分类映射确定" : "接口未提供入库目标";
  }

  async function mapLimit(items, limit, mapper) {
    var index = 0;
    var results = new Array(items.length);
    var workers = [];
    var workerCount = Math.min(limit, items.length);
    for (var i = 0; i < workerCount; i += 1) {
      workers.push((async function () {
        while (index < items.length) {
          var current = index;
          index += 1;
          try { results[current] = await mapper(items[current], current); }
          catch (error) { results[current] = { error: safeError(error) }; }
        }
      })());
    }
    await Promise.all(workers);
    return results;
  }

  async function loadApprovals(manual) {
    state.approvals.loading = true;
    state.approvals.error = "";
    if (state.page === "approvals") renderApprovals();
    try {
      var payload = await request("/console/documents?page=1&page_size=30&status=AWAITING_APPROVAL");
      state.approvals.items = Array.isArray(payload.items) ? payload.items : [];
      state.approvals.total = Number(payload.total) || 0;
      var newDetails = manual ? {} : Object.assign({}, state.approvals.details);
      var detailIds = state.approvals.items.map(fileId).filter(function (id) { return !!id && !newDetails[id]; });
      await mapLimit(detailIds, 5, async function (id) {
        try { newDetails[id] = await request("/files/" + encodeURIComponent(id)); }
        catch (error) { newDetails[id] = { _load_error: safeError(error) }; }
      });
      state.approvals.details = newDetails;
      if (manual) toast("待审核列表已刷新。", "success");
    } catch (error) {
      state.approvals.items = [];
      state.approvals.total = 0;
      state.approvals.details = {};
      state.approvals.error = safeError(error);
      if (manual) toast("待审核列表刷新失败：" + state.approvals.error, "error");
    }
    state.approvals.loading = false;
    if (state.page === "approvals") renderApprovals();
  }

  function renderApprovalCard(item) {
    var id = fileId(item);
    var detail = state.approvals.details[id];
    var card = el("article", "approval-card");
    var head = el("div", "approval-head");
    var title = el("div");
    add(title, el("h3", "approval-title", fileName(item)), el("div", "file-sub", categoryLabel(item.category_label || item.category) + " · " + id));
    var status = statusPill(item.status_label || "待人工审核", "AWAITING_APPROVAL");
    add(head, title, status);
    card.appendChild(head);
    var summary = detail && !detail._load_error ? analysisSummary(detail) : "";
    var reason = detail && !detail._load_error ? analysisReason(detail) : "";
    var body = detail && !detail._load_error ? documentBody(detail) : "";
    var mainText = summary || (body ? body.slice(0, 240) + (body.length > 240 ? "…" : "") : "");
    if (detail && detail._load_error) mainText = "文档详情读取失败：" + detail._load_error;
    if (!mainText) mainText = "正文与模型摘要暂未由详情接口返回，可打开详情再次查看。";
    card.appendChild(el("p", "approval-summary", mainText));
    if (reason) {
      var reasonLine = el("p", "approval-summary");
      reasonLine.style.color = "#747b85";
      reasonLine.style.marginTop = "6px";
      reasonLine.textContent = "模型理由：" + reason;
      card.appendChild(reasonLine);
    }
    var meta = el("div", "approval-meta");
    var confidence = analysisConfidence(detail);
    var confidenceText = confidence === null ? "置信度：未提供" : "置信度：" + confidence.toFixed(0) + "%";
    var confidenceWrap = el("span");
    if (confidence !== null) {
      var track = el("span", "confidence-track");
      var fill = el("i");
      fill.style.width = confidence + "%";
      track.appendChild(fill);
      confidenceWrap.appendChild(track);
    }
    confidenceWrap.appendChild(document.createTextNode(confidenceText));
    add(meta, confidenceWrap, el("span", "", "目标知识库：" + detailTarget(detail, item)), el("span", "", "最后处理：" + formatDateTime(item.last_processed_at || item.completed_at || item.started_at)));
    card.appendChild(meta);
    var actions = el("div", "approval-actions");
    actions.appendChild(button("查看正文与流程", "document-detail", "button-small", { id: id }));
    actions.appendChild(button("拒绝", "review-document", "button-small", { id: id, approved: "false" }));
    actions.appendChild(button("批准并继续入库", "review-document", "button-primary button-small", { id: id, approved: "true" }));
    card.appendChild(actions);
    return card;
  }

  function renderApprovals() {
    var root = el("div");
    var actions = el("div", "heading-actions");
    actions.appendChild(button("刷新待审核", "refresh-now", "button-small", {}));
    add(root, pageHeading("人工审核", "核对模型判断、原文依据与目标知识库，再批准或拒绝。批准后由后台任务继续处理。", actions));
    var body;
    if (state.approvals.error) body = emptyState("待审核数据加载失败", state.approvals.error, "error", "refresh-now");
    else if (state.approvals.loading && !state.approvals.items.length) body = emptyState("正在读取待审核文件", "正在查询待入库审核记录及其模型判断。", "loading");
    else if (!state.approvals.items.length) body = emptyState("当前没有待审核文件", "没有待人工审核的正文记录。", "empty");
    else {
      body = el("div", "approval-list");
      state.approvals.items.forEach(function (item) { body.appendChild(renderApprovalCard(item)); });
    }
    var panelActions = el("div", "panel-header-actions");
    panelActions.appendChild(el("span", "small subtle", "待审核 " + prettyNumber(state.approvals.total) + " 份"));
    root.appendChild(panel("审核队列", "原文与摘要来自文件详情接口；没有返回的字段会明确标记为未提供。", body, panelActions));
    els.mainContent.replaceChildren(root);
  }

  function normalizeEvidence(value) {
    if (!value) return {};
    if (typeof value === "string") {
      try { value = JSON.parse(value); } catch (error) { return { original_basis: value }; }
    }
    return value && typeof value === "object" ? value : {};
  }

  function evidenceValue(evidence, keys) {
    for (var i = 0; i < keys.length; i += 1) {
      if (evidence[keys[i]] !== undefined && evidence[keys[i]] !== null && evidence[keys[i]] !== "") return evidence[keys[i]];
    }
    return "";
  }

  function humanValue(value) {
    if (value === null || value === undefined || value === "") return "未提供";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) return value.map(humanValue).join("；");
    if (typeof value === "object") {
      var nested = firstText(value, ["text", "quote", "excerpt", "content", "reason", "label", "name", "title", "date"]);
      return nested || "已记录，详情由服务端保留";
    }
    return "已记录";
  }

  function cleanupObjectName(id) {
    var detail = state.cleanup.details[String(id || "")];
    if (!id) return "—";
    if (!detail) return String(id);
    if (detail._load_error) return String(id) + "（名称暂不可读）";
    return (detail.filename || detail.imagefilename || String(id)) + "（" + id + "）";
  }

  function cleanupEvidenceBasis(evidence, candidate) {
    var quote = evidenceValue(evidence, ["evidence_quote", "source_excerpt", "source_text", "original_text", "original_basis", "basis", "evidence_text"]);
    if (typeof quote === "string" && quote.trim()) return "原文摘录：“" + quote.trim() + "”";
    var replacementEvidence = evidence.replacement_evidence;
    if (Array.isArray(replacementEvidence)) {
      var matching = replacementEvidence.filter(function (item) {
        return item && (item.old_document_id === candidate.document_id || item.old_document_id === candidate.file_id);
      })[0] || replacementEvidence[0];
      if (matching && typeof matching.quote === "string" && matching.quote.trim()) return "替代文件中的原文：“" + matching.quote.trim() + "”";
    }
    var reasoning = evidenceValue(evidence, ["reasoning", "reason", "decision_reason", "explanation"]);
    if (candidate.kind === "duplicate" && evidence.content_sha256) {
      return "核验依据：完整解析正文 SHA-256 一致（" + String(evidence.content_sha256) + "）。" + (reasoning ? " " + humanValue(reasoning) : "");
    }
    return reasoning ? humanValue(reasoning) : "扫描结果未单独提供原文摘录";
  }

  async function loadCleanup(manual) {
    state.cleanup.loading = true;
    state.cleanup.error = "";
    if (state.page === "cleanup") renderCleanup();
    var params = new URLSearchParams();
    params.set("page", String(state.cleanup.page));
    params.set("size", String(state.cleanup.pageSize));
    if (state.cleanup.status) params.set("status", state.cleanup.status);
    try {
      var payload = await request("/maintenance/cleanup-candidates?" + params.toString());
      state.cleanup.items = Array.isArray(payload.items) ? payload.items : [];
      state.cleanup.total = Number(payload.total) || 0;
      var ids = [];
      state.cleanup.items.forEach(function (item) {
        if (item.file_id) ids.push(String(item.file_id));
        if (item.replacement_file_id) ids.push(String(item.replacement_file_id));
      });
      ids = ids.filter(function (id, index) { return ids.indexOf(id) === index; });
      var detailMap = manual ? {} : Object.assign({}, state.cleanup.details);
      var detailIds = ids.filter(function (id) { return !detailMap[id]; });
      await mapLimit(detailIds, 5, async function (id) {
        try { detailMap[id] = await request("/files/" + encodeURIComponent(id)); }
        catch (error) { detailMap[id] = { _load_error: safeError(error) }; }
      });
      state.cleanup.details = detailMap;
      state.cleanup.error = "";
      if (manual) toast("清理建议已刷新。", "success");
    } catch (error) {
      state.cleanup.items = [];
      state.cleanup.total = 0;
      state.cleanup.details = {};
      state.cleanup.error = safeError(error);
      if (manual) toast("清理建议刷新失败：" + state.cleanup.error, "error");
    }
    state.cleanup.loading = false;
    if (state.page === "cleanup") renderCleanup();
  }

  function candidateCard(candidate) {
    var evidence = normalizeEvidence(candidate.evidence);
    var card = el("article", "candidate-card");
    var head = el("div", "candidate-head");
    var title = el("div");
    var kindLabels = { expiration: "过期文档", duplicate: "内容重复", version: "制度版本替换" };
    var kind = kindLabels[candidate.kind] || (candidate.kind || "清理建议");
    var targetName = cleanupObjectName(candidate.file_id);
    add(title, el("h3", "candidate-title", kind + " · " + targetName), el("div", "file-sub", "建议编号 " + candidate.id + " · 文档ID " + (candidate.document_id || "未提供")));
    add(head, title, statusPill(statusLabel(candidate.status), candidate.status));
    card.appendChild(head);

    var date = evidenceValue(evidence, ["expiration_date", "expires_at", "valid_until"]);
    var basis = cleanupEvidenceBasis(evidence, candidate);
    var evidenceGrid = el("div", "evidence-grid");
    [
      ["失效日期", date ? humanValue(date) : "原文未提供明确失效日期"],
      ["目标数据集", candidate.dataset_id || "未提供"],
      ["保留文件", candidate.replacement_file_id ? cleanupObjectName(candidate.replacement_file_id) : "无替代文件"],
      ["原文依据", basis]
    ].forEach(function (entry) {
      var box = el("div", "evidence-item");
      add(box, el("strong", "", entry[0]), el("span", "", entry[1]));
      evidenceGrid.appendChild(box);
    });
    card.appendChild(evidenceGrid);

    var audit = el("details", "candidate-evidence");
    audit.appendChild(el("summary", "", "查看审核与执行审计"));
    var auditGrid = el("div", "evidence-grid");
    [
      ["候选文件ID", candidate.file_id || "未提供"],
      ["知识库文档ID", candidate.document_id || "未提供"],
      ["审核人", candidate.reviewed_by || "尚未审核"],
      ["审核意见", candidate.review_comment || "未填写"],
      ["创建时间", formatDateTime(candidate.created_at)],
      ["执行时间", formatDateTime(candidate.executed_at)],
      ["尝试次数", candidate.attempts === undefined ? "未提供" : prettyNumber(candidate.attempts)],
      ["最近错误", candidate.last_error || "无"]
    ].forEach(function (entry) {
      var box = el("div", "evidence-item");
      add(box, el("strong", "", entry[0]), el("span", "", entry[1]));
      auditGrid.appendChild(box);
    });
    audit.appendChild(auditGrid);
    card.appendChild(audit);

    var actions = el("div", "candidate-actions");
    actions.appendChild(button("查看候选文档", "document-detail", "button-small", { id: candidate.file_id || "" }));
    if (["pending", "failed", "approved"].indexOf(candidate.status) >= 0) {
      actions.appendChild(button("拒绝建议", "review-cleanup", "button-small", { id: candidate.id, approved: "false" }));
      actions.appendChild(button("批准建议", "review-cleanup", "button-small", { id: candidate.id, approved: "true" }));
    }
    if (["approved", "failed"].indexOf(candidate.status) >= 0) {
      actions.appendChild(button(candidate.status === "failed" ? "确认后重试" : "确认并执行清理", "execute-cleanup", "button-danger button-small", { id: candidate.id }));
    }
    card.appendChild(actions);
    return card;
  }

  function renderCleanup() {
    var root = el("div");
    var actions = el("div", "heading-actions");
    actions.appendChild(button("扫描过期与重复", "scan-cleanup", "button-small", {}));
    actions.appendChild(button("扫描制度版本", "scan-versions", "button-primary button-small", {}));
    add(root, pageHeading("清理维护", "先预览清理建议，再单独审核与执行。删除请求仍由服务端复核并记录审计。", actions));
    if (state.cleanup.task) {
      var taskInfo = el("div", "callout");
      taskInfo.textContent = "预览任务已排队：" + state.cleanup.task.task_id + "。" + (state.cleanup.task.message ? " " + state.cleanup.task.message : "") + "建议列表刷新后显示后台生成的结果。";
      root.appendChild(taskInfo);
    }
    var bar = el("div", "filter-bar");
    var statuses = [
      { value: "", label: "全部审核状态" },
      { value: "pending", label: "待审核" },
      { value: "approved", label: "已批准" },
      { value: "rejected", label: "已拒绝" },
      { value: "failed", label: "执行失败" },
      { value: "deleted", label: "已清理" },
      { value: "stale", label: "文档已变化" }
    ];
    var filter = selectControl(statuses, state.cleanup.status);
    filter.addEventListener("change", function () { state.cleanup.status = filter.value; state.cleanup.page = 1; loadCleanup(false); });
    add(bar, createField("建议状态", filter, ""), button("刷新建议", "refresh-now", "button-small", {}));
    root.appendChild(bar);
    var body;
    if (state.cleanup.error) body = emptyState("清理建议读取失败", state.cleanup.error, "error", "refresh-now");
    else if (state.cleanup.loading && !state.cleanup.items.length) body = emptyState("正在读取清理建议", "正在加载服务端保存的候选、审核及执行记录。", "loading");
    else if (!state.cleanup.items.length) body = emptyState("暂无清理建议", "扫描操作只提交预览任务；待后台扫描完成后，建议会出现在此处。", "empty");
    else {
      body = el("div", "candidate-list");
      state.cleanup.items.forEach(function (candidate) { body.appendChild(candidateCard(candidate)); });
    }
    root.appendChild(panel("清理建议与执行审计", "原文依据、保留文件、目标数据集和服务端审核状态。", body));
    var totalPages = Math.max(1, Math.ceil((state.cleanup.total || 0) / state.cleanup.pageSize));
    var footer = el("div", "table-footer");
    footer.appendChild(el("span", "", "共 " + prettyNumber(state.cleanup.total) + " 条建议"));
    var pagination = el("div", "pagination");
    var prev = button("上一页", "cleanup-page", "button-small", { page: Math.max(1, state.cleanup.page - 1) });
    prev.disabled = state.cleanup.page <= 1 || state.cleanup.loading;
    var next = button("下一页", "cleanup-page", "button-small", { page: Math.min(totalPages, state.cleanup.page + 1) });
    next.disabled = state.cleanup.page >= totalPages || state.cleanup.loading;
    add(pagination, prev, el("span", "page-count", "第 " + state.cleanup.page + " / " + totalPages + " 页"), next);
    footer.appendChild(pagination);
    root.appendChild(footer);
    els.mainContent.replaceChildren(root);
  }

  async function submitAction(action, payload) {
    var body = Object.assign({ action: action, limit: 20, dat_file_path: null, update_existing: false, dry_run: true }, payload || {});
    var result = await request("/console/actions", { method: "POST", body: body });
    if (!result || result.success !== true || !result.task_id) {
      throw new Error((result && result.message) || "服务端未确认任务已排队。");
    }
    var run = { task_id: result.task_id, message: result.message || "任务已排队" };
    if (action === "scan_cleanup" || action === "scan_versions") state.cleanup.task = run;
    toast("任务已排队：" + result.task_id + "。" + (result.message || ""), "success");
    closeModal();
    if (state.page === "overview") loadOverview(false);
    else if (state.page === "cleanup") renderCleanup();
    else if (state.page === "documents") loadDocuments(false);
    return result;
  }

  function openModal(title, description, body, actions) {
    state.lastFocus = document.activeElement;
    els.modalTitle.textContent = title;
    els.modalDescription.textContent = description || "";
    els.modalBody.replaceChildren(body || el("div"));
    els.modalFooter.replaceChildren();
    (actions || []).forEach(function (action) { els.modalFooter.appendChild(action); });
    els.modalLayer.hidden = false;
    window.setTimeout(function () {
      var first = els.modalCard.querySelector("input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])");
      if (first) first.focus(); else els.modalCard.focus();
    }, 0);
  }

  function closeModal() {
    if (els.modalLayer.hidden) return;
    els.modalLayer.hidden = true;
    if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
  }

  function openRunModal(preset) {
    var available = [
      { value: "import", label: "导入 DAT 文件" },
      { value: "process_pending", label: "批量处理待处理正文" },
      { value: "scan_cleanup", label: "预览扫描过期与重复" },
      { value: "scan_versions", label: "预览扫描制度版本" }
    ];
    var body = el("div");
    var actionSelect = selectControl(available, preset || "import");
    actionSelect.id = "run-action-type";
    var limitInput = textInput("20", "20", "number");
    limitInput.min = "1";
    limitInput.max = "5000";
    limitInput.id = "run-limit";
    var limitWrap = createField("任务处理上限", limitInput, "批量处理默认 20；清理扫描最多 5000。", "run-limit-wrap");
    var pathInput = textInput("", "留空时由服务端选择最新文件");
    pathInput.id = "run-dat-path";
    var pathWrap = createField("DAT 文件路径（可选）", pathInput, "路径只提交给服务端，不会保存在浏览器。", "run-path-wrap");
    var updateLabel = el("label", "check-row");
    var update = el("input");
    update.type = "checkbox";
    update.id = "run-update-existing";
    add(updateLabel, update, el("span", "", "更新已存在的文件记录"));
    var updateWrap = el("div", "field run-update-wrap");
    add(updateWrap, el("span", "field-label", "导入选项"), updateLabel);
    var notice = el("div", "callout warning");
    notice.textContent = "清理扫描固定为预览模式，只生成建议，不会执行删除。批准建议与执行清理需要在“清理维护”页面分开完成。";
    add(body, createField("运行任务", actionSelect, "提交后显示真实任务编号及排队结果。"), limitWrap, pathWrap, updateWrap, notice);
    function updateVisibility() {
      var value = actionSelect.value;
      var scanning = value === "scan_cleanup" || value === "scan_versions";
      limitWrap.hidden = !scanning && value !== "process_pending";
      pathWrap.hidden = value !== "import";
      updateWrap.hidden = value !== "import";
      notice.hidden = !scanning;
    }
    actionSelect.addEventListener("change", updateVisibility);
    updateVisibility();
    var cancel = button("取消", "close-modal", "", {});
    var submit = button("提交任务", "", "button-primary", {});
    submit.addEventListener("click", async function () {
      submit.disabled = true;
      try {
        var action = actionSelect.value;
        var payload = { limit: Number(limitInput.value) || 20, dry_run: true };
        if (action === "import") {
          payload.dat_file_path = pathInput.value.trim() || null;
          payload.update_existing = update.checked;
        }
        await submitAction(action, payload);
      } catch (error) {
        toast("任务提交失败：" + safeError(error), "error");
        submit.disabled = false;
      }
    });
    openModal("手动运行", "提交到后台任务队列；当前页面不会把排队状态显示成已完成。", body, [cancel, submit]);
  }

  function closeDrawer() {
    if (els.drawerLayer.hidden) return;
    els.drawerLayer.hidden = true;
    if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
  }

  function showDrawerLoading(filename) {
    els.drawerTitle.textContent = filename || "文档详情";
    els.drawerBody.replaceChildren(emptyState("正在读取文档详情", "正在请求正文、流程日志与附件信息。", "loading"));
    els.drawerLayer.hidden = false;
    window.setTimeout(function () { els.drawerClose.focus(); }, 0);
  }

  function stageEntries(detail, logs) {
    var stageDefs = [
      ["读取文件", ["download", "read", "读取", "下载"]],
      ["解密或直读", ["decrypt", "解密", "direct", "直读"]],
      ["解析正文", ["pars", "解析", "extract", "提取"]],
      ["模型分析", ["analy", "模型", "ai", "分类"]],
      ["人工审核", ["approv", "审核"]],
      ["Dify 入库", ["dify", "upload", "入库", "知识库"]]
    ];
    var entries = [];
    stageDefs.forEach(function (definition) {
      var matching = logs.filter(function (log) {
        var step = String(log.step || "").toLowerCase();
        return definition[1].some(function (hint) { return step.indexOf(hint.toLowerCase()) >= 0; });
      });
      var latest = matching.length ? matching[matching.length - 1] : null;
      var status = "unrecorded";
      if (latest) status = String(latest.status || "").toLowerCase() === "failed" ? "error" : "done";
      entries.push({ name: definition[0], status: status, log: latest });
    });
    return entries;
  }

  function detailField(labelText, value, mono) {
    var field = el("div", "detail-field");
    add(field, el("strong", "", labelText));
    field.appendChild(el("span", mono ? "mono" : "", value === null || value === undefined || value === "" ? "未提供" : value));
    return field;
  }

  function renderDocumentDrawer(id, detail, logsResult, attachmentsResult) {
    els.drawerTitle.textContent = detail.filename || detail.imagefilename || id;
    var body = el("div");
    var actionRow = el("div", "drawer-actions");
    actionRow.appendChild(button("下载正文文件", "download-file", "button-small", { id: id }));
    if (isRetryableDocument({ status: detail.processing_status, is_zw: detail.is_zw })) {
      actionRow.appendChild(button("重新处理", "process-file", "button-primary button-small", { id: id }));
    }
    add(body, actionRow);

    var summaryFields = el("div", "detail-grid");
    add(summaryFields,
      detailField("文件标识", detail.imagefileid || id, true),
      detailField("业务分类", categoryLabel(detail.business_category)),
      detailField("处理状态", statusLabel(detail.processing_status), false),
      detailField("当前阶段", detail.current_step || detail.processing_message || "接口未提供"),
      detailField("首次同步", formatDateTime(detail.created_at)),
      detailField("处理开始", formatDateTime(detail.processing_started_at)),
      detailField("处理完成", formatDateTime(detail.processing_completed_at)),
      detailField("目标知识库", detailTarget(detail)),
      detailField("目标数据集", detail.dify_dataset_id || "尚未写入数据集"),
      detailField("Dify 文档编号", detail.document_id || "尚未入库", true),
      detailField("文件大小", detail.filesize === null || detail.filesize === undefined ? "未提供" : (prettyNumber(detail.filesize) + " 字节")),
      detailField("正文文件", detail.is_zw === true ? "是" : (detail.is_zw === false ? "否" : "接口未提供")),
      detailField("文件路径", detail.filerealpath || "未提供", true)
    );
    body.appendChild(panel("处理概况", "以下内容来自文件详情接口。", summaryFields));

    if (detail.last_error) {
      var errorBox = el("div", "callout danger");
      errorBox.textContent = "最近错误：" + detail.last_error;
      body.appendChild(errorBox);
    }

    var analysis = getAnalysis(detail);
    var analysisBody = el("div");
    var summary = analysisSummary(detail);
    var reason = analysisReason(detail);
    var confidence = analysisConfidence(detail);
    var analysisFields = el("div", "detail-grid");
    add(analysisFields,
      detailField("模型摘要", summary || "接口未返回模型摘要"),
      detailField("置信度", confidence === null ? "接口未返回置信度" : confidence.toFixed(0) + "%"),
      detailField("是否建议入库", detail.should_add_to_kb === true ? "建议入库" : (detail.should_add_to_kb === false ? "不建议入库" : "接口未提供")),
      detailField("分析理由", reason || "接口未返回判断理由")
    );
    add(analysisBody, analysisFields);
    body.appendChild(panel("模型判断", "摘要和判断理由仅展示接口实际返回的字段。", analysisBody));

    var logs = [];
    if (logsResult && logsResult.status === "fulfilled") logs = Array.isArray(logsResult.value.logs) ? logsResult.value.logs : [];
    if (!logs.length && Array.isArray(detail.processing_logs)) logs = detail.processing_logs;
    logs = logs.slice().sort(function (a, b) { return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime(); });
    var stages = stageEntries(detail, logs);
    var stageList = el("div", "stage-list");
    stages.forEach(function (stage) {
      var row = el("div", "stage-row" + (stage.status === "done" ? " done" : (stage.status === "error" ? " error" : "")));
      var marker = el("span", "stage-dot");
      if (stage.status === "done") marker.appendChild(iconNode("check", "ui-icon stage-icon"));
      else if (stage.status === "error") marker.appendChild(iconNode("alert", "ui-icon stage-icon"));
      else marker.textContent = "·";
      var copy = el("div");
      add(copy, el("div", "stage-name", stage.name), el("div", "stage-note", stage.log ? (stage.log.message || statusLabel(stage.log.status)) : "未记录该阶段日志"));
      var time = stage.log ? formatTime(stage.log.created_at) : "";
      add(row, marker, copy, el("span", "stage-time", time));
      stageList.appendChild(row);
    });
    body.appendChild(panel("处理流程", "没有阶段日志的步骤会标记为“未记录”，不会推断为已完成。", stageList));

    var logList = el("div", "log-list");
    if (!logs.length) {
      logList.appendChild(emptyState("暂无处理日志", logsResult && logsResult.status === "rejected" ? safeError(logsResult.reason) : "日志接口没有返回记录。", logsResult && logsResult.status === "rejected" ? "error" : "empty"));
    } else {
      logs.forEach(function (log) {
        var item = el("article", "log-entry");
        var head = el("header");
        add(head, el("span", "", (log.step || "处理步骤") + " · " + statusLabel(log.status)), el("span", "", formatDateTime(log.created_at)));
        add(item, head, el("p", "", log.message || "接口未提供日志内容"));
        logList.appendChild(item);
      });
    }
    body.appendChild(panel("处理日志", "日志以纯文本显示。", logList));

    var text = documentBody(detail);
    var contentBox = el("pre", "content-preview");
    if (text) contentBox.textContent = text;
    else contentBox.textContent = "正文接口未返回解析文本。当前详情接口若尚未暴露 parsed_content，此处会保持明确的空状态。";
    body.appendChild(panel("解析正文", "正文按纯文本安全展示，不会执行文件内容中的 HTML。", contentBox));

    var attachmentList = el("div", "attachment-list");
    if (attachmentsResult && attachmentsResult.status === "fulfilled") {
      var attachments = Array.isArray(attachmentsResult.value.attachments) ? attachmentsResult.value.attachments : [];
      if (!attachments.length) attachmentList.appendChild(emptyState("没有附件", attachmentsResult.value.message || "附件接口未返回相关文件。", "empty"));
      else attachments.forEach(function (attachment) {
        var item = el("div", "attachment-item");
        var label = el("span", "", attachment.imagefilename || attachment.filename || attachment.imagefileid || "附件");
        var link = el("a", "button button-small", "下载附件");
        link.href = API + "/oafile/download/" + encodeURIComponent(attachment.imagefileid || "");
        link.setAttribute("download", "");
        add(item, label, link);
        attachmentList.appendChild(item);
      });
    } else {
      attachmentList.appendChild(emptyState("附件暂不可用", attachmentsResult ? safeError(attachmentsResult.reason) : "尚未请求附件接口。", "error"));
    }
    body.appendChild(panel("附件", "附件通过现有文件下载接口提供。", attachmentList));
    els.drawerBody.replaceChildren(body);
  }

  async function openDocumentDetail(id) {
    var sequence = (state.detailSequence || 0) + 1;
    state.detailSequence = sequence;
    if (!id) { toast("缺少文件标识，无法打开详情。", "error"); return; }
    state.lastFocus = document.activeElement;
    showDrawerLoading(id);
    var results = await Promise.allSettled([
      request("/files/" + encodeURIComponent(id)),
      request("/logs/" + encodeURIComponent(id)),
      request("/files/" + encodeURIComponent(id) + "/attachments")
    ]);
    if (sequence !== state.detailSequence) return;
    if (results[0].status === "rejected") {
      els.drawerTitle.textContent = id;
      els.drawerBody.replaceChildren(emptyState("文档详情读取失败", safeError(results[0].reason), "error"));
      return;
    }
    renderDocumentDrawer(id, results[0].value, results[1], results[2]);
  }

  async function processDocument(id) {
    if (!id) return;
    try {
      var result = await request("/files/" + encodeURIComponent(id) + "/process", { method: "POST" });
      if (!result || result.success !== true || !result.task_id) throw new Error((result && result.message) || "服务端未确认处理任务已排队。");
      toast("处理任务已排队：" + result.task_id, "success");
      if (state.page === "documents") loadDocuments(false);
      if (state.page === "overview") loadOverview(false);
      closeDrawer();
    } catch (error) {
      toast("重新处理失败：" + safeError(error), "error");
    }
  }

  function openDocumentReview(id, approved) {
    var body = el("div");
    var reviewer = textInput("", "请输入审核人姓名");
    reviewer.id = "document-reviewer";
    reviewer.maxLength = 120;
    var comment = textarea("", approved ? "可填写批准依据或补充说明" : "说明拒绝原因");
    comment.id = "document-review-comment";
    comment.maxLength = 2000;
    var callout = el("div", approved ? "callout" : "callout warning");
    callout.textContent = approved ? "批准后，后台会重新读取、解析并继续入库；任务排队成功不代表已经入库完成。" : "拒绝后，这份文件将停止当前入库流程。请写明原因便于后续追踪。";
    add(body, createField("审核人", reviewer, "此姓名用于审核操作记录。"), createField("审核意见", comment, "意见会随审批请求交给后台任务。"), callout);
    var cancel = button("取消", "close-modal", "", {});
    var submit = button(approved ? "确认批准" : "确认拒绝", "", approved ? "button-primary" : "button-danger", {});
    submit.addEventListener("click", async function () {
      var name = reviewer.value.trim();
      if (!name) { reviewer.focus(); toast("请填写审核人。", "error"); return; }
      if (!approved && !comment.value.trim()) { comment.focus(); toast("拒绝时请填写原因。", "error"); return; }
      submit.disabled = true;
      var auditComment = "审核人：" + name + "\n审核意见：" + comment.value.trim();
      try {
        var result = await request("/files/" + encodeURIComponent(id) + "/approve", {
          method: "POST", body: { approved: !!approved, comment: auditComment }
        });
        if (!result || result.success !== true || !result.task_id) throw new Error((result && result.message) || "服务端未确认审批任务已排队。");
        closeModal();
        toast((approved ? "批准" : "拒绝") + "请求已提交，任务编号：" + result.task_id, "success");
        if (state.page === "approvals") loadApprovals(false);
        if (state.page === "documents") loadDocuments(false);
      } catch (error) {
        submit.disabled = false;
        toast("审批提交失败：" + safeError(error), "error");
      }
    });
    openModal(approved ? "批准并继续入库" : "拒绝入库", approved ? "请核对文档后记录审核人和意见。" : "拒绝操作会写入审核意见。", body, [cancel, submit]);
  }

  function openCleanupReview(id, approved) {
    var candidate = state.cleanup.items.filter(function (item) { return String(item.id) === String(id); })[0];
    var body = el("div");
    var name = cleanupObjectName(candidate && candidate.file_id);
    var reviewer = textInput("", "请输入审核人姓名");
    reviewer.id = "cleanup-reviewer";
    reviewer.maxLength = 200;
    var comment = textarea("", approved ? "可填写审核说明" : "说明拒绝原因");
    comment.id = "cleanup-review-comment";
    comment.maxLength = 2000;
    var warning = el("div", approved ? "callout warning" : "callout");
    warning.textContent = approved ? "此操作仅批准清理建议，不会删除知识库文档。删除必须再点击“执行清理”，并在下一步确认具体对象。" : "拒绝后该建议不能执行。请填写拒绝依据。";
    add(body, el("div", "callout", "审核对象：" + name), createField("审核人", reviewer, "必填，写入服务端清理审计记录。"), createField("审核意见", comment, "拒绝时必须填写。"), warning);
    var cancel = button("取消", "close-modal", "", {});
    var submit = button(approved ? "批准建议" : "拒绝建议", "", approved ? "button-primary" : "button-danger", {});
    submit.addEventListener("click", async function () {
      if (!reviewer.value.trim()) { reviewer.focus(); toast("请填写审核人。", "error"); return; }
      if (!approved && !comment.value.trim()) { comment.focus(); toast("拒绝时请填写原因。", "error"); return; }
      submit.disabled = true;
      try {
        var result = await request("/maintenance/cleanup-candidates/" + encodeURIComponent(id) + "/review", {
          method: "POST", body: { approved: !!approved, reviewer: reviewer.value.trim(), comment: comment.value.trim() }
        });
        if (!result || result.success !== true) throw new Error("服务端未确认审核结果已保存。");
        closeModal();
        toast(approved ? "清理建议已批准；尚未执行删除。" : "清理建议已拒绝。", "success");
        loadCleanup(false);
      } catch (error) {
        submit.disabled = false;
        toast("审核提交失败：" + safeError(error), "error");
      }
    });
    openModal(approved ? "审核并批准建议" : "拒绝清理建议", "候选文档：" + name, body, [cancel, submit]);
  }

  function openCleanupExecution(id) {
    var candidate = state.cleanup.items.filter(function (item) { return String(item.id) === String(id); })[0];
    if (!candidate) { toast("未找到这条清理建议，请刷新列表。", "error"); return; }
    var targetName = cleanupObjectName(candidate.file_id);
    var retainName = candidate.replacement_file_id ? cleanupObjectName(candidate.replacement_file_id) : "无替代文件";
    var body = el("div");
    var warning = el("div", "callout danger");
    warning.textContent = "此操作会提交知识库删除任务。请再次确认下方具体对象；服务端仍会检查文档版本、数据集身份和审核状态。";
    var facts = el("div", "detail-grid");
    add(facts,
      detailField("待清理文件", targetName),
      detailField("知识库文档编号", candidate.document_id || "未提供", true),
      detailField("目标数据集", candidate.dataset_id || "未提供", true),
      detailField("保留文件", retainName),
      detailField("审核人", candidate.reviewed_by || "未提供"),
      detailField("审核意见", candidate.review_comment || "未填写")
    );
    var acknowledge = el("label", "check-row");
    var checkbox = el("input");
    checkbox.type = "checkbox";
    checkbox.id = "cleanup-execution-confirm";
    var ackText = "我已核对待清理文件“" + targetName + "”及目标数据集，并确认提交执行。";
    add(acknowledge, checkbox, el("span", "", ackText));
    add(body, warning, facts, acknowledge);
    var cancel = button("取消", "close-modal", "", {});
    var submit = button(candidate.status === "failed" ? "提交重试" : "确认执行", "", "button-danger", {});
    submit.disabled = true;
    checkbox.addEventListener("change", function () { submit.disabled = !checkbox.checked; });
    submit.addEventListener("click", async function () {
      if (!checkbox.checked) return;
      submit.disabled = true;
      try {
        var result = await request("/maintenance/cleanup-candidates/" + encodeURIComponent(id) + "/execute", { method: "POST" });
        if (!result || result.success !== true || !result.task_id) throw new Error("服务端未确认清理任务已排队。");
        closeModal();
        toast("清理任务已排队：" + result.task_id + "。当前状态仍待后台执行结果确认。", "success");
        loadCleanup(false);
      } catch (error) {
        submit.disabled = !checkbox.checked;
        toast("执行清理失败：" + safeError(error), "error");
      }
    });
    openModal(candidate.status === "failed" ? "确认重试清理" : "确认执行清理", "将提交清理建议编号 " + candidate.id + " 对应的知识库删除任务。", body, [cancel, submit]);
  }

  function knowledgeItems(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.items)) return payload.items;
    if (payload && Array.isArray(payload.knowledge_bases)) return payload.knowledge_bases;
    return [];
  }

  function mappingItems(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.items)) return payload.items;
    if (payload && Array.isArray(payload.mappings)) return payload.mappings;
    return [];
  }

  async function loadSettings(manual) {
    if (state.settings.dirty) return;
    var tab = state.settings.tab;
    var tasks = [];
    var labels = [];
    if (tab === "runtime" && (!state.settings.loadedConfig || manual)) {
      state.settings.configLoading = true;
      state.settings.configError = "";
      tasks.push(request("/console/config"));
      labels.push("config");
    }
    if ((tab === "knowledge" || tab === "mapping") && (!state.settings.loadedKnowledge || manual)) {
      tasks.push(request("/console/knowledge-bases"));
      labels.push("knowledge");
    }
    if (tab === "mapping" && (!state.settings.loadedMappings || manual)) {
      tasks.push(request("/console/category-mappings"));
      labels.push("mappings");
    }
    if (state.page === "settings") renderSettings();
    if (!tasks.length) return;
    var results = await Promise.allSettled(tasks);
    results.forEach(function (result, index) {
      var key = labels[index];
      if (key === "config") {
        state.settings.configLoading = false;
        if (result.status === "fulfilled") {
          state.settings.config = result.value || {};
          state.settings.loadedConfig = true;
          state.settings.configError = "";
        } else {
          state.settings.config = null;
          state.settings.configError = safeError(result.reason);
        }
      }
      if (key === "knowledge") {
        if (result.status === "fulfilled") {
          state.settings.knowledgeBases = knowledgeItems(result.value);
          state.settings.loadedKnowledge = true;
          state.settings.knowledgeError = "";
        } else {
          state.settings.knowledgeBases = [];
          state.settings.knowledgeError = safeError(result.reason);
        }
      }
      if (key === "mappings") {
        if (result.status === "fulfilled") {
          state.settings.mappings = mappingItems(result.value);
          state.settings.loadedMappings = true;
          state.settings.mappingsError = "";
        } else {
          state.settings.mappings = [];
          state.settings.mappingsError = safeError(result.reason);
        }
      }
    });
    if (state.page === "settings") renderSettings();
    if (manual) {
      var errors = [state.settings.configError, state.settings.knowledgeError, state.settings.mappingsError].filter(Boolean);
      toast(errors.length ? "配置刷新失败：" + errors.join("；") : "配置数据已刷新。", errors.length ? "error" : "success");
    }
  }

  function changeSettingsTab(tab) {
    if (["runtime", "knowledge", "mapping"].indexOf(tab) < 0) return;
    if (state.settings.dirty) {
      openDiscardChangesDialog("切换配置页会丢弃当前未保存的修改。", function () {
        state.settings.dirty = false;
        state.settings.tab = tab;
        renderSettings();
        loadSettings(false);
      });
      return;
    }
    state.settings.tab = tab;
    renderSettings();
    loadSettings(false);
  }

  function renderSettingsTabs() {
    var tabs = el("div", "settings-tabs");
    [["runtime", "运行配置"], ["knowledge", "知识库管理"], ["mapping", "分类映射"]].forEach(function (item) {
      var tab = el("button", "settings-tab", item[1]);
      tab.type = "button";
      tab.dataset.action = "settings-tab";
      tab.dataset.tab = item[0];
      tab.setAttribute("aria-selected", state.settings.tab === item[0] ? "true" : "false");
      tabs.appendChild(tab);
    });
    return tabs;
  }

  function renderSettings() {
    var root = el("div");
    var refreshActions = el("div", "heading-actions");
    refreshActions.appendChild(button("刷新配置", "refresh-now", "button-small", {}));
    add(root, pageHeading("系统配置", "管理 NAS、解析、模型网关、Dify、清理规则、知识库和分类映射。", refreshActions));
    root.appendChild(renderSettingsTabs());
    var dirtyNote = el("div", "dirty-note", state.settings.dirty ? "有未保存的修改。自动刷新已跳过，离开前请保存或明确丢弃。" : "");
    dirtyNote.id = "settings-dirty-note";
    root.appendChild(dirtyNote);
    if (state.settings.tab === "runtime") root.appendChild(renderRuntimeSettings());
    else if (state.settings.tab === "knowledge") root.appendChild(renderKnowledgeSettings());
    else root.appendChild(renderMappingSettings());
    els.mainContent.replaceChildren(root);
  }

  function configLabels(keys) {
    var fields = state.settings.config && state.settings.config.fields || [];
    return keys.map(function (key) {
      var field = fields.filter(function (item) { return item.key === key; })[0];
      return field && field.label || key;
    }).join("、");
  }

  function groupLabel(group) {
    var names = {
      nas_import: "NAS 与导入", nas: "NAS 与导入", import: "NAS 与导入",
      parser: "解析与模型", model: "解析与模型", ai: "解析与模型", llm: "解析与模型",
      dify: "Dify 与分类映射", knowledge: "Dify 与分类映射",
      cleanup: "清理与筛选", filter: "清理与筛选",
      database: "基础连接", redis: "基础连接", base: "基础连接", infrastructure: "基础连接"
    };
    return names[String(group || "").toLowerCase()] || group || "其他配置";
  }

  function configFieldControl(field, values, secrets) {
    var key = String(field.key || "");
    var type = String(field.type || "text").toLowerCase();
    var secret = !!field.secret;
    var value = values && values[key];
    var isBoolean = ["bool", "boolean", "checkbox"].indexOf(type) >= 0;
    var input;
    var shell = el("div", "config-field" + (["textarea", "multiline"].indexOf(type) >= 0 ? " full-width" : ""));
    var labelId = "cfg-label-" + key.replace(/[^a-zA-Z0-9_-]/g, "-");
    var fieldHead = el("div", "field-head");
    var left = el("span", "field-label", field.label || key);
    left.id = labelId;
    fieldHead.appendChild(left);
    fieldHead.appendChild(el("span", "apply-tag", field.apply === "restart" ? "保存后需重启" : "即时生效"));
    shell.appendChild(fieldHead);
    if (secret) {
      var configured = !!(secrets && secrets[key]);
      input = textInput("", configured ? "已配置；留空保留原值" : "未配置；输入后保存", "password");
      input.autocomplete = "new-password";
      input.dataset.configKey = key;
      input.dataset.secret = "true";
      input.setAttribute("aria-labelledby", labelId);
      shell.appendChild(input);
      var stateText = el("div", "secret-status" + (configured ? "" : " not-set"), configured ? "已配置，页面不回显" : "未配置");
      shell.appendChild(stateText);
      if (field.display_value) shell.appendChild(el("p", "field-help", "连接地址摘要：" + field.display_value + "。此摘要只用于识别目标，不会作为密钥值提交。"));
      if (configured && field.clearable !== false) {
        var clearLabel = el("label", "check-row");
        var clear = el("input");
        clear.type = "checkbox";
        clear.dataset.clearSecret = key;
        add(clearLabel, clear, el("span", "", "清除已保存值"));
        shell.appendChild(clearLabel);
      }
    } else if (isBoolean) {
      var label = el("label", "check-row");
      input = el("input");
      input.type = "checkbox";
      input.checked = value === true || value === "true" || value === 1;
      input.dataset.configKey = key;
      input.dataset.configType = type;
      input.setAttribute("aria-labelledby", labelId);
      add(label, input, el("span", "", input.checked ? "已启用" : "已停用"));
      shell.appendChild(label);
    } else if (type === "select" || (Array.isArray(field.options) && field.options.length)) {
      var opts = (field.options || []).map(function (option) {
        return { value: option.value, label: option.label || String(option.value) };
      });
      input = selectControl(opts, value);
      input.dataset.configKey = key;
      input.dataset.configType = type;
      input.setAttribute("aria-labelledby", labelId);
      shell.appendChild(input);
    } else if (["textarea", "multiline"].indexOf(type) >= 0) {
      input = textarea(value, field.help || "");
      input.dataset.configKey = key;
      input.dataset.configType = type;
      input.setAttribute("aria-labelledby", labelId);
      shell.appendChild(input);
    } else {
      var inputType = ["integer", "int", "number", "float", "decimal"].indexOf(type) >= 0 ? "number" : (type === "url" ? "url" : "text");
      input = textInput(value, "", inputType);
      input.dataset.configKey = key;
      input.dataset.configType = type;
      input.setAttribute("aria-labelledby", labelId);
      if (field.min !== undefined && field.min !== null) input.min = String(field.min);
      if (field.max !== undefined && field.max !== null) input.max = String(field.max);
      if (inputType === "number") input.step = type === "float" || type === "decimal" ? "any" : "1";
      shell.appendChild(input);
    }
    if (field.help) shell.appendChild(el("p", "field-help", field.help));
    return shell;
  }

  function renderRuntimeSettings() {
    var wrapper = el("div");
    var config = state.settings.config;
    if (state.settings.configError) return emptyState("配置读取失败", state.settings.configError, "error", "refresh-now");
    if (!config) return emptyState(state.settings.configLoading ? "正在读取系统配置" : "尚未读取系统配置", "读取失败时不会显示默认值冒充当前配置。", state.settings.configLoading ? "loading" : "empty", "refresh-now");
    var fields = Array.isArray(config.fields) ? config.fields : [];
    if (!fields.length) return emptyState("服务端没有返回可编辑配置项", "请确认后端配置接口已提供字段定义。", "empty");
    var groups = {};
    fields.forEach(function (field) {
      var label = groupLabel(field.group);
      if (!groups[label]) groups[label] = [];
      groups[label].push(field);
    });
    Object.keys(groups).forEach(function (name) {
      var section = el("section", "settings-group");
      section.appendChild(el("h2", "", name));
      var grid = el("div", "config-grid");
      groups[name].forEach(function (field) { grid.appendChild(configFieldControl(field, config.values || {}, config.secrets || {})); });
      section.appendChild(grid);
      wrapper.appendChild(section);
    });
    var restart = Array.isArray(config.restart_required) ? config.restart_required : [];
    if (state.settings.conflict) {
      var conflict = el("div", "callout warning");
      conflict.textContent = "保存时发现配置版本已被其他操作更新。此次修改未覆盖服务端新版本；请明确丢弃当前表单后重新载入，再决定如何修改。";
      wrapper.appendChild(conflict);
      var reload = button("丢弃当前修改并重新载入", "discard-reload-config", "button-small", {});
      wrapper.appendChild(reload);
    }
    var note = el("div", "callout");
    note.textContent = "热配置会在 API 后续请求及 Worker 后续任务中读取；运行中的任务继续使用开始时配置。数据库、Redis 等基础连接参数不会自动切换，需要重启 API、Worker 和 Beat。";
    if (restart.length) note.textContent += " 当前待重启项：" + configLabels(restart) + "。";
    wrapper.appendChild(note);
    var footer = el("div", "config-footer");
    var footerCopy = el("div");
    add(footerCopy, el("span", "version-badge", "配置版本 " + (config.version === undefined ? "未提供" : config.version)), el("p", "", "最近更新：" + formatDateTime(config.updated_at)));
    var footerActions = el("div", "heading-actions");
    footerActions.appendChild(button("保存配置", "save-config", "button-primary", {}));
    add(footer, footerCopy, footerActions);
    wrapper.appendChild(footer);
    return wrapper;
  }

  function markSettingsDirty() {
    state.settings.dirty = true;
    var note = byId("settings-dirty-note");
    if (note) note.textContent = "有未保存的修改。自动刷新已跳过，离开前请保存或明确丢弃。";
  }

  function configValueFromControl(control) {
    if (control.type === "checkbox") return !!control.checked;
    var type = control.dataset.configType || "text";
    if (["int", "integer"].indexOf(type) >= 0) return control.value === "" ? null : parseInt(control.value, 10);
    if (["number", "float", "decimal"].indexOf(type) >= 0) return control.value === "" ? null : Number(control.value);
    return control.value;
  }

  async function saveRuntimeConfig() {
    if (!state.settings.config || !state.settings.config.fields) return;
    var config = state.settings.config;
    var values = {};
    var clearSecrets = [];
    var invalid = false;
    var firstInvalidControl = null;
    config.fields.forEach(function (field) {
      var key = String(field.key || "");
      var control = findByDataValue("data-config-key", key);
      if (field.secret) {
        var clear = findByDataValue("data-clear-secret", key);
        if (clear && clear.checked) clearSecrets.push(key);
        if (control && control.value && !(clear && clear.checked)) values[key] = control.value;
      } else if (control) {
        var value = configValueFromControl(control);
        if (control.type === "number" && control.value !== "" && !isFinite(Number(control.value))) invalid = true;
        if (!control.checkValidity()) {
          invalid = true;
          if (!firstInvalidControl) firstInvalidControl = control;
        }
        var previous = config.values ? config.values[key] : undefined;
        var previousValue = previous;
        if (control.type === "checkbox") previousValue = previous === true || previous === "true" || previous === 1;
        else if (["int", "integer"].indexOf(control.dataset.configType || "") >= 0 && previous !== null && previous !== undefined && previous !== "") previousValue = parseInt(previous, 10);
        else if (["number", "float", "decimal"].indexOf(control.dataset.configType || "") >= 0 && previous !== null && previous !== undefined && previous !== "") previousValue = Number(previous);
        if (value !== previousValue) values[key] = value;
      }
    });
    if (invalid) {
      if (firstInvalidControl && firstInvalidControl.reportValidity) firstInvalidControl.reportValidity();
      else toast("有数值配置格式无效，请检查后再保存。", "error");
      return;
    }
    if (!Object.keys(values).length && !clearSecrets.length) {
      state.settings.dirty = false;
      renderSettings();
      toast("没有需要保存的配置修改。", "");
      return;
    }
    state.settings.saving = true;
    var saveButton = document.querySelector('[data-action="save-config"]');
    if (saveButton) saveButton.disabled = true;
    try {
      var result = await request("/console/config", {
        method: "PATCH",
        body: { version: config.version, values: values, clear_secrets: clearSecrets, operator: "页面操作" }
      });
      if (!result || result.success !== true) throw new Error((result && result.message) || "服务端未确认配置已保存。");
      state.settings.dirty = false;
      state.settings.conflict = false;
      state.settings.configLoading = true;
      var hot = Array.isArray(result.hot_applied) ? result.hot_applied : [];
      var restart = Array.isArray(result.restart_required) ? result.restart_required : [];
      await loadSettings(true);
      var message = result.message || "配置已持久化。";
      if (hot.length) message += " 即时生效：" + configLabels(hot) + "。";
      if (restart.length) message += " 需重启 API、Worker、Beat：" + configLabels(restart) + "。";
      toast(message, "success");
    } catch (error) {
      if (error && error.status === 409) {
        state.settings.conflict = true;
        // 保留用户正在编辑的 DOM；不能用旧的服务端值重绘表单覆盖草稿。
        if (!byId("runtime-config-conflict")) {
          var conflictNotice = el("div", "callout warning", "配置已被其他操作更新，本次修改未保存。当前输入已保留；请明确丢弃草稿后读取最新版本再保存。");
          conflictNotice.id = "runtime-config-conflict";
          var reloadAction = button("丢弃当前修改并重新载入", "discard-reload-config", "button-small", {});
          conflictNotice.appendChild(reloadAction);
          var footer = document.querySelector(".config-footer");
          if (footer && footer.parentNode) footer.parentNode.insertBefore(conflictNotice, footer);
        }
      }
      toast("配置保存失败：" + safeError(error), "error");
      if (saveButton) saveButton.disabled = false;
    } finally {
      state.settings.saving = false;
    }
  }

  function knowledgeStatusLabel(value) {
    var status = String(value || "").toUpperCase();
    if (status === "ACTIVE") return "启用";
    if (status === "INACTIVE") return "停用";
    if (status === "MAINTENANCE") return "维护中";
    return value || "状态未知";
  }

  function knowledgeCard(item) {
    var id = item.id;
    var card = el("article", "kb-card");
    var header = el("div", "kb-card-header");
    var copy = el("div");
    add(copy, el("h3", "", item.name || "未命名知识库"), el("p", "", (item.description || "暂无描述") + " · " + knowledgeStatusLabel(item.status)));
    var configured = item.api_key_configured ? "密钥已配置（不回显）" : "密钥未配置";
    add(header, copy, statusPill(configured, item.api_key_configured ? "completed" : "pending"));
    card.appendChild(header);
    var grid = el("div", "kb-edit-grid");
    function fieldControl(labelText, key, value, type, wide, help) {
      var input = type === "textarea" ? textarea(value, "") : textInput(value, type === "password" ? "留空保留已有密钥" : "", type === "password" ? "password" : "text");
      input.dataset.kbId = String(id);
      input.dataset.kbKey = key;
      if (type === "password") input.autocomplete = "new-password";
      var wrap = createField(labelText, input, help, wide ? "full-width" : "");
      grid.appendChild(wrap);
    }
    fieldControl("知识库名称", "name", item.name, "text", false, "");
    fieldControl("Dify 数据集 ID", "dify_dataset_id", item.dify_dataset_id, "text", false, "已有入库文档后，服务端可能禁止更改数据集身份。");
    fieldControl("Dify 接口地址", "base_url", item.base_url, "text", false, "留空使用系统默认地址。" );
    fieldControl("API Key", "api_key", "", "password", false, configured);
    fieldControl("描述", "description", item.description, "textarea", true, "");
    if (item.api_key_configured) {
      var clearKey = el("input");
      clearKey.type = "checkbox";
      clearKey.dataset.kbId = String(id);
      clearKey.dataset.kbKey = "clear_api_key";
      var clearWrap = el("label", "check-row");
      add(clearWrap, clearKey, el("span", "", "清除本库专用密钥，改用系统默认密钥"));
      grid.appendChild(clearWrap);
    }
    var statusSelect = selectControl([
      { value: "ACTIVE", label: "启用" },
      { value: "INACTIVE", label: "停用" },
      { value: "MAINTENANCE", label: "维护中" }
    ], String(item.status || "ACTIVE").toUpperCase());
    statusSelect.dataset.kbId = String(id);
    statusSelect.dataset.kbKey = "status";
    grid.appendChild(createField("状态", statusSelect, ""));
    card.appendChild(grid);
    var footer = el("div", "mapping-actions");
    footer.appendChild(button("保存知识库", "save-knowledge-base", "button-small", { id: id }));
    footer.appendChild(el("span", "subtle tiny", "数据集身份变更由服务端按已入库文档校验。"));
    card.appendChild(footer);
    return card;
  }

  function renderKnowledgeSettings() {
    var wrapper = el("div");
    if (state.settings.knowledgeError) return emptyState("知识库配置读取失败", state.settings.knowledgeError, "error", "refresh-now");
    if (!state.settings.loadedKnowledge) return emptyState("正在读取知识库配置", "知识库密钥只显示是否已配置。", "loading");
    var list = el("div");
    if (!state.settings.knowledgeBases.length) list.appendChild(emptyState("尚未配置知识库", "可在下方添加 Dify 数据集配置。", "empty"));
    else state.settings.knowledgeBases.forEach(function (item) { list.appendChild(knowledgeCard(item)); });
    wrapper.appendChild(panel("已配置知识库", "现有 API Key 不会回显。更换密钥时输入新值；留空会保留原值。", list));

    var addCard = el("section", "settings-group");
    addCard.appendChild(el("h2", "", "添加知识库"));
    var grid = el("div", "config-grid");
    var newName = textInput("", "业务知识库名称"); newName.id = "new-kb-name";
    var newDataset = textInput("", "Dify 数据集 ID"); newDataset.id = "new-kb-dataset";
    var newUrl = textInput("", "http://dify.internal"); newUrl.id = "new-kb-url";
    var newKey = textInput("", "API Key", "password"); newKey.id = "new-kb-key"; newKey.autocomplete = "new-password";
    var newDescription = textarea("", "用途说明"); newDescription.id = "new-kb-description";
    add(grid,
      createField("知识库名称", newName, ""),
      createField("Dify 数据集 ID", newDataset, "数据集 ID 会与入库文档绑定。"),
      createField("Dify 接口地址", newUrl, "可留空使用系统地址。"),
      createField("API Key", newKey, "只在提交时发送，保存后不会回显。"),
      createField("描述", newDescription, "", "full-width")
    );
    addCard.appendChild(grid);
    addCard.appendChild(button("添加知识库", "create-knowledge-base", "button-primary", {}));
    wrapper.appendChild(addCard);
    return wrapper;
  }

  function mappingRow(item, index) {
    var row = el("div", "mapping-row");
    row.dataset.mappingIndex = String(index);
    var category = selectControl(CATEGORY_OPTIONS.map(function (entry) { return { value: entry[0], label: entry[1] }; }), item.business_category);
    category.dataset.mapField = "business_category";
    category.dataset.mappingIndex = String(index);
    var kbOptions = state.settings.knowledgeBases.map(function (kb) { return { value: kb.id, label: kb.name + " · " + kb.dify_dataset_id }; });
    var knowledge = selectControl(kbOptions, item.knowledge_base_id, "选择知识库");
    knowledge.dataset.mapField = "knowledge_base_id";
    knowledge.dataset.mappingIndex = String(index);
    var confidence = textInput(item.min_confidence_score === undefined ? 70 : item.min_confidence_score, "70", "number");
    confidence.min = "0"; confidence.max = "100"; confidence.step = "1";
    confidence.dataset.mapField = "min_confidence_score";
    confidence.dataset.mappingIndex = String(index);
    var threshold = textInput(item.auto_approve_threshold === undefined ? 90 : item.auto_approve_threshold, "90", "number");
    threshold.min = "0"; threshold.max = "100"; threshold.step = "1";
    threshold.dataset.mapField = "auto_approve_threshold";
    threshold.dataset.mappingIndex = String(index);
    var prompt = textarea(item.ai_prompt_template || "", "输入该分类的模型提示词");
    prompt.dataset.mapField = "ai_prompt_template";
    prompt.dataset.mappingIndex = String(index);
    var active = el("input");
    active.type = "checkbox";
    active.checked = item.is_active !== false;
    active.dataset.mapField = "is_active";
    active.dataset.mappingIndex = String(index);
    var activeWrap = el("label", "check-row");
    add(activeWrap, active, el("span", "", active.checked ? "启用" : "停用"));
    var remove = button("移除", "remove-mapping", "button-small", { index: index });
    add(row,
      createField("业务分类", category, ""),
      createField("目标知识库", knowledge, ""),
      createField("最低置信度", confidence, "0–100"),
      createField("自动审核阈值", threshold, "0–100"),
      createField("模型提示词", prompt, ""),
      createField("状态", activeWrap, ""),
      remove
    );
    return row;
  }

  function renderMappingSettings() {
    var wrapper = el("div");
    if (state.settings.knowledgeError) return emptyState("知识库配置读取失败", state.settings.knowledgeError, "error", "refresh-now");
    if (state.settings.mappingsError) return emptyState("分类映射读取失败", state.settings.mappingsError, "error", "refresh-now");
    if (!state.settings.loadedMappings || !state.settings.loadedKnowledge) return emptyState("正在读取分类映射", "正在读取业务分类和知识库配置。", "loading");
    var note = el("div", "callout");
    note.textContent = "每个业务分类可绑定目标知识库，并设置最低置信度、自动审核阈值与模型提示词。保存后服务端会更新持久化映射并清空相关缓存。";
    wrapper.appendChild(note);
    var mappingPanel = el("section", "settings-group");
    var header = el("div", "panel-header");
    var copy = el("div");
    add(copy, el("h2", "", "业务分类映射"), el("p", "", "未保存的修改不会影响正在运行的任务。"));
    add(header, copy, button("新增分类映射", "add-mapping", "button-small", {}));
    mappingPanel.appendChild(header);
    if (!state.settings.mappings.length) mappingPanel.appendChild(emptyState("暂无分类映射", "新增后选择分类及目标知识库。", "empty"));
    else {
      var scroll = el("div", "mapping-scroll");
      state.settings.mappings.forEach(function (item, index) { scroll.appendChild(mappingRow(item, index)); });
      mappingPanel.appendChild(scroll);
    }
    mappingPanel.appendChild(button("保存分类映射", "save-mappings", "button-primary", {}));
    wrapper.appendChild(mappingPanel);
    return wrapper;
  }

  function mappingRowsFromForm() {
    var rows = {};
    document.querySelectorAll("[data-map-field]").forEach(function (control) {
      var index = Number(control.dataset.mappingIndex);
      var field = control.dataset.mapField;
      if (!rows[index]) rows[index] = {};
      if (field === "is_active") rows[index][field] = !!control.checked;
      else if (field === "min_confidence_score" || field === "auto_approve_threshold" || field === "knowledge_base_id") rows[index][field] = control.value === "" ? null : Number(control.value);
      else rows[index][field] = control.value;
    });
    return Object.keys(rows).sort(function (a, b) { return Number(a) - Number(b); }).map(function (index) {
      var row = rows[index];
      return {
        business_category: row.business_category || "",
        knowledge_base_id: row.knowledge_base_id,
        min_confidence_score: row.min_confidence_score,
        auto_approve_threshold: row.auto_approve_threshold,
        ai_prompt_template: row.ai_prompt_template || "",
        is_active: row.is_active !== false
      };
    });
  }

  async function saveKnowledgeBase(id) {
    var otherDrafts = [];
    document.querySelectorAll("[data-kb-key]").forEach(function (control) {
      if (control.dataset.kbId === String(id)) return;
      var baseline = state.settings.knowledgeBases.filter(function (item) { return String(item.id) === control.dataset.kbId; })[0];
      var key = control.dataset.kbKey;
      var value = control.type === "checkbox" ? control.checked : control.value;
      var original = key === "api_key" ? "" : key === "clear_api_key" ? false : (baseline && baseline[key] || "");
      if (value !== original) otherDrafts.push({id: control.dataset.kbId, key: key, value: value});
    });
    var newDraft = {};
    ["name", "dataset", "url", "key", "description"].forEach(function (key) {
      var input = byId("new-kb-" + key);
      if (input && input.value) newDraft[key] = input.value;
    });
    var body = {};
    var controls = document.querySelectorAll("[data-kb-id]");
    var matchingControls = Array.prototype.filter.call(controls, function (control) { return control.dataset.kbId === String(id); });
    matchingControls.forEach(function (control) {
      var key = control.dataset.kbKey;
      if (!key) return;
      if (key === "api_key") {
        if (control.value) body.api_key = control.value;
      } else body[key] = control.type === "checkbox" ? control.checked : control.value;
    });
    if (body.clear_api_key) delete body.api_key;
    if (body.base_url !== undefined && !body.base_url.trim()) body.base_url = null;
    if (body.description !== undefined && body.description === "") body.description = "";
    try {
      await request("/console/knowledge-bases/" + encodeURIComponent(id), { method: "PATCH", body: body });
      matchingControls.forEach(function (control) { if (control.dataset.kbKey === "api_key") control.value = ""; });
      state.settings.dirty = false;
      state.settings.loadedKnowledge = false;
      await loadSettings(true);
      otherDrafts.forEach(function (draft) {
        var control = document.querySelector('[data-kb-id="' + draft.id + '"][data-kb-key="' + draft.key + '"]');
        if (control) {
          if (control.type === "checkbox") control.checked = draft.value;
          else control.value = draft.value;
        }
      });
      Object.keys(newDraft).forEach(function (key) { var input = byId("new-kb-" + key); if (input) input.value = newDraft[key]; });
      if (otherDrafts.length || Object.keys(newDraft).length) markSettingsDirty();
      toast("当前知识库配置已保存，其他未保存输入已保留。密钥不会在页面回显。", "success");
    } catch (error) {
      toast("知识库保存失败：" + safeError(error), "error");
    }
  }

  async function createKnowledgeBase() {
    var name = byId("new-kb-name");
    var dataset = byId("new-kb-dataset");
    var url = byId("new-kb-url");
    var key = byId("new-kb-key");
    var description = byId("new-kb-description");
    if (!name.value.trim()) { name.focus(); toast("请填写知识库名称。", "error"); return; }
    if (!dataset.value.trim()) { dataset.focus(); toast("请填写 Dify 数据集 ID。", "error"); return; }
    var payload = {
      name: name.value.trim(),
      description: description.value,
      dify_dataset_id: dataset.value.trim(),
      base_url: url.value.trim() || null,
      status: "ACTIVE"
    };
    if (key.value) payload.api_key = key.value;
    try {
      await request("/console/knowledge-bases", { method: "POST", body: payload });
      key.value = "";
      state.settings.dirty = false;
      state.settings.loadedKnowledge = false;
      await loadSettings(true);
      toast("知识库已添加。API Key 只由服务端保存。", "success");
    } catch (error) {
      toast("添加知识库失败：" + safeError(error), "error");
    }
  }

  async function saveMappings() {
    var rows = mappingRowsFromForm();
    var seenCategories = {};
    var invalid = false;
    rows.forEach(function (row) {
      if (!row.business_category || !row.knowledge_base_id || seenCategories[row.business_category]) invalid = true;
      seenCategories[row.business_category] = true;
      if (row.min_confidence_score === null || row.min_confidence_score < 0 || row.min_confidence_score > 100 || row.auto_approve_threshold === null || row.auto_approve_threshold < 0 || row.auto_approve_threshold > 100) invalid = true;
    });
    if (invalid) { toast("请检查分类映射：每条记录须有唯一分类、目标知识库和 0–100 的阈值。", "error"); return; }
    try {
      await request("/console/category-mappings", { method: "PUT", body: { items: rows } });
      state.settings.dirty = false;
      state.settings.loadedMappings = false;
      await loadSettings(true);
      toast("分类映射已保存，缓存将由服务端清理。", "success");
    } catch (error) {
      toast("分类映射保存失败：" + safeError(error), "error");
    }
  }

  function addMappingRow() {
    var current = mappingRowsFromForm();
    var used = {};
    current.forEach(function (item) { used[item.business_category] = true; });
    var next = CATEGORY_OPTIONS.filter(function (item) { return !used[item[0]]; })[0];
    if (!next) { toast("所有业务分类都已有映射。", ""); return; }
    var firstKb = state.settings.knowledgeBases[0];
    current.push({
      business_category: next[0],
      knowledge_base_id: firstKb ? firstKb.id : null,
      min_confidence_score: 70,
      auto_approve_threshold: 90,
      ai_prompt_template: "",
      is_active: true
    });
    state.settings.mappings = current;
    markSettingsDirty();
    renderSettings();
  }

  function removeMappingRow(index) {
    var current = mappingRowsFromForm();
    current.splice(Number(index), 1);
    state.settings.mappings = current;
    markSettingsDirty();
    renderSettings();
  }

  function openDiscardChangesDialog(message, onDiscard) {
    var body = el("div", "callout warning", message + "未保存内容会从当前页面清除。此操作不会改动服务端已保存配置。");
    var cancel = button("继续编辑", "close-modal", "", {});
    var discard = button("丢弃修改并继续", "", "button-danger", {});
    discard.addEventListener("click", function () {
      closeModal();
      state.settings.conflict = false;
      onDiscard();
    });
    openModal("丢弃未保存修改？", "当前表单包含尚未保存的内容。", body, [cancel, discard]);
  }

  function requestPageChange(page) {
    if (state.page === "settings" && state.settings.dirty && page !== "settings") {
      openDiscardChangesDialog("离开系统配置页会丢弃当前修改。", function () {
        state.settings.dirty = false;
        setPage(page);
      });
      return;
    }
    setPage(page);
  }

  function cleanValue(value, fallback) {
    return value === undefined || value === null || value === "" ? (fallback || "—") : value;
  }

  async function runHealthCheck() {
    state.overview.errors.health = "";
    toast("正在请求系统连接检测…");
    try {
      state.overview.health = await request("/system/status");
      state.overview.healthLoadedAt = Date.now();
      state.overview.errors.health = "";
      if (state.page === "overview") renderOverview();
      toast("系统连接状态已更新。", "success");
    } catch (error) {
      state.overview.health = null;
      state.overview.healthLoadedAt = Date.now();
      state.overview.errors.health = safeError(error);
      if (state.page === "overview") renderOverview();
      toast("系统检测失败：" + state.overview.errors.health, "error");
    }
  }

  async function handleAction(actionNode) {
    var action = actionNode.dataset.action;
    var id = actionNode.dataset.id;
    if (action === "navigate") { requestPageChange(actionNode.dataset.page); return; }
    if (action === "refresh-now") {
      if (state.page === "settings" && state.settings.dirty) { toast("有未保存修改，已跳过刷新以保护当前输入。", ""); return; }
      refreshCurrent(true);
      return;
    }
    if (action === "refresh-health") { runHealthCheck(); return; }
    if (action === "open-run") { openRunModal(actionNode.dataset.preset || "import"); return; }
    if (action === "search-documents") {
      var search = byId("document-search");
      if (search) state.documents.filters.q = search.value;
      state.documents.page = 1;
      loadDocuments(false);
      return;
    }
    if (action === "documents-page") { state.documents.page = Number(actionNode.dataset.page) || 1; loadDocuments(false); return; }
    if (action === "cleanup-page") { state.cleanup.page = Number(actionNode.dataset.page) || 1; loadCleanup(false); return; }
    if (action === "document-detail") { openDocumentDetail(id); return; }
    if (action === "download-file") {
      if (!id) { toast("缺少文件标识，无法下载。", "error"); return; }
      window.location.href = API + "/oafile/download/" + encodeURIComponent(id);
      return;
    }
    if (action === "process-file") { processDocument(id); return; }
    if (action === "review-document") { openDocumentReview(id, actionNode.dataset.approved === "true"); return; }
    if (action === "review-cleanup") { openCleanupReview(id, actionNode.dataset.approved === "true"); return; }
    if (action === "execute-cleanup") { openCleanupExecution(id); return; }
    if (action === "scan-cleanup" || action === "scan-versions") {
      var scanAction = action === "scan-cleanup" ? "scan_cleanup" : "scan_versions";
      var scanPayload = { limit: 50, dry_run: true };
      try { await submitAction(scanAction, scanPayload); }
      catch (error) { toast("预览扫描提交失败：" + safeError(error), "error"); }
      return;
    }
    if (action === "settings-tab") { changeSettingsTab(actionNode.dataset.tab); return; }
    if (action === "save-config") { saveRuntimeConfig(); return; }
    if (action === "discard-reload-config") {
      openDiscardChangesDialog("重新读取会丢弃当前修改，并使用服务端最新配置版本。", function () {
        state.settings.dirty = false;
        state.settings.loadedConfig = false;
        state.settings.config = null;
        loadSettings(true);
      });
      return;
    }
    if (action === "save-knowledge-base") { saveKnowledgeBase(actionNode.dataset.id); return; }
    if (action === "create-knowledge-base") { createKnowledgeBase(); return; }
    if (action === "add-mapping") { addMappingRow(); return; }
    if (action === "remove-mapping") { removeMappingRow(actionNode.dataset.index); return; }
    if (action === "save-mappings") { saveMappings(); return; }
    if (action === "close-modal") { closeModal(); return; }
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      if (!els.modalLayer.hidden) { closeModal(); event.preventDefault(); return; }
      if (!els.drawerLayer.hidden) { closeDrawer(); event.preventDefault(); return; }
      if (els.sidebar.classList.contains("is-open")) {
        els.sidebar.classList.remove("is-open");
        els.mobileMenu.setAttribute("aria-expanded", "false");
        event.preventDefault();
      }
    }
    var dialog = !els.modalLayer.hidden ? els.modalCard : (!els.drawerLayer.hidden ? els.detailDrawer : null);
    if (!dialog || event.key !== "Tab") return;
    var focusable = dialog.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])");
    var list = Array.prototype.slice.call(focusable).filter(function (item) { return !item.hidden && item.getClientRects().length > 0; });
    if (!list.length) { event.preventDefault(); dialog.focus(); return; }
    var first = list[0];
    var last = list[list.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function onSettingsInput(event) {
    var target = event.target;
    if (!target) return;
    if (target.dataset.configKey || target.dataset.clearSecret !== undefined || target.dataset.kbKey || target.dataset.mapField || (target.id && target.id.indexOf("new-kb-") === 0)) {
      markSettingsDirty();
    }
    if (target.dataset.mapField === "is_active") {
      var next = target.nextElementSibling;
      if (next) next.textContent = target.checked ? "启用" : "停用";
    }
    if (target.dataset.configKey && target.type === "checkbox") {
      var label = target.nextElementSibling;
      if (label) label.textContent = target.checked ? "已启用" : "已停用";
    }
  }

  function initialize() {
    els = {
      mainContent: byId("main-content"),
      pageTitle: byId("page-title"),
      globalDate: byId("global-date"),
      refreshToggle: byId("refresh-toggle"),
      refreshLabel: byId("refresh-label"),
      runAction: byId("run-action"),
      refreshNow: byId("refresh-now"),
      mobileMenu: byId("mobile-menu"),
      sidebar: byId("sidebar"),
      modalLayer: byId("modal-layer"),
      modalCard: byId("modal-card"),
      modalTitle: byId("modal-title"),
      modalDescription: byId("modal-description"),
      modalBody: byId("modal-body"),
      modalFooter: byId("modal-footer"),
      modalClose: byId("modal-close"),
      drawerLayer: byId("drawer-layer"),
      detailDrawer: byId("detail-drawer"),
      drawerTitle: byId("drawer-title"),
      drawerBody: byId("drawer-body"),
      drawerClose: byId("drawer-close"),
      toastRegion: byId("toast-region")
    };
    els.globalDate.value = state.date;
    els.refreshToggle.setAttribute("aria-pressed", "true");
    document.querySelectorAll(".nav-item[data-page]").forEach(function (item) {
      item.addEventListener("click", function () { requestPageChange(item.dataset.page); });
    });
    els.globalDate.addEventListener("change", function () { setGlobalDate(els.globalDate.value); });
    els.refreshToggle.addEventListener("click", toggleAutoRefresh);
    els.refreshNow.addEventListener("click", function () {
      if (state.page === "settings" && state.settings.dirty) { toast("有未保存修改，已跳过刷新以保护当前输入。", ""); return; }
      refreshCurrent(true);
    });
    els.runAction.addEventListener("click", function () { openRunModal("import"); });
    els.mobileMenu.addEventListener("click", function () {
      var open = !els.sidebar.classList.contains("is-open");
      els.sidebar.classList.toggle("is-open", open);
      els.mobileMenu.setAttribute("aria-expanded", open ? "true" : "false");
    });
    els.modalClose.addEventListener("click", closeModal);
    els.drawerClose.addEventListener("click", closeDrawer);
    els.modalLayer.addEventListener("click", function (event) {
      if (event.target.dataset.closeModal === "true") closeModal();
      var actionNode = event.target.closest ? event.target.closest('[data-action="close-modal"]') : null;
      if (actionNode) closeModal();
    });
    els.drawerLayer.addEventListener("click", function (event) {
      if (event.target.dataset.closeDrawer === "true") closeDrawer();
    });
    els.drawerBody.addEventListener("click", function (event) {
      var actionNode = event.target.closest ? event.target.closest("[data-action]") : null;
      if (actionNode) handleAction(actionNode);
    });
    els.mainContent.addEventListener("click", function (event) {
      var actionNode = event.target.closest ? event.target.closest("[data-action]") : null;
      if (actionNode) handleAction(actionNode);
    });
    els.modalBody.addEventListener("click", function (event) {
      var actionNode = event.target.closest ? event.target.closest("[data-action]") : null;
      if (actionNode) handleAction(actionNode);
    });
    els.mainContent.addEventListener("input", onSettingsInput);
    els.mainContent.addEventListener("change", onSettingsInput);
    document.addEventListener("keydown", onKeyDown);
    state.timer = window.setInterval(function () {
      if (state.autoRefresh) refreshCurrent(false);
    }, 15000);
    renderOverview();
    loadOverview(false);
  }

  document.addEventListener("DOMContentLoaded", initialize);
})();
