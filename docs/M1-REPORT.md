# M1 改造报告:检索可靠化

- 日期:2026-11-03
- 基线:见 `docs/M0-REPORT.md` / `tests/golden/BASELINE-M0.md`
- 本阶段后:`tests/golden/BASELINE.md`(M1 数据)、回归测试 9/9 通过

## 1. 改动清单

| 文件 | 改动 |
|---|---|
| `retrieval.py`(新增,~430 行) | 三路召回 + RRF 融合 + 置信度门控 + 索引器。纯 stdlib,零新依赖 |
| `server.py`(6 处手术,其余未动) | schema 增量迁移;上传走索引器;同名更新版本化;`search_chunks` 委托 retrieval;chat 接门控;删除时清理索引 |
| `tests/test_retrieval_m1.py`(新增) | 8 条回归:中文召回/拒答/同名更新/索引回填/幂等/删除清理 |
| `tests/golden/run_baseline.py` | ops 用例读取 `superseded` 字段 |

**未动**:前端、notes/tasks/memories/agents 全部业务域、现有 FTS 触发器、依赖清单(仍然只有 pypdf/PyMuPDF/pymupdf4llm)。

## 2. 机制说明

### D1 修复:三路召回 + RRF(检索层,`/api/search` 与 chat 共用)

1. **腿 A 原文 FTS**(原 chunks_fts,与 M0 相同):拉丁词 + 多字中文段;单字 run(如"的")剔除,不再污染排序。
2. **腿 B 中文双字 FTS**(新 `chunks_bigram`):查询与文档都切滑动双字后匹配——中文召回的真正修复。
3. **腿 C 哈希嵌入向量**(新 `chunk_vectors`):字符 n-gram 符号哈希 → 384 维 L2 归一,余弦召回。零第三方依赖、离线确定性;接口按可插拔设计,后续可换真嵌入模型/rerank。
4. 三路各自排序后 **RRF(k=60)** 融合;LIKE 兜底只在三路全空时启用,并标记 `like_fallback`。
5. 每个 chunk 建立 `content_hash`(D7)+ 双字索引 + 向量,启动时对旧数据幂等回填(`backfill_indexes`)。

### D2 修复:问答拒答门控(只作用于 `/api/chat`;`/api/search` 永远返回原始结果)

规则顺序:
1. 无结果 → 拒答(`no_results`)
2. LIKE 精确子串 → 放行(`like_exact`)
3. 查询含**库中完全不存在的拉丁词** → 拒答(`unknown_term`)
4. **信息字 IDF 加权覆盖率 ≥ 0.45** → 放行(`cjk_coverage`):功能字(的/是/什么/多少/哪)不计入,稀有字权重高——问了一个库里没有的字,覆盖被显著压低
5. top1 命中 ≥2 个拉丁词 → 放行(`latin_multi`)
6. 其余 → 拒答(`low_confidence`),事件日志记录拒答原因

### D3 修复:同名资料版本化更新

同名不同内容导入 → 新建 source,**旧版标 `superseded=1, superseded_by=<新id>`**,三路召回与 chat 引用一律排除被取代版本(资料列表仍可见,可删可溯)。事件日志记录"旧版本标记为被取代(N 份)"。

## 3. 基线对比(M0 → M1,同一 55 用例 + 5 操作用例)

| 指标 | M0 | M1 | 说明 |
|---|---|---|---|
| 总体 search@5 / citation_hit / kw_in_answer | 0.667 / 0.667 / 0.667 | **1.0 / 0.956 / 0.956** | |
| fact_single(34) | 0.706(纯中文 0/10) | **1.0** | D1 修复的直接收益 |
| fact_cross(7) | 0.857 | 0.714(检索命中仍 1.0) | FC02/FC04 被门控拦截,见 §4 |
| no_answer 正确拒答 / 垃圾引用 | 0.4 / 0.6 | **1.0 / 0.0** | D2 修复 |
| conflict_surfaced | 0.0 | **1.0** | 涌现效果:检索修好后 top4 摘要天然并列两版口径(非专门机制) |
| OP01/OP02 幂等导入 | 通过 | 通过 | 未回归 |
| OP03 同名更新 | 新旧并存、无标记 | **旧版标 superseded** | D3 修复 |
| OP04/OP05 更新后检索 | 新旧同时被引、矛盾不可见 | **只剩新版被检索/被引** | D3 修复 |
| 回归测试 | 1/1 | **9/9** | 原 workflow + 新 8 条 |

## 4. 已知边界(如实记录)

1. **词法门控的边界**:FC02("Athena 和 Hermes 各自的集群规模上限")与 FC04("年报营收 vs Q4 单季营收")被拒答——它们与垃圾问题 NA07/NA10 在词面上不可分(焦点词不存在、背景词全存在,覆盖率 0.289/0.305 vs 无答案侧最高 0.362)。检索层全部命中(search@5=1.0),只是门控不放行。**根治要靠语义判别(M2 的 LLM judge 或真嵌入模型),不靠继续调阈值**——0.28~0.36 区间同时站着对错两类问题。
2. **哈希嵌入是词法模糊匹配,不是语义**:向量的作用是兜底模糊召回,不能理解"毛利率≠营收"。同理 NA07/NA10 仍拒答失败边界内(实际它们被正确拒答了,但 FC02/FC04 被误伤——同一枚硬币的两面)。
3. **conflict_surfaced=1.0 是涌现不是机制**:两份口径进入 top4 摘要所以并列出现;若口径分散在更远位置仍会只报一边。真正的冲突检测/标注(仿 knowledge-engine 的 claim_evidence)留给 M2。
4. **citations 与答案内容仍无一致性校验**(D6 未动):citations 固定取融合检索 top6。M2 结合知识编译层一起做。
5. **大库性能未验证**:向量腿是全表扫描 + 纯 Python 点积,万级 chunk 内可用;更大的库需要 sqlite-vec 或降维,当前规模(几十~几千 chunk)无压力。

## 5. 对 M2 的输入

- 知识编译层(wiki 页面/双向链接/index.md/log.md)按原计划;lint 里的"疑似矛盾"可直接消费 §4.3 的缺口。
- AI 修改 diff/undo 复用 memories.status 审核流;版本快照表可仿 `superseded/superseded_by` 的模式。
- 页面与 chunks 的证据关联表建议照抄 knowledge-engine 的 `evidence`/`claim_evidence` 设计(此前已核实其 schema)。
- LLM judge(低置信带免责声明的第二档回答)可作为 M2 的可选项,用来收编 FC02/FC04 这类"检索到了但门控拦截"的 case。
