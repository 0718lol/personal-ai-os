# P1 迭代报告与完成度对照

- 日期:2026-11-03
- 本轮目标:按总规划表格补齐 P1 缺口,并把验证面扩到真实语料
- 验证:回归 **22/22**;合成黄金集 55 用例(全绿);真实简历 10 用例(全过);巡检 cron 每 10 分钟跑测试

## 一、完成度对照表(对照总规划)

### 三层架构

| 层 | 状态 | 证据 |
|---|---|---|
| 证据层 | ✅ | 原始文件只读保存、SHA-256 幂等、chunk 带 source_id/页码/content_hash、三级解析回退 |
| 知识层 | ✅ | 主题页/实体页/双向链接/index.md/log.md/版本快照/回滚;**本轮新增别名与重定向页** |
| 应用层 | ⚠️ | 问答(三档置信)+检索(三路 RRF)+**本轮 compose(周报/提纲/学习材料,抽取式)**;MCP/Agent 接口未做 |

### P0(必须可靠)—— 7/7 全部完成

| 项 | 状态 |
|---|---|
| 重复导入不产生重复资料 | ✅ OP01/OP02 |
| 文件变化只处理受影响内容 | ✅ 同名更新→新版本 source + 旧版 superseded,旧 chunk 退出检索 |
| 原始文件永不被 AI 覆盖 | ✅ 上传即只读;AI 只写 wiki 层 |
| 回答定位到原文 | ✅ chunk 级引用+页码 |
| 无答案不硬编 | ✅ 三档门控,自信垃圾引用 0% |
| 整理有 diff 和回滚 | ✅ 快照+回滚+回滚留痕 |
| 基础评测集 | ✅ 55 合成 + 10 真实用例,基线可复现 |

### P1(产品差异)—— 本轮从 3/6 补到 6/6

| 项 | 状态 | 说明 |
|---|---|---|
| 自动生成并增量更新知识页面 | ✅ | 上传即增量编译受影响页面 |
| 同一实体的别名合并 | ✅ **本轮** | `merge_pages`:证据并入规范页,源页转重定向存根(历史保留),别名进实体抽取的归并表 |
| 双向链接和主题目录 | ✅ | [[slug]] + index.md 自动维护 |
| 孤立/断链/重复/冲突/过期检查 | ✅ **本轮补疑似矛盾** | lint 六类:orphan/broken_link/duplicate_entity/stale_evidence/empty_page/**suspected_conflict**(同页不同来源同单位不同数值,warning 级) |
| 人工修订不被编译覆盖 | ✅ **本轮** | origin=manual 页面被自动编译跳过(dry_run 报告 skipped),`force` 为显式逃生口 |
| 基于指定资料生成周报/提纲/学习材料 | ✅ **本轮** | `POST /api/wiki/compose`:outline/weekly/study 三模板,抽取式、全带 [[出处]] 页码,可存为页面(manual 保护) |

### P2(实验)—— 按数据决策

| 项 | 状态 |
|---|---|
| PageIndex / LightRAG / Graphiti | 暂缓——黄金集失败案例为 0,无实验必要性(符合"先证明现有方案失败"的门槛) |
| 只读 MCP | ❌ 未做,下一迭代候选(API 已齐,MCP 是薄封装) |
| 长期记忆 | memories 审核流已有;与 wiki 整合未做 |

### 六类核心对象

| 对象 | 状态 |
|---|---|
| Source / Chunk / WikiPage | ✅(WikiPage 本轮加 aliases) |
| Claim/Citation | ⚠️ 页面级证据(wiki_evidence)已落,结论级 Claim 未拆出 |
| ChangeSet | ✅ **本轮**:每次编译的增删改都落 wiki_pending_ops(diff+原因+证据 payload),`wiki_auto_apply` 开=自动应用+留审计,关=进待审队列人工发布 |
| LintIssue | ✅ **本轮加 severity**;处理状态持久化未做 |

### 四阶段执行提示词

| 阶段 | 状态 |
|---|---|
| 1 体检 | ✅ M0(报告+基线) |
| 2 可靠入库/检索/引用 | ✅ M1(损坏 PDF/空文件降级测试本轮补;并发导入压力测试未做) |
| 3 知识编译/lint/回滚 | ✅ M2 + 本轮(ChangeSet 化、别名、人工保护补齐) |
| 4 前沿实验 | 依数据暂缓(见 P2) |

## 二、本轮代码变更

| 文件 | 变更 |
|---|---|
| `wiki.py`(重写,~700 行) | 编译统一为"计划→ChangeSet→应用/待审"管线;别名合并;人工保护;疑似矛盾 lint;compose;重定向页语义 |
| `server.py` | schema 新列(wiki_pages.aliases、ops.source/payload)+ 6 个新端点(settings GET/POST、merge、compose、rebuild force) |
| `tests/test_p1_iteration.py`(新增 7 条) | 别名合并/人工保护+force/ChangeSet 队列与审计/疑似矛盾/compose/损坏 PDF 与空文件 |

## 三、验证数字

- 回归:22/22(原 15 + 新 7)
- 合成黄金集:fact_single 1.0 / fact_cross 1.0 / 自信垃圾引用 0.0 / conflict_surfaced 1.0
- 真实简历(2 份 PDF):事实 8/8、无答案拒答 2/2、wiki 18 页、lint 干净
- 舆情闭环:巡检 cron 每 10 分钟跑一次 22 条回归(改动即验证,失败即上报)

## 四、剩余缺口(下一迭代建议顺序)

1. **只读 MCP server**(P2 唯一高性价比项):把 /api/search、/api/chat、/api/wiki/pages 包成 MCP 工具,编程 Agent 即可安全用库;写入仍走 propose 审核流
2. **前端 UI**:wiki 页面浏览/diff 审核队列/compose 入口(后端 API 全齐,public/app.js 未动)
3. Claim 级证据拆分 + lint 处理状态持久化
4. 并发导入压力测试;compose 接模型 key 后的 LLM 增强;中文实体抽取(需分词或 LLM)
5. 真实语料扩容:目前 10 条真实用例,建议再灌会议纪要/项目文档类资料,黄金集扩到 100+
