# 配置目录说明

`configs/` 存放可复用的策略配置和研究配置。

## 目录结构

```text
configs/
  examples/              # 最小示例配置，用于演示 CLI 和 schema
  strategies/
    brooks/              # Brooks 系列当前维护配置
```

## 当前配置

- `examples/single_breakout_atr.toml`
  - 单标的 `breakout_atr` 示例。
  - 用于验证单策略 CLI 和嵌套配置结构。

- `strategies/brooks/price_action_portfolio.toml`
  - 当前维护的 Brooks PA 组合基线。
  - BTCUSDT `1h/4h` + ETHUSDT `30m/4h`。
  - 适合常规研究回测。

- `strategies/brooks/aggressive_15pct.toml`
  - 激进 15% 风险研究配置。
  - BTC/ETH/NEAR 组合，其中 NEAR 为 short-only。
  - 只用于研究，不适合直接实盘。

## 新增策略配置规则

- 新配置应放到对应策略目录，不放根目录。
- 文件名应描述策略、资产池和风险档位。
- 可以复现实验结果的配置才进入 `configs/strategies/`。
- 临时扫描参数不应作为长期配置提交，应通过后续 `bn_quant.research` 模块生成。
