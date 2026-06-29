# 防未来数据设计

内容基准：2026-06-29

本文把回测中的“未来函数”统一定义为 point-in-time 可见性问题。这里的“防未来函数”不是单个工具函数，而是一组数据契约、事件循环、特征构建、训练切分和执行模拟边界。任何策略、因子或外部数据接入都必须先回答：在决策时刻 `now`，这条信息是否已经真实可获得。

## 核心概念

### 时间字段

每类数据都必须尽量拆分以下时间字段，不能只保留一个 `timestamp`：

| 字段 | 含义 | 用途 |
| --- | --- | --- |
| `event_time` | 事件在市场或链上发生的时间 | 统计归属和窗口聚合 |
| `window_start` / `window_end` | K 线、指标桶、聚合窗口的起止时间 | 判断 bar 是否完成 |
| `exchange_time` | 交易所声明的时间 | 跨交易所对齐 |
| `block_time` | 区块链区块时间 | 链上事件归属 |
| `publish_time` | 数据源正式发布或 API 可查询时间 | 防公告、funding、OI、TVL 提前可见 |
| `received_at` | 本系统实际收到数据的时间 | 模拟真实延迟和本地 clock |
| `finalized_at` | 数据达到最终确认或不可逆状态的时间 | 链上 finality、reorg、结算值 |
| `available_at` | 回测允许读取该行数据的最早时间 | 所有策略和因子读取的唯一可见性边界 |

默认规则：

```text
available_at = max(publish_time, received_at, finalized_at, event_time + source_latency)
```

如果数据集缺少显式 `available_at`，只能使用该数据类型的保守默认规则。不能用 `event_time` 直接替代 `available_at`，除非该数据源在事件发生时就能被真实观察。

### 回测时钟

回测至少包含三个时刻：

| 时刻 | 含义 | 当前设计 |
| --- | --- | --- |
| `decision_time` | 策略做决策的时间 | 当前 fast bar 可见后的 `available_at` |
| `execution_time` | 订单允许成交的时间 | 下一根可执行 bar 或更细粒度 replay 事件 |
| `mark_time` | 估值和风控使用的时间 | 不晚于当前事件循环时间 |

禁止把同一个 bar 的 close 信号直接用同一个 close 成交。Bar close 决策只能在该 bar 完成且可见后发生，成交必须进入下一可执行事件，除非策略明确使用 tick/order book replay，并且该 tick 在 `decision_time` 之后。

### 可见性 API

策略代码不得直接读取完整历史数组。所有读取必须经过 point-in-time view：

| API 概念 | 作用 |
| --- | --- |
| `closed_bars(interval, lookback)` | 返回 `available_at <= now` 且已完成的 K 线前缀 |
| `visible_funding()` | 返回 `available_at <= now` 的 funding 事件 |
| `asof(now)` | 对预计算特征、趋势过滤器、regime 模型做时间切片 |
| `PrefixSequence` | 允许缓存全量特征，但策略只能看到前缀长度 |
| `next_executable_bar()` | 把决策和成交拆开，避免 close 决策 close 成交 |

当前代码对应：

- `context_futures.data.availability.available_at_for_candle`
- `context_futures.data.availability.available_at_for_funding`
- `context_futures.backtest.market_view.MarketView`
- `context_futures.backtest.market_view.FeatureCache`
- `context_futures.strategies.base.TrendFilter.asof`
- `context_futures.strategies.brooks.regime.BrooksRegimeFilter.asof`

## 总不变量

1. 策略只能读 `available_at <= now` 的数据。
2. K 线只能在 `close_time + latency` 或显式 `available_at` 后可见。
3. 当前未完成 K 线的 high、low、close、volume、VWAP、taker volume 不能被 bar-close 策略读取。
4. 高周期 K 线必须等该周期完成后才能被低周期策略读取。1h 策略不能提前读取未完成 4h K 线。
5. Funding、OI、清算、TVL、新闻、链上标签等外部数据必须按发布或确认时间可见，不能按最终归属时间可见。
6. 横截面排名、标准化、PCA、机器学习训练只能使用当时已存在且可交易的 universe。
7. 所有全样本统计都必须改成 rolling/expanding/walk-forward，并在决策前 shift 或 asof。
8. 执行模拟不能假设无限流动性、免费成交、未来盘口、未来撤单或必成交限价单。
9. artifact 必须记录数据根目录、配置、账户模式、时间窗口、git commit 和配置 hash，保证结果可复查。

## 数据类型风险与设计

### K 线与行情数据

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 未收盘 K 线 | 读取当前 bar 的 high/low/close/volume/VWAP | bar-close 策略只读已完成 bar；intrabar 策略必须用 tick replay |
| 当前 high/low | 用完整 bar 的最高最低判断本 bar 内是否触发 | 用更细粒度事件顺序 replay；没有 replay 时只能下一 bar 成交 |
| 当前 volume/VWAP | 在 bar 未结束前读取最终 volume 或 VWAP | 使用 partial bar 数据集，且每个 partial row 有 `available_at` |
| Funding 预测值 | 在区间内提前知道最终 funding | 预测值和最终值分两类数据，各自有 `available_at` |
| 未来 tick | bar 策略读取下一 tick 或下一 bar | 所有 tick 也按 `available_at` 进入事件循环 |
| Close 决策 Close 成交 | 用本 bar close 产生信号并用同一 close 价格成交 | 当前实现使用下一可执行 bar |
| 跨周期提前引用 | 1h 策略读取未完成 4h、日线、周线、月线 | 高周期 bar 必须 `available_at <= now` |

### Funding / 永续合约

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| Funding fee 最终值 | 在结算前知道实际费用 | fee 只在结算事件 `available_at` 后入账 |
| Funding rate 最终值 | funding interval 内提前知道最终 rate | 预测 rate 和最终 rate 分表或分字段 |
| Funding 排名 | 用未来区间的全市场排名 | 按每个 symbol 的 rate 可见时间做 asof 横截面 |
| 历史均值包含未来 | rolling mean 未 shift 或全样本均值 | 只用 `available_at <= now` 的历史 |

### Open Interest

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 最终 OI | 在统计桶未发布前读取最终 OI | OI row 使用 `publish_time/available_at` |
| 未公布 OI | 用交易所后来补发的数据 | 补发数据的 `available_at` 是补发时间 |
| OI 排名 | 横截面使用未来 symbol 或未来值 | point-in-time universe + asof rank |
| OI delta / EMA | 计算包含未来桶 | 对可见序列做 diff/EMA |

### 清算数据

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 清算总额/比例 | 在窗口未结束前知道完整窗口总额 | 聚合窗口完成并发布后才可见 |
| 清算热力图未来值 | 用未来价格路径生成密集区 | 只使用当时已发布的订单或统计 |
| 清算密集区 | 用未来清算事件反推区间 | 密集区算法只能输入历史可见事件 |
| 最大清算订单 | 在事件前或发布前已知 | 按事件流 `available_at` replay |

### Order Book / Order Flow

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 未来盘口 | 用成交后的 depth 做下单依据 | order book snapshot/delta 按接收时间 replay |
| 未来深度变化 | 用未来 bid/ask depth 估计滑点 | 成交时只看执行前最近盘口 |
| 未来撤单 | 知道挂单会撤或保留 | queue 模型只用当时 book delta |
| 成交队列 | queue position 按最终成交结果倒推 | 需要明确排队规则和本订单入队时间 |
| Order flow 回放错误 | 同一时间戳事件顺序任意排序 | 使用 exchange sequence 或保守排序规则 |

### 成交数据

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 未来成交 | 当前决策读取后续 trade | trade event 按 `available_at` replay |
| Aggressor side | 使用后验推断的主动方向 | 记录推断算法和可见时间；不能用未来 quote |
| Delta volume / Footprint / CVD | 聚合窗口包含未来成交 | 只按可见 trade 前缀滚动更新 |

### 跨交易所与价格源

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 未来价差 | 不同交易所数据按 event time 强行对齐 | 使用 `received_at/available_at` asof join |
| 数据延迟 | 假设所有交易所同时可见 | 每个 source 独立 latency model |
| 时间不同步 | exchange timestamp 和 local timestamp 混用 | 保留 source clock，并统一转为 `available_at` |
| 聚合行情错位 | 先更新 index 后更新成分价格 | composite/index 视作独立数据源，有自己的 `available_at` |
| Mark/Index/Oracle/TWAP/VWAP | 使用后来修正或最终窗口值 | 用发布时刻可见的版本，修订另存版本链 |

### 链上数据

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 未确认区块 | 使用 pending 或未 final 区块当作确定事实 | 区分 mempool、confirmed、finalized |
| 未来区块状态 | 查询最终状态数据库并按历史 block time 使用 | 使用 point-in-time state snapshot |
| 最终确认余额 | 使用当前节点回放后的最终余额 | 每个状态变更有 `finalized_at` |
| Token holder / active address | 使用未来统计窗口结果 | 窗口完成且统计发布后可见 |
| TVL / gas / whale / NFT | 用最终聚合值回填历史 | 聚合 row 必须有 `available_at` |
| 链上标签 | 用后来识别的 Smart Money、Whale、CEX、MEV label 回标历史 | label 是时变表：`label`, `valid_from`, `known_at` |

### DeFi 与 Token 数据

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| TVL/APY/APR 最终值 | 用日终或修正值做盘中决策 | 使用 source 发布版本和 `available_at` |
| Pool liquidity | 用成交后流动性 | liquidity snapshot 按事件 replay |
| LP 收益率 | 用最终结算收益 | 只用当时累计可见收益 |
| Borrow rate / utilization | 用窗口最终值 | rate update 事件化 |
| Future supply/unlock/vesting | 提前使用后来披露或执行的数据 | 区分公告日、计划生效日、实际执行日 |
| Burn/mint | 使用未来链上执行 | 以确认或 finality 后可见 |

### 新闻与事件

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 上币公告 | 用交易所公告生效时间，不用发布时间 | `available_at = publish_time + collection_latency` |
| 下架公告 | 提前知道最终下架 | 只在公告发布后可见 |
| 空投名单 | 使用未来名单筛历史 | 名单有公布时间，未公布前不可见 |
| 治理提案 | 使用最终投票结果 | proposal、snapshot、vote、final result 分事件 |
| Snapshot 时间 | 用 snapshot 后才公布的信息提前筛选 | snapshot 条件可在 snapshot 前知道，名单只能公布后知道 |

### 标签与实体识别

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| Smart Money / VC / Whale | 用后来归因标签回填历史 | label table 必须有 `known_at` |
| Exchange wallet / CEX address | 使用未来识别结果 | 地址标签按版本管理 |
| MEV / Entity label | 以后验聚类结果做历史决策 | 聚类版本有训练数据截止时间 |

### 回测数据集与 universe

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 幸存币偏差 | 只保留当前仍存在的币 | point-in-time symbol universe |
| Delisted token 被删除 | 删除历史交易对 | 保留 delisted symbol 和历史规则 |
| Rug pull 缺失 | 清理失败项目 | 数据集必须记录失败项目 |
| 只测大币 | 用当前市值筛历史 | 市值筛选按当时可见数据 |
| 忽略历史交易对 | 当前交易对列表回填历史 | exchangeInfo/versioned listing table |

### 时间同步

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| Exchange timestamp 错位 | 不同交易所按裸 timestamp join | source-specific asof join |
| Block timestamp 错位 | block time 当成接收时间 | block finality 后才可见 |
| Local timestamp 错位 | 本地抓取时间覆盖事件时间 | 同时保留 event/publish/received |
| REST 与 WebSocket 混用 | REST 补数覆盖 WebSocket 可见时间 | 补数 row 的 `available_at` 是补数可见时间 |
| Event time 与 receive time 混用 | 用事件归属时间判断可见性 | 策略只看 `available_at` |

### 多周期

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 1m 引用未完成 5m | 低周期提前读取高周期聚合结果 | 高周期 `window_end + latency` 后可见 |
| 5m 引用未完成 1h | 同上 | `MarketView.closed_bars("1h")` asof |
| 日线/周线/月线未结束 | 盘中使用日终周终月终指标 | 引入 partial bar 数据，否则不可见 |

### 因子构建

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| Rolling 未 shift | 预测下一 bar 却使用当前 label 所在 bar | 明确 feature timestamp，必要时 shift |
| EMA 包含未来 | 用全量 EMA 后不切前缀 | 可缓存全量，但策略只能读可见前缀 |
| Z-score 全样本 | 用未来均值/方差标准化历史 | rolling/expanding 标准化 |
| PCA 全样本 | 用全窗口训练 PCA | walk-forward fit/transform |
| 排名使用未来样本 | 横截面包含未来币种或未来值 | point-in-time universe + asof rank |
| 横截面标准化 | 包含尚未上市或无可见数据的币 | 只包含当时可交易且数据可见的 symbol |

### 机器学习

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| Label leakage | label 窗口和 feature 窗口重叠错误 | 明确 prediction horizon 和 embargo |
| Feature leakage | 特征使用未来修订值 | 特征表写 `available_at` 和版本 |
| Random shuffle | 时间序列随机拆分训练测试 | walk-forward / expanding split |
| Train/test 时间穿越 | 测试期信息参与训练 | 每个模型记录 train_end_time |
| Hyperparameter overfitting | 用测试集反复调参 | 嵌套验证或单独 validation 窗口 |

### 执行层

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| 无限流动性 | 任意数量按 close 全部成交 | slippage、深度、成交量约束 |
| 忽略手续费变化 | 用当前费率回填历史 | fee schedule point-in-time |
| 忽略 funding 成本 | 永续持仓不扣 funding | funding settlement event 入账 |
| 忽略爆仓价格 | 杠杆持仓永不爆仓 | liquidation/bankruptcy price 模型 |
| 忽略撮合顺序 | 同一 bar 内先止盈后止损任意选择 | 需要 tick/order book replay；无 replay 时保守处理 |
| Market order 全部成交 | 不看盘口深度 | 使用执行前盘口或保守滑点模型 |
| 限价单必成交 | 价格触达就默认成交 | 需要 queue position；否则按保守 fill rule |

### 链上特有执行顺序

| 风险 | 禁止行为 | 正确设计 |
| --- | --- | --- |
| Reorg | 未考虑区块重组 | 决策数据必须达到配置确认数或 finality |
| Mempool | 把 mempool 当确定成交 | mempool 只能作为单独不确定信号源 |
| Flash loan | 事件发生后才知道攻击路径 | 按交易顺序和区块确认可见 |
| Oracle 更新 | 使用区块内未来 oracle price | 使用 transaction order 或 oracle publish event |
| MEV 顺序 | 忽略同区块交易顺序 | 需要 transaction index/log index |
| 跨链桥到账 | 用源链事件时间当目标链到账时间 | 目标链确认后才可用 |

## 代码设计规则

### 数据层

所有新数据类型都应实现以下契约：

```text
raw source -> typed domain row -> parquet row
typed row 必须保留 event_time/source_time/publish_time/received_at/finalized_at/available_at 中可获得的字段
parquet row 必须至少能推导 available_at
```

新增数据读取器时，必须提供：

1. `available_at_for_<data_kind>()` 默认规则。
2. domain dataclass 中的 `available_at` 字段。
3. market view 或 feature view 中的 `visible_<data_kind>()`。
4. 一个测试：未来 row 存在于数据集中，但在 `now` 不可见。

### 策略层

策略只允许依赖 `StrategyContext` / `MarketView` 暴露的数据：

```text
允许：
ctx.closed_bars()
ctx.closed_bars("4h")
ctx.visible_funding()
ctx.trend_filter(...).trend_at(close_time)

禁止：
data.bars_by_interval["4h"][-1]
full_dataframe.iloc[-1]
rolling_result computed on full sample without visible prefix
global zscore / PCA / rank directly reused in strategy
```

如果必须预计算全量特征，只能把预计算结果视为 cache，策略读取时仍要通过 visible prefix 或 `asof(now)` 裁剪。

### 回测层

事件循环必须遵守：

1. 事件按 `available_at` 排序。
2. 同一时间多事件排序要稳定且可解释。
3. 决策事件和成交事件分离。
4. 策略持仓、资金、funding、手续费按事件时间推进。
5. 每次写 artifact 时记录时间窗口、数据根目录和代码版本。

当前单标的和组合回测已经使用 K 线 `available_at` 驱动决策，并用下一可执行 bar 成交。未来接入 tick/order book 时，应把 tick/order book 作为更细粒度事件源，而不是绕过该时钟。

### 研究与报告层

报告可以在回测结束后统计全样本表现，但报告统计不能反向进入策略特征。任何“筛选币种、筛选周期、调参”的结果必须进入下一轮 out-of-sample 或 walk-forward 验证，不能在同一窗口内既筛选又报告最终收益。

Universe matrix 必须记录：

- 当时可交易 symbol universe 的构造规则。
- 每个 symbol 的上市、下架、数据起止时间。
- 每个窗口的 train/validation/test 归属，如果用于参数选择。

## 当前覆盖与缺口

当前已经覆盖：

- parquet 数据默认读取 `data/parquet/binance_usdm`。
- K 线和 funding 支持 `available_at`。
- `MarketView.closed_bars()` 隐藏未来 bar、未完成高周期 bar 和未来 funding。
- 趋势和 regime filter 提供 `asof(now)` 防止查询未来。
- 单标的和组合回测使用 bar close 决策、下一可执行 bar 成交。
- 测试覆盖未来 K 线、未来 funding、跨周期可见性、Brooks 信号未来 K 线依赖。

当前仍需补齐：

- OI、liquidation、order book、tick、mark/index/oracle、on-chain、news、labels 等数据类型的 typed row 和 visible API。
- point-in-time symbol universe、listing/delisting、fee schedule、exchange rules 版本化。
- ML walk-forward、feature store、model registry 中的训练截止时间和 embargo。
- 更真实的滑点、盘口深度、限价单 queue position、爆仓和 liquidation 模型。
- 链上 finality/reorg/mempool/bridge/oracle 的专用事件模型。

## PR 检查清单

每个策略、数据、因子或执行层改动都必须回答：

1. 这个输入在 `decision_time` 是否 `available_at <= now`？
2. 如果是聚合窗口，窗口是否已经结束并发布？
3. 如果是高周期数据，当前高周期 bar 是否已经完成？
4. 如果是横截面数据，当前 symbol universe 是否 point-in-time？
5. 如果是链上数据，是否已经达到所需确认数或 finality？
6. 如果是新闻、标签、公告，是否使用发布时间或标签 known time？
7. 如果是 rolling/EMA/z-score/PCA/rank，是否只基于可见前缀或 walk-forward fit？
8. 如果是 ML，训练集是否严格早于测试集，是否有 embargo？
9. 如果是执行结果，是否依赖未来 high/low、未来盘口或限价单必成交假设？
10. 是否新增了“未来 row 存在但不可见”的测试？

答不清楚时，该改动只能进入研究备注，不能进入策略核心。
