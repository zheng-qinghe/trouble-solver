# TroubleSolver —— 会自我证伪的建模助手

**English**: [README.en.md](README.en.md)

> 所有"AI 建模"工具都在解决**怎么写出来**，没人解决**怎么知道它是对的**。
> TroubleSolver 只做后一件事：给一段业务问题，产出**带验证台账、能被第三方按脚本复算**的解答包，
> 并**主动告诉你它在什么条件下失效**。

```
0 形式化 ──▶【人：口径确认】      业务问题 → 数学对象 / 目标 / 约束 / 口径 / 验收标准
1 基线   ──▶【人：基线可复现】    先给最笨但可信的基线，否则"改善了多少"无从谈起
2 建模    解析优先（能闭式就闭式），数值兜底，两条路径同时写
3 证伪 ★  跑七条验证协议，主动构造反例；翻转就改结论并留痕   ← 与所有同类工具的分水岭
4 稳健    参数区间 / 最坏情形 / 口径对照（不同口径给不同答案，并列报出）
5 交付    台账 → 报告 + 脚本，强制"局限与失效边界"章节
6 复核    换目录独立重跑，逐数字对账，不一致就打回
```

只有两个人工卡点（**口径确认**、**基线可复现**）——这两处错了后面全白做，其余全自动。

> 📄 **发布页 / 使用说明（带思维导图）**：用浏览器直接打开 `docs/index.html`
> （单文件、零依赖、可离线看）。里面有"怎么用"的四步、七条协议、台账状态机、
> 数字零手写的机制说明，以及三个"防护真的会拦"的实测输出。

## 它不做什么（先说清楚）

- ❌ **不写竞赛论文**：红海，且与学术诚信冲突。它输出的是业务解答包，不是参赛作品。
- ❌ **不承诺"最优解"**：只承诺"**在明确口径与假设下的最优解 + 失效边界**"。
- ❌ **不替你决定口径**：业务口径与财务口径打架时，两套都算、并列报出，拍板是你的活。
- ❌ 不做 Web UI / 多智能体角色扮演 / 数据库 / 账号体系。

## 核心机制

### 七条验证协议（产品本体，不是提示词技巧）

| # | 协议 | 判据 |
|---|---|---|
| P1 | 双路径交叉 | 两种**独立**实现给出同一结论，相对误差 < 1e-9 |
| P2 | 细步重扫 | 任何"恒成立/从无例外"断言，必须 ≥10× 细化步长重扫 + 主动构造最坏构型 |
| P3 | 连续复核 | 离散网格算出的极值必须用连续/自适应搜索复核，报**区间**不报单点 |
| P4 | 极限与量纲 | 参数 → 0/∞/临界值时退化为已知结果；量纲自洽 |
| P5 | 反例搜索 | 主动搜使结论翻转的参数区域，报"翻转边界" |
| P6 | 口径声明 | 每个数字标：来源 / 定义 / 适用边界 / 能否外推 |
| P7 | 台账对账 | 每个对外数字都能由一条命令重算，**禁止手抄** |

P2 / P3 / P5 是"**主动找自己错**"，与只查格式的传统 QA 不是一回事——这三条是门槛。

### 可追溯台账 + 数字零手写

每条结论一个条目，状态机驱动：`new → verifying → verified / refuted / stale`。
交付物**只能引用 `verified`**；被证伪的条目**连同证据一起留在台账里**
（删掉就等于让同一个错误再来一次）；上游参数一改，依赖它的结论自动 `stale`。

报告与证伪记录里的每个数字都写成 `{{m.路径}}` 占位符，从 `out/metrics.json` 注入，
**取不到值就直接构建失败**——不给"手抄一个数字"留后路。

### 泛化：引擎不认识你的领域

协议不是写在提示词里给人看的文字，而是**能跑的检查器**（`src/troublesolver/checks.py`）。
引擎只认识**结论类型**（等式 / 极值 / 全称断言 / 最优性 / 口径相关 / …），
不认识库存、照明、促销、信贷评分。每条结论声明自己的类型，引擎据此**强制跑齐**该类型该跑的协议：

```jsonc
{ "kind": "全称断言",                                  // ← 类型决定必跑 P2+P5
  "checks": [{"protocol": "P2", "fn": "cover_margin_aged",
              "lo": 0, "hi": 2000, "base_n": 51}] }    // ← fn 是案例 verify.py 里的钩子
```

于是加一个**全新领域**的难题只要三步：
写 `charter.md`（问题说明书）→ 写 `solve.py` + `verify.py`（钩子）→ 声明 `kind`/`checks`。
**引擎一行都不用改。** 台账里的 `protocols` 也不再手写，它由"实际跑过且通过"的检查决定。

→ 详见 [`docs/generalization.md`](docs/generalization.md)（含"能泛化什么 / 不能泛化什么"的诚实边界）。

## 30 秒上手

```bash
# 案例 A：库存随机优化族（单 SKU 每周备货量决策）
PYTHONPATH=src python3 -m troublesolver.cli solve examples/newsvendor_inventory
PYTHONPATH=src python3 -m troublesolver.cli audit examples/newsvendor_inventory

# 案例 B：几何 / 全称断言族（园区步道照明覆盖）——同一引擎，零改动
PYTHONPATH=src python3 -m troublesolver.cli solve examples/facility_coverage
PYTHONPATH=src python3 -m troublesolver.cli audit examples/facility_coverage

# 案例 C：统计量 / 全称断言 / 口径相关（消费信贷审批阈值）——金融风控领域
PYTHONPATH=src python3 -m troublesolver.cli solve examples/loan_approval_threshold
PYTHONPATH=src python3 -m troublesolver.cli audit examples/loan_approval_threshold

# 案例 D：生物 / 资源（渔业最大可持续产量 MSY）——连续优化 + 全称断言 + 口径相关
PYTHONPATH=src python3 -m troublesolver.cli solve examples/fishery_msy
PYTHONPATH=src python3 -m troublesolver.cli audit examples/fishery_msy

# 看台账
PYTHONPATH=src python3 -m troublesolver.cli ledger show examples/facility_coverage/ledger.json

# LLM 编排：读 charter.md + 阶段指令，让模型生成案例文件，再跑同一套闭环
#（需 $TSOLVE_LLM_API_KEY；密钥只从环境变量读，代码里搜不到）
PYTHONPATH=src python3 -m troublesolver.cli agent path/to/newcase
PYTHONPATH=src python3 -m troublesolver.cli agent path/to/newcase --mock   # 离线零密钥（CI 用）
PYTHONPATH=src python3 -m troublesolver.cli agent path/to/newcase --dry-run  # 只打印拼好的提示
```

实际输出（节选）：

```
【阶段 0 形式化】问题说明书：通过
【阶段 1-2 基线与建模】求解脚本已运行，数字出口 out/metrics.json
  基线 Q0=150 件，周期望利润=1007.35 元（键 baseline）
【阶段 3-5 证伪与交付】台账 9 条，状态分布 {"verified": 8, "refuted": 1}
  已生成 report.md
  已生成 falsify.md
闭环通过：报告/证伪记录里的每个数字都来自 out/metrics.json（P7）
```

`tsolve audit` 会在**临时目录**里独立重跑一遍求解脚本，再把冻结的数字与检查结论逐个比对，
并检查结论状态有没有偷偷漂移。改一个参数试试——它会立刻拦住你：

```
  - 数字漂移：result.recommend_Q 期望 133，实测 134（容差 1e-09）
```

## 目录结构

```
trouble-solver/
├── prompts/                    给 agent 的阶段指令（阶段 0 / 2 / 3 / 5）
│   ├── 00_intake.md            引导提问：12 个维度把问题问全
│   ├── 20_model.md             基线与建模：双路径、数字零手写
│   ├── 30_falsify.md           证伪：七条协议与三条真实血例
│   └── 50_deliver.md           交付：交付包清单与硬性规则
├── src/troublesolver/
│   ├── cli.py                  tsolve charter / ledger / solve / audit / agent
│   ├── charter.py              问题说明书完整性校验（卡点①）
│   ├── ledger.py               台账状态机 + 交付前对账（P7）
│   ├── checks.py               ★ 可执行检查器 + 结论类型→必跑协议矩阵（泛化的核心）
│   ├── orchestrate.py          LLM 编排：prompts + charter.md → 案例文件 → 引擎闭环
│   ├── case.py                 案例编排：闭环与独立复核
│   └── report.py               模板渲染：数字只能来自 metrics.json
├── examples/
│   ├── newsvendor_inventory/   案例 A：库存随机优化族（9 条台账）
│   ├── facility_coverage/      案例 B：几何 / 全称断言族（7 条台账，自动抓到窄带陷阱）
│   ├── loan_approval_threshold/ 案例 C：统计量 / 全称断言 / 口径相关族（6 条台账，金融风控）
│   └── fishery_msy/            案例 D：生物 / 资源族（5 条台账，局部额外死亡带制造的窄带陷阱）
├── tests/                      44 项：把"防护真的会拦"当成测试来跑
└── docs/{methods.md,ledger.md,generalization.md}
```

### 一个案例 = 一个目录

```
charter.md          问题说明书（12 节，机器校验；卡点① 凭据）
solve.py            求解脚本，唯一数字出口 out/metrics.json
verify.py           ★ 验证钩子：把"可检查的对象"暴露给通用检查器
ledger.spec.json    结论清单（声明式：kind 结论类型 + checks 要跑的检查 + {{m.路径}} 引用数字）
report.template.md  报告模板（禁止手写数字）
falsify.template.md 证伪记录模板
expected.json       冻结数字（golden file），供 tsolve audit 回归
out/                脚本产出，不入库
```

## 现状与路线图

| 版本 | 内容 | 状态 |
|---|---|---|
| v0.1 | 骨架 + 三阶段 + 台账 + 一个案例跑通全闭环 + 独立复核 | **已完成** |
| v0.2 | **协议引擎化**（`checks.py`：七条可执行检查器）+ **结论类型→必跑协议矩阵** + 三个异构案例（库存 / 设施覆盖 / 信贷风控）+ 检查结论纳入 golden 回归 | **已完成**（44 项测试通过） |
| v0.3 | **LLM 编排层**（`tsolve agent`：读 charter.md + 阶段指令生成案例文件，再跑闭环）+ 第 4 个领域案例（生物 / 资源）+ 英文 README | **已完成**（53 项测试通过） |
| v0.4 | 报告/图表产出模块（高分辨率输出、禁用彩色文字、缺字形检测）+ 交付合规模式 | 计划中 |
| v0.5 | 技术文章 + 首个公开发布 | 计划中 |

**当前边界（自行判断能不能用）**：`prompts/` 的四个阶段指令现在**通过 `tsolve agent` 接上了 LLM 编排**——
LLM 读 `charter.md` 生成 `solve.py` / `verify.py` / `ledger.spec.json` / 模板 / `expected.json`，
但这些生成物**仍走和手写案例完全相同的引擎闭环**（卡点、七条协议、台账、数字对账、独立复核一个不少）。
所以分工是：**LLM 负责"把问题想成代码"，引擎负责"证明代码得出的结论没作弊"**。
它仍不保证 LLM 一定想得对——但凡 LLM 写出的结论，都会被七条协议独立验证、被 `audit` 逐数字对账；
想错了会被当场降级为 `refuted` 并留痕（见案例 B / C / D）。密钥只从环境变量读，代码里搜不到。

## 设计取舍（为什么这么"小"）

- **本地文件是唯一状态**：没有数据库、没有隐藏状态，`git diff` 就是全部变更历史。
- **案例即测试**：`expected.json` 冻结关键数字，prompt 或代码一改就报警，防止结论悄悄漂移。
- **每加一个功能先问"真的需要吗"**：不需要就删。这份仓库的价值在约束，不在功能数。

## 血缘

七条协议与台账设计的每一条判据都来自真实事故：粗步长整段跳过 2° 宽的违例带却输出"恒成立"、
连续上确界只比网格峰值大 0.15% 足以让结论反转、自建仿真的虚拟时间差点和正式测试数字填进同一张表……
把它们固化成机器可执行的检查，是这份仓库存在的理由。

## 许可

Apache-2.0（见 `LICENSE`，含专利授权，便于公司采用）。
