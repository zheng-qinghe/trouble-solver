# packaging/ —— 把 TroubleSolver 打包成"可任职"的形态

> **仓库是唯一真源，专家包是产物。** 引擎（`src/`）、四阶段指令（`prompts/`）、
> 真实案例（`examples/`）都在**构建时拷贝**，所以仓库一改，重跑构建脚本就同步了 ——
> **不存在"两份拷贝互相漂移"**。（这正是最容易出事的地方：改了仓库、忘了同步包。）

```
packaging/
├── expert/                         WorkBuddy 专家包的定义源（人手维护，进 git）
│   ├── plugin.json                 专家卡片（职业/分类/标签/推荐问法）
│   ├── README.md                   专家包里那份 README
│   ├── agents/troublesolver.md     WorkBuddy 版角色卡（含 frontmatter）
│   ├── avatars/expert.png          头像（512×512 PNG）
│   ├── bin/{tsolve,tsolve-mcp}     包内可执行入口
│   └── skills/troublesolver/
│       ├── SKILL.md                内置技能说明
│       ├── references/             协议矩阵 · 案例契约 · 12 维度问法
│       └── scripts/{tsolve,tsolve_mcp}.py   内置引擎入口（薄壳）
└── make_expert_package.sh          构建脚本：拼装 + 校验 + 注册
```

## 构建

```bash
bash packaging/make_expert_package.sh                 # 装到 WorkBuddy 专家目录（默认）
bash packaging/make_expert_package.sh /tmp/out/troublesolver   # 或任意目录
```

它会：拷贝定义源 → 从 `src/` 拷引擎 → 从 `prompts/` 拷阶段指令 → 从 `examples/` 拷案例
→ 清 `__pycache__` → 调 `validate_expert.py` 校验 → 调 `register_expert.py` 注册。

## 两种"任职"形态的关系

| 形态 | 面向谁 | 入口 | 定义在哪 |
|---|---|---|---|
| **MCP server** | **任何**支持 MCP 的宿主（Claude Code / Cursor / 企业自研 Agent / WorkBuddy） | `install/mcp_stdio.py`（免装）或 `tsolve-mcp`（装后） | `src/troublesolver/mcp_server.py` |
| **WorkBuddy 专家卡** | WorkBuddy 的专家中心 | 专家目录里的 `plugin.json` | `packaging/expert/` |

**MCP 是主形态**（跨宿主才叫"任何企业或个人项目"）；专家卡是 WorkBuddy 内的一个增量包装 ——
它同样是**从同一份仓库代码构建出来的**，不是另写一套。

## 铁律

- **不要手改产物**（WorkBuddy 专家目录里的那份）。要改就改 `packaging/expert/` 或仓库源码，然后重跑构建。
- **不可修改** `plugin.json` 的 `name`、`agentName`、专家目录名、`agents/*.md` 文件名
  —— 它们是唯一标识，改了专家就"丢了"；要改名只能重建。
- 加了新案例 / 改了引擎后，**记得重跑构建**（`tsolve` 的版本与 `examples/` 会一起更新）。
