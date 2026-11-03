# 当前版本检索评测报告

- 运行时间:2026-11-03T14:25:17
- 黄金集:55 个评测用例 + 5 个操作性用例(tests/golden/golden_cases.json)
- 环境:隔离数据目录,无模型 API key(走 local_answer 降级路径)

## 总体指标

| 指标 | 数值 |
|---|---|
| search_top5_hit | 1.0 |
| citation_hit | 1.0 |
| kw_in_answer | 1.0 |

## 分类别指标

| 类别 | n | search@5 | citation_hit | kw_in_answer | kw_in_evidence | 附加 |
|---|---|---|---|---|---|---|
| fact_single | 34 | 1.0 | 1.0 | 1.0 | 1.0 |  |
| fact_cross | 7 | 1.0 | 1.0 | 1.0 | 1.0 |  |
| no_answer | 10 | None | None | None | None | correct_abstain=0.4, low_tier_answered=0.6, answered_with_citations=0.6, junk_citation=0.0 |
| conflict | 4 | 1.0 | 1.0 | 1.0 | 1.0 | conflict_surfaced=1.0 |

## 操作性用例(导入/更新行为)

| id | 名称 | 关键观察 | pass |
|---|---|---|---|
| OP01 | 重复导入同一文件 | `{"duplicate_flag": true, "chunk_count_unchanged": true}` | True |
| OP02 | 相同内容改名导入 | `{"duplicate_flag": true, "source_count_with_same_content": 1}` | True |
| OP03 | 同名资料内容更新 | `{"duplicate_flag": false, "athena_source_count_before": 1, "athena_source_count_after": 2, "old_marked_superseded": true}` | None |
| OP04 | 更新后检索返回新旧哪个版本 | `{"old_version_in_top3": false, "new_version_in_top3": true, "old_in_chat_evidence": false, "new_in_chat_evidence": true}` | None |
| OP05 | 更新后版本号问题的新旧证据 | `{"citations": ["...天,冷数据自动归档到对象存储,归档保留 3 年。\n【K13】自版本 2.5 起,Athena 支持 Kafka 作为上游数据源,支持断点续传与 Exactly-Once 语义。", "…台 FAQ\n\n【K70】客户数据会被用于模型训练吗?不会。客户数据仅用于提供的服务本身,不用于任何模型训练。\n【K71】支持 SSO 吗?企业版支持基于 SAML 2.0 的单点登录;社区版暂不支持。\n【K72】支持哪些导出格式?目前支持", "…es 消息队列产品规格\n\n【K20】Hermes 单分区最大容量 8GB,单个集群最多支持 256 个节点。\n【K21】版本 2.1 引入幂等生产者,版本 2.2 引入事务消息。\n【K22】默认副本数为 3,创建 Topic 时可以调整,"]}` | None |

## fact_single 未达标用例(0 条)


## fact_cross 引用未覆盖全部文档(0 条)
