# Paper Runner Notes

日期：2026-06-26

## 已实现

新增 `scripts/paper_runner.py`，用于常驻 paper trading。

能力：

- 多标的轮询，默认 BTCUSDT/ETHUSDT。
- 多策略实例并行，状态按 `strategy_id:symbol` 隔离。
- 只处理已收盘 K 线。
- 状态持久化到 JSON，重启后不会重复处理同一根 K 线。
- 同一策略实例的同一标的同一时间只持一个方向。
- 按 ATR 初始止损和移动止损管理持仓。
- 反向信号平仓。
- 当前 funding rate 过滤。
- 组合级名义仓位控制。
- 单标的名义仓位控制。
- 每笔风险预算按 `risk_fraction * equity` 控制。

## 运行

单轮检查：

```bash
PYTHONPATH=src python3 scripts/paper_runner.py --config config.toml --symbols BTCUSDT ETHUSDT --state state/paper_state.json --once
```

常驻轮询：

```bash
PYTHONPATH=src python3 scripts/paper_runner.py --config config.toml --symbols BTCUSDT ETHUSDT --state state/paper_state.json --poll-seconds 60
```

多策略配置：

```bash
PYTHONPATH=src python3 scripts/paper_runner.py --config config.multi.example.toml --symbols BTCUSDT ETHUSDT --state state/paper_state_multi.json --once
```

`[[strategies]]` 存在时，paper runner 会使用这些策略实例替代单个 `[strategy]`。持仓 key 形如 `breakout_4h_pa:BTCUSDT`。

## 风控规则

- 单标的名义仓位上限：`max_symbol_notional_fraction * equity`。
- 组合总名义仓位上限：`max_total_notional_fraction * equity`。
- 杠杆上限：`leverage * equity`。
- 实际开仓数量取以下三者最小值：
  - `risk_fraction * equity / stop_distance`
  - 单标的剩余名义空间
  - 组合剩余名义空间

## 当前限制

- 这是 paper runner，不会下真实订单。
- 研究脚本仍以单策略评估为主；多策略组合回测尚未实现。
- Paper 资金费率只做开仓前过滤，未按实时 funding event 扣费；历史回测已计入 funding。
- 尚未接 Binance User Data Stream。
- 尚未实现实盘订单状态回补、止损单同步和断线后重建本地状态。
- 当前按单向持仓模式设计，不支持 Hedge Mode。

## 下一步

下一步不是调参数，而是接 live execution safety layer：

- User Data Stream 监听订单成交、撤单、账户变动。
- 启动时从 Binance 拉当前仓位和未成交订单，重建状态。
- 每个实盘仓位必须有 reduce-only 止损单。
- 断线重连后校验本地状态和交易所状态一致。
- 组合级风险检查必须在真实下单前再次执行。
