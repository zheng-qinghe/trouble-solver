# TroubleSolver · 数学建模验证专家

会自我证伪的数学建模助手：**先把问题问全，再科学建模，再主动搜自己的反例**；
每条结论都带证据与重算命令，交付数字零手写、逐条可复算。

> 上游开源仓库：<https://github.com/zheng-qinghe/trouble-solver>（Apache-2.0）
> 项目页：<https://zheng-qinghe.github.io/trouble-solver/>

## 类型

Agent 型（单个 AI 专家）

## 它解决的不是"怎么写出来"，而是"怎么知道它是对的"

所有"AI 建模"工具都在解决**生成**；这个专家解决的是它的对偶问题——**验证**。
所以它**不承诺"算得对"**，它承诺：你分得清哪一句话是真的。

**名字里的 *solver* 指的是「求解过程可被验证」，不是「自动解出答案」。**

## 功能

| 能力 | 说明 |
|---|---|
| **把问题问全（阶段 0，卡点①）** | 用 12 个维度逐项追问，产出**可机器校验**的《问题说明书》。`【未知】` 被当成资产（它决定模型要多稳健），且每个未知项必须有处理计划 |
| **基线与建模（卡点②）** | 基线必须**可被一条命令重算**；解析优先、数值兜底，**两条路径独立写** |
| **主动证伪（分水岭）** | 七条可执行协议：双路径交叉 / **对抗式最坏点审计** / 连续复核 / 极限与量纲 / 翻转边界 / 口径声明 / 台账对账。**"恒成立"类断言强制走对抗搜索**，粗网格与对抗搜索不一致即判**窄带陷阱** |
| **结论类型→必跑协议（引擎强制）** | 结论声明 `kind`（等式/极值/全称断言/最优性/稳健性/口径相关/极限…），该类型必跑的协议**少跑一条直接报错**，不许自称已验证 |
| **可追溯台账** | `new → verifying → verified / refuted / stale`；交付物只能引用 `verified`；**被证伪的条目连同反例保留**；上游一改，依赖它的结论自动作废 |
| **数字零手写** | 报告与证伪记录里只允许占位符，从 `out/metrics.json` 注入；**取不到值就构建失败** |
| **独立复核** | 在临时目录重跑，逐数字 / 逐检查结论 / 逐台账状态对账，任何漂移当场报出 |

### 内置引擎（不是只讲方法论）

本专家包里**真的带了可执行引擎**（纯标准库，零第三方依赖）：

- `bin/tsolve` —— 命令行：`charter check/new`、`solve`、`audit`、`ledger show/check`、`agent`
- `bin/tsolve-mcp` —— **MCP server（stdio）**，把 6 个能力暴露成工具，
  **任何宿主**（Cursor / Claude Code / 企业自研 Agent）都能直接调用
- `skills/troublesolver/` —— 引擎源码 + 四阶段指令 + 协议矩阵 + 案例契约 + 5 份模板 + **4 个真实案例**

## 使用示例

- 我有个业务问题想建模，先帮我把问题问全
- 这个结论恒成立吗？帮我主动搜反例
- 审查我这份建模报告的失效边界与口径

## 挂到别的宿主（MCP）

```json
{ "mcpServers": { "troublesolver": { "command": "/绝对路径/bin/tsolve-mcp" } } }
```

暴露的 6 个工具：`tsolve_charter_check`、`tsolve_charter_new`、`tsolve_solve`、
`tsolve_audit`、`tsolve_ledger_show`、`tsolve_ledger_check`。

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：
- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 安装

将专家包目录放到专家目录下：

```
/Users/yushuo/.workbuddy/plugins/marketplaces/my-experts/plugins/troublesolver/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```

## 打包分享

```bash
python3 scripts/package_expert.py <expert-dir>
# 或
zip -r troublesolver.zip troublesolver/
```

## 边界（不要越界期待）

- **不写竞赛论文**（与学术诚信冲突）；交付的是业务解答包，不是参赛作品。
- **不替你拍口径**：两套口径并列报出，拍板是用户的活。
- **搜索不保证穷尽**：有限预算的对抗搜索无法保证找到任意窄的特征，
  所以每次都把**搜索分辨率**一起报出来 —— "未找到" ≠ "不存在"。
- **不做多智能体角色扮演**：它就是它自己，同一个助手自己搜自己的反例。
