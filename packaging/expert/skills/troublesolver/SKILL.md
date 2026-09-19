---
name: troublesolver
description: TroubleSolver 建模与验证引擎（随专家打包，零第三方依赖）。当需要把业务问题形式化、写案例（charter/solve/verify/ledger）、跑七条验证协议、生成可追溯台账与可复算报告，或复核一份建模交付物是否"数字可重算"时使用。触发词：数学建模、建模、结论验证、恒成立、反例、失效边界、台账、可复算、charter、ledger、tsolve。
---

# TroubleSolver 建模与验证引擎（内置）

> 这个 skill 把 TroubleSolver 的**可执行引擎**一起带进来了 —— 所以你不是"讲方法论"，
> 而是**真的能跑**：卡点校验、七条协议、台账状态机、数字对账、独立复核。
>
> 引擎在 `scripts/troublesolver/`（纯标准库，**不联网、不读密钥**）。
> 上游仓库与文档：<https://github.com/zheng-qinghe/trouble-solver>

## 一、先读哪三份

| 文件 | 什么时候读 |
|---|---|
| `references/intake-12-dimensions.md` | 开工第一步：把问题问全（阶段 0，卡点①） |
| `references/protocols.md` | 建模/证伪时：七条协议 + **结论类型→必跑矩阵** |
| `references/case-contract.md` | 写代码前：一个案例 = 一个目录的 **6 件套** |

阶段指令全文在 `prompts/`（`00_intake` / `20_model` / `30_falsify` / `50_deliver`）。
需要脚手架时，从 `templates/` 复制（`charter.md`、`ledger.spec.json`、
`report.template.md`、`falsify.template.md`、`expected.json`）。

## 二、怎么跑（命令）

```bash
# 若 tsolve 不在 PATH，用本包内的：<plugin>/bin/tsolve
tsolve charter new   <charter.md>      # 生成《问题说明书》空白模板
tsolve charter check <charter.md>      # 卡点①：12 节齐了吗、口径表填了吗、未知项有处理计划吗
tsolve solve <case_dir>                # 闭环：形式化 → 基线 → 建模 → 证伪 → 台账 → 交付
tsolve audit <case_dir>                # 阶段 6：临时目录独立重跑 + 逐数字/逐检查对账
tsolve ledger show  <ledger.json>      # 看台账
tsolve ledger check <ledger.json>      # 交付前对账（P7）
tsolve agent <case_dir>                # LLM 编排：读 charter + 阶段指令生成案例文件（需密钥）
tsolve agent <case_dir> --mock         # 离线演练（零网络零密钥）
tsolve agent <case_dir> --dry-run      # 只打印拼好的提示
```

**返回码约定**：`0` 通过；`2` 卡点/对账未通过（必须修，不许"先发出去"）。

## 三、引擎的三条硬规则（绕不过去）

1. **卡点①**：`charter.md` 未通过 → `solve` 拒绝往下走（口径错了后面全白做）。
2. **必跑协议**：标 `verified` 的结论必须声明 `kind`，且该类型的必跑协议一条不少，否则直接报错。
3. **数字零手写**：`report.template.md` / `falsify.template.md` 里只能写 `{{m.路径}}`；
   占位符取不到值 → **构建失败**（不是留空）。

## 四、怎么加一个新领域（不改引擎）

1. 写 `charter.md`（12 节，`tsolve charter check` 通过）；
2. 写 `solve.py`（唯一出口 `out/metrics.json`，含 `baseline` 键）+ `verify.py`（把可检查对象暴露成钩子）；
3. 在 `ledger.spec.json` 里声明每条结论的 `kind` 与 `checks`；
4. `tsolve solve .` → `tsolve audit .`。

**引擎只认识结论类型**（等式 / 极值 / 全称断言 / 最优性 / 稳健性 / 口径相关 / 极限 …），
不认识你的领域 —— 领域知识留在案例的 `verify.py` 里。

## 五、四个可参照的真实案例

`examples/` 里有四个异构案例（库存随机 / 设施覆盖几何 / 信贷风控 / 渔业 MSY），
后三个各自自动抓到一种**不同机理**的窄带陷阱（几何缺口 / 统计越界带 / 局部额外死亡带）。
读它们最快理解"契约怎么落地"。

## 六、边界（不要越界承诺）

- **不写竞赛论文**（与学术诚信冲突）；交付的是业务解答包。
- **不替用户拍口径**：两套口径并列报出，拍板是用户的活。
- **搜索不保证穷尽**：P2 每次都报搜索分辨率，"未找到" ≠ "不存在"。
