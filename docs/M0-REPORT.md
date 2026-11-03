# M0 项目体检报告

- 日期:2026-11-03
- 对象:`0718lol/personal-ai-os` @ `cff3907`(main)
- 结论:**改造可行,M1 优先修复中文检索与无答案防护**。基线已量化,全部数据可复现(见 `tests/golden/`)。

## 1. 数据流(现状)

```
上传文件(multipart /api/sources/upload)
  → SHA-256 checksum 查重(命中 → duplicate:true,关联项目,结束)
  → extract_text(kind 分派)
       pdf → 9 级回退链:docling CLI → marker CLI → mineru CLI → pymupdf4llm
             → PyMuPDF → node mupdf → markitdown → pypdf → rough
       其他 → 按 utf-8/utf-16/latin-1 直接读文本(md/csv/txt 一视同仁)
  → normalize_text → evidence_chunks(1400 字 / 180 重叠;PDF 先按页切)
  → SQLite: sources(含 checksum/quality_json/parser_engine) + chunks(source_id,
     chunk_index,page_start,page_end)  [无 chunk 内容哈希、无版本字段]
  → FTS5 chunks_fts(外部内容表 + ai/ad/au 三个触发器同步)
  → 检索 /api/search:FTS bm25() 排序 → 不足 limit 时 LIKE '%q%' 兜底拼接
  → 问答 /api/chat:search_chunks(8 条) → call_llm(有 key 走 OpenAI 兼容接口,
     无 key 走 local_answer:拼接 top4 摘要) → citations 固定取 contexts[:6]
  → 周边域:notes/tasks/memories(status 审核流)/agents/runs/collections(项目)/
     events(追加式操作日志)/connectors/playbooks/insights/deliverables
```

## 2. 模块地图

| 位置 | 内容 | 备注 |
|---|---|---|
| `server.py`(2256 行,单文件) | schema(`init_db`,17 张表)、解析链、分块、检索、HTTP 路由(do_GET/do_POST/do_DELETE)、全部业务域 | 无模块边界,是最大技术债;M1 允许按职责拆分 |
| `public/`(app.js 1698 行) | 原生 JS 前端,无构建步骤 | 检索/问答改动需同步前端引用跳转 |
| `pdf_extract_node.mjs` | node mupdf 解析适配器 | 可选回退,无 node 时跳过 |
| `tests/test_workflow.py` | 项目/笔记/任务回归(子进程起服务 + 临时数据目录) | 本基线沿用同一模式 |
| `tests/golden/`(本次新增) | 合成语料生成器、60 条黄金用例、基线运行器、`BASELINE.md` | 复现:`make_fixtures.py` → `run_baseline.py` |

存储:单 SQLite 文件(`PERSONAL_AI_OS_DATA_DIR` 可隔离);运行依赖仅 pypdf/PyMuPDF/pymupdf4llm;**需要 Python ≥3.10**(`str | None` 运行时求值,3.9 会崩)。

## 3. 与 M0 前核查结论的对照

| 此前判断 | 实测 | 状态 |
|---|---|---|
| checksum 幂等导入已实现 | OP01/OP02 通过(同文件、同内容改名均 duplicate) | ✅ 证实 |
| chunks 已有 source_id/chunk_index/page_start/page_end | schema 属实;PDF 页码回跳可用 | ✅ 证实 |
| 检索是 FTS5 bm25 + LIKE 兜底 | 属实;但中文查询命中能力见 D1 | ✅ 证实 + 新缺陷 |
| memories.status 审核流、events 追加日志 | 属实(candidate→approved→archived) | ✅ 证实 |
| citations 落到 chunk 级 | citations 固定取检索 top6,与答案内容无关联校验 | ⚠️ 部分证实(见 D6) |

## 4. 缺陷清单(按基线数据定级)

| # | 级别 | 缺陷 | 基线证据 |
|---|---|---|---|
| D1 | **P0** | **中文自然语言检索基本失效**:FTS5 unicode61 把连续中文当作单个 token,自然中文问题无法匹配;LIKE 兜底要求整句连续子串,同样失效。检索可用性完全依赖问题里恰好带英文/数字词 | fact_single 10 条纯中文问题 **0/10** 全部检索为空而拒答;含英文词的 24 条全部通过(70.6%);conflict 4 条纯中文 0/4 |
| D2 | **P0** | **无答案防护弱**:检索非空即引用,LIKE 兜底会捞出弱相关内容冒充证据,local_answer 把它们当作"可追溯摘要"输出 | no_answer 正确拒答率仅 **40%**,垃圾引用率 **60%** |
| D3 | **P1** | **资料更新无版本语义**:同名不同内容导入后新旧 source 并存,无 superseded 标记,新旧 chunk 同时可检、同时被引,矛盾不可见 | OP03:source 1→2、无任何标记;OP04:新旧吞吐值同现于 top3 与引用;OP05:2.4 与 2.5 两版 chunk 同页被引 |
| D4 | **P1** | **冲突内容无处理机制**:两文档口径冲突时既不并列呈现也不提示冲突 | conflict_surfaced = **0%** |
| D5 | P2 | 单文件 2256 行,HTTP/解析/检索/业务全域耦合,改动回归面大 | wc -l;M1 拆分时需测试护航 |
| D6 | P2 | 引用与答案脱钩:citations 恒为检索 top6,不校验答案是否真的使用该证据;"引用看起来很全"但不等于"答案有据" | /api/chat 实现(chat() 方法) |
| D7 | P3 | chunk 无 content_hash,跨版本 chunk 不可比对;文档级 checksum 有但未用于更新判定 | schema |

已验证可用的部分:幂等导入、PDF 9 级回退链(合成 PDF 提取正常)、FTS 触发器同步、中文查询参数解码、页码级引用结构、memory 审核流、events 日志。

## 5. 黄金测试集

- `tests/golden/golden_cases.json`:55 个评测用例(fact_single 34 / fact_cross 7 / no_answer 10 / conflict 4)+ 5 个操作性用例,覆盖事实问答、跨文档总结、无答案、重复导入、资料更新、冲突内容。
- 语料:`make_fixtures.py` 生成 12 个文件(7 md + 2 pdf + 1 csv + 2 个更新/副本变体),事实带 `【Kxx】` 标记便于对账。
- 复现:`.venv/bin/python tests/golden/make_fixtures.py && .venv/bin/python tests/golden/run_baseline.py`(隔离临时数据目录,不污染真实 data/)。
- **局限**:当前为合成语料,数字偏乐观;接入用户真实资料后需扩充用例并重跑基线。

## 6. 基线指标(2026-11-02,无 key 降级路径)

| 类别 | n | search@5 | citation_hit | kw_in_answer | 附加 |
|---|---|---|---|---|---|
| fact_single | 34 | 0.706 | 0.706 | 0.706 | 纯中文子集 0/10 |
| fact_cross | 7 | 0.857 | 0.857 | 0.857 | 3 条未覆盖全部文档 |
| no_answer | 10 | — | — | — | 正确拒答 0.4 / 垃圾引用 0.6 |
| conflict | 4 | 0.0 | 0.0 | 0.0 | 冲突呈现 0.0 |
| 总体 | 55 | 0.667 | 0.667 | 0.667 | |

操作性用例:OP01 ✅ OP02 ✅ OP03–05 记录缺陷(见 D3)。

## 7. 对 M1 的输入(按数据定优先级)

1. **D1 修复是 M1 第一优先**:中文检索修复(分词或字符 n-gram 的 BM25 腿)+ 向量召回腿 + RRF。这不是"锦上添花的混合检索",而是"从不可用到可用"的修复。
2. **D2 与 D1 同批处理**:检索改为可置信排序后,设无答案阈值,LIKE 兜底降级为最后手段并显式标注"低置信"。
3. **D3 版本化更新**:同名更新 → 新版 source + 旧版标 superseded 并从默认检索中剔除(保留可回溯)。
4. D4(冲突)、D6(引用一致性)留给 M2 的知识编译层与评测增强。
5. D5:拆分 `server.py` 建议在 M1 动手前先做最小拆分(extraction / retrieval / llm / http 四模块),全程跑 `tests/test_workflow.py` + golden 守护。
