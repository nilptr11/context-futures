# Brooks 策略族架构

内容基准：2026-06-29

本文记录 Brooks 在代码中的工程边界。交易思想以 `docs/brooks/principles.md` 为准，本文只说明如何把这些思想组织成可回测、可扩展、可复现的策略族。

## 顶层边界

项目保留两个顶层策略名：

- `brooks`：Brooks-inspired 价格行为策略族，承载趋势回调、突破回踩、失败突破等 setup。
- `breakout_atr`：baseline 策略，用于 smoke test、回测引擎校验和对照研究。

不要把每个 Brooks setup 暴露成顶层策略名。Brooks 的核心是先读市场循环和控制权，再按 setup 选择交易机会；因此顶层策略应是 `brooks`，setup 是策略族内部的可组合分支。

## Brooks Setup Registry

Brooks 的运行时决策不是“形态触发器”，而是 `MarketRead -> TradeHypothesis -> EvidenceLedger -> TraderEquation -> Decision`。

`TradeHypothesis` 是交易语义的核心：

- `family`：交易假设家族，例如趋势延续、突破延续、区间 fade、反转尝试。
- `variant`：形态证据语言，例如 H2、楔形回调、突破回踩、失败突破。
- `thesis`：为什么这一边可能赚钱。
- `invalidation`：在哪里证明这个想法错了。
- `target`：合理目标模型。
- `management`：这笔交易更接近 scalp、swing、trail 还是 scale。

Brooks setup 的工程入口分两层：

- `config/brooks_setups.py`：只描述 setup 配置字段、配置类型、周期缩放和 profile enable/disable。该层不能 import strategy runtime。
- `strategies/brooks/setups/registry.py`：描述 setup 的运行时能力，包括 detector、context gate 和所需历史长度。

每个 setup 在 config spec 中声明：

- `kind_value`：稳定的 setup 标识字符串，对应 `SetupKind.value`。
- `config_attr`：对应 `BrooksSetupConfig` 的配置字段。
- `config_cls`：该 setup 的配置 dataclass。
- `scale`：universe 不同时间周期下如何缩放该 setup 的周期参数。
- `set_enabled`：profile 如何强制启用或禁用该 setup。

每个 setup 在 runtime registry 中声明。这里的 `kind` 是技术检测槽位，不是完整交易语义：

- `kind`：稳定的 setup 标识。
- `config_spec`：对应的 config spec。
- `detector`：该 setup 的扫描器。
- `context_allows`：该 setup 是否适合当前市场上下文。
- `side_context_allows`：需要按多空方向二次过滤的 setup 在这里声明 side-specific gate。
- `required_history`：运行该 setup 需要的最小历史长度。

新增交易思想时，优先判断它是新的 `SetupFamily`，还是现有 family 下的新 `PatternVariant`。只有需要独立配置、独立扫描入口或独立启用矩阵时，才新增 setup 技术槽位。

setup 专属评分和 evidence 位于 `strategies/brooks/setups/scoring.py`。`decision.py` 只保留通用 context score、trader equation 和 candidate 组装。

setup 专属 candidate 验收阈值位于 `strategies/brooks/setups/acceptance.py`。`decision.py` 只调用该模块，不直接写每个 setup 的阈值分支。

setup detector 应返回具体信号类型，例如 `BreakoutPullbackSignal` 或 `FailedBreakoutSignal`。`SetupSignal` 只作为 union 类型使用，不作为承载所有字段的大一统 dataclass。

setup trade plan 必须使用 `SetupKind` 判别，不允许依赖 `reason` 字符串前缀。

每个 accepted candidate 必须携带 `TradeHypothesis`。研究和 reporting 应优先按 `setup_family + pattern_variant + market_cycle` 分桶，而不是只看技术 `setup_kind`。

正式交易和研究探针通过 `SetupScanMode` 区分：

- `PRODUCTION`：只扫描当前 profile/config 启用的 setup。
- `RESEARCH_PROBE`：扫描所有当前市场上下文允许的 setup，用于记录 disabled setup 的研究日志。

外部调用应显式传入 `SetupScanMode`，不要使用布尔参数表达 research/prod 差异。

`strategies.brooks` 顶层只暴露外部稳定入口，例如 `BrooksStrategy`、`BrooksDecisionRecord`、`SetupKind` 和 `SetupScanMode`。测试或内部模块需要访问 scorer、detector、plan、context 时，应直接 import 具体模块。

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
