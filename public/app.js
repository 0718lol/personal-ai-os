const state = {
  view: "home",
  dashboard: null,
  sources: [],
  notes: [],
  tasks: [],
  projects: [],
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
  ["home", "今日推进"],
  ["projects", "项目"],
  ["playbooks", "项目模板"],
  ["sources", "资料库"],
  ["wiki", "知识页面"],
  ["search", "搜索"],
  ["chat", "问答"],
  ["notes", "笔记"],
  ["tasks", "任务"],
  ["decisions", "决策"],
  ["deliverables", "交付物"],
  ["memories", "记忆"],
  ["agents", "智能体"],
  ["runs", "运行记录"],
  ["connectors", "连接器"],
  ["settings", "设置"],
];

const routeAliases = {
  workspace: "projects",
  workspaces: "projects",
  collection: "projects",
  collections: "projects",
  project: "projects",
  projects: "projects",
  library: "sources",
  source: "sources",
  memories_review: "memories",
  agent_runs: "runs",
};

const text = {
  navGroups: ["推进", "项目资料", "自动化", "系统"],
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
    collection: "项目",
    project: "项目",
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
  view.dataset.page = state.view;
  $("#view-kicker").textContent = kicker;
  $("#view-title").textContent = title;
}

const iconPaths = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  projects: '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V4h8v3M3 12h18M10 12v3h4v-3"/>',
  playbooks: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  sources: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  wiki: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/>',
  search: '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
  chat: '<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V6a3 3 0 0 1 3-3h7a8 8 0 0 1 8 8Z"/><path d="M7 8h9M7 12h6"/>',
  notes: '<path d="M14 3H5v18h14V8Zm0 0v5h5M8 12h8M8 16h5"/>',
  tasks: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m7 12 3 3 7-7"/>',
  decisions: '<path d="M12 3v18M5 7h14M5 7l-3 7h6L5 7Zm14 0-3 7h6l-3-7ZM7 21h10"/>',
  deliverables: '<path d="M4 7h16v14H4ZM3 3h18v4H3ZM9 12h6"/>',
  memories: '<path d="M12 4C7-1 1 5 5 9c-5 3-1 10 4 8 0 5 7 5 7 0 5 2 9-5 4-8 4-4-2-10-8-5Zm0 0v16M7 8l5 2 5-2M6 14l6-2 6 2"/>',
  agents: '<rect x="3" y="7" width="18" height="14" rx="4"/><path d="M12 3v4M8 12v2M16 12v2M8 18h8"/>',
  runs: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
  connectors: '<path d="m8 8 8 8M7 3l4 4-4 4-4-4Zm10 10 4 4-4 4-4-4Z"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
};
function uiIcon(name, className = "") {
  return `<svg class="ui-icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.notes}</svg>`;
}

function renderNav() {
  const groups = [
    [text.navGroups[0], navItems.slice(0, 3)],
    [text.navGroups[1], navItems.slice(3, 12)],
    [text.navGroups[2], navItems.slice(12, 15)],
    [text.navGroups[3], navItems.slice(15)],
  ];
  $("#nav").innerHTML = groups.map(([label, items]) => `
    <div class="nav-group">
      <div class="nav-label">${label}</div>
      ${items.map(([key, itemLabel]) => `
        <button class="${state.view === key ? "active" : ""}" data-nav="${key}" aria-current="${state.view === key ? "page" : "false"}">
          ${uiIcon(key)}<span>${itemLabel}</span>${state.view === key ? '<i class="nav-active-dot"></i>' : ""}
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

async function loadProjects() {
  try {
    return await api("/api/projects");
  } catch (error) {
    const legacy = await api("/api/collections");
    return legacy.map(normalizeLegacyProject);
  }
}

function normalizeLegacyProject(project = {}) {
  const counts = project.counts || {};
  return {
    ...project,
    display_name: project.display_name || project.name || "未命名项目",
    goal: project.goal || project.description || "",
    counts: {
      sources: Number(counts.sources || 0),
      notes: Number(counts.notes || 0),
      tasks: Number(counts.tasks || 0),
      done_tasks: Number(counts.done_tasks || 0),
      memories: Number(counts.memories || 0),
      memory_candidates: Number(counts.memory_candidates || 0),
    },
    resume: project.resume || {
      health: "待同步",
      progress: "后端正在切换到项目推进版本。",
      next_step: "刷新或等待托管服务重启后，会显示完整项目恢复卡。",
      blocker: "旧后端暂时不支持项目详情接口。",
      decision: "暂无明确决策记录。",
      next_tasks: [],
    },
  };
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
  setTitle("项目推进", "今日推进");
  await refreshDashboard();
  const { counts, projects = [], tasks, memories, events } = state.dashboard;
  const focusProjects = projects
    .filter((project) => project.id !== "inbox")
    .sort((a, b) => projectPriorityScore(b) - projectPriorityScore(a))
    .slice(0, 4);
  view.innerHTML = `
    <div class="command-strip">
      <button class="primary" data-nav="projects">新建/打开项目</button>
      <button data-nav="notes">记录项目进展</button>
      <button data-nav="sources">添加项目资料</button>
      <button data-nav="agents">运行推进员</button>
      <button data-nav="playbooks">套用项目模板</button>
    </div>
    <div class="grid cols-4 home-metrics">
      ${metric("项目", projects.length)}
      ${metric("待推进任务", counts.tasks)}
      ${metric("待确认记忆", counts.memory_candidates)}
      ${metric("解析问题", counts.parse_failures)}
    </div>
    <div class="grid two wide-left" style="margin-top:16px">
      ${panel("优先推进", focusProjects.length ? `
        <div class="project-board">
          ${focusProjects.map((project) => projectCard(project)).join("")}
        </div>
      ` : empty("还没有项目", "先创建一个项目，后续资料、笔记、任务和记忆都会围绕它组织。"), `<button data-nav="projects">管理项目</button>`)}
      ${panel("今日下一步", tasks.length ? taskList(tasks.slice(0, 6)) : empty("没有待办任务", "在项目笔记里写 TODO: 可以自动创建下一步。"))}
    </div>
    <div class="grid two balanced-grid" style="margin-top:16px">
      ${panel("待确认上下文", memories.length ? memoryList(memories.filter((memory) => memory.status === "candidate").slice(0, 4)) : empty("没有待审记忆", "项目关键事实和决策会先进审核箱，避免静默污染上下文。"))}
      ${panel("项目时间线", events.length ? timelineList(events.slice(0, 8)) : empty("还没有活动", "导入资料、记录笔记、运行智能体后，这里会形成可追溯时间线。"))}
    </div>
  `;
  bindTaskButtons();
  bindProjectButtons();
  bindMemoryButtons();
  bindInlineNav();
}

function projectPriorityScore(project) {
  const counts = project.counts || {};
  let score = 0;
  if (!counts.tasks) score += 40;
  if (counts.memory_candidates) score += 20;
  if (counts.sources && !counts.notes) score += 15;
  score += Math.min(Number(counts.tasks || 0), 8);
  return score;
}

function metric(label, value) {
  return `<section class="panel metric"><div class="metric-value">${value}</div><div class="metric-label">${label}</div></section>`;
}

function opsTile(title, value, body) {
  return `<div class="ops-tile"><div class="tag">${escapeHtml(title)}</div><div class="ops-value">${escapeHtml(value)}</div><div class="small">${escapeHtml(body)}</div></div>`;
}

function projectCard(project, compact = false) {
  const resume = project.resume || {};
  const counts = project.counts || {};
  return `
    <article class="item project-card">
      <div class="item-row">
        <div>
          <div class="project-card-heading"><span class="project-symbol">${uiIcon(project.id === "inbox" ? "sources" : "projects")}</span><div class="item-title">${escapeHtml(tCollectionName(project.display_name || project.name))}</div></div>
          <div class="meta">${escapeHtml(resume.health || "待推进")} · ${counts.tasks || 0} 个下一步 · ${counts.sources || 0} 份资料 · ${counts.notes || 0} 条笔记</div>
        </div>
        <button class="ghost project-open" data-project="${project.id}" aria-label="打开${escapeHtml(tCollectionName(project.display_name || project.name))}">打开 ${uiIcon("arrow")}</button>
      </div>
      ${project.goal ? `<p>${escapeHtml(project.goal)}</p>` : ""}
      ${resumeCard(resume, compact)}
    </article>
  `;
}

function resumeCard(resume = {}, compact = false) {
  return `
    <div class="resume-card">
      <div>
        <span class="tag">上次进展</span>
        <p>${escapeHtml(resume.progress || "还没有可恢复的项目状态。")}</p>
      </div>
      <div>
        <span class="tag">下一步</span>
        <p>${escapeHtml(resume.next_step || "补一条 TODO，明确最小下一步。")}</p>
      </div>
      ${compact ? "" : `
        <div>
          <span class="tag">卡点</span>
          <p>${escapeHtml(resume.blocker || "暂无明确卡点。")}</p>
        </div>
        <div>
          <span class="tag">最近决策</span>
          <p>${escapeHtml(resume.decision || "暂无明确决策记录。")}</p>
        </div>
      `}
    </div>
  `;
}

function timelineList(events) {
  return `<div class="timeline">${events.map((event) => `
    <article class="timeline-item">
      <div class="item-title">${escapeHtml(event.title)}</div>
      <div class="meta">${tStatus(event.kind)} · ${formatDate(event.created_at)}</div>
      ${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ""}
    </article>
  `).join("")}</div>`;
}

function bindProjectButtons() {
  document.querySelectorAll("[data-project]").forEach((button) => {
    button.addEventListener("click", () => navigate("projects", button.dataset.project));
  });
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

function projectSelect(id, label = "所属项目") {
  return `
    <label class="small" for="${escapeHtml(id)}">${escapeHtml(label)}</label>
    <select id="${escapeHtml(id)}">
      <option value="">不挂项目</option>
      ${state.projects.map((project) => `<option value="${project.id}">${escapeHtml(tCollectionName(project.display_name || project.name))}</option>`).join("")}
    </select>
  `;
}

async function renderSources(selectedId = "") {
  if (selectedId) state.selectedSource = await api(`/api/sources/${encodeURIComponent(selectedId)}`);
  setTitle("采集", "资料库");
  [state.sources, state.projects] = await Promise.all([api("/api/sources"), loadProjects()]);
  view.innerHTML = `
    <div class="grid two">
      <div class="grid">
        ${panel("导入", `
          <form id="upload-form" class="upload-box form-stack">
            <input id="upload-title" placeholder="可选标题" />
            ${projectSelect("upload-project", "选择所属项目")}
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
  setTitle("项目启动", "项目模板");
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
            <button class="primary" data-playbook="${playbook.id}">创建项目骨架</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
  document.querySelectorAll("[data-playbook]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.textContent = "正在应用...";
      const result = await api(`/api/playbooks/${button.dataset.playbook}/apply`, { method: "POST" });
      state.view = "projects";
      renderNav();
      await renderProjects(result.collection_id);
    });
  });
}

async function renderProjects(selectedId = "") {
  setTitle("工作空间 / 项目", "我的项目");
  state.projects = await loadProjects();
  const selectedProject = selectedId ? await loadProjectDetail(selectedId) : null;
  const active = state.projects.filter(p => p.id !== "inbox");
  const total = key => state.projects.reduce((n, p) => n + Number(p.counts?.[key] || 0), 0);
  view.innerHTML = `
    <section class="workspace-hero">
      <div class="hero-copy"><span class="eyebrow">YOUR IDEAS, IN MOTION</span><h2>让每一个想法，<br>都有下一步<span>。</span></h2><p>收好资料，理清思路。把零散的灵感，变成持续推进的项目。</p><button class="primary" id="focus-new-project">${uiIcon("plus")}新建项目</button><button class="hero-secondary" data-nav="playbooks">从模板开始 ${uiIcon("arrow")}</button></div>
      <div class="hero-visual" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-note note-back">${uiIcon("sources")}<span>收集灵感</span><i></i><i></i></div><div class="hero-note note-front"><span class="hero-note-icon">${uiIcon("wiki")}</span><strong>让知识连接起来</strong><span class="note-line"></span><span class="note-line short"></span><div class="note-footer"><span class="tiny-dot"></span> 一点一滴，持续生长 ${uiIcon("arrow")}</div></div><span class="hero-spark spark-one">✧</span><span class="hero-spark spark-two">+</span></div>
    </section>
    <div class="project-overview"><div>${uiIcon("projects")}<span>我的项目</span><strong>${active.length}</strong></div><div>${uiIcon("sources")}<span>已收集资料</span><strong>${total("sources")}</strong></div><div>${uiIcon("tasks")}<span>待推进任务</span><strong>${total("tasks")}</strong></div><div>${uiIcon("notes")}<span>项目笔记</span><strong>${total("notes")}</strong></div></div>
    <div class="projects-layout ${selectedProject ? "has-detail" : ""}">
      <div class="projects-main"><div class="section-heading"><div><span class="eyebrow">PROJECT LIBRARY</span><h2>你的项目空间 <span>${state.projects.length}</span></h2></div><span class="small">资料、进展与下一步，都在这里</span></div>
        <div class="project-board">${state.projects.map(project => projectCard(project, true)).join("") || empty("从一个小目标开始", "创建第一个项目，把资料和行动组织起来。")}</div>
        ${selectedProject ? `<div class="selected-project-detail">${projectDetail(selectedProject)}</div>` : `<section class="project-guide"><span class="guide-icon">${uiIcon("wiki")}</span><div><h3>项目，是知识的生长容器</h3><p>导入一份资料，记下一条想法，或写下一项 TODO。每次回来，都能接着上次的进度。</p><button class="text-button" data-nav="sources">去收集第一份资料 ${uiIcon("arrow")}</button></div></section>`}
      </div>
      <aside class="project-create">${panel("开启一个新项目", `<p class="form-intro">不必一开始就想清楚所有细节。<br>给它一个名字，然后开始。</p><form id="project-form" class="form-stack"><label for="project-name">项目名称</label><input id="project-name" placeholder="例如：我的研究笔记" required maxlength="200"><label for="project-goal">想要完成什么 <span class="small">选填</span></label><textarea id="project-goal" placeholder="记下目标，或者此刻的一个想法…" rows="4"></textarea><button class="primary" type="submit">${uiIcon("plus")}创建项目</button><div id="project-status" class="small" role="status"></div></form>`)}<div class="project-tip">${uiIcon("playbooks")}<div><strong>还没有头绪？</strong><p>用一个现成模板，开始你的研究、创作或产品计划。</p><button class="text-button" data-nav="playbooks">浏览项目模板 ${uiIcon("arrow")}</button></div></div></aside>
    </div>
  `;
  $("#project-form").addEventListener("submit", saveProject);
  $("#focus-new-project").addEventListener("click", () => { $("#project-name").scrollIntoView({behavior:"smooth", block:"center"}); $("#project-name").focus({preventScroll:true}); });
  bindProjectButtons(); bindSourceButtons(); bindTaskButtons(); bindInlineNav();
}

async function loadProjectDetail(projectId) {
  try {
    return await api(`/api/projects/${projectId}`);
  } catch (error) {
    const project = state.projects.find((item) => item.id === projectId);
    if (!project) throw error;
    return {
      project: normalizeLegacyProject(project),
      sources: [],
      notes: [],
      tasks: [],
      memories: [],
      events: [],
      insights: [],
      deliverables: [],
    };
  }
}

function projectDetail(detail) {
  const project = detail.project;
  return panel(tCollectionName(project.display_name || project.name), `
    <div class="project-detail">
      ${project.goal ? `<p class="project-goal">${escapeHtml(project.goal)}</p>` : ""}
      ${resumeCard(project.resume)}
      <div class="grid cols-4 compact-metrics">
        ${metric("资料", project.counts.sources || 0)}
        ${metric("笔记", project.counts.notes || 0)}
        ${metric("待办", project.counts.tasks || 0)}
        ${metric("记忆", project.counts.memories || 0)}
      </div>
      <div class="toolbar project-actions">
        <button data-nav="sources">添加资料</button>
        <button data-nav="notes">记录进展</button>
        <button data-nav="agents">运行推进员</button>
      </div>
      <div class="project-sections">
        ${sectionBlock("下一步任务", detail.tasks.length ? taskList(detail.tasks) : empty("没有任务", "在项目笔记里写 TODO: 可以自动创建任务。"))}
        ${sectionBlock("结构化洞察", detail.insights?.length ? insightList(detail.insights) : empty("没有洞察", "整理项目笔记后，会提取决策、问题、风险和行动。"))}
        ${sectionBlock("交付物", detail.deliverables?.length ? deliverableMiniList(detail.deliverables) : empty("没有交付物", "可以在交付物页生成周报、计划、复盘或客户汇报。"))}
        ${sectionBlock("最近资料", detail.sources.length ? listSources(detail.sources, false) : empty("没有资料", "把项目文档、客户材料、链接摘录或 PDF 导入进来。"))}
        ${sectionBlock("最近笔记", detail.notes.length ? noteMiniList(detail.notes) : empty("没有笔记", "记录进展、决策、问题和待办。"))}
        ${sectionBlock("时间线", detail.events.length ? timelineList(detail.events) : empty("没有活动", "项目活动会自动进入时间线。"))}
      </div>
    </div>
  `);
}

function insightList(insights) {
  return `<div class="list">${insights.map((insight) => `
    <article class="item">
      <div class="item-row">
        <div>
          <div class="item-title">${escapeHtml(insight.title)}</div>
          <div class="meta">${escapeHtml(insightKindLabel(insight.kind))} · 置信度 ${Number(insight.confidence || 0).toFixed(2)} · ${formatDate(insight.created_at)}</div>
          <p>${escapeHtml(insight.body)}</p>
        </div>
        <span class="tag">${escapeHtml(insight.status || "open")}</span>
      </div>
    </article>
  `).join("")}</div>`;
}

function insightKindLabel(kind) {
  return {
    decision: "决策",
    question: "问题",
    risk: "风险",
    follow_up: "跟进",
    action: "行动",
  }[kind] || kind;
}

function deliverableMiniList(deliverables) {
  return `<div class="list">${deliverables.map((item) => `
    <article class="item">
      <div class="item-title">${escapeHtml(item.title)}</div>
      <div class="meta">${escapeHtml(deliverableTemplateLabel(item.template))} · ${formatDate(item.created_at)}</div>
      <pre class="run-output">${escapeHtml(String(item.body || "").slice(0, 700))}</pre>
    </article>
  `).join("")}</div>`;
}

function deliverableTemplateLabel(template) {
  return {
    weekly: "项目周报",
    plan: "下一步计划",
    review: "项目复盘",
    client: "客户汇报",
    risk: "风险清单",
  }[template] || template;
}

function sectionBlock(title, body) {
  return `
    <section class="section-block">
      <h3>${escapeHtml(title)}</h3>
      ${body}
    </section>
  `;
}

function noteMiniList(notes) {
  return `<div class="list">${notes.map((note) => `
    <article class="item">
      <div class="item-title">${escapeHtml(displayNoteTitle(note))}</div>
      <div class="meta">${formatDate(note.updated_at)}</div>
      <p>${escapeHtml(notePreview(note))}</p>
    </article>
  `).join("")}</div>`;
}

async function saveProject(event) {
  event.preventDefault();
  const name = $("#project-name").value.trim();
  if (!name) return;
  const status = $("#project-status");
  try {
    const project = await api("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, goal: $("#project-goal").value }),
    });
    status.textContent = "已创建。";
    showToast("项目已创建");
    await renderProjects(project.id);
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

async function renderCollections(selectedId = "") {
  return renderProjects(selectedId);
}

async function saveCollection(event) {
  return saveProject(event);
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
  data.append("project_id", $("#upload-project")?.value || "");
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
  bindSourceButtons();
}

function renderMessage(message) {
  const label = message.role === "assistant" ? ({confident:"有检索证据 · 请核对引用", low:"低置信 · 证据可能不足", abstain:"证据不足 · 已拒答"})[message.confidence] : "";
  return `<div class="message ${message.role === "user" ? "user" : ""}">${label ? `<div class="small">${escapeHtml(label)}</div>` : ""}${escapeHtml(message.content)}</div>`;
}

function citationList() {
  const last = [...state.chat].reverse().find((message) => message.role === "assistant");
  if (!last?.citations?.length) return empty("还没有引用", "导入资料后提问，回答会显示引用来源。");
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
    state.chat.push({ role: "assistant", content: result.answer, citations: result.citations, confidence: result.confidence });
  } catch (error) {
    state.chat.pop();
    state.chat.push({ role: "assistant", content: userMessage(error), citations: [] });
  }
  await renderChat();
  bindSourceButtons();
}

async function renderNotes() {
  setTitle("采集", "笔记");
  [state.notes, state.projects] = await Promise.all([api("/api/notes"), loadProjects()]);
  view.innerHTML = `
    <div class="grid two notes-grid">
      ${panel("快速笔记", `
        <form id="note-form" class="form-stack">
          <input id="note-title" placeholder="标题" />
          ${projectSelect("note-project", "选择所属项目")}
          <textarea id="note-body" placeholder="记录项目进展。TODO: 会变成任务；决策: 会进入恢复卡；问题: 会变成卡点；记忆: 会进入审核箱。"></textarea>
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
        <div class="toolbar note-actions">
          <button class="ghost" data-organize-note="${note.id}" type="button">整理洞察</button>
        </div>
      </details>
    `).join("")}</div>
  ` : empty("没有匹配笔记", "换个关键词再试。");
  bindOrganizeNoteButtons();
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
      body: JSON.stringify({ title: $("#note-title").value.trim() || "无标题", body, project_id: $("#note-project")?.value || "" }),
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

function bindOrganizeNoteButtons() {
  document.querySelectorAll("[data-organize-note]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "整理中...";
      try {
        const result = await api(`/api/notes/${button.dataset.organizeNote}/organize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        showToast(`已提取 ${result.insights.length} 条洞察`);
      } catch (error) {
        showToast(userMessage(error), "error");
      } finally {
        button.disabled = false;
        button.textContent = "整理洞察";
      }
    });
  });
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

async function renderDecisions() {
  setTitle("项目判断", "决策");
  [state.notes, state.memories] = await Promise.all([api("/api/notes"), api("/api/memories")]);
  const noteDecisions = state.notes.flatMap((note) => extractDecisionLines(note).map((decision) => ({
    title: decision,
    source: displayNoteTitle(note),
    created_at: note.updated_at,
    body: note.body,
  })));
  const memoryDecisions = state.memories
    .filter((memory) => memory.status === "approved" && /决策|决定|原则|约束/.test(`${memory.title} ${memory.body}`))
    .map((memory) => ({
      title: memory.title,
      source: "已批准记忆",
      created_at: memory.updated_at,
      body: memory.body,
    }));
  const decisions = [...noteDecisions, ...memoryDecisions].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  view.innerHTML = `
    ${panel("决策日志", decisions.length ? `
      <div class="list">
        ${decisions.map((decision) => `
          <article class="item">
            <div class="item-title">${escapeHtml(decision.title)}</div>
            <div class="meta">${escapeHtml(decision.source)} · ${formatDate(decision.created_at)}</div>
            <p>${escapeHtml(String(decision.body || "").slice(0, 220))}</p>
          </article>
        `).join("")}
      </div>
    ` : empty("还没有决策", "在项目笔记里写“决策: 选择方案 A，因为...”即可进入决策日志和项目恢复卡。"))}
  `;
}

function extractDecisionLines(note) {
  return String(note.body || "").split(/\r?\n/)
    .map((line) => line.trim())
    .map((line) => line.match(/^(?:[-*]\s*)?(?:决策|决定|DECISION)[:：](.+)$/i))
    .filter(Boolean)
    .map((match) => match[1].trim())
    .filter(Boolean);
}

async function renderDeliverables() {
  setTitle("输出", "交付物");
  state.projects = await loadProjects();
  const projectId = state.projects[0]?.id || "";
  const deliverables = projectId ? await api(`/api/deliverables?project_id=${encodeURIComponent(projectId)}`) : [];
  view.innerHTML = `
    <div class="grid two wide-left">
      ${panel("生成交付物", `
        <form id="deliverable-form" class="form-stack">
          ${projectSelect("deliverable-project", "选择项目")}
          <label class="small" for="deliverable-template">模板</label>
          <select id="deliverable-template">
            <option value="weekly">项目周报</option>
            <option value="plan">下一步计划</option>
            <option value="review">项目复盘</option>
            <option value="client">客户汇报</option>
            <option value="risk">风险清单</option>
          </select>
          <div class="split-actions"><button class="primary" type="submit">生成 Markdown</button></div>
          <div id="deliverable-status" class="small"></div>
        </form>
      `)}
      ${panel("最近交付物", deliverables.length ? deliverableMiniList(deliverables) : empty("还没有交付物", "选择项目和模板后，可以生成可复制的 Markdown。"))}
    </div>
  `;
  const select = $("#deliverable-project");
  if (select && projectId) select.value = projectId;
  $("#deliverable-form").addEventListener("submit", createDeliverable);
}

async function createDeliverable(event) {
  event.preventDefault();
  const status = $("#deliverable-status");
  const projectId = $("#deliverable-project").value;
  if (!projectId) {
    status.textContent = "请选择项目。";
    status.className = "small error";
    return;
  }
  status.textContent = "正在生成...";
  try {
    const item = await api("/api/deliverables", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, template: $("#deliverable-template").value }),
    });
    status.innerHTML = `已生成：${escapeHtml(item.title)}`;
    showToast("交付物已生成");
    await renderDeliverables();
  } catch (error) {
    status.textContent = userMessage(error);
    status.className = "small error";
    showToast(userMessage(error), "error");
  }
}

async function renderMemories() {
  setTitle("长期上下文", "记忆");
  [state.memories, state.projects] = await Promise.all([api("/api/memories"), loadProjects()]);
  const candidates = state.memories.filter((memory) => memory.status === "candidate");
  const approved = state.memories.filter((memory) => memory.status === "approved");
  const archived = state.memories.filter((memory) => memory.status === "archived");
  view.innerHTML = `
    <div class="grid two balanced-grid">
      ${panel("记忆审核箱", candidates.length ? memoryList(candidates) : empty("没有待审记忆", "在笔记里写 MEMORY: 或 记忆: 可以创建可审核记忆。"))}
      ${panel("新增记忆", `
        <form id="memory-form" class="form-stack">
          <input id="memory-title" placeholder="标题" />
          ${projectSelect("memory-project", "选择所属项目")}
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
      body: JSON.stringify({ title: $("#memory-title").value, body, status: $("#memory-status").value, project_id: $("#memory-project")?.value || "" }),
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
        <div class="local-model-box">
          <div class="item-row">
            <div>
              <div class="item-title">本地模型自动发现</div>
              <div class="small">检测 Ollama、LM Studio、LocalAI、Jan 等 OpenAI-compatible 本地服务。</div>
            </div>
            <button id="discover-models" type="button">扫描本地模型</button>
          </div>
          <div id="model-discovery-results" class="model-discovery-results"></div>
        </div>
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
  $("#discover-models").addEventListener("click", discoverModels);
}

async function discoverModels() {
  const button = $("#discover-models");
  const results = $("#model-discovery-results");
  button.disabled = true;
  button.textContent = "扫描中...";
  results.innerHTML = `<div class="small">正在检查常见本地模型端口...</div>`;
  try {
    const discovery = await api("/api/models/discover");
    if (!discovery.found?.length) {
      results.innerHTML = `
        <div class="notice">
          <div class="notice-title">没有发现正在运行的本地模型服务</div>
          <p>可以先启动 Ollama、LM Studio、LocalAI 或 Jan，并确认它们开放 OpenAI-compatible API。</p>
        </div>
      `;
      return;
    }
    results.innerHTML = `
      <div class="list">
        ${discovery.found.map((item, index) => `
          <article class="item">
            <div class="item-row">
              <div>
                <div class="item-title">${escapeHtml(item.provider)} · ${escapeHtml(item.model)}</div>
                <div class="meta">${escapeHtml(item.base_url)} · ${item.models.length} 个模型</div>
                <div class="tool-row">${item.models.slice(0, 6).map((model) => `<span class="tag">${escapeHtml(model)}</span>`).join("")}</div>
              </div>
              <button class="primary" data-local-model="${index}" type="button">使用</button>
            </div>
          </article>
        `).join("")}
      </div>
    `;
    results.querySelectorAll("[data-local-model]").forEach((itemButton) => {
      itemButton.addEventListener("click", () => applyDiscoveredModel(discovery.found[Number(itemButton.dataset.localModel)]));
    });
  } catch (error) {
    results.innerHTML = `<div class="small error">${escapeHtml(userMessage(error))}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "扫描本地模型";
  }
}

function applyDiscoveredModel(item) {
  $("#settings-base-url").value = item.base_url;
  $("#settings-model").value = item.model;
  $("#settings-api-key").value = item.api_key || "local";
  showToast(`已填入 ${item.provider} / ${item.model}，点击保存设置后生效`);
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
    if (viewName === "sources") await renderSources(payload);
    if (viewName === "wiki") await renderWiki(payload);
    if (viewName === "search") await renderSearch(payload);
    if (viewName === "chat") await renderChat();
    if (viewName === "notes") await renderNotes();
    if (viewName === "projects") await renderProjects(payload);
    if (viewName === "collections") await renderCollections(payload);
    if (viewName === "tasks") await renderTasks();
    if (viewName === "decisions") await renderDecisions();
    if (viewName === "deliverables") await renderDeliverables();
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

async function wikiPost(path, data = {}) {
  return api(`/api/wiki/${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
}

async function renderWiki(slug = "") {
  setTitle("知识库", "知识页面");
  const [pages, pending, lint, settings] = await Promise.all([
    api("/api/wiki/pages"), api("/api/wiki/pending"), api("/api/wiki/lint"), api("/api/wiki/settings"),
  ]);
  const page = slug ? await api(`/api/wiki/pages/${encodeURIComponent(slug)}`) : null;
  const e = escapeHtml;
  const link = (s, title = s) => `<button type="button" data-wiki-page="${e(s)}">${e(title)}</button>`;
  view.innerHTML = `
    <div class="toolbar"><span>${pages.length} 个页面 · ${pending.length} 条待审 · ${lint.issues.length} 项检查提示</span><button id="wiki-refresh">刷新</button><button id="wiki-rebuild">整理资料</button></div>
    <p class="small">上传资料后自动整理为知识页面。人工修订经审核发布后保留，历史正文可回滚。</p>
    <label class="wiki-setting"><input id="wiki-auto" type="checkbox" ${settings.auto_apply ? "checked" : ""}> 自动发布资料整理结果（关闭后进入待审队列）</label>
    <div class="wiki-layout">
      ${panel("页面目录", `<label>筛选页面<input id="wiki-filter" placeholder="按标题查找"></label><div id="wiki-directory">${pages.map(p => `<div class="wiki-directory-item" data-title="${e(p.title.toLowerCase())}">${link(p.slug, p.title)}<span class="small">${e(({topic:"主题",entity:"实体",compose:"材料",manual:"手工"})[p.kind] || p.kind)} · ${p.evidence_count} 条证据</span></div>`).join("") || empty("还没有知识页面", "先去资料库上传文件，再回来查看。")}</div><button data-nav="sources">前往资料库</button>`)}
      ${panel(page ? page.title : "阅读与修订", page ? `
        <p class="small">${page.origin === "manual" ? "人工维护" : page.origin === "redirect" ? "重定向" : "自动整理"} · ${e(page.updated_at)}</p>
        <pre class="wiki-body">${e(page.body).replace(/\[\[([^\]]+)\]\]/g, (_, target) => link(target, `[[${target}]]`))}</pre>
        <details><summary>原文证据（${page.evidence.length}）</summary>${page.evidence.map(ev => `<article class="wiki-evidence"><button data-wiki-source="${e(ev.source_id)}">${e(ev.source_title)} · 第 ${ev.page_start}–${ev.page_end} 页</button>${ev.superseded ? '<strong class="error"> 已被新版取代</strong>' : ""}<p>${e(ev.quote)}</p></article>`).join("") || '<p class="small">此页面暂无原文证据。</p>'}</details>
        <p>出链：${page.links_out.map(s => link(s)).join(" ") || "无"}</p><p>入链：${page.links_in.map(s => link(s)).join(" ") || "无"}</p>
        <details><summary>修订正文（先进入审核队列）</summary><form id="wiki-edit"><label>标题<input name="title" value="${e(page.title)}" required></label><label>正文<textarea name="body" rows="12" required>${e(page.body)}</textarea></label><label>修改说明<input name="note" placeholder="本次修改原因"></label><button class="primary">生成待审差异</button></form></details>
        <details><summary>正文历史与回滚</summary><p class="small">回滚会产生新版本；恢复范围为历史正文。</p>${page.revisions.map(r => `<div class="toolbar"><span>版本 ${r.rev} · ${e(r.note)} · ${e(r.created_at)}</span><button data-wiki-rev="${r.rev}">恢复此正文</button></div>`).join("")}</details>` : empty("选择一个页面", "点击左侧目录阅读正文、核对原文证据或提交修订。"))}
    </div>
    ${panel(`待审修改（${pending.length}）`, pending.map(op => `<details class="wiki-op"><summary>${e(op.proposed_title)} · ${e(({create:"新建",update:"更新",delete:"删除"})[op.op_type] || op.op_type)}</summary><p>${e(op.note)}</p><pre class="wiki-diff">${e(op.diff_text)}</pre><details><summary>完整拟发布正文</summary><pre class="wiki-body">${e(op.proposed_body)}</pre></details><div class="toolbar"><button class="primary" data-wiki-op="${e(op.id)}" data-action="apply">批准发布${op.op_type === "delete" ? "删除" : ""}</button><button data-wiki-op="${e(op.id)}" data-action="discard">丢弃</button></div></details>`).join("") || '<p class="small">没有待审修改。</p>')}
    ${panel("生成带出处的材料", `<form id="wiki-compose"><label>材料标题<input name="title" required placeholder="例如：本周研究进展"></label><label>类型<select name="template"><option value="outline">提纲</option><option value="weekly">周报素材</option><option value="study">学习材料</option></select></label><fieldset><legend>选择知识页面</legend><div class="wiki-picks">${pages.filter(p => p.origin !== "redirect").map(p => `<label><input type="checkbox" name="slug" value="${e(p.slug)}"> ${e(p.title)}</label>`).join("") || "请先导入资料"}</div></fieldset><p class="small">按所选页面的原文证据抽取要点，请核对后使用。</p><button class="primary" ${pages.length ? "" : "disabled"}>预览材料</button></form><div id="wiki-compose-result"></div>`)}
    ${panel("知识检查", lint.issues.map(i => `<p><strong>${e(i.severity === "error" ? "错误" : "提示")}</strong> ${link(i.slug)} · ${e(i.detail)}</p>`).join("") || '<p class="small">未发现断链、孤立页、陈旧证据或疑似矛盾。</p>')}
  `;
  bindInlineNav();
  const action = (selector, fn) => view.querySelectorAll(selector).forEach(el => el.addEventListener("click", async () => {
    el.disabled = true;
    try { await fn(el); } catch (error) { showToast(userMessage(error), "error"); }
    finally { el.disabled = false; }
  }));
  action("[data-wiki-page]", el => navigate("wiki", el.dataset.wikiPage));
  action("[data-wiki-source]", el => navigate("sources", el.dataset.wikiSource));
  action("#wiki-refresh", () => navigate("wiki", slug));
  action("#wiki-rebuild", async () => { await wikiPost("rebuild", {dry_run:false}); await navigate("wiki"); showToast("资料已整理，待审结果见审核队列"); });
  $("#wiki-auto").addEventListener("change", async event => {
    const input = event.target; input.disabled = true;
    try { await wikiPost("settings", {auto_apply:input.checked}); showToast("发布方式已保存"); }
    catch (error) { input.checked = !input.checked; showToast(userMessage(error), "error"); }
    finally { input.disabled = false; }
  });
  $("#wiki-filter").addEventListener("input", event => view.querySelectorAll(".wiki-directory-item").forEach(el => {el.hidden = !el.dataset.title.includes(event.target.value.toLowerCase());}));
  action("[data-wiki-op]", async el => {
    await wikiPost(`ops/${encodeURIComponent(el.dataset.wikiOp)}/${el.dataset.action}`);
    await navigate("wiki"); showToast(el.dataset.action === "apply" ? "修改已发布" : "修改已丢弃");
  });
  action("[data-wiki-rev]", async el => {
    if (!window.confirm(`将「${page.title}」正文恢复至版本 ${el.dataset.wikiRev}？当前正文会保留为历史版本。`)) return;
    await wikiPost(`pages/${encodeURIComponent(slug)}/rollback`, {rev:Number(el.dataset.wikiRev)});
    await navigate("wiki", slug); showToast("正文已恢复");
  });
  if (page) $("#wiki-edit").addEventListener("submit", async event => {
    event.preventDefault(); const form = event.target; const button = form.querySelector("button"); button.disabled = true;
    try { await wikiPost("propose", {slug, ...Object.fromEntries(new FormData(form))}); await navigate("wiki", slug); showToast("修订已进入待审队列"); }
    catch (error) { showToast(userMessage(error), "error"); }
    finally { button.disabled = false; }
  });
  $("#wiki-compose").addEventListener("submit", async event => {
    event.preventDefault(); const form = event.target; const data = new FormData(form); const slugs = data.getAll("slug");
    if (!slugs.length) { showToast("请至少选择一个页面", "error"); return; }
    const button = form.querySelector("button"); button.disabled = true;
    try {
      const result = await wikiPost("compose", {slugs, title:data.get("title"), template:data.get("template"), save:false});
      $("#wiki-compose-result").innerHTML = `<h3>材料预览</h3><pre class="wiki-body">${e(result.markdown)}</pre><button id="wiki-save-compose" class="primary">提交到待审队列</button>`;
      action("#wiki-save-compose", async () => {
        const title = String(data.get("title"));
        await wikiPost("propose", {slug:`material-${Date.now()}`, title, body:result.markdown, note:"材料预览后提交"});
        await navigate("wiki"); showToast("材料已进入待审队列");
      });
    } catch (error) { showToast(userMessage(error), "error"); }
    finally { button.disabled = false; }
  });
}
