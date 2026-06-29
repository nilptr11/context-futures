# Brooks 策略族架构

内容基准：2026-06-29

本文记录 Brooks 在代码中的工程边界。交易思想以 `docs/brooks/principles.md` 为准，本文只说明如何把这些思想组织成可回测、可扩展、可复现的策略族。

## 顶层边界

项目保留两个顶层策略名：

- `brooks`：Brooks-inspired 价格行为策略族，承载趋势回调、突破回踩、失败突破等 setup。
- `breakout_atr`：baseline 策略，用于 smoke test、回测引擎校验和对照研究。

不要把每个 Brooks setup 暴露成顶层策略名。Brooks 的核心是先读市场循环和控制权，再按 setup 选择交易机会；因此顶层策略应是 `brooks`，setup 是策略族内部的可组合分支。

## Brooks Setup Registry

Brooks setup 的工程入口是 `strategies/brooks/setups/registry.py`。

每个 setup 在 registry 中声明：

- `kind`：稳定的 setup 标识。
- `config_attr`：对应 `BrooksSetupConfig` 的配置字段。
- `required_history`：运行该 setup 需要的最小历史长度。
- `scale`：universe 不同时间周期下如何缩放该 setup 的周期参数。
- `set_enabled`：profile 如何强制启用或禁用该 setup。

新增 setup 时，优先补 registry，再补 detector、配置 schema、测试和文档。避免在 strategy、universe、context、scanner 中散落新的 setup 分支。

## 配置层级

通用策略配置放在 `StrategyCommonConfig`：

- `market.atr_period`：策略和执行层共享的 ATR 周期。
- `trade`：止损、移动止损和 R 倍目标。
- `trend`：慢周期趋势和 regime 读取参数。
- `execution`：方向和资金费率过滤。

策略专属配置放在各自类型：

- `BreakoutAtrStrategyConfig.breakout.window`：baseline 突破窗口。
- `BrooksStrategyConfig.brooks`：Brooks regime、setup、trader equation、trade plan 和 evidence 参数。

不要把通用参数放回 `breakout`。`breakout` 只表达 baseline 或 Brooks breakout setup 的专属语义。

## Universe Profile

universe profile 是研究矩阵的配置，不是策略配置。内置 profile 放在 `configs/universe_profiles/`：

- `template_config` 指向一个 Brooks 策略模板。
- `enabled_setups` 指定矩阵研究中启用哪些 Brooks setup。

`cf-universe-backtest --profile` 只读取 profile 文件，不在代码中按 profile 名写特殊逻辑。新增研究 profile 时先加 TOML，再加必要测试。

## Trader Equation

Brooks 的 context score 使用 `brooks.trader_equation.context_weights` 配置权重。代码只执行权重计算，不隐藏策略参数。

权重用于复现实验和调参，不应被理解为真实统计概率。任何权重变化都需要配套回测和分桶观察。
