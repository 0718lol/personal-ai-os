# M0 基线评测报告

- 运行时间:2026-11-02T23:59:46
- 黄金集:55 个评测用例 + 5 个操作性用例(tests/golden/golden_cases.json)
- 环境:隔离数据目录,无模型 API key(走 local_answer 降级路径)

## 总体指标

| 指标 | 数值 |
|---|---|
| search_top5_hit | 0.667 |
| citation_hit | 0.667 |
| kw_in_answer | 0.667 |

## 分类别指标

| 类别 | n | search@5 | citation_hit | kw_in_answer | kw_in_evidence | 附加 |
|---|---|---|---|---|---|---|
| fact_single | 34 | 0.706 | 0.706 | 0.706 | 0.706 |  |
| fact_cross | 7 | 0.857 | 0.857 | 0.857 | 0.857 |  |
| no_answer | 10 | None | None | None | None | correct_abstain=0.4, junk_citation=0.6 |
| conflict | 4 | 0.0 | 0.0 | 0.0 | 0.0 | conflict_surfaced=0.0 |

## 操作性用例(导入/更新行为)

| id | 名称 | 关键观察 | pass |
|---|---|---|---|
| OP01 | 重复导入同一文件 | `{"duplicate_flag": true, "chunk_count_unchanged": true}` | True |
| OP02 | 相同内容改名导入 | `{"duplicate_flag": true, "source_count_with_same_content": 1}` | True |
| OP03 | 同名资料内容更新 | `{"duplicate_flag": false, "athena_source_count_before": 1, "athena_source_count_after": 2, "old_marked_superseded": false}` | None |
| OP04 | 更新后检索返回新旧哪个版本 | `{"old_version_in_top3": true, "new_version_in_top3": true, "old_in_chat_evidence": true, "new_in_chat_evidence": true}` | None |
| OP05 | 更新后版本号问题的新旧证据 | `{"citations": ["...数据保留策略:热数据保留 30 天,冷数据自动归档到对象存储,归档保留 3 年。\n【K13】自版本 2.4 起,Athena 支持 Kafka 作为上游数据源,支持断点续传。", "...天,冷数据自动归档到对象存储,归档保留 3 年。\n【K13】自版本 2.5 起,Athena 支持 Kafka 作为上游数据源,支持断点续传与 Exactly-Once 语义。"]}` | None |

## fact_single 未达标用例(10 条)

- FS01 `一线城市出差住宿报销上限是多少?` top1='' abstained=True
- FS02 `二线城市出差住宿每晚能报销多少?` top1='' abstained=True
- FS03 `出差餐补标准是多少?需要开发票吗?` top1='' abstained=True
- FS04 `入职满五年每年有几天年假?` top1='' abstained=True
- FS06 `公司每周哪一天全员远程?` top1='' abstained=True
- FS07 `入职满一年有多少天年假?` top1='' abstained=True
- FS20 `全员安全演练原定什么时候启动?` top1='' abstained=True
- FS27 `新员工入职当天怎么办理工牌?` top1='' abstained=True
- FS28 `入职电脑什么时候完成预装?` top1='' abstained=True
- FS29 `转正答辩需要谁参加?` top1='' abstained=True

## fact_cross 引用未覆盖全部文档(3 条)

- FC03 `一线城市住宿报销标准和试用期时长分别是多少?`
- FC04 `年报里的全年营收和 Q4 单季营收分别是多少?`
- FC06 `Q3 招聘计划和安全演练时间分别是什么?`
