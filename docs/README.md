# 文档目录说明

`docs/` 只保留当前仍能指导维护、回测和后续策略开发的长期文档。

`reports/` 只作为回测 CSV、临时分析结果等生成产物目录。`reports/*.csv` 默认由 `.gitignore` 忽略，不纳入长期维护文档。

## 保留原则

- 当前可复现的回测结论。
- 当前 Brooks 策略研究、验证和审计。
- 当前报告字段、诊断分数和月度收益分析说明。

## 不再保留

- 旧脚本、旧 runner、旧 flat 配置相关说明。
- 已被 `brooks_price_action` 取代的旧策略过程记录。
- 只记录探索过程、但不能直接指导当前代码维护的长篇研究草稿。
- 一次性参数扫描过程文档。

CSV 回测产物属于本地生成文件；需要长期保留的结果应整理成 `docs/` 下的 Markdown 结论。

## 当前维护文档

- `brooks_and_lookahead_audit.md`
- `brooks_strategy_research.md`
- `brooks_price_action_validation.md`
- `brooks_single_account_optimization.md`
- `decision_score_telemetry.md`
