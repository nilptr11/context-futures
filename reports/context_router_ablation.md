# Brooks Context Router Ablation

日期：2026-06-27

更新：本报告记录的是旧 `brooks_context_router` 的消融结果。该策略名和架构已被 `brooks_price_action` 取代；新的实现不再让 Context 直接路由到 Signal，而是通过 Candidate Trade 和 Trader's Equation 决策。见 `reports/brooks_price_action_refactor.md`。

## 目标

验证“量化 Brooks 的 Context，而不是机械量化 Pattern”的第一版实现。

本轮新增：

- `context_engine.py`
- `setups.py`
- `BrooksContextRouterStrategy`

Router 的目标是：

```text
Market Context -> Setup Router -> Strategy Signal
```

而不是：

```text
Pattern -> Trade
```

## 已实现的 Context 路由

| Context | Setup | Status |
| --- | --- | --- |
| Bull/Bear Trend | trend pullback | 可用 |
| Breakout Phase | breakout pullback | 已实现，但不合格 |
| Trading Range / Breakout Mode | failed breakout | 已实现，但不合格 |

## Ablation 结果

配置：

- BTCUSDT: `1h` entry + `4h` context
- ETHUSDT: `30m scaled` entry + `4h` context
- `risk_fraction = 0.02`
- `max_symbol_notional_fraction = 5.0`
- `leverage = 20`

| Scenario | BTC Return | BTC DD | BTC Trades | BTC PF | ETH Return | ETH DD | ETH Trades | ETH PF | Combined |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| trend_only | 31.56% | -10.45% | 53 | 1.535 | 18.34% | -13.16% | 60 | 1.237 | 24.95% |
| breakout_only | -35.55% | -44.38% | 226 | 0.860 | -67.06% | -74.11% | 360 | 0.752 | -51.31% |
| failed_only | -88.99% | -89.11% | 606 | 0.785 | -97.76% | -98.34% | 1204 | 0.754 | -93.38% |
| trend_breakout | -18.45% | -37.46% | 274 | 0.941 | -59.85% | -74.38% | 416 | 0.814 | -39.15% |
| all_routes | -91.38% | -92.46% | 881 | 0.819 | -99.12% | -99.40% | 1620 | 0.748 | -95.25% |

## 结论

Context Router 的架构方向正确，但新增 setup 不能直接启用。

当前有效部分仍然是：

```text
Trend Context -> Pullback Continuation
```

当前不合格部分：

```text
Breakout Context -> Breakout Pullback
Range Context -> Failed Breakout
```

失败原因不是 Brooks 思想错，而是第一版 setup 过于机械：

- `breakout_pullback` 只看突破和回踩，缺少 breakout quality、follow-through、measured move 空间。
- `failed_breakout` 只看区间外失败返回，缺少 range 边界质量、二次确认、拥挤度和成本过滤。
- 两者显著增加交易次数，把策略从低频 Context trading 变成过度交易。

## 已采取保护

`StrategyConfig` 默认：

```python
context_enable_trend_pullback = True
context_enable_breakout_pullback = False
context_enable_failed_breakout = False
```

也就是说，`brooks_context_router` 默认只启用已验证的 trend pullback 路由。

需要研究 breakout 或 failed breakout 时，必须在配置中显式打开对应开关。

## 下一步

优先改进顺序：

1. `breakout_pullback`
   - 增加 breakout follow-through。
   - 要求回踩不深回旧区间。
   - 要求到 measured move 至少有 `1.5R` 空间。
2. `failed_breakout`
   - 只在高质量 trading range 边缘交易。
   - 要求突破后快速收回，同时反向强 K 有 follow-through。
   - 加入 funding/OI/taker buy-sell evidence 后再启用。
3. Context Engine
   - 增加 external evidence slots：funding、OI、taker buy/sell volume。
   - 先作为过滤器，不作为单独开仓信号。

## 数据限制

Binance 官方 USD-M REST 的部分衍生品统计数据不适合直接做 2021-2026 长历史回测：

- Open Interest Statistics: 官方文档说明仅提供最近 1 个月数据。
- Taker Buy/Sell Volume: 官方文档说明仅提供最近 30 天数据。

因此：

- funding 可以继续做长历史回测；
- OI、taker buy/sell volume 更适合先接入 paper/live context；
- 若要对 OI/CVD 做多年回测，需要第三方历史数据源或从现在开始自行沉淀。
