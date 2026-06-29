# Brooks 策略研究总览

内容基准：2026-06-27

本文是 Brooks 研究文档的入口索引。长期内容按主题拆分维护，避免单个文档同时承载理念、实现、回测和路线图。

## 阅读顺序

1. [价格行为思想](brooks/principles.md)
   - Brooks 价格行为总纲、市场循环、交易结构、形态语义和交易纪律。
2. [后续路线与实现纪律](brooks/roadmap.md)
   - 后续研究顺序和每次进入策略核心前必须回答的问题。
3. [策略族架构](brooks/architecture.md)
   - Brooks setup registry、配置层级、universe profile 和 trader equation 的工程边界。

## 维护边界

Brooks 文档允许按主题拆分。新增长期内容应落到 `docs/brooks/` 的现有主题文件中；如果主题边界已经不合适，先调整本索引。

维护规则：

- 回测 CSV、临时分箱和扫描结果留在 `reports/`、`data/backtests/` 或本地实验输出，不作为长期策略文档。
- 关键历史结果只能作为研究线索，不能作为“已经符合 Brooks”的证明。
