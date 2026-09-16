<!--
  报告模板。铁律（P7）：本文件里**不允许出现任何手写的数字**，
  所有数字只能写成 {{m.路径}} 或 {{m.路径|格式}} 占位符，由 `mm solve` 从 out/metrics.json 注入。
  取不到值就直接报错——宁可跑不出来，也不许把猜的数字印在交付物上。
-->
# 单 SKU 每周备货量决策 · 分析报告

- 案例：`examples/newsvendor_inventory`
- 数字来源：`out/metrics.json`（本报告不含任何手写数字）
- 复现命令：`python solve.py` ／ 复核命令：`mm audit examples/newsvendor_inventory`
- 台账：{{ledger.n}} 条结论，其中已证 {{ledger.verified}} 条、已证伪（留痕）{{ledger.refuted}} 条

## 一、结论（可直接执行）

**建议每周备货 {{m.result.recommend_Q}} 件。**

相对现状做法（均值 × 1.2 = {{m.baseline.Q}} 件），每周期望利润从 {{m.baseline.profit_caliberB|.2f}} 元
提升到 {{m.P1_dual_path.profit_pathB|.2f}} 元，**每周多 {{m.result.gain_vs_baseline_per_week|.2f}} 元（+{{m.result.gain_vs_baseline_pct|.1f}}%）**，年化约 {{m.result.gain_vs_baseline_annual|.0f}} 元。

> 这不是"最优值"，而是**在明确口径下的最优解 + 已知失效边界**（见第四节）。
> 若促销概率上升到 {{m.P5_counterexample.flip_point|.0%}} 以上，本推荐值失效，须改用更大的备货量。

## 二、基线对照

| 项目 | 现状基线 | 本模型推荐 | 差异 |
|---|---|---|---|
| 每周备货量 Q（件） | {{m.baseline.Q}} | {{m.result.recommend_Q}} | {{m.result.Q_vs_baseline}} 件 |
| 周期望利润（元，口径B） | {{m.baseline.profit_caliberB|.2f}} | {{m.P1_dual_path.profit_pathB|.2f}} | +{{m.result.gain_vs_baseline_per_week|.2f}} |
| 周期望利润（元，口径A） | {{m.baseline.profit_caliberA|.2f}} | 见 §四.4 | 口径不同不可相减 |

样本：{{m.n_weeks}} 周（均值 {{m.mean|.1f}}、中位 {{m.median|.1f}}、最小 {{m.min|.0f}}、最大 {{m.max|.0f}}），其中促销周 {{m.n_promo_weeks}} 个。

> **口径警告（P6）**：本表两列利润必须同口径比较。口径A（缺货惩罚 0 元/件，财务口径）
> 与口径B（缺货惩罚 {{m.params.L_caliberB}} 元/件，运营口径）相差 {{m.P6_caliber.Q_diff}} 件备货量，
> 若按口径A 备货而真实成本结构是口径B，每周期望利润损失 {{m.P6_caliber.weekly_loss_if_use_A_but_true_is_B|.2f}} 元。

## 三、验证记录

| 协议 | 判据 | 本案例结果 | 判定 |
|---|---|---|---|
| P1 双路径交叉 | 两独立方法相对误差 < 1e-9 | 分位数法 Q={{m.P1_dual_path.Q_pathA_fractile}} vs 数值枚举 Q={{m.P1_dual_path.Q_pathB_numeric}}，利润相对差 {{m.P1_dual_path.rel_diff_profit|.2e}} | 通过 |
| P2 细步重扫 | "恒成立"类断言必须 ≥10× 细化重扫 | **本例未触发**：产出中不含"恒/一定/总是"类断言（触发条件与记录格式见 `falsify.md`） | 不适用 |
| P3 连续复核 | 离散极值须用连续/自适应复核，报区间 | 离散峰值 Q={{m.P3_continuous.Q_discrete_opt}}；连续分位数 {{m.P3_continuous.Q_continuous_quantile|.2f}}；0.1% 平台 = [{{m.P3_continuous.profit_band_0p1pct.0}}, {{m.P3_continuous.profit_band_0p1pct.1}}] | 通过（报区间） |
| P4 极限与量纲 | 参数取极限须退化为已知结果 | 缺货惩罚 → 0 时临界分位数退化为经典报童比 {{m.P1_dual_path.critical_fractile_caliberA|.4f}} | 通过（另一条极限未覆盖，见 `falsify.md`） |
| P5 反例搜索 | 主动搜使结论翻转的参数区域 | 促销概率 ≥ {{m.P5_counterexample.flip_point|.0%}} 时基线由偏保守转为偏激进；推荐值在该区间失效 | 通过（1 条反例） |
| P6 口径声明 | 每个数字标来源/定义/边界/可外推 | 见 §二 口径警告与台账 `caliber` 字段 | 通过 |
| P7 台账对账 | 每个对外数字可由一条命令重算 | 本报告数字全部由占位符注入；`mm audit` 独立重跑逐项比对 | 通过 |

## 四、局限与失效边界（**必读**）

1. **促销概率 ≥ {{m.P5_counterexample.flip_point|.0%}} 即失效**：本推荐值 {{m.result.recommend_Q}} 件只在该点以下成立；
   到该档位最优解已是 {{m.P5_counterexample.scan.4.Q_opt}} 件，促销概率 {{m.P5_counterexample.scan.5.promo_prob|.0%}} 时更达 {{m.P5_counterexample.scan.5.Q_opt}} 件。
   **促销排期一变，结论就要重算。**
2. **数据截尾偏差**：需求用"实际售出量"，缺货周的未满足需求未计入 → 均值系统性低估，真实最优备货量应略大于 {{m.result.recommend_Q}}。
   方向已知、幅度未知，故本版不修正。
3. **单周期模型**：未建模跨周库存结转与需求趋势。若存在明显季节性，应改多周期模型。
4. **口径依赖**：本推荐值建立在口径B（缺货惩罚 {{m.params.L_caliberB}} 元/件）之上。口径A 下的最优值只有 {{m.P6_caliber.Q_caliberA_L0}} 件；
   **两个口径谁是"真"，需要业务方拍板**，工具不做这个决定。
5. **样本外推**：{{m.n_weeks}} 周样本只含 {{m.n_promo_weeks}} 个促销周，促销分布本身无法由此估计。

## 五、台账摘要

共 {{ledger.n}} 条：已证 {{ledger.verified}} 条、已证伪留痕 {{ledger.refuted}} 条。
交付物只允许引用"已证"条目；被证伪的条目连证据一起保留在 `ledger.json` 中，防止同一个错误结论再次被写进报告。

- 查看：`mm ledger show examples/newsvendor_inventory/ledger.json`
- 对账：`mm ledger check examples/newsvendor_inventory/ledger.json`

## 六、复现方式

```bash
cd examples/newsvendor_inventory
python solve.py        # 重算 → out/metrics.json
mm solve .             # 走完整闭环：卡点校验 → 台账 → 本报告
mm audit .             # 独立重跑 + 逐数字对账（阶段 6）
```
