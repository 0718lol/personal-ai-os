const state = {
  view: "home",
  dashboard: null,
  sources: [],
  notes: [],
  tasks: [],
  collections: [],
  playbooks: [],
  memories: [],
  agents: [],
  runs: [],
  connectors: [],
  selectedSource: null,
  chat: [],
  conversationId: null,
  noteQuery: "",
  notePage: 1,
  toastTimer: null,
};

const NOTE_PAGE_SIZE = 10;

const navItems = [
  ["home", "首页"],
  ["playbooks", "场景方案"],
  ["sources", "资料库"],
  ["search", "搜索"],
  ["chat", "问答"],
  ["notes", "笔记"],
  ["collections", "工作区"],
  ["tasks", "任务"],
  ["memories", "记忆"],
  ["agents", "智能体"],
  ["runs", "运行记录"],
  ["connectors", "连接器"],
  ["settings", "设置"],
];

const routeAliases = {
  workspace: "collections",
  workspaces: "collections",
  collection: "collections",
  library: "sources",
  source: "sources",
  memories_review: "memories",
  agent_runs: "runs",
};

const text = {
  navGroups: ["操作", "整理", "自动化", "系统"],
  status: {
    ready: "已就绪",
    empty: "无可抽取文本",
    open: "待处理",
    done: "已完成",
    candidate: "待审核",
    approved: "已批准",
    archived: "已归档",
    enabled: "已启用",
    planned: "待配置",
    completed: "已完成",
    local: "本地",
    cloud: "云端",
    manual: "手动",
    note: "笔记",
    playbook: "场景方案",
    source: "资料",
    settings: "设置",
    collection: "工作区",
    memory: "记忆",
    agent: "智能体",
    chat: "问答",
    connector: "连接器",
    pdf: "PDF",
    text: "文本",
    fact: "事实",
    principle: "原则",
  },
  agentNames: {
    Librarian: "资料管理员",
    Planner: "计划助手",
    Researcher: "研究助手",
    Reviewer: "审核助手",
    librarian: "资料管理员",
    planner: "计划助手",
    researcher: "研究助手",
    reviewer: "审核助手",
  },
  agentPurpose: {
    "Keep the knowledge base clean.": "检查资料库、解析失败和索引质量。",
    "Turn notes and conversations into plans.": "把笔记、任务和对话整理成行动计划。",
    "Create cited briefs from local sources.": "基于本地资料生成带引用的研究摘要。",
    "Review memory and decision quality.": "审核记忆、决策质量和过期假设。",
  },
  connectorNames: {
    "Browser capture": "浏览器采集",
    Calendar: "日历",
    "Folder watch": "文件夹监听",
    GitHub: "GitHub",
    Notion: "Notion",
  },
  connectorDescriptions: {
    "Save URLs and page snapshots from the browser.": "保存网页链接和页面快照。",
    "Use events for planning and daily briefs.": "把日程用于计划和每日简报。",
    "Sync selected local folders into Sources.": "把选定本地文件夹同步进资料库。",
    "Index repositories, issues, pull requests, and docs.": "索引仓库、issue、PR 和文档。",
    "Capture pages and databases into collections.": "把页面和数据库采集到工作区。",
  },
  toolNames: {
    local_search: "本地搜索",
    source_reader: "读取资料",
    task_writer: "写入任务",
    memory_reader: "读取记忆",
    parser_report: "解析报告",
    activity_log: "活动日志",
  },
  permissions: {
    read: "读取权限",
    oauth: "OAuth 授权",
    token: "访问令牌",
    extension: "浏览器扩展",
    config: "配置项",
  },
  schedules: {
    daily: "每日",
    weekly: "每周",
  },
  playbookNames: {
    "Research lab": "研究实验室",
    "Founder command": "创业指挥台",
    "Developer brain": "开发者大脑",
    "Writer studio": "写作工作室",
    "Analyst desk": "分析师工作台",
  },
  collectionNames: {
    Inbox: "收件箱",
    "Research Lab": "研究实验室",
    "Founder Command": "创业指挥台",
    "Developer Brain": "开发者大脑",
    "Writer Studio": "写作工作室",
    "Analyst Desk": "分析师工作台",
  },
  taskTitles: {
    "Import 5 core papers": "导入 5 篇核心论文",
    "Ask Researcher for a cited brief": "让研究助手生成带引用的摘要",
    "Approve durable research memories": "审核并批准长期研究记忆",
    "Import competitor notes": "导入竞品笔记",
    "Capture current product decisions": "记录当前产品决策",
    "Run Planner for next actions": "运行计划助手梳理下一步行动",
    "Import architecture docs": "导入架构文档",
    "Capture unresolved bugs": "记录未解决问题",
    "Run Librarian to audit parse/index quality": "运行资料管理员检查解析和索引质量",
    "Import source material": "导入素材资料",
    "Capture 3 article angles": "记录 3 个文章角度",
    "Run Researcher for an evidence outline": "运行研究助手生成证据大纲",
    "Import current reports": "导入近期报告",
    "Capture open questions": "记录待回答问题",
    "Run Reviewer to find stale assumptions": "运行审核助手查找过期假设",
  },
};

const $ = (selector) => document.querySelector(selector);
const view = $("#view");

class AppApiError extends Error {
  constructor(message, { status = 0, detail = "", path = "" } = {}) {
    super(message);
    this.name = "AppApiError";
    this.status = status;
    this.detail = detail;
    this.path = path;
  }
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function tStatus(value = "") {
  return text.status[value] || value || "未设置";
}

function tAgentName(value = "") {
  return text.agentNames[value] || value;
}

function tAgentPurpose(value = "") {
  return text.agentPurpose[value] || value;
}

function tConnectorName(value = "") {
  return text.connectorNames[value] || value;
}

function tConnectorDescription(value = "") {
  return text.connectorDescriptions[value] || value;
}

function tTool(value = "") {
  return text.toolNames[value] || tAgentName(value);
}

function tPermission(value = "") {
  return text.permissions[value] || value || text.permissions.config;
}

function tSchedule(value = "") {
  return text.schedules[value] || value;
}

function tPlaybookName(value = "") {
  return text.playbookNames[value] || value;
}

function tCollectionName(value = "") {
  return text.collectionNames[value] || value;
}

function tTaskTitle(value = "") {
  return text.taskTitles[value] || value;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new AppApiError("无法连接本地服务。请稍后重试，或刷新页面。", { path });
  }
  if (!response.ok) {
    const detail = await response.text();
    throw normalizeApiError(response.status, detail, path);
  }
  return response.json();
}

function normalizeApiError(status, rawDetail, path) {
  const detail = extractApiDetail(rawDetail);
  const lower = detail.toLowerCase();
  let message = detail;
  if (!detail || lower === "not found") {
    message = "没有找到需要的数据。请刷新页面，或回到首页重新进入。";
  } else if (status === 404) {
    message = detail.startsWith("没有") ? detail : `没有找到需要的数据：${detail}`;
  } else if (status === 400) {
    message = detail || "提交内容不完整，请检查后再试。";
  } else if (status === 401 || status === 403) {
    message = "当前没有权限执行这个操作。请检查模型服务或连接器配置。";
  } else if (status >= 500) {
    message = "服务处理失败。请刷新页面后重试；如果仍然出现，请查看运行日志。";
  }
  return new AppApiError(message, { status, detail, path });
}

function extractApiDetail(rawDetail = "") {
  const value = String(rawDetail || "").trim();
  if (!value) return "";
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed === "string") return parsed;
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
    if (parsed && typeof parsed.message === "string") return parsed.message;
  } catch {
    return value.replace(/^Error:\s*/i, "");
  }
  return value;
}

function userMessage(error) {
  if (error instanceof AppApiError) return error.message;
  const detail = extractApiDetail(error?.message || "");
  if (!detail || detail.toLowerCase() === "not found") return "页面暂时无法加载。请刷新页面，或回到首页重新进入。";
  return detail;
}

function renderLoadError(error, retryView = state.view) {
  console.error("View failed to load", error);
  return `
    <section class="empty error-state">
      <div class="empty-title error">页面暂时无法加载</div>
      <p>${escapeHtml(userMessage(error))}</p>
      <div class="toolbar">
        <button class="primary" data-retry-view="${escapeHtml(retryView)}">重试</button>
        <button data-nav="home">回到首页</button>
      </div>
    </section>
  `;
}

function showToast(message, tone = "success") {
  let toast = $("#toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    document.body.appendChild(toast);
  }
  toast.className = `toast ${tone}`;
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 3200);
}

function setTitle(kicker, title) {
  $("#view-kicker").textContent = kicker;
  $("#view-title").textContent = title;
}

function renderNav() {
  const groups = [
    [text.navGroups[0], navItems.slice(0, 5)],
    [text.navGroups[1], navItems.slice(5, 9)],
    [text.navGroups[2], navItems.slice(9, 12)],
  ];
  $("#nav").innerHTML = groups.map(([label, items]) => `
    <div class="nav-group">
      <div class="nav-label">${label}</div>
      ${items.map(([key, itemLabel]) => `
        <button class="${state.view === key ? "active" : ""}" data-nav="${key}">
          <span>${itemLabel}</span>
        </button>
      `).join("")}
    </div>
  `).join("");
  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.onclick = () => navigate(button.dataset.nav);
  });
}

function empty(title, body) {
  return `<div class="empty"><div class="empty-title">${escapeHtml(title)}</div><p>${escapeHtml(body)}</p></div>`;
}

function panel(title, body, action = "") {
  return `
    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">${escapeHtml(title)}</h2>
        ${action}
      </div>
      <div class="panel-body">${body}</div>
    </section>
  `;
}

async function refreshDashboard() {
  state.dashboard = await api("/api/dashboard");
}

function modelStatusNotice(settings, compact = false, showAction = true) {
  const configured = settings?.api_key_configured === "yes";
  if (configured) {
    return `
      <div class="notice success">
        <div class="notice-title">模型已配置</div>
        <p>问答会在引用本地资料后，使用 ${escapeHtml(settings.model)} 生成回答。</p>
      </div>
    `;
  }
  return `
    <div class="notice">
      <div class="notice-title">未配置模型，当前使用本地检索摘要</div>
      <p>${compact ? "回答会基于本地资料命中片段生成摘要，不会发送到远程模型。" : "你仍然可以导入资料、搜索、查看证据和提问；配置 API key 后，回答会更自然，也能做更复杂的综合分析。"}</p>
      ${showAction ? `<button class="ghost" data-nav="settings" type="button">配置模型</button>` : ""}
    </div>
  `;
}

async function renderHome() {
  setTitle("指挥中心", "首页");
  await refreshDashboard();
  const { counts, recent_sources: recentSources, tasks, memories, agents, runs, connectors, parser_stats: parserStats } = state.dashboard;
  view.innerHTML = `
    <div class="command-strip">
      <button class="primary" data-nav="sources">导入资料</button>
      <button data-nav="playbooks">选择场景方案</button>
      <button data-nav="chat">向资料库提问</button>
      <button data-nav="notes">记录笔记</button>
      <button data-nav="agents">运行智能体</button>
    </div>
    <div class="grid cols-4 home-metrics">
      ${metric("资料", counts.sources)}
      ${metric("长期记忆", counts.memories)}
      ${metric("待办任务", counts.tasks)}
      ${metric("解析问题", counts.parse_failures)}
    </div>
    <div class="grid two balanced-grid" style="margin-top:16px">
      ${panel("运行队列", `
        <div class="ops-grid">
          ${opsTile("资料导入", `${counts.sources} 份资料`, parserStats.length ? parserStats.map((row) => `${row.engine}: ${row.count}`).join(" · ") : "还没有解析记录")}
          ${opsTile("记忆", `${counts.memory_candidates} 条待审核`, memories.length ? memories.slice(0, 3).map((m) => m.title).join(" · ") : "还没有捕获长期记忆")}
          ${opsTile("智能体", `${agents.length} 个模板`, agents.map((agent) => tAgentName(agent.name)).join(" · "))}
          ${opsTile("连接器", `${connectors.filter((c) => c.status === "enabled").length} 个已启用`, connectors.map((c) => `${tConnectorName(c.name)}: ${tStatus(c.status)}`).join(" · "))}
        </div>
      `)}
      ${panel("今日任务", tasks.length ? taskList(tasks) : empty("没有待办任务", "在笔记里写 TODO: 或 待办: 可以自动生成任务。"))}
    </div>
    <div class="grid two balanced-grid" style="margin-top:16px">
      ${panel("最近资料", recentSources.length ? listSources(recentSources, false) : empty("还没有资料", "导入文档后，会开始建立你的本地上下文层。"))}
      ${panel("最近运行", runs.length ? runList(runs) : empty("还没有运行记录", "可以在智能体页面运行研究、计划、资料审核或记忆审核。"))}
    </div>
  `;
  bindSourceButtons();
  bindTaskButtons();
  bindInlineNav();
}

function metric(label, value) {
  return `<section class="panel metric"><div class="metric-value">${value}</div><div class="metric-label">${label}</div></section>`;
}

function opsTile(title, value, body) {
  return `<div class="ops-tile"><div class="tag">${escapeHtml(title)}</div><div class="ops-value">${escapeHtml(value)}</div><div class="small">${escapeHtml(body)}</div></div>`;
}

function bindInlineNav() {
  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.onclick = () => navigate(button.dataset.nav);
  });
}

function listSources(sources, showActions = true) {
  return `<div class="list">${sources.map((source) => `
    <article class="item">
      <div class="item-row">
        <div>
          <div class="item-title">${escapeHtml(source.title)}</div>
          <div class="meta">${sourceMeta(source)} · ${formatDate(source.created_at)}</div>
          ${source.status !== "ready" ? `<div class="small error">${tStatus(source.status)} ${escapeHtml(source.error || "")}</div>` : ""}
        </div>
        ${showActions ? `<button class="ghost" data-source="${source.id}">打开</button>` : `<button class="ghost" data-source="${source.id}">打开</button>`}
      </div>
    </article>
  `).join("")}</div>`;
}

function sourceMeta(source) {
  const size = `${Math.round((source.size_bytes || 0) / 1024)} KB`;
  const engine = source.parser_engine ? `引擎 ${source.parser_engine}` : tStatus(source.kind);
  const pages = source.page_count ? `${source.page_count} 页` : "";
  const chars = source.char_count ? `${source.char_count} 字符` : "";
  return [escapeHtml(tStatus(source.kind)), size, escapeHtml(engine), pages, chars].filter(Boolean).join(" · ");
}

function qualityReport(source) {
  if (!source.quality_json) return "";
  try {
    return JSON.stringify(JSON.parse(source.quality_json), null, 2);
  } catch {
    return source.quality_json;
  }
}

function qualityData(source) {
  if (!source.quality_json) return {};
  try {
    return JSON.parse(source.quality_json);
  } catch {
    return {};
  }
}

function locationLabel(item = {}) {
  const start = Number(item.page_start || 0);
  const end = Number(item.page_end || 0);
  if (!start) return "全文";
  if (end && end !== start) return `第 ${start}-${end} 页`;
  return `第 ${start} 页`;
}

function qualitySummary(source) {
  const quality = qualityData(source);
  const bits = [];
  if (quality.engine) bits.push(`解析引擎：${quality.engine}`);
  if (quality.evidence_chunks != null) bits.push(`证据块：${quality.evidence_chunks} 个`);
  if (quality.pages_with_text != null && source.page_count) bits.push(`有文本页：${quality.pages_with_text}/${source.page_count}`);
  if (quality.page_coverage != null && source.page_count) bits.push(`页覆盖率：${Math.round(Number(quality.page_coverage || 0) * 100)}%`);
  if (quality.citation_granularity) bits.push(`引用粒度：${quality.citation_granularity === "page" ? "页码级" : "全文级"}`);
  return bits.length ? `<div class="evidence-summary">${bits.map((bit) => `<span class="tag">${escapeHtml(bit)}</span>`).join("")}</div>` : "";
}

async function renderSources() {
  setTitle("采集", "资料库");
  state.sources = await api("/api/sources");
  view.innerHTML = `
    <div class="grid two">
      <div class="grid">
        ${panel("导入", `
          <form id="upload-form" class="upload-box form-stack">
            <input id="upload-title" placeholder="可选标题" />
            <input id="upload-file" class="visually-hidden-file" type="file" accept=".txt,.md,.markdown,.pdf,.csv,.json" required />
            <div class="file-picker">
              <label class="file-button" for="upload-file">选择文件</label>
              <span id="upload-file-name">尚未选择文件</span>
            </div>
            <div class="split-actions">
              <button type="submit" class="primary">导入资料</button>
            </div>
            <div id="upload-status" class="small"></div>
          </form>
        `)}
        ${panel("资料列表", state.sources.length ? listSources(state.sources) : empty("还没有导入资料", "可以上传 Markdown、文本、CSV、JSON 或 PDF 文件。"))}
      </div>
      ${panel("资料查看器", sourceViewer())}
    </div>
  `;
  $("#upload-form").addEventListener("submit", uploadSource);
  $("#upload-file").addEventListener("change", () => {
    const file = $("#upload-file").files[0];
    $("#upload-file-name").textContent = file ? file.name : "尚未选择文件";
  });
  bindSourceButtons();
}

async function renderPlaybooks() {
  setTitle("选择场景", "场景方案");
  state.playbooks = await api("/api/playbooks");
  view.innerHTML = `
    <div class="grid cols-3">
      ${state.playbooks.map((playbook) => `
        <article class="panel playbook-card">
          <div class="panel-body">
            <div class="item-row">
              <div>
                <div class="item-title">${escapeHtml(tPlaybookName(playbook.name))}</div>
                <div class="meta">${escapeHtml(playbook.audience)}</div>
              </div>
              <span class="tag">${playbook.agents.length} 个智能体</span>
            </div>
            <p>${escapeHtml(playbook.scenario)}</p>
            <div class="outcome">${escapeHtml(playbook.outcome)}</div>
            <div class="tool-row">
              ${playbook.agents.map((agent) => `<span class="tag">${escapeHtml(tAgentName(agent))}</span>`).join("")}
            </div>
            <button class="primary" data-playbook="${playbook.id}">应用方案</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
  document.querySelectorAll("[data-playbook]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.textContent = "正在应用...";
      const result = await api(`/api/playbooks/${button.dataset.playbook}/apply`, { method: "POST" });
      state.view = "runs";
      renderNav();
      await renderRuns(result.run_id);
    });
  });
}

async function renderCollections() {
  setTitle("整理", "工作区");
  state.collections = await api("/api/collections");
  view.innerHTML = `
    <div class="grid two">
      ${panel("创建工作区", `
        <form id="collection-form" class="form-stack">
          <input id="collection-name" placeholder="工作区名称" />
          <textarea id="collection-description" placeholder="用途、范围，以及哪些资料应该放进来"></textarea>
          <div class="split-actions"><button class="primary" type="submit">创建工作区</button></div>
          <div id="collection-status" class="small"></div>
        </form>
      `)}
      ${panel("已有工作区", state.collections.length ? `
        <div class="list">
          ${state.collections.map((collection) => `
            <article class="item">
              <div class="item-row">
                <div>
                  <div class="item-title">${escapeHtml(tCollectionName(collection.name))}</div>
                  <div class="meta">${formatDate(collection.created_at)}</div>
                </div>
                <span class="swatch" style="background:${escapeHtml(collection.color)}"></span>
              </div>
              <p>${escapeHtml(collection.description || "暂无说明")}</p>
            </article>
          `).join("")}
        </div>
      ` : empty("还没有工作区", "可以应用一个场景方案，或为项目、主题、客户创建工作区。"))}
    </div>
  `;
  $("#collection-form").addEventListener("submit", saveCollection);
}

async function saveCollection(event) {
  event.preventDefault();
  const name = $("#collection-name").value.trim();
  if (!name) return;
  const status = $("#collection-status");
  try {
    await api("/api/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: $("#collection-description").value }),
    });
    status.textContent = "已创建。";
    showToast("工作区已创建");
    await renderCollections();
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

function sourceViewer() {
  if (!state.selectedSource) {
    return empty("尚未选择资料", "从资料列表打开一份资料，可以查看抽取文本和内容块。");
  }
  const source = state.selectedSource;
  return `
    <div class="item" style="margin-bottom:12px">
      <div class="item-title">${escapeHtml(source.title)}</div>
      <div class="meta">${escapeHtml(source.original_name)} · ${sourceMeta(source)} · ${source.chunks.length} 个内容块</div>
    </div>
    ${qualitySummary(source)}
    ${source.quality_json ? `<details class="item" style="margin-bottom:12px"><summary class="item-title">解析报告</summary><pre class="small">${escapeHtml(qualityReport(source))}</pre></details>` : ""}
    ${source.chunks.length ? `<details class="item evidence-list" style="margin-bottom:12px" open><summary class="item-title">页码证据块</summary>
      <div class="list">
        ${source.chunks.slice(0, 12).map((chunk) => `
          <article class="evidence-item">
            <div class="meta">${locationLabel(chunk)} · 内容块 ${chunk.chunk_index}</div>
            <p>${escapeHtml(chunk.content.slice(0, 260))}</p>
          </article>
        `).join("")}
      </div>
      ${source.chunks.length > 12 ? `<div class="small">已显示前 12 个证据块；搜索和问答会使用全部 ${source.chunks.length} 个证据块。</div>` : ""}
    </details>` : ""}
    <div class="source-text">${escapeHtml(source.text_content || "没有抽取到文本。")}</div>
    <div class="toolbar" style="margin-top:12px">
      <button class="danger" id="delete-source">删除资料</button>
    </div>
  `;
}

async function uploadSource(event) {
  event.preventDefault();
  const fileInput = $("#upload-file");
  const status = $("#upload-status");
  if (!fileInput.files[0]) return;
  const data = new FormData();
  data.append("file", fileInput.files[0]);
  data.append("title", $("#upload-title").value);
  status.textContent = "正在导入并抽取文本...";
  try {
    const result = await api("/api/sources/upload", { method: "POST", body: data });
    status.textContent = result.duplicate ? "这份资料已存在。" : `已导入 ${result.chunks} 个内容块。`;
    showToast(result.duplicate ? "这份资料已存在" : `资料已导入，生成 ${result.chunks} 个证据块`);
    fileInput.value = "";
    $("#upload-title").value = "";
    state.selectedSource = result.source.id ? await api(`/api/sources/${result.source.id}`) : null;
    await renderSources();
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

function bindSourceButtons() {
  document.querySelectorAll("[data-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedSource = await api(`/api/sources/${button.dataset.source}`);
      state.view = "sources";
      renderNav();
      await renderSources();
    });
  });
  const deleteButton = $("#delete-source");
  if (deleteButton && state.selectedSource) {
    deleteButton.addEventListener("click", async () => {
      if (!confirm(`确定删除「${state.selectedSource.title}」吗？`)) return;
      await api(`/api/sources/${state.selectedSource.id}`, { method: "DELETE" });
      state.selectedSource = null;
      await renderSources();
    });
  }
}

async function renderSearch(query = "") {
  setTitle("查找", "搜索");
  const results = query ? await api(`/api/search?q=${encodeURIComponent(query)}&limit=18`) : { results: [] };
  view.innerHTML = `
    ${panel("统一搜索", `
      <form id="search-form" class="toolbar">
        <input id="search-input" type="search" value="${escapeHtml(query)}" placeholder="搜索关键词、主题、人物或决策" />
        <button class="primary" type="submit">搜索</button>
      </form>
    `)}
    <div style="margin-top:16px">
      ${panel("搜索结果", results.results.length ? `
        <div class="list">
          ${results.results.map((result) => `
            <article class="item">
              <div class="item-row">
                <div>
                  <div class="item-title">${escapeHtml(result.title)}</div>
                  <div class="meta">${tStatus(result.kind)} · ${locationLabel(result)} · 内容块 ${result.chunk_index}</div>
                </div>
                <button class="ghost" data-source="${result.source_id}">打开</button>
              </div>
              <p class="snippet">${result.snippet}</p>
            </article>
          `).join("")}
        </div>
      ` : empty(query ? "没有匹配结果" : "搜索已就绪", query ? "可以换一个更宽泛的问题，或导入更多资料。" : "当前使用 SQLite FTS，并在必要时回退到普通文本匹配。"))}
    </div>
  `;
  $("#search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    navigate("search", $("#search-input").value.trim());
  });
  bindSourceButtons();
}

async function renderChat() {
  setTitle("提问", "问答");
  const settings = await api("/api/settings");
  view.innerHTML = `
    <div class="grid two">
      ${panel("对话", `
        ${modelStatusNotice(settings, true)}
        <div class="chat-log" id="chat-log">
          ${state.chat.length ? state.chat.map(renderMessage).join("") : empty("向你的资料库提问", "回答会引用已导入资料，并标出证据来源。")}
        </div>
        <form id="chat-form" class="form-stack" style="margin-top:14px">
          <textarea id="chat-question" placeholder="询问已导入资料、决策、任务或笔记"></textarea>
          <div class="split-actions">
            <button type="submit" class="primary">提问</button>
          </div>
        </form>
      `)}
      ${panel("引用来源", citationList())}
    </div>
  `;
  $("#chat-form").addEventListener("submit", askQuestion);
  bindInlineNav();
}

function renderMessage(message) {
  return `<div class="message ${message.role === "user" ? "user" : ""}">${escapeHtml(message.content)}</div>`;
}

function citationList() {
  const last = [...state.chat].reverse().find((message) => message.role === "assistant" && message.citations?.length);
  if (!last) return empty("还没有引用", "导入资料后提问，回答会显示引用来源。");
  return `<div class="list">${last.citations.map((citation, index) => `
    <div class="item citation">
      <div class="item-row">
        <div>
          <div class="item-title">[${index + 1}] ${escapeHtml(citation.title)}</div>
          <div class="meta">${escapeHtml(citation.location || locationLabel(citation))}</div>
          <div class="small">${escapeHtml(citation.snippet)}</div>
        </div>
        <button class="ghost" data-source="${citation.source_id}">打开</button>
      </div>
    </div>
  `).join("")}</div>`;
}

async function askQuestion(event) {
  event.preventDefault();
  const input = $("#chat-question");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  state.chat.push({ role: "user", content: question });
  state.chat.push({ role: "assistant", content: "正在检索本地上下文...", citations: [] });
  await renderChat();
  try {
    const result = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, conversation_id: state.conversationId }),
    });
    state.conversationId = result.conversation_id;
    state.chat.pop();
    state.chat.push({ role: "assistant", content: result.answer, citations: result.citations });
  } catch (error) {
    state.chat.pop();
    state.chat.push({ role: "assistant", content: userMessage(error), citations: [] });
  }
  await renderChat();
  bindSourceButtons();
}

async function renderNotes() {
  setTitle("采集", "笔记");
  state.notes = await api("/api/notes");
  view.innerHTML = `
    <div class="grid two notes-grid">
      ${panel("快速笔记", `
        <form id="note-form" class="form-stack">
          <input id="note-title" placeholder="标题" />
          <textarea id="note-body" placeholder="写一条笔记。以 TODO: 或 待办: 开头的行会自动变成任务；以 记忆: 开头的行会进入记忆审核。"></textarea>
          <div class="split-actions"><button type="submit" class="primary">保存笔记</button></div>
          <div id="note-status" class="small"></div>
        </form>
      `)}
      ${panel("笔记列表", state.notes.length ? `
        <div class="note-tools">
          <input id="note-filter" type="search" placeholder="搜索笔记" value="${escapeHtml(state.noteQuery)}" autocomplete="off" />
          <div class="small" id="note-count"></div>
          <div id="note-pager"></div>
        </div>
        <div id="note-results"></div>
      ` : empty("还没有笔记", "可以在这里记录决策、提醒和项目上下文。"))}
    </div>
  `;
  $("#note-form").addEventListener("submit", saveNote);
  renderNoteResults();
  const filter = $("#note-filter");
  if (filter) {
    filter.addEventListener("input", () => {
      state.noteQuery = filter.value;
      state.notePage = 1;
      renderNoteResults();
    });
  }
}

function matchingNotes() {
  const noteQuery = state.noteQuery.trim().toLowerCase();
  return noteQuery
    ? state.notes.filter((note) => `${note.title} ${note.body}`.toLowerCase().includes(noteQuery))
    : state.notes;
}

function renderNoteResults() {
  const results = $("#note-results");
  if (!results) return;
  const filteredNotes = matchingNotes();
  const totalPages = Math.max(1, Math.ceil(filteredNotes.length / NOTE_PAGE_SIZE));
  state.notePage = Math.min(Math.max(1, state.notePage), totalPages);
  const start = (state.notePage - 1) * NOTE_PAGE_SIZE;
  const visibleNotes = filteredNotes.slice(start, start + NOTE_PAGE_SIZE);
  const count = $("#note-count");
  if (count) count.textContent = filteredNotes.length ? `第 ${state.notePage} 页，共 ${totalPages} 页 · ${filteredNotes.length} 条笔记` : "没有匹配笔记";
  const pager = $("#note-pager");
  if (pager) {
    pager.innerHTML = filteredNotes.length ? `
      <div class="note-pagination">
        <button class="ghost" data-note-page="prev" type="button" ${state.notePage <= 1 ? "disabled" : ""}>上一页</button>
        <span class="small">每页 ${NOTE_PAGE_SIZE} 条</span>
        <button class="ghost" data-note-page="next" type="button" ${state.notePage >= totalPages ? "disabled" : ""}>下一页</button>
      </div>
    ` : "";
    pager.querySelectorAll("[data-note-page]").forEach((button) => {
      button.addEventListener("click", () => {
        state.notePage += button.dataset.notePage === "next" ? 1 : -1;
        renderNoteResults();
      });
    });
  }
  results.innerHTML = visibleNotes.length ? `
    <div class="list note-list">${visibleNotes.map((note) => `
      <details class="item note-card">
        <summary>
          <span class="item-title">${escapeHtml(displayNoteTitle(note))}</span>
          <span class="meta">${formatDate(note.updated_at)}</span>
          <span class="note-preview">${escapeHtml(notePreview(note))}</span>
        </summary>
        <div class="note-body">${escapeHtml(note.body)}</div>
      </details>
    `).join("")}</div>
  ` : empty("没有匹配笔记", "换个关键词再试。");
}

function displayNoteTitle(note) {
  const title = String(note.title || "").trim();
  const firstLine = String(note.body || "").trim().split(/\r?\n/)[0]?.trim() || "";
  const looksAutoNumericTitle = title === firstLine && /^[0-9]+$/.test(title);
  return !title || title === "无标题" || note.title_source === "empty" || looksAutoNumericTitle ? "无标题" : title;
}

function notePreview(note) {
  return String(note.body || "").trim().slice(0, 160);
}

async function saveNote(event) {
  event.preventDefault();
  const body = $("#note-body").value.trim();
  if (!body) return;
  const status = $("#note-status");
  try {
    const result = await api("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("#note-title").value.trim() || "无标题", body }),
    });
    const createdBits = [];
    if (result.tasks?.length) createdBits.push(`${result.tasks.length} 个任务`);
    if (result.memories?.length) createdBits.push(`${result.memories.length} 条待审记忆`);
    status.textContent = createdBits.length ? `已保存，并创建 ${createdBits.join("、")}。` : "已保存。";
    showToast(createdBits.length ? `笔记已保存，并创建 ${createdBits.join("、")}` : "笔记已保存");
    $("#note-title").value = "";
    $("#note-body").value = "";
    state.notePage = 1;
    await renderNotes();
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

async function renderTasks() {
  setTitle("计划", "任务");
  state.tasks = await api("/api/tasks");
  view.innerHTML = `
    ${panel("任务队列", state.tasks.length ? taskList(tasksToDisplay(state.tasks)) : empty("还没有任务", "在笔记中写 TODO: 或 待办: 可以自动创建任务。"))}
  `;
  bindTaskButtons();
}

function taskList(tasks) {
  return `<div class="list">${tasks.map((task) => `
    <article class="item">
      <div class="item-row">
        <div>
          <div class="item-title" style="${task.status === "done" ? "text-decoration:line-through;color:var(--muted)" : ""}">${escapeHtml(tTaskTitle(task.title))}</div>
          <div class="meta">${tStatus(task.status)} · ${tStatus(task.source_type)} · ${formatDate(task.created_at)}</div>
        </div>
        <button class="ghost" data-task="${task.id}">${task.status === "done" ? "重新打开" : "完成"}</button>
      </div>
    </article>
  `).join("")}</div>`;
}

function tasksToDisplay(tasks) {
  return tasks;
}

function bindTaskButtons() {
  document.querySelectorAll("[data-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/tasks/${button.dataset.task}/toggle`, { method: "POST" });
      if (state.view === "tasks") await renderTasks();
      else await renderHome();
    });
  });
}

async function renderMemories() {
  setTitle("长期上下文", "记忆");
  state.memories = await api("/api/memories");
  const candidates = state.memories.filter((memory) => memory.status === "candidate");
  const approved = state.memories.filter((memory) => memory.status === "approved");
  const archived = state.memories.filter((memory) => memory.status === "archived");
  view.innerHTML = `
    <div class="grid two balanced-grid">
      ${panel("记忆审核箱", candidates.length ? memoryList(candidates) : empty("没有待审记忆", "在笔记里写 MEMORY: 或 记忆: 可以创建可审核记忆。"))}
      ${panel("新增记忆", `
        <form id="memory-form" class="form-stack">
          <input id="memory-title" placeholder="标题" />
          <textarea id="memory-body" placeholder="偏好、项目事实、决策或长期上下文"></textarea>
          <div class="toolbar">
            <select id="memory-status">
              <option value="candidate">待审核</option>
              <option value="approved">已批准</option>
            </select>
            <button class="primary" type="submit">保存记忆</button>
          </div>
          <div id="memory-status-text" class="small"></div>
        </form>
      `)}
    </div>
    <div class="grid two balanced-grid" style="margin-top:16px">
      ${panel("已批准", approved.length ? memoryList(approved) : empty("没有已批准记忆", "已批准记忆会成为长期个人上下文。"))}
      ${panel("已归档", archived.length ? memoryList(archived) : empty("没有归档记忆", "归档记忆仍可查看，但不会进入活跃上下文。"))}
    </div>
  `;
  $("#memory-form").addEventListener("submit", saveMemory);
  bindMemoryButtons();
}

function memoryList(memories) {
  return `<div class="list">${memories.map((memory) => `
    <article class="item">
      <div class="item-row">
        <div>
          <div class="item-title">${escapeHtml(memory.title)}</div>
          <div class="meta">${tStatus(memory.status)} · ${tStatus(memory.memory_type)} · 置信度 ${Number(memory.confidence || 0).toFixed(2)} · ${formatDate(memory.created_at)}</div>
          <p>${escapeHtml(memory.body)}</p>
        </div>
      </div>
      <div class="toolbar">
        ${memory.status !== "approved" ? `<button class="ghost" data-memory="${memory.id}" data-memory-status="approved">批准</button>` : ""}
        ${memory.status !== "archived" ? `<button class="ghost" data-memory="${memory.id}" data-memory-status="archived">归档</button>` : ""}
        ${memory.status !== "candidate" ? `<button class="ghost" data-memory="${memory.id}" data-memory-status="candidate">移回审核箱</button>` : ""}
      </div>
    </article>
  `).join("")}</div>`;
}

async function saveMemory(event) {
  event.preventDefault();
  const body = $("#memory-body").value.trim();
  if (!body) return;
  const status = $("#memory-status-text");
  try {
    await api("/api/memories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("#memory-title").value, body, status: $("#memory-status").value }),
    });
    $("#memory-title").value = "";
    $("#memory-body").value = "";
    status.textContent = "已保存。";
    showToast("记忆已保存");
    await renderMemories();
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

function bindMemoryButtons() {
  document.querySelectorAll("[data-memory]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/memories/${button.dataset.memory}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: button.dataset.memoryStatus }),
      });
      await renderMemories();
    });
  });
}

async function renderAgents() {
  setTitle("自动化", "智能体");
  state.agents = await api("/api/agents");
  view.innerHTML = `
    <div class="grid cols-3">
      ${state.agents.map(agentCard).join("")}
    </div>
    <div style="margin-top:16px">
      ${panel("运行智能体", `
        <form id="agent-run-form" class="form-stack">
          <select id="agent-id">
            ${state.agents.map((agent) => `<option value="${agent.id}">${escapeHtml(tAgentName(agent.name))}</option>`).join("")}
          </select>
          <textarea id="agent-input" placeholder="问题、计划上下文或审核重点"></textarea>
          <div class="split-actions"><button class="primary" type="submit">运行</button></div>
          <div id="agent-run-status" class="small"></div>
        </form>
      `)}
    </div>
  `;
  $("#agent-run-form").addEventListener("submit", runAgent);
}

function agentCard(agent) {
  return `
    <article class="panel agent-card">
      <div class="panel-body">
        <div class="item-row">
          <div>
            <div class="item-title">${escapeHtml(tAgentName(agent.name))}</div>
            <div class="meta">${agent.schedule ? `计划任务 ${escapeHtml(tSchedule(agent.schedule))}` : "手动运行"} · ${agent.enabled ? "已启用" : "已停用"}</div>
          </div>
          <span class="tag">${agent.tools.length} 个工具</span>
        </div>
        <p>${escapeHtml(tAgentPurpose(agent.purpose))}</p>
        <div class="tool-row">${agent.tools.map((tool) => `<span class="tag">${escapeHtml(tTool(tool))}</span>`).join("")}</div>
      </div>
    </article>
  `;
}

async function runAgent(event) {
  event.preventDefault();
  const status = $("#agent-run-status");
  status.textContent = "正在运行...";
  try {
    const result = await api(`/api/agents/${$("#agent-id").value}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: $("#agent-input").value }),
    });
    status.textContent = "已完成。";
    showToast("智能体运行完成");
    state.view = "runs";
    renderNav();
    await renderRuns(result.id);
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

async function renderRuns(highlightId = "") {
  setTitle("观察", "运行记录");
  state.runs = await api("/api/runs");
  view.innerHTML = state.runs.length
    ? `<div class="list">${runList(state.runs, highlightId)}</div>`
    : empty("还没有运行记录", "运行智能体后，会在这里生成可追溯的执行记录。");
}

function runList(runs, highlightId = "") {
  return runs.map((run) => `
    <article class="item ${run.id === highlightId ? "highlight" : ""}">
      <div class="item-row">
        <div>
          <div class="item-title">${escapeHtml(tAgentName(run.agent_name || run.agent_id))}</div>
          <div class="meta">${tStatus(run.status)} · ${formatDate(run.created_at)} · 输入 ${escapeHtml(run.input || "无")}</div>
        </div>
        <span class="tag">${run.logs?.length || 0} 条日志</span>
      </div>
      <pre class="run-output">${escapeHtml(run.output)}</pre>
      <details>
        <summary class="small">运行日志</summary>
        <pre class="small">${escapeHtml(JSON.stringify(run.logs || [], null, 2))}</pre>
      </details>
    </article>
  `).join("");
}

async function renderConnectors() {
  setTitle("集成", "连接器");
  state.connectors = await api("/api/connectors");
  view.innerHTML = `
    <div class="grid cols-3">
      ${state.connectors.map((connector) => `
        <article class="panel agent-card">
          <div class="panel-body">
            <div class="item-row">
              <div>
                <div class="item-title">${escapeHtml(tConnectorName(connector.name))}</div>
                <div class="meta">${tStatus(connector.kind)} · ${tStatus(connector.status)}</div>
              </div>
              <span class="tag">${escapeHtml(tPermission(connector.config.permission || "config"))}</span>
            </div>
            <p>${escapeHtml(tConnectorDescription(connector.description))}</p>
            <button class="ghost" data-connector="${connector.id}">${connector.status === "enabled" ? "停用" : "启用占位"}</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
  document.querySelectorAll("[data-connector]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/connectors/${button.dataset.connector}/toggle`, { method: "POST" });
      await renderConnectors();
    });
  });
}

async function renderSettings() {
  setTitle("控制", "设置");
  const settings = await api("/api/settings");
  view.innerHTML = `
    <div class="grid two">
      ${panel("模型服务", `
        ${modelStatusNotice(settings, false, false)}
        <form id="settings-form" class="form-stack">
          <label class="small">Base URL</label>
          <input id="settings-base-url" value="${escapeHtml(settings.base_url)}" />
          <label class="small">模型</label>
          <input id="settings-model" value="${escapeHtml(settings.model)}" />
          <label class="small">API key</label>
          <input id="settings-api-key" type="password" placeholder="${settings.api_key_configured === "yes" ? "已配置。留空则保留现有 key。" : "尚未配置 key"}" />
          <div class="split-actions"><button type="submit" class="primary">保存设置</button></div>
          <div id="settings-status" class="small"></div>
        </form>
      `)}
      ${panel("隐私边界", `
        <div class="list">
          <div class="item"><div class="item-title">本地存储</div><div class="small">资料和抽取文本保存在当前产品目录里。</div></div>
          <div class="item"><div class="item-title">远程模型调用</div><div class="small">只有配置 API key 后，问答上下文才会发送给模型服务。</div></div>
          <div class="item"><div class="item-title">密钥</div><div class="small">API key 不写入源码，只保存在本地运行数据中。</div></div>
        </div>
      `)}
    </div>
  `;
  $("#settings-form").addEventListener("submit", saveSettings);
}

async function saveSettings(event) {
  event.preventDefault();
  const status = $("#settings-status");
  try {
    await api("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url: $("#settings-base-url").value,
        model: $("#settings-model").value,
        api_key: $("#settings-api-key").value,
      }),
    });
    status.textContent = "已保存。";
    showToast("设置已保存");
    await refreshDashboard();
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

async function navigate(viewName, payload = "") {
  viewName = routeAliases[viewName] || viewName;
  if (!navItems.some(([key]) => key === viewName)) viewName = "home";
  state.view = viewName;
  if (location.hash.slice(1) !== viewName) {
    history.replaceState(null, "", `#${viewName}`);
  }
  renderNav();
  try {
    if (viewName === "home") await renderHome();
    if (viewName === "playbooks") await renderPlaybooks();
    if (viewName === "sources") await renderSources();
    if (viewName === "search") await renderSearch(payload);
    if (viewName === "chat") await renderChat();
    if (viewName === "notes") await renderNotes();
    if (viewName === "collections") await renderCollections();
    if (viewName === "tasks") await renderTasks();
    if (viewName === "memories") await renderMemories();
    if (viewName === "agents") await renderAgents();
    if (viewName === "runs") await renderRuns();
    if (viewName === "connectors") await renderConnectors();
    if (viewName === "settings") await renderSettings();
  } catch (error) {
    view.innerHTML = renderLoadError(error, viewName);
    bindInlineNav();
    document.querySelectorAll("[data-retry-view]").forEach((button) => {
      button.addEventListener("click", () => navigate(button.dataset.retryView));
    });
  }
}

$("#global-search").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = $("#global-search-input").value.trim();
  navigate("search", query);
});

window.addEventListener("hashchange", () => {
  const next = routeAliases[location.hash.slice(1)] || location.hash.slice(1) || "home";
  if (navItems.some(([key]) => key === next)) navigate(next);
  else navigate("home");
});

renderNav();
const initialView = routeAliases[location.hash.slice(1)] || location.hash.slice(1);
navigate(navItems.some(([key]) => key === initialView) ? initialView : "home");
