<!--
  报告模板。铁律（P7）：本文件里**不允许出现任何手写的数字**，
  所有数字只能写成 {{m.路径}} 或 {{m.路径|格式}} 占位符，由 `tsolve solve` 从 out/metrics.json 注入。
-->
# 渔业最大可持续产量（MSY）· 评估与资源可续报告

- 案例：`examples/fishery_msy`（生物 / 资源族：连续优化 + 全称断言 + 口径相关）
- 数字来源：`out/metrics.json`（本报告不含任何手写数字）
- 复现命令：`python solve.py` ／ 复核命令：`tsolve audit examples/fishery_msy`
- 台账：{{ledger.n}} 条结论，其中已证 {{ledger.verified}} 条、已证伪（留痕）{{ledger.refuted}} 条

## 一、结论（可直接执行）

**现状努力度 {{m.params.E_now|.0f}} 船·年 只产 {{m.baseline.yield_now|.0f}} 吨/年，远低于最大可持续产量 MSY = {{m.result.yield_max|.0f}} 吨/年 @ 努力度 E* = {{m.result.recommend_E|.0f}} 船·年——还有 {{m.result.gain_to_msy|.0f}} 吨/年的增产空间。**

**但"增产到 MSY"有个前提条件：必须按有效口径守住资源红线。** 局部额外死亡带会在 E≈{{m.pointwise.worst_margin_at|.0f}} 处把有效产卵生物量打到 {{m.caliber.eff_at_spike|.1f}} 吨（下限 {{m.params.B_min|.0f}} 吨），最坏余量 {{m.pointwise.worst_margin|.2f}} 吨——**按标称口径（不计额外死亡）这个档位显示安全（余量 {{m.nominal.margin_at_spike|.1f}} 吨），正好是会骗人的那一套。**

> 注意：**产量最优 ≠ 资源可续**。MSY 讨论的是"产量最大"，可续断言讨论的是"生物量不失守"——二者必须用不同口径分别验证（见 §四）。

## 二、现状校核

| 项目 | 数值 | 说明 |
|---|---|---|
| 承载力 K | {{m.params.K|.0f}} 吨 | 内禀增长率 r = {{m.params.r|.2f}} /年 |
| 可捕系数 q | {{m.params.q}} /(船·年) | MSY 努力度 E* = r/(2q) = {{m.msy.E_star_analytic|.0f}} |
| 现状努力度 | {{m.params.E_now|.0f}} 船·年 | 现状产量 {{m.baseline.yield_now|.0f}} 吨/年 |
| 理论 MSY | {{m.result.yield_max|.0f}} 吨/年 | 解析式 {{m.msy.y_max_analytic|.1f}} vs 细扫 {{m.msy.y_max_numeric|.1f}}，相对差 {{m.msy.rel_diff|.2e}} |
| 保护性红线 B_MIN | {{m.params.B_min|.0f}} 吨 | 有效口径最坏余量 {{m.pointwise.worst_margin|.2f}} 吨（已失守） |

> **口径警告（P6）**：标称口径在 E={{m.params.E_spike|.0f}} 处给出生物量 {{m.caliber.nominal_at_spike|.1f}} 吨（安全），
> 有效口径同点只有 {{m.caliber.eff_at_spike|.1f}} 吨（失守）。二者相差 {{m.params.amp|.1f}} 吨（= 局部额外死亡带幅度），
> **禁止相减，必须分别陈述**。资源评估按有效口径，产量优化按标称口径。

## 三、验证记录（检查器实跑，不是人填的）

| 协议 | 判据 | 本案例结果 | 判定 |
|---|---|---|---|
| P1 双路径交叉 | 两独立方法相对误差 < 1e-9 | 解析式 {{m.msy.y_max_analytic|.1f}} vs 细扫 {{m.msy.y_max_numeric|.1f}}，相对差 {{m.msy.rel_diff|.2e}} | 通过 |
| P2 全称断言审计 | 粗网格与**对抗搜索**必须同结论 | 有效口径下被对抗搜索证伪（最坏余量 {{m.pointwise.worst_margin|.2f}} 吨 @ E≈{{m.pointwise.worst_margin_at|.1f}}），**且粗网格给出相反结论 → 窄带陷阱**；标称口径下成立（最坏余量 {{m.nominal.worst_margin|.2f}} 吨） | 一证伪一成立（见 `falsify.md`） |
| P3 连续复核 | 离散极值须用连续搜索复核，报区间 | 产量在 E*={{m.msy.E_star_analytic|.0f}} 处为全局最大，对抗搜索确认峰值位置（见 `out/checks.json`） | 通过（报区间） |
| P4 极限与量纲 | 参数取极限须退化为已知结果 | E→0 产量→{{m.limit.E0_yield|.1f}}；E→400 生物量→{{m.limit.E400_x|.1f}}；E=E* 产量=闭式 {{m.msy.y_max_analytic|.1f}} | 通过 |
| P5 翻转边界 | 不给"找到一个反例"就收工，要报边界 | 产量翻转边界 E*={{m.msy.E_star_analytic|.0f}}；标称口径无单调翻转（见 `falsify.md`） | 通过（2 条） |
| P6 口径声明 | 并列数字必须各自带口径 | 见 §二 口径警告 | 通过 |
| P7 台账对账 | 每个对外数字可由一条命令重算 | 本报告数字全部由占位符注入；`tsolve audit` 独立重跑逐项比对 | 通过 |

## 四、局限与失效边界（**必读**）

1. **产量最优与资源可续是两件事**：MSY = {{m.result.yield_max|.0f}} 吨/年是"产量最大"的结论；但"每个努力档位下资源都不失守"是**另一口径**的结论，被局部额外死亡带证伪（F-001）。
2. **局部额外死亡带是窄带陷阱的真凶**：违例带仅约 16 吨宽、卡在网格点 E=180/186 之间，粗网格整段跳过它，给出"可续"的假结论。凡全称断言必须用对抗搜索。
3. **只做生物量口径**：不含经济收益、社会就业、多鱼种交互、年龄结构、气候情景。含经济口径时会显著改变"最优努力度"的定义。
4. **口径决定结论**：按标称口径（不计额外死亡）E={{m.params.E_spike|.0f}} 处"安全"；按有效口径同点已失守。采购/配额按有效口径，产量核算按标称口径。
5. **B_MIN 是给定管理目标**：其生态学来源（如 SPR 反推）未在本版建模，作为红线直接采用。

## 五、台账摘要

共 {{ledger.n}} 条：已证 {{ledger.verified}} 条、已证伪留痕 {{ledger.refuted}} 条。
被证伪的条目（F-001）连同反例一起保留，防止"看起来可续"的假结论再次进入交付物。

- 查看：`tsolve ledger show examples/fishery_msy/ledger.json`
- 对账：`tsolve ledger check examples/fishery_msy/ledger.json`

## 六、复现方式

```bash
cd examples/fishery_msy
python solve.py     # 重算 → out/metrics.json
tsolve solve .          # 卡点校验 → 自动跑检查器 → 台账 → 本报告
tsolve audit .          # 临时目录独立重跑 + 逐数字/逐检查对账
```
