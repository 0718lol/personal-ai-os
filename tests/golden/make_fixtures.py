#!/usr/bin/env python3
"""生成黄金测试集所需的合成语料(8 个文本文件 + 2 个 PDF)。

所有事实都以【Kxx】标记内联,便于排查引用;问题本身不包含标记。
运行: .venv/bin/python tests/golden/make_fixtures.py
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

DOCS: dict[str, str] = {
    "员工手册.md": """# 远帆科技员工手册(2026 年 3 月版,节选)

## 差旅与报销

【K01】员工出差住宿报销标准:一线城市每晚 600 元以内,二线城市每晚 450 元以内,超支部分自理。
【K02】出差期间餐补为每日 100 元,按实际出差天数发放,不需要提供发票。
【K04】单笔报销金额超过 5000 元的,除直属主管审批外,还需要 CTO 会签后才能进入付款流程。

## 假期与考勤

【K03】年假天数:入职满 1 年不满 5 年的每年 10 天;满 5 年的每年 15 天,未休年假年底清零。
【K05】标准办公时间为 9:30 至 18:30;每周三为全员远程日,不需要到办公室。
""",
    "Athena产品规格.md": """# Athena 数据网关产品规格 v2.4

【K10】Athena 数据网关单节点最大并发连接数为 2000,单节点标称吞吐为 35000 QPS。
【K11】认证方式:支持 OIDC 与服务账号两种方式;不支持 LDAP,LDAP 支持计划在 2027 年评估。
【K12】数据保留策略:热数据保留 30 天,冷数据自动归档到对象存储,归档保留 3 年。
【K13】自版本 2.4 起,Athena 支持 Kafka 作为上游数据源,支持断点续传。
""",
    "Hermes产品规格.md": """# Hermes 消息队列产品规格

【K20】Hermes 单分区最大容量 8GB,单个集群最多支持 256 个节点。
【K21】版本 2.1 引入幂等生产者,版本 2.2 引入事务消息。
【K22】默认副本数为 3,创建 Topic 时可以调整,最小为 2。
""",
    "2026-03经营会纪要.md": """# 2026 年 3 月经营会纪要

【K30】决策:云供应商初选为辰光云,由基础设施组在 5 月前完成合同评审。
【K31】决策:H2 研发预算定为 1200 万元,优先投入网关与消息队列两条产品线。
【K32】待办:全员安全演练定于 5 月启动,由 SRE 组负责方案。
""",
    "2026-04经营会纪要.md": """# 2026 年 4 月经营会纪要

【K33】决策:云供应商由 3 月初选的辰光云改选为北岸云,原因是存储单价与 SLA 条款。
【K34】决策:H2 研发预算由 1200 万元上调至 1500 万元,追加部分用于招聘。
【K35】待办:Q3 计划新增招聘 12 人,其中后端 5 人、SRE 4 人、测试 3 人。
【K36】提示:因费用管控,一线城市出差住宿报销上限自 5 月起由 600 元调整为 500 元。
【K37】变更:安全演练由 5 月延后至 7 月,与容量压测合并进行。
""",
    "RAG评测研究笔记.md": """# RAG 评测与检索融合研究笔记

【K40】RAGAS 的 faithfulness 指标衡量答案中的论断能否被检索到的证据支撑,取值范围 0 到 1。
【K41】RRF (Reciprocal Rank Fusion) 融合公式为 score = sum(1/(k+rank)),其中 k 通常取 60。
【K42】HyDE 的核心思想是先让 LLM 生成一个假设性答案,再用假设答案去检索真实文档。
【K43】MRR (Mean Reciprocal Rank) 是所有查询的正确结果排名倒数的平均值。
""",
    "平台FAQ.md": """# 平台 FAQ

【K70】客户数据会被用于模型训练吗?不会。客户数据仅用于提供的服务本身,不用于任何模型训练。
【K71】支持 SSO 吗?企业版支持基于 SAML 2.0 的单点登录;社区版暂不支持。
【K72】支持哪些导出格式?目前支持 CSV 与 JSON 两种格式导出。
""",
}

ATHENA_V2 = """# Athena 数据网关产品规格 v2.5

【K10】Athena 数据网关单节点最大并发连接数为 2000,单节点标称吞吐为 52000 QPS。
【K11】认证方式:支持 OIDC 与服务账号两种方式;不支持 LDAP,LDAP 支持计划在 2027 年评估。
【K12】数据保留策略:热数据保留 30 天,冷数据自动归档到对象存储,归档保留 3 年。
【K13】自版本 2.5 起,Athena 支持 Kafka 作为上游数据源,支持断点续传与 Exactly-Once 语义。
"""

CSV_2025 = """quarter,季度,营收(万元),新增客户,流失率(%)
2025-Q1,一季度,7200,45,1.8
2025-Q2,二季度,8100,52,1.6
2025-Q3,三季度,9600,63,1.5
2025-Q4,四季度,11100,74,1.2
"""

ONBOARDING_SECTIONS = [
    "远帆科技新人入职指南",
    "【K50】工牌办理:入职当天上午 9:00 到一楼前台找行政领取临时工牌。",
    "【K51】电脑配置:请在入职前 3 天提交设备申请,IT 会在入职前完成开发环境预装。",
    "【K52】试用期:6 个月;转正答辩需要直属主管与 HRBP 同时参加。",
]

ANNUAL_SECTIONS = [
    "远帆科技 2025 年度报告(草稿)",
    "【K60】2025 年全年营收 3.6 亿元,同比增长 42%。",
    "【K61】截至 2025 年底,企业客户数达到 870 家,年度续费率 91%。",
    "【K62】全年研发投入 6800 万元,占营收比例 18.9%。",
]


def wrap_cjk(text: str, width: int = 40) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        while len(raw) > width:
            lines.append(raw[:width])
            raw = raw[width:]
        lines.append(raw)
    return lines


def make_pdf(path: Path, sections: list[str]) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72.0
    for section in sections:
        for line in wrap_cjk(section):
            if y > 770:
                page = doc.new_page()
                y = 72.0
            if line:
                page.insert_text((72, y), line, fontname="china-s", fontsize=11)
            y += 18
    doc.save(str(path))
    doc.close()


def verify_pdf(path: Path, needle: str) -> None:
    doc = pymupdf.open(str(path))
    text = "".join(p.get_text() for p in doc)
    doc.close()
    if needle not in text:
        raise SystemExit(f"PDF 校验失败:{path.name} 中找不到 {needle}")


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, content in DOCS.items():
        (FIXTURES / name).write_text(content, encoding="utf-8")
    (FIXTURES / "Athena产品规格.v2.md").write_text(ATHENA_V2, encoding="utf-8")
    (FIXTURES / "2025季度经营指标.csv").write_text(CSV_2025, encoding="utf-8")
    (FIXTURES / "员工手册-副本.md").write_text(DOCS["员工手册.md"], encoding="utf-8")
    make_pdf(FIXTURES / "新人入职指南.pdf", ONBOARDING_SECTIONS)
    make_pdf(FIXTURES / "2025年度报告草稿.pdf", ANNUAL_SECTIONS)
    verify_pdf(FIXTURES / "新人入职指南.pdf", "K50")
    verify_pdf(FIXTURES / "2025年度报告草稿.pdf", "K60")
    print(f"fixtures 就绪:{len(list(FIXTURES.iterdir()))} 个文件 -> {FIXTURES}")


if __name__ == "__main__":
    main()
