#!/usr/bin/env bash
# 把 TroubleSolver "雇"进一个项目：投递《岗位说明书》+ 接好 MCP 工具。
#
#   bash install/hire.sh [目标项目目录]     # 默认当前目录
#   bash install/hire.sh --undo [目录]      # 撤回（删掉投递的文件、从 .mcp.json 摘掉这一项）
#
# 它做三件事（都可逆）：
#   1) 把 agents/troublesolver.md 投到 <项目>/.agents/troublesolver.md（宿主可读的岗位说明书）
#   2) 若存在 .claude/ 目录，额外复制一份到 .claude/agents/（Claude Code 的项目级 subagent）
#   3) 在 <项目>/.mcp.json 里登记 troublesolver MCP server（保留已有条目；先备份原文件）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # 仓库根
PY="${TSOLVE_PYTHON:-python3}"
UNDO=0
if [ "${1:-}" = "--undo" ]; then UNDO=1; shift; fi
TARGET="${1:-$(pwd)}"

if [ ! -d "$TARGET" ]; then
  echo "目标目录不存在：$TARGET" >&2
  exit 2
fi
TARGET="$(cd "$TARGET" && pwd)"

"$PY" - "$HERE" "$TARGET" "$UNDO" <<'PY'
import json, os, shutil, sys

repo, target, undo = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
card_src = os.path.join(repo, "agents", "troublesolver.md")
launcher = os.path.join(repo, "install", "mcp_stdio.py")

agents_dir = os.path.join(target, ".agents")
card_dst = os.path.join(agents_dir, "troublesolver.md")
claude_dir = os.path.join(target, ".claude")
claude_dst = os.path.join(claude_dir, "agents", "troublesolver.md")
mcp_path = os.path.join(target, ".mcp.json")
KEY = "troublesolver"

def load_mcp():
    if os.path.exists(mcp_path):
        with open(mcp_path, encoding="utf-8") as f:
            return json.load(f)
    return {}

if undo:
    removed = []
    for p in (card_dst, claude_dst):
        if os.path.exists(p):
            os.remove(p); removed.append(os.path.relpath(p, target))
    cfg = load_mcp()
    if KEY in (cfg.get("mcpServers") or {}):
        del cfg["mcpServers"][KEY]
        if os.path.exists(mcp_path):
            shutil.copy2(mcp_path, mcp_path + ".bak")
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        removed.append(".mcp.json 中的 %s" % KEY)
    print("已撤回：%s" % ("、".join(removed) if removed else "（本就没装）"))
    raise SystemExit(0)

if not os.path.exists(card_src):
    print("找不到岗位说明书：%s" % card_src, file=sys.stderr)
    raise SystemExit(2)

os.makedirs(agents_dir, exist_ok=True)
shutil.copy2(card_src, card_dst)
print("✔ 岗位说明书  -> %s" % os.path.relpath(card_dst, target))

if os.path.isdir(claude_dir):
    os.makedirs(os.path.dirname(claude_dst), exist_ok=True)
    shutil.copy2(card_src, claude_dst)
    print("✔ Claude 级  -> %s" % os.path.relpath(claude_dst, target))

cfg = load_mcp()
cfg.setdefault("mcpServers", {})
server = {"command": "python3", "args": [launcher]}
if cfg["mcpServers"].get(KEY) == server:
    print("= MCP 已登记（未改动）")
else:
    if os.path.exists(mcp_path):
        shutil.copy2(mcp_path, mcp_path + ".bak")
    cfg["mcpServers"][KEY] = server
    with open(mcp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("✔ MCP 工具   -> %s（%s）" % (os.path.relpath(mcp_path, target), KEY))

print("\n它现在能干的 6 件事：tsolve_charter_check / tsolve_charter_new / tsolve_solve /"
      "\ntsolve_audit / tsolve_ledger_show / tsolve_ledger_check")
print("宿主重启后生效；撤回用：bash install/hire.sh --undo %s" % target)
PY
