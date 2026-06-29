# Brooks 后续路线与实现纪律

内容基准：2026-06-27

本文维护 Brooks 研究路线和进入策略核心前的检查清单。

## 后续路线

1. 暂以 `trend_pullback` 为研究起点，不急着增加更多 setup。
2. 先用 decision journal 研究 no-trade、channel、breakout、breakout mode、trading range、neutral、overlay 的分布。
3. 将 `breakout_pullback` 拆成多空、标的、regime、follow-through 分桶验证。
4. 验证 failed breakout 的 trapped trader 证据链：trap score、range quality、two-sided transition、回到区间后的反向强度和拥挤证据。
5. 验证 structure telemetry：range midpoint、range edge、support/resistance magnet、measured move 和 fixed R fallback；只有证明单调有效后，magnet 才能进入目标选择。
6. 用代码生成 setup performance、score calibration、target model 报告，而不是恢复旧脚本。
7. 接入更可靠的历史 OI/taker/liquidation 数据后，再验证 crypto crowding evidence。
8. 所有策略增强必须同时通过 Brooks 逻辑检查和未来函数检查。

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
这个改动在 idx 时刻能否真实获得？

回归验收检查：
aggressive_15pct 在 2025-01-01 到 2026-06-27 是否仍能复现或接近 6707.49 final equity、101 trades、56.44% win rate、1.641 profit factor？
```

如果任一问题答不清楚，就不进入策略核心。
