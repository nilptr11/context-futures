# Brooks Price Action Validation

日期：2026-06-27

配置：

- `config.brooks_price_action_20x_mixed.example.toml`
- BTCUSDT: `1h` entry + `4h` context
- ETHUSDT: `30m` entry + `4h` context
- `risk_fraction = 0.02`
- `max_symbol_notional_fraction = 5.0`
- `max_total_notional_fraction = 8.0`
- `leverage = 20`
- funding、fee、slippage 计入回测

## 全样本

| Strategy | Symbol | Return | Max DD | Trades | Win Rate | Profit Factor |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `brooks_pa_btc_1h` | BTCUSDT | 24.13% | -7.14% | 30 | 50.00% | 1.784 |
| `brooks_pa_eth_30m` | ETHUSDT | 35.85% | -4.51% | 31 | 54.84% | 2.204 |

简单等权组合约：

```text
return = 29.99%
```

## 2025-01-01 之后样本外

| Strategy | Symbol | Return | Max DD | Trades | Win Rate | Profit Factor |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `brooks_pa_btc_1h` | BTCUSDT | 11.99% | -3.03% | 5 | 80.00% | 6.316 |
| `brooks_pa_eth_30m` | ETHUSDT | 14.45% | -3.16% | 13 | 61.54% | 2.199 |

简单等权组合约：

```text
return = 13.22%
```

## 关键观察

第一次重构后，若只靠软评分过滤，`trend_pullback` 会在弱 EMA 方向里大量生成候选，导致交易数膨胀到上千笔并显著亏损。

修正后：

- Always-In 控制权、range、climax、趋势/突破状态作为候选交易最低资格；
- Context/Setup/Signal/Target/Edge 作为统一交易决策层；
- 结构化 invalidation 和 measured move target 已进入 signal；
- 默认路径交易频率回到几十笔级别。

结构交易计划的影响：

- BTC 全样本收益低于固定 2R 版本，但交易数和回撤也下降；
- ETH 全样本收益和回撤都明显改善；
- 2025 年之后样本外，BTC/ETH 交易数减少，回撤显著下降。

Funding crowding evidence 的影响：

- 默认参数已调整为更严格的同向 funding crowding penalty；
- 全样本 BTC/ETH 均减少交易并改善回撤/利润因子；
- 2025 年之后样本外结果与结构交易计划版本一致，没有额外交易被过滤。

OI/taker crowding evidence 的影响：

- paper/live 已接入 OI statistics 和 taker buy/sell volume；
- fetch_klines 后续会保存 `taker_buy_volume`，新 K 线 CSV 可用于历史 taker evidence；
- 当前验证所用旧 CSV 没有 `taker_buy_volume` 字段，因此本报告中的历史回测数字没有因 OI/taker evidence 变化。

## 结论

这次重构没有证明 breakout/failed-breakout 已可用。

当前可用结论仍然是：

```text
强 Always-In 趋势或突破背景
  -> 合格 pullback candidate
  -> Trader's Equation 通过
  -> 入场
```

下一步优先补：

- crypto crowding evidence；
- breakout/failed-breakout 的结构目标与 trapped trader evidence；
- 再重新验证 breakout/failed-breakout。
