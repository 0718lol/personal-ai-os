# RAG 评测与检索融合研究笔记

【K40】RAGAS 的 faithfulness 指标衡量答案中的论断能否被检索到的证据支撑,取值范围 0 到 1。
【K41】RRF (Reciprocal Rank Fusion) 融合公式为 score = sum(1/(k+rank)),其中 k 通常取 60。
【K42】HyDE 的核心思想是先让 LLM 生成一个假设性答案,再用假设答案去检索真实文档。
【K43】MRR (Mean Reciprocal Rank) 是所有查询的正确结果排名倒数的平均值。
