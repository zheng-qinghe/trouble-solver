"""TroubleSolver MCP server —— 让它能被**任何宿主**"雇"进去。

这是"任职"的关键一层：不是提示词，而是一个**可被任何 Agent 宿主调用的工具端点**。
Claude Code / Cursor / 企业自研 Agent / 自建编排，只要支持 MCP，就能把 TroubleSolver
当成自己的一个"员工"来用——它不聊天，它**干活并留下可核对的证据**。

用法（装好后）：

    pip install -e .
    tsolve-mcp                      # stdio 传输，供宿主拉起

宿主配置（任选）：

    # Claude Code
    claude mcp add troublesolver -- tsolve-mcp

    # Cursor / 通用 MCP JSON
    { "mcpServers": { "troublesolver": { "command": "tsolve-mcp" } } }

    # 不装包也能用：指向仓库里的启动脚本
    { "mcpServers": { "troublesolver": { "command": "python3",
      "args": ["/abs/path/to/trouble-solver/install/mcp_stdio.py"] } } }

暴露 6 个工具：
    tsolve_charter_check / tsolve_charter_new / tsolve_solve /
    tsolve_audit / tsolve_ledger_show / tsolve_ledger_check

协议：MCP over stdio，换行分隔的 JSON-RPC 2.0（零第三方依赖）。
⚠️ stdout 是协议通道 —— 所有诊断只写 stderr；引擎一律用 echo=False 调用。
"""
from __future__ import annotations

import json
import os
import sys

from . import charter as ch
from .case import Case
from .ledger import Ledger

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "troublesolver", "version": "1.0.0"}

TOOLS = [
    {
        "name": "tsolve_charter_check",
        "description": "卡点①：校验《问题说明书》charter.md 是否问全"
                       "（12 节齐全、口径表填满、每个【未知】都有处理计划、用户已确认）。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "charter.md 的路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "tsolve_charter_new",
        "description": "生成《问题说明书》空白模板（12 节骨架 + 口径表）。已存在则不覆盖。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "要生成到的路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "tsolve_solve",
        "description": "跑通一个案例的完整闭环：卡点校验 → 运行 solve.py → 自动执行必跑协议 →"
                       "建台账 → 渲染 report.md / falsify.md。返回 0 才说明闭环通过。",
        "inputSchema": {
            "type": "object",
            "properties": {"case_dir": {"type": "string", "description": "案例目录"}},
            "required": ["case_dir"],
        },
    },
    {
        "name": "tsolve_audit",
        "description": "阶段 6 独立复核：在临时目录重跑 solve.py 与全部检查，逐数字、逐检查结论、"
                       "逐台账状态对账（需要 expected.json）。任何漂移都会被报出来。",
        "inputSchema": {
            "type": "object",
            "properties": {"case_dir": {"type": "string", "description": "案例目录"}},
            "required": ["case_dir"],
        },
    },
    {
        "name": "tsolve_ledger_show",
        "description": "查看台账：条目状态分布，以及每条结论的 id / 状态 / 结论摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {"ledger": {"type": "string", "description": "ledger.json 的路径"}},
            "required": ["ledger"],
        },
    },
    {
        "name": "tsolve_ledger_check",
        "description": "交付前台账对账（P7）：每条结论是否有证据、有重算命令、口径是否齐备、"
                       "是否引用了已证伪/已作废的条目。",
        "inputSchema": {
            "type": "object",
            "properties": {"ledger": {"type": "string", "description": "ledger.json 的路径"}},
            "required": ["ledger"],
        },
    },
]


def _require(path, what):
    """工具面必须对"路径不存在"报错——不能让宿主误以为检查通过了。"""
    if not os.path.exists(path):
        raise FileNotFoundError("%s 不存在：%s" % (what, path))
    return path


def _charter_check(a):
    rep = ch.check(_require(a["path"], "charter.md"))
    return 0 if rep.ok else 2, rep.render()


def _charter_new(a):
    path = a["path"]
    if os.path.exists(path):
        return 1, "已存在，不覆盖：%s" % path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(ch.blank_template())
    return 0, "已生成模板：%s" % path


def _solve(a):
    rc, log, problems = Case(_require(a["case_dir"], "案例目录")).solve(echo=False)
    body = "\n".join(log)
    if problems:
        body += "\n未通过（%d 项）：\n" % len(problems) + "\n".join("  - %s" % p for p in problems)
    return rc, body


def _audit(a):
    rc, log, problems = Case(_require(a["case_dir"], "案例目录")).audit(echo=False)
    body = "\n".join(log)
    if problems:
        body += "\n未通过（%d 项）：\n" % len(problems) + "\n".join("  - %s" % p for p in problems)
    return rc, body


def _ledger_show(a):
    led = Ledger(_require(a["ledger"], "ledger.json"))
    lines = ["台账：%s（共 %d 条）" % (a["ledger"], len(led.entries)),
             "状态分布：%s" % json.dumps(led.summary(), ensure_ascii=False)]
    for e in led.entries:
        lines.append("  [%-9s] %-10s %s" % (e["status"], e["id"], e["claim"][:72]))
    return 0, "\n".join(lines)


def _ledger_check(a):
    led = Ledger(_require(a["ledger"], "ledger.json"))
    problems = led.check()
    if problems:
        return 2, ("对账未通过（%d 项）：\n" % len(problems)
                   + "\n".join("  - %s" % p for p in problems))
    return 0, ("对账通过：%d 条台账，状态分布 %s"
               % (len(led.entries), json.dumps(led.summary(), ensure_ascii=False)))


HANDLERS = {
    "tsolve_charter_check": _charter_check,
    "tsolve_charter_new": _charter_new,
    "tsolve_solve": _solve,
    "tsolve_audit": _audit,
    "tsolve_ledger_show": _ledger_show,
    "tsolve_ledger_check": _ledger_check,
}


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(rid, payload):
    _send({"jsonrpc": "2.0", "id": rid, "result": payload})


def _error(rid, code, message):
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def handle(req):
    """处理一条 JSON-RPC 请求（通知则只执行、不回应）。可单独导入用于测试。"""
    rid = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}

    if method == "initialize":
        _result(rid, {"protocolVersion": PROTOCOL_VERSION,
                      "capabilities": {"tools": {}},
                      "serverInfo": SERVER_INFO})
    elif method in ("notifications/initialized", "initialized"):
        pass                                        # 通知，无需响应
    elif method == "tools/list":
        _result(rid, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            _result(rid, {"content": [{"type": "text", "text": "未知工具：%s" % name}],
                          "isError": True})
            return
        try:
            rc, text = fn(args)
        except Exception as exc:                    # noqa: BLE001
            _result(rid, {"content": [{"type": "text",
                                       "text": "%s: %s" % (type(exc).__name__, exc)}],
                          "isError": True})
            return
        _result(rid, {"content": [{"type": "text",
                                   "text": "%s\n(exit code: %d)" % (text, rc)}],
                      "isError": rc != 0})
    elif method == "ping":
        _result(rid, {})
    else:
        if rid is not None:
            _error(rid, -32601, "Method not found: %s" % method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            print("bad json: %s" % exc, file=sys.stderr)
            continue
        if isinstance(req, list):                   # 批量请求
            for r in req:
                handle(r)
        else:
            handle(req)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
