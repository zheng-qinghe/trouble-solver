# 把 TroubleSolver 雇进你的项目

> "任职"不是一句自我介绍，而是**两样能落地的东西**：
> 一份**岗位说明书**（宿主读得懂的 agent 角色卡）+ 一个**可被调用的工具端点**（MCP server）。
> 两者都在本仓库里，**任何人 clone 下来就能雇**。

## 方式 A：一键雇进一个项目（推荐）

```bash
git clone <repo> trouble-solver
bash trouble-solver/install/hire.sh /path/to/your-project
```

它会（三步都可逆）：

1. 投递岗位说明书 → `<项目>/.agents/troublesolver.md`
2. 若项目里有 `.claude/`，额外复制到 `.claude/agents/`（Claude Code 的项目级 subagent）
3. 在 `<项目>/.mcp.json` 里登记 `troublesolver` MCP server（**保留已有条目**，改动前先备份为 `.bak`）

撤回：`bash install/hire.sh --undo /path/to/your-project`

## 方式 B：装成命令（全局可用）

```bash
pip install -e /path/to/trouble-solver
tsolve          # 命令行
tsolve-mcp      # MCP server（stdio）
```

装完后任何宿主的配置只要写 `"command": "tsolve-mcp"` 即可。

## 方式 C：手动接入各宿主（不装包也行）

**通用 MCP JSON**（放到宿主的 MCP 配置里，路径换成你的实际位置）：

```json
{
  "mcpServers": {
    "troublesolver": {
      "command": "python3",
      "args": ["/abs/path/to/trouble-solver/install/mcp_stdio.py"]
    }
  }
}
```

| 宿主 | 接法 |
|---|---|
| **Claude Code** | `claude mcp add troublesolver -- python3 /abs/path/install/mcp_stdio.py`；项目级 agent 卡放 `.claude/agents/troublesolver.md` |
| **Cursor** | MCP 配置（`~/.cursor/mcp.json` 或项目级）里加上面那段 JSON |
| **WorkBuddy** | 连接器管理页 →「自定义连接器」→ 指向 `install/mcp_stdio.py`，然后点 **Trust** |
| **企业自研 / 自建编排** | 任何支持 MCP 的客户端按上面 JSON 拉起即可；也可直接 `subprocess` 调 `tsolve` CLI |

## 它会成为你团队里的什么角色

**一个"不会替你吹牛"的建模与验证岗。** 它交付的不是一段结论，而是：

- 一份**可机器校验**的《问题说明书》（把问题问全，卡点①）
- 一个**能一键复现**的求解脚本与基线（卡点②）
- 一张**可追溯台账**：每条结论带状态、证据、重算命令
- 一份**主动写清失效边界**的报告 —— 它会去搜自己的反例

## 6 个工具

| 工具 | 干什么 |
|---|---|
| `tsolve_charter_check` | 卡点①：问题说明书写全了吗（12 节 / 口径表 / 未知项处理计划 / 用户确认） |
| `tsolve_charter_new` | 生成《问题说明书》空白模板 |
| `tsolve_solve` | 跑通闭环：形式化 → 基线 → 建模 → 证伪 → 台账 → 交付 |
| `tsolve_audit` | 阶段 6 独立复核：临时目录重跑 + 逐数字 / 逐检查对账 |
| `tsolve_ledger_show` | 查看台账（状态分布 + 每条结论摘要） |
| `tsolve_ledger_check` | 交付前台账对账（P7） |

**返回约定**：工具返回的文本末尾带 `(exit code: N)`；`N != 0` 时 `isError = true`。
也就是说 —— **宿主能直接判断它这次干活是否通过**，不需要人肉读日志。

## 为什么这不是"又一个提示词"

| 只给提示词 | 本项目给你的 |
|---|---|
| 角色写在文档里，靠模型自觉 | 角色有**机器校验的凭据**：`charter.md` 12 节 + 口径表 + 未知项处理计划，不过就不许往下走 |
| 结论对不对看模型心情 | 结论类型**强制**跑齐对应协议（少一条直接报错），且**主动搜自己的反例** |
| 报告数字随手写 | 报告里只允许占位符，从 `out/metrics.json` 注入；**取不到值就构建失败** |
| 换个机器就复现不了 | `tsolve audit` 在临时目录重跑，逐数字对账，漂移当场报出 |
