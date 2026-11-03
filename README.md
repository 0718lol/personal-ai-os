# Personal AI OS

一个本地优先的个人 AI 工作台：把 PDF、资料、笔记、任务、长期记忆和轻量智能体放进同一个清爽界面里。

它不是又一个“上传 PDF 然后聊天”的小工具。Personal AI OS 的目标是成为研究者、产品经理、开发者、独立创作者和咨询分析师的个人知识操作台：资料进来以后，可以被搜索、引用、整理、记住，并逐步变成任务、决策和行动。

## 适合谁

- 研究者和学生：管理论文、PDF、实验记录、文献线索和研究问题。
- 产品经理和创业者：沉淀竞品资料、用户反馈、路线图、会议结论和待办事项。
- 开发者和技术负责人：整理架构笔记、调试记录、方案评审、项目上下文。
- 写作者和内容研究者：收集素材、保存灵感、检索来源、形成文章大纲。
- 咨询、投资、分析岗位：处理报告、政策、市场材料、会议笔记和风险判断。

## 核心体验

- 第一屏直接进入工作台，不做营销落地页。
- 本地 SQLite 存储，资料和笔记默认留在本机。
- 上传 Markdown、文本、CSV、JSON、PDF，自动抽取文本并建立检索内容块。
- PDF 多解析器回退：优先使用高质量解析器，失败时自动降级。
- 统一搜索资料、笔记、任务。
- 问答支持引用来源，没有模型 key 时也能用本地检索摘要。
- 笔记支持分页、搜索、无标题状态、正文预览、展开完整查看。
- TODO/待办自动转任务，记忆内容进入审核箱。
- 长期记忆有审核、批准、归档流程，不会静默污染上下文。
- 智能体模板、运行记录、连接器占位，为后续自动化扩展留出路径。
- 设置页清楚展示模型配置和隐私边界。

## 为什么值得做

现在很多 AI 工具把“聊天”当成全部体验，但真实工作流通常是：

1. 资料不断进来。
2. 你需要快速找到过去看过的东西。
3. 重要事实要变成长期上下文。
4. 决策和任务要能被追踪。
5. AI 生成的回答必须能回到来源。

Personal AI OS 把这些放在一起：先做一个能每天用的本地工作台，再逐步扩展为真正的个人 AI 操作系统。

## 功能一览

| 模块 | 能做什么 |
| --- | --- |
| 首页 | 快速导入、提问、记录笔记、查看运行队列和最近资料 |
| 资料库 | 上传文件、解析 PDF、查看文本、页码证据块和解析报告 |
| 搜索 | 横跨资料、笔记、任务的统一检索 |
| 问答 | 基于本地资料回答，展示引用来源 |
| 笔记 | 快速记录、分页浏览、搜索、展开完整内容 |
| 任务 | 从笔记中的 `TODO:` 或 `待办:` 自动生成任务 |
| 记忆 | 从笔记中提取候选记忆，人工审核后进入长期上下文 |
| 智能体 | 研究、计划、资料审核、记忆审核等模板 |
| 连接器 | GitHub、Notion、文件夹监听、日历、浏览器采集等扩展入口 |
| 设置 | 模型服务、API key、隐私边界 |

## 本地运行

要求：

- Python 3.11+
- Node.js 18+

安装依赖：

```bash
cd personal-ai-os
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm install
```

启动：

```bash
PORT=8000 ./start.sh
```

打开：

```text
http://localhost:8000
```

测试时可以通过 `PERSONAL_AI_OS_DATA_DIR` 指定独立数据目录，避免污染默认工作区：

```bash
PERSONAL_AI_OS_DATA_DIR=/tmp/personal-ai-os-test .venv/bin/python -m unittest discover -s tests -q
```

如果你在 ASteam 产品托管环境里运行，`app.toml` 已经配置好入口，平台会自动注入 `$PORT` 并托管服务。

## 模型配置

不配置模型也可以使用：

- 导入资料
- 搜索资料和笔记
- 查看 PDF 抽取内容
- 使用本地检索摘要
- 记录笔记、任务和记忆候选

配置 OpenAI-compatible API 后，问答会在引用本地资料后调用模型生成更自然的回答。

API key 存在本地运行数据中，不写入源码。

## 数据和隐私

- SQLite 数据库位于 `data/`，默认不会提交到 Git。
- 上传文件和抽取文本也在本地产品目录中。
- 只有在你配置模型 key 并触发问答时，相关上下文才会发送给模型服务。
- `.env`、运行日志、数据库、`node_modules`、缓存目录都已在 `.gitignore` 中排除。

## 当前阶段

这是一个可用的早期版本，重点是把核心工作流跑通：

- 本地资料库
- PDF 能力
- 笔记和分页列表
- 任务抽取
- 记忆审核
- 引用式问答
- 清爽的桌面/移动端体验

后续适合继续推进：

- 更强的 OCR 和扫描 PDF 支持
- 真实语义嵌入模型和更大规模检索验证
- 可编辑记忆
- 更多连接器
- 智能体权限和审批
- 导入/导出工作区
- 多项目隔离

## 项目结构

```text
personal-ai-os/
├── public/              # 前端界面
├── server.py            # Python 后端和 SQLite API
├── mcp_server.py        # 只读 MCP server（stdio JSON-RPC）
├── pdf_extract_node.mjs # Node PDF 解析回退
├── requirements.txt     # Python 依赖
├── package.json         # Node 依赖
├── app.toml             # ASteam 托管配置
└── start.sh             # 启动脚本
```

## 设计原则

- 用户体验优先于代码优雅。
- 第一屏直接进入核心操作。
- 常用动作明显，步骤少。
- 手机和电脑都要能用。
- 空状态、错误状态、成功反馈必须清楚。
- 本地优先，远程模型可替换。
- 记忆和自动化必须可审查、可回退。


## 知识页面工作流（2026-11-03）

1. 在「资料库」上传资料，再进入「知识页面」浏览主题与实体。
2. 阅读正文、双向链接和原文证据，点击证据可打开对应资料。
3. 展开「修订正文」，填写修改后生成待审差异；在待审队列核对差异与完整正文，再批准或丢弃。
4. 「正文历史与回滚」可恢复历史正文并保留新版本。回滚范围为正文，不含标题、别名和证据关系。
5. 选择页面生成提纲、周报素材或学习材料，预览后提交待审，审核发布。生成采用原文抽取，不等于模型综合写作。
6. 「自动发布资料整理结果」默认开启；关闭后，后续自动编译结果先进入审核队列。切换不会自动处理已有队列。

人工维护的页面不会被自动整理覆盖。页面正文变化后，旧提案会被拦截，请丢弃并重新生成。早期没有保存正文基线的旧队列也需重新生成。

检索使用原文 FTS、中文双字 FTS、字符哈希向量和 RRF；哈希向量不具备真实语义理解。问答区显示低置信与拒答状态，且只显示当前回答的引用。无答案合成评测中，4/10 拒答、6/10 低置信作答，不能把低置信提示当作答案正确。

## 只读 MCP 接口
`mcp_server.py` 通过 stdio JSON-RPC（MCP 协议）把知识库以只读方式暴露给 MCP 客户端（如 Claude Desktop、Cursor 等）：

- `wiki_search`：门控检索，返回置信档（confident/low/abstain）与证据片段
- `wiki_read_page`：读取页面正文、证据、结论与修订历史
- `wiki_list_pages`：列出全部知识页面
- `wiki_lint`：列出知识检查问题及处理状态

启动（数据目录与主服务一致，默认 `data/`）：

```bash
.venv/bin/python mcp_server.py
```

MCP 客户端配置示例（command 按实际路径调整）：

```json
{
  "mcpServers": {
    "personal-ai-os": {
      "command": "/path/to/personal-ai-os/.venv/bin/python",
      "args": ["/path/to/personal-ai-os/mcp_server.py"],
      "env": { "PERSONAL_AI_OS_DATA_DIR": "/path/to/personal-ai-os/data" }
    }
  }
}
```

说明：
- 数据库以 SQLite 只读模式打开，不提供任何写操作工具。
- 服务未启动或数据库不存在时，工具调用会返回错误文本。
- 回归测试见 `tests/test_mcp_server.py`。

## 验证与数据边界

```bash
.venv/bin/python -m unittest discover -s tests -q
node --check public/app.js
.venv/bin/python tests/golden/run_baseline.py
```

黄金集覆盖 55 条查询与 5 条导入/更新操作；另有 10 条真实 PDF 评测，结果见 `tests/golden/`。关键词命中与引用覆盖不等于事实正确性，模型生成路径尚未验收。历史 M0/M1/M2/P1 报告保留用于追溯，最新验收结论见 `docs/CLOSEOUT.md`。

浏览器验收脚本为 `tests/browser_smoke.cjs`，依赖额外安装的 Playwright 与 Chromium；启动使用全新 `PERSONAL_AI_OS_DATA_DIR` 的隔离服务后，以 `BROWSER_SMOKE_BASE=http://127.0.0.1:<端口> node tests/browser_smoke.cjs` 执行。可通过 `PLAYWRIGHT_MODULE` 与 `BROWSER_EXECUTABLE` 指定已有运行时。该脚本会上传测试资料并操作审核队列，仅用于隔离实例。

启动脚本优先使用项目 `.venv`，启动时不联网安装依赖。`npm install` 在初始化时完成；未安装 Node 解析依赖时仍可使用 Python PDF 解析器。

当前运行数据位于 `data/`，与测试隔离且被 Git 忽略。备份时请在停止服务后复制整个 `data/`，包括 SQLite、原始上传文件与 Wiki 镜像。恢复时先停止服务，再还原该目录。程序不会自动迁移或删除其他应用的知识库。
