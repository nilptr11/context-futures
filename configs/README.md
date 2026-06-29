# 配置目录说明

`configs/` 存放可复用的策略配置和研究配置。

## 目录结构

```text
configs/
  examples/              # 最小示例配置，用于演示 CLI 和 schema
  strategies/
    brooks/              # Brooks 系列当前维护配置
  universe_profiles/     # universe 矩阵研究 profile
```

## 当前配置

- `examples/single_breakout_atr.toml`
  - 单标的 `breakout_atr` 示例。
  - 用于验证单策略 CLI 和嵌套配置结构。

- `strategies/brooks/trend_continuation_portfolio.toml`
  - 当前维护的 Brooks 趋势延续组合配置。
  - BTCUSDT `1h/4h` + ETHUSDT `30m/4h`。
  - 适合常规研究回测。

- `strategies/brooks/breakout_pullback_research.toml`
  - Brooks breakout pullback 研究配置。
  - 在 `trend_continuation_portfolio.toml` 基础上启用 breakout pullback，并提高 breakout 质量、回踩质量、控制差和空头阈值。
  - 只用于研究 breakout 分支，不作为当前默认维护配置。

- `strategies/brooks/aggressive_15pct.toml`
  - 激进 15% 风险研究配置。
  - BTC/ETH/NEAR 组合，其中 NEAR 为 short-only。
  - 可使用通用市场数据集 `data/parquet/binance_usdm/`，按 parquet 分区拆分。
  - 只用于研究，不适合直接实盘。

- `universe_profiles/brooks_trend_continuation_baseline.toml`
  - Brooks family baseline profile，使用 `trend_continuation_portfolio.toml` 作为模板。
  - 只启用趋势延续家族当前对应的 `TREND_PULLBACK`。

- `universe_profiles/brooks_breakout_continuation_baseline.toml`
  - Brooks family baseline profile，使用 `breakout_pullback_research.toml` 作为模板。
  - 只启用突破延续家族当前对应的 `BREAKOUT_PULLBACK`。

- `universe_profiles/brooks_range_fade_baseline.toml`
  - Brooks family baseline profile，使用 `trend_continuation_portfolio.toml` 作为模板。
  - 只启用区间 fade 家族当前对应的 `FAILED_BREAKOUT`。

- `universe_profiles/brooks_breakout_research.toml`
  - universe 矩阵 profile，使用 `breakout_pullback_research.toml` 作为模板。
  - 启用 `TREND_PULLBACK` 和 `BREAKOUT_PULLBACK`。

## 新增策略配置规则

- 新配置应放到对应策略目录，不放根目录。
- 文件名应描述策略、资产池和风险档位。
- 可以复现实验结果的配置才进入 `configs/strategies/`。
- universe 扫描组合放入 `configs/universe_profiles/`，不要在代码中按 profile 名写特殊逻辑。
- Brooks family baseline 应使用 universe profile 表达，不新增顶层策略类。
- 临时扫描参数不应作为长期配置提交，应放在本地实验脚本或临时输出中。
