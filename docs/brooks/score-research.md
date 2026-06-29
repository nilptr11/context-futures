# Brooks 决策分数研究

内容基准：2026-06-27

本文维护 Brooks 决策分数的观察、解释边界和后续研究方式。

## 现有样本观察

- `context_score` 有正向意义，但不是线性越高越好。
- `probability_score >= 0.75` 目前更有优势，但样本不足。
- `edge_score_r` 高分区有优势，中间区间非单调。
- `setup_score` 公式需要重审，可能混合了不同 pullback 类型。
- `candidate_reason` 和 setup evidence 已进入 decision summary，可用于拆分 H2/L2、wedge、breakout pullback、target model。

## 新增 telemetry 后的初步观察

- 正常配置 2024-01-01 到 2026-06-27 中，accepted trades 主要来自 trend wedge pullback；wedge 是当前最值得继续研究的趋势回调分支。
- 激进配置 2025-01-01 到 2026-06-27 中，trend/channel pullback 贡献主要收益，breakout pullback 贡献弱；其中 breakout pullback bull 即使 breakout quality / retest 分数较高，实际 PnL 仍为负。
- 这说明当前 breakout quality 和 retest quality 只能证明“有突破和回踩形态”，还不能证明 Brooks 意义上的强 follow-through、机构共识改变和足够目标空间。
- 因此，breakout pullback 在进入默认策略前，必须继续拆分多空、target model、follow-through、market-cycle transition 和失败后表现，不能只按 accept rate 或 setup score 放松。

## 解释纪律

- `probability_score` 在校准前只能叫概率 proxy，不能当作真实胜率。
- `EvidenceLedger` 只能说明当前公式如何合成分数，不能自动证明证据有效。
- 每个分数必须能拆成 Brooks 语义：market cycle、control、failed attempt、follow-through、location、target room、crowding。
- 任何分数如果跨 setup_kind 或 regime 后表现非单调，先拆分样本，不直接调高/调低权重。

## 后续研究方式

1. 用 `EvidenceLedger` 按证据项导出分桶报告，验证 control、follow-through、location、crowding 等子项是否单调。
2. 单独分析 setup 构成：深度、腿数、EMA 触碰、double test、wedge、反方失败速度。
3. 用 decision journal 分析 accepted/rejected 的分布，再按 `setup_kind`、side、symbol、regime、market-cycle transition 分桶。
4. 分析不同 target 模型：固定 R、measured move、range midpoint、range edge、major high/low magnet。
5. 再决定是否调整 `decision_min_probability_score` 或 `decision_min_edge_score_r`。
