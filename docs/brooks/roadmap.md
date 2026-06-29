# Brooks 后续路线与实现纪律

内容基准：2026-06-29

本文维护 Brooks 研究路线和进入策略核心前的检查清单。

## 实现纪律

每次新增功能前先写清楚：

```text
Brooks 逻辑依据：
这个改动回答 control/context/trapped traders/follow-through/invalidation/trader's equation 中的哪一个？

市场循环检查：
这个改动在 trend/channel/breakout/trading range 中分别代表什么？是否错误地跨 regime 共用同一含义？

分数解释检查：
这个分数是未校准 proxy 还是真实统计概率？它能否按 setup_kind/side/symbol/regime 分桶验证？

未来函数检查：
这个改动在 idx 时刻能否真实获得？具体按 `docs/future_leakage_design.md` 的 point-in-time 数据契约和 PR 检查清单执行。

架构回归验收检查：
以下检查必须通过：ruff、mypy、pytest、compileall，以及代表性 Brooks shared portfolio 回测和 universe profile smoke。

策略表现验收检查：
aggressive_15pct 在 2023-01-01 到 2026-06-28 是否仍能复现或接近以下指标？
  final_equity: 46525.22
  total_return: 46425.22%
  max_drawdown: -59.10%
  trades: 189
  win_rate: 53.97%
  profit_factor: 1.659
  funding: 94.07
```

如果任一问题答不清楚，就不进入策略核心。
