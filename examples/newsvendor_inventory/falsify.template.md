<!--
  证伪记录模板（阶段 3）。数字同样只能来自 out/metrics.json。
  关键区别：这里记录的是**"我试着证明自己错了，结果如何"**——
  没触发的协议要写"未触发 + 原因"，未覆盖的区域要显式写"未覆盖"，不许留空。
-->
# 证伪记录 · 单 SKU 每周备货量决策

对应 `prompts/30_falsify.md` 的输出格式。本文件与 `report.md` 同源，
数字均由 `out/metrics.json` 注入。

## P1 双路径交叉

| 结论 ID | 路径 A | 路径 B | 相对误差 | 判定 |
|---|---|---|---|---|
| C-003 | 临界分位数 `{{m.P1_dual_path.critical_fractile_caliberB|.4f}}` → Q = {{m.P1_dual_path.Q_pathA_fractile}} | 对 Q ∈ [0, {{m.params.Q_max}}] 逐点枚举 → Q = {{m.P1_dual_path.Q_pathB_numeric}} | {{m.P1_dual_path.rel_diff_profit|.2e}} | 两条路径给出同一最优值 |

> 说明：路径A 是闭式（临界分位数），路径B 是暴力枚举——实现完全独立，
> 唯一的共同输入是同一份 `data/demand.csv`。两者吻合说明分位数实现与取整规则没写错。

## P2 细步重扫

| 断言 | 原步长 | 细化后步长 | 是否仍成立 | 最坏构型 |
|---|---|---|---|---|
| —— | —— | —— | —— | —— |

**本例未触发 P2（显式声明，不是省略）**：触发条件是结论中出现"恒成立 / 一定 / 总是 / 从无例外"类断言。
本案例的结论是"在给定样本与口径下的最优备货量 {{m.result.recommend_Q}} 件"，属**条件最优**而非全称断言，
不存在"粗步长跳过窄违例带"的风险面（Q 是整数域 [0, {{m.params.Q_max}}]，枚举步长恒为 1，不会跳格）。
若后续把需求改建成连续分布，则必须补 P2。

## P3 连续复核

| 量 | 网格值 | 连续值 / 区间 | 窄峰宽度 | 取数口径 |
|---|---|---|---|---|
| 最优备货量 Q* | {{m.P3_continuous.Q_discrete_opt}} | {{m.P3_continuous.Q_continuous_quantile|.2f}} | 0.1% 利润平台 = [{{m.P3_continuous.profit_band_0p1pct.0}}, {{m.P3_continuous.profit_band_0p1pct.1}}] | 报区间，不报单点 |

> 说明：样本含 {{m.n_promo_weeks}} 个促销周，经验分位数落在两个样本之间，
> 因此"最优值"本质上是一个平台而不是一个点。报告里报 {{m.result.recommend_Q}} 件，
> 是因为整数决策恰好落在平台内；若平台跨度为 0，则应报连续分位数 {{m.P3_continuous.Q_continuous_quantile|.2f}} 并说明取整方向。

## P4 极限与量纲

| 参数极限 | 预期退化结果 | 实测 | 判定 |
|---|---|---|---|
| 缺货惩罚 L → 0 | 退化为经典报童临界比 (p−c)/(p−v)，且与"零缺货惩罚"口径的最优解一致 | 临界分位数 {{m.P1_dual_path.critical_fractile_caliberA|.4f}}，对应最优 Q = {{m.P6_caliber.Q_caliberA_L0}} | 通过 |
| 需求方差 → 0（各周需求相同） | 最优 Q 应等于该常数，分位数法失去意义 | **未覆盖** | 未覆盖（样本方差不为 0，属理论边界，不影响本案例结论） |
| 产能 Q_max 收紧到最优值以下 | 最优解被上界截断 | **未覆盖**（当前 Q_max = {{m.params.Q_max}}，远大于最优值） | 未覆盖 |

量纲自洽检查：售价/进价/残值/缺货惩罚同为元·件⁻¹，期望利润为元·周⁻¹，年化量为元·年⁻¹，无混用。

## P5 反例搜索（最重要）

| 促销概率 | 最优 Q | 相对基线 |
|---|---|---|
| {{m.P5_counterexample.scan.0.promo_prob|.0%}} | {{m.P5_counterexample.scan.0.Q_opt}} | {{m.P5_counterexample.scan.0.Q_opt_vs_baseline}} |
| {{m.P5_counterexample.scan.1.promo_prob|.0%}} | {{m.P5_counterexample.scan.1.Q_opt}} | {{m.P5_counterexample.scan.1.Q_opt_vs_baseline}} |
| {{m.P5_counterexample.scan.2.promo_prob|.0%}} | {{m.P5_counterexample.scan.2.Q_opt}} | {{m.P5_counterexample.scan.2.Q_opt_vs_baseline}} |
| {{m.P5_counterexample.scan.3.promo_prob|.0%}} | {{m.P5_counterexample.scan.3.Q_opt}} | {{m.P5_counterexample.scan.3.Q_opt_vs_baseline}} |
| {{m.P5_counterexample.scan.4.promo_prob|.0%}} | {{m.P5_counterexample.scan.4.Q_opt}} | +{{m.P5_counterexample.scan.4.Q_opt_vs_baseline}} |
| {{m.P5_counterexample.scan.5.promo_prob|.0%}} | {{m.P5_counterexample.scan.5.Q_opt}} | +{{m.P5_counterexample.scan.5.Q_opt_vs_baseline}} |

**反例（结论翻转）**：
现状基线"均值 × 1.2 = {{m.baseline.Q}} 件"在促销概率低于 {{m.P5_counterexample.flip_boundary_cont|.2%}} 时**偏保守**（备多了），
一旦促销概率达到 {{m.P5_counterexample.flip_boundary_cont|.2%}} 就转为**偏激进**（备少了），
涨到 {{m.P5_counterexample.scan.5.promo_prob|.0%}} 时最优备货量已跳到 {{m.P5_counterexample.scan.5.Q_opt}} 件。
→ **同一个基线，在对促销频率的两种假设下，对错完全相反。**

搜索范围与未覆盖区域（必须写明）：
- 已扫描：促销概率 {{m.P5_counterexample.scan.0.promo_prob|.0%}} → {{m.P5_counterexample.scan.5.promo_prob|.0%}} 共 6 档；
- 未扫描：促销**倍数**（固定为 3.1 倍）、促销持续多周、以及促销与季节性的叠加；
- 因此本反例只能说明"促销频率是结论的敏感方向"，**不能**给出精确的翻转阈值——
  真实翻转点落在 {{m.P5_counterexample.scan.3.promo_prob|.0%}} 与 {{m.P5_counterexample.scan.4.promo_prob|.0%}} 之间。

## P6 口径对照

| 术语 | 口径 A 定义 | 口径 B 定义 | 对本模型结论的影响 |
|---|---|---|---|
| 缺货惩罚 L | 财务口径：缺货不影响已确认收入，L = 0 | 运营口径：客户流失 + 口碑，L = {{m.params.L_caliberB}} 元/件 | 最优备货量差 {{m.P6_caliber.Q_diff}} 件（{{m.P6_caliber.Q_caliberA_L0}} vs {{m.P6_caliber.Q_caliberB_L8}}） |
| 利润 | 毛利口径（不含缺货惩罚） | 含缺货惩罚的期望利润 | 两套并列报出，禁止相减或混排 |

**口径混用的代价（量化）**：按口径A 备货、真实成本结构却是口径B →
每周期望利润损失 {{m.P6_caliber.weekly_loss_if_use_A_but_true_is_B|.2f}} 元，年化 {{m.P6_caliber.annual_loss_if_use_A_but_true_is_B|.0f}} 元。
这笔钱没有出现在任何人的账上，但真实存在——**这就是不声明口径的成本。**

## P7 台账对账

- 本文件与 `report.md` 中每个数字都是**占位符**（形如 `m.键路径`，两对大括号包起来），
  由 `mm solve` 从 `out/metrics.json` 注入——本文件不含任何手写数字；
- 重算命令：`python solve.py`；独立复核：`mm audit examples/newsvendor_inventory`（临时目录重跑 + 逐数字比对）；
- 台账 `ledger.json` 中每一条 `verified` 都带 `recompute` 命令与证据文件，缺一即报错。

## 失效边界（已同步进交付报告第四节）

1. 促销概率 ≥ {{m.P5_counterexample.flip_boundary_cont|.2%}} → 推荐值 {{m.result.recommend_Q}} 件失效；
2. 需求数据为截尾的实际售出量 → 真实最优备货量应略大于 {{m.result.recommend_Q}} 件（方向确定、幅度未知）；
3. 单周期模型，不含跨周结转与需求趋势；
4. 结论依附于口径B（L = {{m.params.L_caliberB}} 元/件），口径A 下最优值是 {{m.P6_caliber.Q_caliberA_L0}} 件；
5. 样本仅 {{m.n_weeks}} 周、{{m.n_promo_weeks}} 个促销周，促销分布无法由样本估计。
