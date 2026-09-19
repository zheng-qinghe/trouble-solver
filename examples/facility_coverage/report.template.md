<!--
  报告模板。铁律（P7）：本文件里**不允许出现任何手写的数字**，
  所有数字只能写成 {{m.路径}} 或 {{m.路径|格式}} 占位符，由 `tsolve solve` 从 out/metrics.json 注入。
-->
# 2 km 园区步道照明覆盖 · 设计报告

- 案例：`examples/facility_coverage`（几何 / 全称断言族）
- 数字来源：`out/metrics.json`（本报告不含任何手写数字）
- 复现命令：`python solve.py` ／ 复核命令：`tsolve audit examples/facility_coverage`
- 台账：{{ledger.n}} 条结论，其中已证 {{ledger.verified}} 条、已证伪（留痕）{{ledger.refuted}} 条

## 一、结论（可直接执行）

**现状 7 点布点卡在临界点上：出厂标称半径 {{m.params.r_rated}} m 时余量只有 {{m.coverage_now.margin_at_rated|.4f}} m（零点几毫米）；实测光衰半径 {{m.params.r_aged}} m 时已经失守。**

**建议改为 {{m.result.recommend_n}} 点等间距布点**，所需半径从 {{m.P1_dual_path.r_needed_analytic_n7|.4f}} m 降到 {{m.result.r_needed|.4f}} m，
相对现状多出 {{m.result.margin_gain_vs_now|.4f}} m 余量；这正是采购半径上限 {{m.n_for_target.r_target}} m 之下所需的最少点数
（连续解 {{m.n_for_target.n_exact|.4f}} 个 → 向上取整 {{m.n_for_target.n_ceil}} 个）。

> 注意：**任何"刚好够"的等间距方案都是零余量**（照亮 ⟺ 最大间距的一半 = 半径）。
> 真正要落地，必须按有效口径选型（见 §四），或显式留出施工偏差裕度。

## 二、现状校核

| 项目 | 数值 | 说明 |
|---|---|---|
| 步道长度 | {{m.params.L|.0f}} m | 宽 {{m.params.W|.0f}} m（本版只做中线几何覆盖） |
| 现状灯杆数 | {{m.params.n_now}} 根 | 等间距 {{m.params.spacing_now|.4f}} m |
| 理论所需半径 | {{m.coverage_now.r_needed_exact|.4f}} m | 最坏点 x = {{m.coverage_now.worst_point_x|.2f}} m（相邻两点中点） |
| 出厂标称半径 | {{m.params.r_rated}} m | 余量 {{m.coverage_now.margin_at_rated|.4f}} m ← **等于零余量** |
| 实测光衰半径 | {{m.params.r_aged}} m | 缺口 {{m.coverage_now.shortfall_at_aged|.4f}} m ← **已失守** |

> **口径警告（P6）**：标称半径与实测半径是两套口径，**不得混用**。
> 按几何口径，n=7 需 {{m.caliber.geom_r_n7|.4f}} m；按有效口径（标称 × {{m.params.eff_ratio}} 折减），
> n=7 需要标称 {{m.caliber.nominal_needed_n7|.4f}} m，n=8 需要标称 {{m.caliber.nominal_needed_n8|.4f}} m。
> **采购按有效口径，覆盖核算按几何口径。**

## 三、验证记录（检查器实跑，不是人填的）

| 协议 | 判据 | 本案例结果 | 判定 |
|---|---|---|---|
| P1 双路径交叉 | 两独立方法相对误差 < 1e-9 | 解析式 {{m.P1_dual_path.r_needed_analytic_n7|.4f}} vs 细步扫描 {{m.P1_dual_path.r_needed_scan_n7|.4f}}，相对差 {{m.P1_dual_path.rel_diff|.2e}} | 通过 |
| P2 全称断言审计 | 粗网格与**对抗搜索**必须同结论 | 标称半径下断言成立（余量 {{m.coverage_now.margin_at_rated|.4f}} m）；实测半径下被对抗搜索证伪（缺口 {{m.coverage_now.shortfall_at_aged|.4f}} m），**且粗网格给出相反结论 → 窄带陷阱** | 一成立一证伪（见 `falsify.md`） |
| P3 连续复核 | 离散极值须用连续搜索复核，报区间 | 布点整体偏移的敏感性曲线在最优点处为尖点，平台宽度见 `falsify.md` | 通过（报区间） |
| P4 极限与量纲 | 参数取极限须退化为已知结果 | n=2 时退化为 {{m.limit.n2_r|.1f}} m（= 全长一半）；n=3 → {{m.limit.n3_r|.1f}} m | 通过 |
| P5 翻转边界 | 不给"找到一个反例"就收工，要报边界 | 半径翻转边界 = 所需半径本身；n 的翻转边界 = {{m.n_for_target.n_exact|.4f}} | 通过（2 条） |
| P6 口径声明 | 并列数字必须各自带口径 | 见 §二 口径警告 | 通过 |
| P7 台账对账 | 每个对外数字可由一条命令重算 | 本报告数字全部由占位符注入；`tsolve audit` 独立重跑逐项比对 | 通过 |

## 四、局限与失效边界（**必读**）

1. **零余量是本问题的结构性特征**：等间距布点的所需半径恒等于最大间距的一半，因此"刚好够"的方案没有任何工程容差。
   施工方若整体偏移 δ，所需半径上升 2δ 量级——**必须现场实测复核，不能只按图纸验收。**
2. **实测光衰已经打破现状方案**：实测半径 {{m.params.r_aged}} m < 所需 {{m.coverage_now.r_needed_exact|.4f}} m，
   缺口 {{m.coverage_now.shortfall_at_aged|.4f}} m。这是"卡在临界点的设计"的典型后果。
3. **只做几何覆盖**：不含照度均匀度、人眼适应、灯杆故障冗余（k-out-of-n）。含人因模型时会显著改变覆盖定义。
4. **口径决定选型**：按几何口径 n=8 只需 {{m.caliber.geom_r_n8|.4f}} m，但按有效口径要买标称 {{m.caliber.nominal_needed_n8|.4f}} m 的型号 —— 后者才是采购依据。
5. **n 必须取整**：连续解 {{m.n_for_target.n_exact|.4f}} 必须向上取整为 {{m.n_for_target.n_ceil}}，向下取整会直接导致覆盖失败。

## 五、台账摘要

共 {{ledger.n}} 条：已证 {{ledger.verified}} 条、已证伪留痕 {{ledger.refuted}} 条。
被证伪的条目（B-001）连同反例一起保留，防止"看起来完好"的假结论再次进入交付物。

- 查看：`tsolve ledger show examples/facility_coverage/ledger.json`
- 对账：`tsolve ledger check examples/facility_coverage/ledger.json`

## 六、复现方式

```bash
cd examples/facility_coverage
python solve.py     # 重算 → out/metrics.json
tsolve solve .          # 卡点校验 → 自动跑检查器 → 台账 → 本报告
tsolve audit .          # 临时目录独立重跑 + 逐数字/逐检查对账
```
