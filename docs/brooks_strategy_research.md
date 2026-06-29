# Brooks 策略研究总览

内容基准：2026-06-27

本文是 Brooks 研究文档的入口索引。长期内容按主题拆分维护，避免单个文档同时承载理念、实现、回测和路线图。

## 阅读顺序

1. [价格行为思想](brooks/principles.md)
   - Brooks 价格行为总纲、市场循环、交易结构、形态语义和交易纪律。
2. [当前实现](brooks/implementation.md)
   - `brooks_price_action` 的代码边界、策略分支、artifact 和 universe runner 约定。
3. [证据与策略优先级](brooks/evidence.md)
   - crypto evidence、策略族优先级和启用边界。
4. [历史回测线索](brooks/backtests.md)
   - universe matrix、常规风险、breakout 研究和激进风险配置结果。
5. [决策分数研究](brooks/score-research.md)
   - `context_score`、`probability_score`、`edge_score_r` 等分数的研究纪律。
6. [后续路线与实现纪律](brooks/roadmap.md)
   - 后续研究顺序和每次进入策略核心前必须回答的问题。

## 维护边界

Brooks 文档允许按主题拆分，但不要再新增游离文档。新增长期内容应落到 `docs/brooks/` 的现有主题文件中；如果主题边界已经不合适，先调整本索引。

维护规则：

- 回测 CSV、临时分箱和扫描结果留在 `reports/`、`data/backtests/` 或本地实验输出，不作为长期策略文档。
- 关键历史结果只能作为研究线索，不能作为“已经符合 Brooks”的证明。
- 若后续发现当前策略只是固定模型套用，应优先修改 [价格行为思想](brooks/principles.md) 和 [当前实现](brooks/implementation.md) 的判断，再改代码。
- 任何新证据在校准前只能进入 telemetry 或 decision journal，不能直接改变 Trader's Equation、target selection 或 position path。

## 核心判断

Brooks 的核心不是形态识别，也不是场景路由，而是交易前的市场阅读：

```text
市场上下文
  -> 证据
  -> 候选交易
  -> Invalidation
  -> 目标空间
  -> Trader's Equation
  -> 交易 / 不交易
```

因此，策略实现必须避免两类错误：

- 把 H2/L2、wedge、breakout、failed breakout 直接当作开仓信号。
- 为了增加交易数，直接打开更多 setup，而不检查目标空间、成本、胜率和结构止损。
