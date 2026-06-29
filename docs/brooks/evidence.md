# Brooks 证据与策略优先级

内容基准：2026-06-27

本文维护 Brooks 研究中的外部证据边界和策略族优先级。

## 加密市场证据

Crypto 数据只能作为上下文证据，不能直接创造交易。

当前已支持：

- funding：削弱同方向拥挤。
- taker buy ratio：识别同方向主动成交拥挤。
- open interest change：辅助判断新仓拥挤。

当前仍缺：

- liquidation spike / stop-run 证据。
- 更长历史的 OI/taker 数据。
- 对 failed breakout 中 trapped traders 的统计验证。

接入纪律：

- funding 高只能说明拥挤或 late risk。
- OI 增减必须结合价格方向解释。
- taker imbalance 只能削弱追随拥挤方向，不能给反向交易直接加分。
- liquidation 要判断是 climax、stop-run，还是普通波动。

## 策略族优先级

### 第一优先级

- `trend_pullback`：当前优先研究路径，不等同于已经完整贯彻 Brooks。
- `brooks_price_action` 的结构止损和 Trader's Equation：继续完善。
- setup 专属校准：按 setup_kind、side、symbol、regime 分桶。

### 第二优先级

- `breakout_pullback`：验证 breakout quality、follow-through、retest quality、transition 和 target room 的分桶表现。
- measured move / structure magnet target：继续用于目标空间和出场过滤，并验证不同 target model。
- crypto crowding evidence：用于 late/crowded 风险惩罚。

### 暂不启用

- `failed_breakout`：证据链不足。
- trading range fade：容易退化成区间网格。
- major trend reversal / climax reversal：逆势误判风险高，先做过滤器或退出逻辑。
