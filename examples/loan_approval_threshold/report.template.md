<!--
  报告模板。铁律（P7）：本文件里**不允许出现任何手写的数字**，
  所有数字只能写成 {{m.路径}} 或 {{m.路径|格式}} 占位符，由 `tsolve solve` 从 out/metrics.json 注入。
-->
# 消费信贷审批阈值 · 决策报告

- 案例：`examples/loan_approval_threshold`（分类阈值 / 全称断言族）
- 数字来源：`out/metrics.json`（本报告不含任何手写数字）
- 复现命令：`python solve.py` ／ 复核命令：`tsolve audit examples/loan_approval_threshold`
- 台账：{{ledger.n}} 条结论，其中已证 {{ledger.verified}} 条、已证伪（留痕）{{ledger.refuted}} 条

## 一、结论（可直接执行）

**现状阈值 {{m.params.T_now}} 是"假安全"：组合平均坏账率只有 {{m.caliber.avg_T600|.4f}}（看着很稳），
但评分 {{m.baseline.worst_at|.1f}} 处的客户违约率高达 {{m.baseline.worst_rate|.4f}}，已越上限 {{m.params.cap|.2f}}。**

**建议把阈值抬到 {{m.result.recommend_T|.0f}}**：该段窄带客群被排除在审批域外，逐点最坏违约率降到
{{m.pointwise.T650_worst_rate|.4f}} ≤ 上限；阈值翻转边界在 {{m.flip.threshold_flip|.2f}}，取整到 {{m.result.recommend_T|.0f}} 留有缓冲。

> 注意：**平均值口径会掩盖局部窄带风险**。监管与风控必须看「逐点最坏口径」，不能用组合平均替自己壮胆。

## 二、现状校核

| 项目 | 数值 | 说明 |
|---|---|---|
| 评分区间 | [{{m.params.score_lo|.0f}}, {{m.params.score_hi|.0f}}] | 现状阈值 {{m.params.T_now|.0f}} |
| 组合平均坏账率 | {{m.caliber.avg_T600|.4f}} | 看似安全（远低于 {{m.params.cap|.2f}}） |
| 逐点最坏违约率 | {{m.baseline.worst_rate|.4f}} @ 评分 {{m.baseline.worst_at|.1f}} | **已越上限 {{m.params.cap|.2f}}** |
| 越上限幅度 | {{m.baseline.worst_rate|.4f}} − {{m.params.cap|.2f}} = {{m.pointwise.T600_margin|.4f}} | 负值=越上限 |

> **口径警告（P6）**：组合平均与逐点最坏是两套口径，**结论相反**，禁止用平均替最坏背书。

## 三、验证记录（检查器实跑，不是人填的）

| 协议 | 判据 | 本案例结果 | 判定 |
|---|---|---|---|
| P1 双路径交叉 | 两独立方法相对误差 < 1e-9 | 解析尖峰 {{m.P1_dual_path.worst_rate_analytic|.4f}} vs 对抗搜索 {{m.P1_dual_path.worst_rate_adversarial|.4f}}，相对差 {{m.P1_dual_path.rel_diff|.2e}} | 通过 |
| P2 全称断言审计 | 粗网格与**对抗搜索**必须同结论 | 阈值 600 下被对抗搜索证伪（评分 {{m.baseline.worst_at|.1f}} 处越上限 {{m.pointwise.T600_margin|.4f}}），**且粗网格给出相反结论 → 窄带陷阱** | 一成立一证伪（见 `falsify.md`） |
| P3 连续复核 | 离散极值须用连续搜索复核，报区间 | 违约率曲线在最坏点处为尖峰，平台宽度见 `falsify.md` | 通过（报区间） |
| P4 极限与量纲 | 参数取极限须退化为已知结果 | 本案例未触发（无极限型结论） | 不适用 |
| P5 翻转边界 | 不给"找到一个反例"就收工，要报边界 | 阈值翻转边界 T* = {{m.flip.threshold_flip|.2f}} | 通过 |
| P6 口径声明 | 并列数字必须各自带口径 | 见 §二 口径警告 + §四两种违约口径 | 通过 |
| P7 台账对账 | 每个对外数字可由一条命令重算 | 本报告数字全部由占位符注入；`tsolve audit` 独立重跑逐项比对 | 通过 |

## 四、局限与失效边界（**必读**）

1. **平均值≠安全**：组合平均 {{m.caliber.avg_T600|.4f}} 看似远低于上限，但逐点最坏 {{m.baseline.worst_rate|.4f}} 已越上限。窄带客群被平均稀释。
2. **窄带是局部尖峰**：中心在评分 {{m.params.bump_center}}、宽度 {{m.params.bump_sigma}} 分，粗网格（步长 5 分）会整段跳过它，给出"全满足"的假结论。
3. **阈值必须向上留缓冲**：翻转边界 {{m.flip.threshold_flip|.2f}}，取整到 {{m.result.recommend_T|.0f}} 才有工程余量；向下取整会重新纳入窄带。
4. **口径决定结论**：30 天逾期口径 {{m.caliber.thirty_day_rate|.4f}} 与 90 天违约口径 {{m.caliber.ninety_day_rate|.4f}} 不同，禁止相减或混用。
5. **模型假设未验证**：违约率函数来自历史抽象，细分客群真实分布未建模；宏观冲击、模型漂移不在本版范围。

## 五、台账摘要

共 {{ledger.n}} 条：已证 {{ledger.verified}} 条、已证伪留痕 {{ledger.refuted}} 条。
被证伪的条目（L-001）连同反例一起保留，防止"平均值安全感"再次进入交付物。

- 查看：`tsolve ledger show examples/loan_approval_threshold/ledger.json`
- 对账：`tsolve ledger check examples/loan_approval_threshold/ledger.json`

## 六、复现方式

```bash
cd examples/loan_approval_threshold
python solve.py     # 重算 → out/metrics.json
tsolve solve .          # 卡点校验 → 自动跑检查器 → 台账 → 本报告
tsolve audit .          # 临时目录独立重跑 + 逐数字/逐检查对账
```
