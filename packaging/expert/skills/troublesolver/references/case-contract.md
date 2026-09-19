# 案例契约：一个案例 = 一个目录的 6 件套

> 加一个**全新领域**的难题只要三步：写 `charter.md` → 写 `solve.py` + `verify.py` → 声明 `kind` / `checks`。
> **引擎一行都不用改。**

## 6 件套（照抄，不要发明）

| 文件 | 硬性要求 |
|---|---|
| `charter.md` | 12 节（标题必须以 `1 现象与触发` … `12 口径表` 开头）；§12 表**至少 1 行数据**且每行 5 格非空；**每个 `【未知】` 行内必须有 `→` 处理计划**；文末 `用户确认：是` |
| `solve.py` | 唯一数字出口 `out/metrics.json`；**必须含 `baseline` 键**；键名**不得含点号**（会截断报告占位符路径）；末尾把关键数字 `print` 出来（人肉可核对） |
| `verify.py` | 验证钩子，内部 `import solve`；`ledger.spec.json` 里 `checks[].fn` 引用的名字必须在此文件**真实存在** |
| `ledger.spec.json` | `{case, claims:[{id, kind, claim, status, method, checks, caliber, evidence, recompute, depends_on}]}`；`claim` 里的数字写成 `{{m.路径}}` |
| `report.template.md` | 数字只能写 `{{m.路径\|格式}}`，**禁止裸数字**（占位符取不到值 → 构建失败） |
| `falsify.template.md` | 同上；七条协议逐条留痕 |
| `expected.json` | golden 冻结：`{tolerance, metrics:{路径:值}, ledger_status:{id:状态}, check_verdicts:{"ID/P2":bool}}` |

**必需程度**：`tsolve solve` 只要求前 4 件；**`tsolve audit` 额外要求 `expected.json`**（缺了直接返回 rc=2）。

## 检查器怎么取参数

`checks[].fn` 的两类钩子：

- **PROVIDER 槽位**（`a`、`b`、`samples`、`values`）：钩子被**零参调用**，返回值就是检查对象
  （如 P1 的两条路径取值、P4 的 `[(参数, 实测, 期望), …]`、P6 的 `[{label,value,caliber}, …]`）。
- **FUNCTION 槽位**（`f`、`g`、`margin`）：钩子被**当函数反复调用**
  （如 P2 的 `margin(x)`、P3 的目标函数 `f(x)`、P5 的翻转判据 `g(param)`）。

纯数值/开关参数原样透传：`lo`、`hi`、`base_n`、`rtol`、`tol`、`starts`、`plateau_tol`、`allow_cross`、`extra_probe`。

**P2 的约定**：`margin(x) > 0` 表示该点**违反**断言（越大越坏）。
**P5 的约定**：`g(param)` 的**符号翻转点**即边界（`g > 0` 表示该侧结论失效）。
**P6 的约定**：两组以上不同口径并列时必须 `"allow_cross": true`，否则引擎报"禁止直接相减"。

## 台账状态机

`new → verifying → verified / refuted / stale`

- 交付物**只能引用 `verified`**；
- **被证伪的条目连同证据一起留在台账里**（删掉 = 让同一个错误再来一次）；
- 上游参数一改，依赖它的结论自动 `stale`。

## 复现命令

```bash
cd <case_dir>
python solve.py                                # 产出 out/metrics.json
tsolve solve  .                                # 卡点校验 → 跑检查器 → 台账 → 渲染报告
tsolve audit  .                                # 临时目录独立重跑 + 逐数字/逐检查对账
tsolve ledger check ./ledger.json              # 只查台账（快）
```

三者的区别：
- `tsolve solve` 回答"**这份交付物是不是从脚本长出来的**"；
- `tsolve audit` 回答"**换台机器、换个时间重跑，数字还一样吗**"；
- `tsolve ledger check` 回答"**每条结论有没有证据、有没有重算命令、有没有引用已作废的结论**"。
