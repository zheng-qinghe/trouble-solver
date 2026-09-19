"""MCP server 的测试：证明"能被任何宿主雇进去"这句话是真的。

测的是**协议层**，不是"提示词写得好不好"：
  1. 握手（initialize）回正确的 protocolVersion / serverInfo / capabilities；
  2. tools/list 暴露 6 个工具，且每个都有可用的 inputSchema；
  3. tools/call 真能把活干完（在真实案例上跑 solve）；
  4. 出错要如实报错（未知工具 / 路径不存在 → isError=true），
     **绝不能让宿主误以为"检查通过了"**；
  5. 通知（无 id）不回应；未知方法回 -32601。

运行： PYTHONPATH=src python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "install", "mcp_stdio.py")
EXAMPLE = os.path.join(ROOT, "examples", "facility_coverage")


def talk(requests, timeout=180):
    """把一串 JSON-RPC 请求喂给 MCP server（stdio），返回按 id 索引的响应。"""
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    p = subprocess.run([sys.executable, LAUNCHER], input=payload,
                       capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise AssertionError("MCP server 退出码 %s，stderr=%s" % (p.returncode, p.stderr[:400]))
    out = {}
    raw = [l for l in p.stdout.splitlines() if l.strip()]
    for line in raw:
        d = json.loads(line)
        out[d.get("id")] = d
    return out, raw, p.stderr


class TestMCPServer(unittest.TestCase):
    def test_握手与工具清单(self):
        res, raw, err = talk([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},   # 通知不该有响应
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        self.assertEqual(err.strip(), "", "协议流里不该有 stderr 噪声")
        self.assertEqual(len(raw), 2, "通知不应产生响应（2 条请求带 id → 2 条响应）")

        init = res[1]["result"]
        self.assertEqual(init["protocolVersion"], "2024-11-05")
        self.assertEqual(init["serverInfo"]["name"], "troublesolver")
        self.assertIn("tools", init["capabilities"])

        tools = res[2]["result"]["tools"]
        names = [t["name"] for t in tools]
        self.assertEqual(sorted(names), sorted([
            "tsolve_charter_check", "tsolve_charter_new", "tsolve_solve",
            "tsolve_audit", "tsolve_ledger_show", "tsolve_ledger_check"]))
        for t in tools:
            self.assertTrue(t["description"], t["name"])
            self.assertEqual(t["inputSchema"]["type"], "object", t["name"])
            self.assertTrue(t["inputSchema"]["required"], t["name"])

    def test_未知方法回_32601(self):
        res, _, _ = talk([{"jsonrpc": "2.0", "id": 9, "method": "no/such/method"}])
        self.assertEqual(res[9]["error"]["code"], -32601)

    def test_未知工具与不存在的路径都要报错(self):
        res, _, _ = talk([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "no_such_tool", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "tsolve_charter_check",
                        "arguments": {"path": "/definitely/not/here.md"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "tsolve_ledger_check",
                        "arguments": {"ledger": "/definitely/not/here.json"}}},
        ])
        for rid in (1, 2, 3):
            self.assertTrue(res[rid]["result"]["isError"],
                            "id=%d 必须报错，否则宿主会误以为通过" % rid)

    def test_在真实案例上跑通solve与台账对账(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        case = os.path.join(td, "case")
        shutil.copytree(EXAMPLE, case)
        res, _, _ = talk([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "tsolve_charter_check",
                        "arguments": {"path": os.path.join(case, "charter.md")}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "tsolve_solve", "arguments": {"case_dir": case}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "tsolve_ledger_check",
                        "arguments": {"ledger": os.path.join(case, "ledger.json")}}},
        ], timeout=300)
        self.assertFalse(res[1]["result"]["isError"], res[1]["result"]["content"][0]["text"])
        self.assertIn("结论          : 通过", res[1]["result"]["content"][0]["text"])

        self.assertFalse(res[2]["result"]["isError"], res[2]["result"]["content"][0]["text"])
        self.assertIn("闭环通过", res[2]["result"]["content"][0]["text"])

        self.assertFalse(res[3]["result"]["isError"], res[3]["result"]["content"][0]["text"])
        self.assertIn("对账通过", res[3]["result"]["content"][0]["text"])


class TestHireScript(unittest.TestCase):
    """install/hire.sh 必须真的把 agent 卡与 MCP 配置投进目标项目，且可撤回。"""

    def test_雇进去再撤回(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        os.makedirs(os.path.join(td, ".claude"), exist_ok=True)      # 触发 Claude 级投递
        # 目标项目里已有一个别的 MCP server —— 必须被保留
        with open(os.path.join(td, ".mcp.json"), "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"other": {"command": "foo"}}}, f)

        hire = os.path.join(ROOT, "install", "hire.sh")
        r = subprocess.run(["bash", hire, td], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

        self.assertTrue(os.path.exists(os.path.join(td, ".agents", "troublesolver.md")))
        self.assertTrue(os.path.exists(os.path.join(td, ".claude", "agents", "troublesolver.md")))
        with open(os.path.join(td, ".mcp.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertIn("troublesolver", cfg["mcpServers"])
        self.assertIn("other", cfg["mcpServers"], "已有的 MCP 条目不能被弄丢")
        self.assertTrue(cfg["mcpServers"]["troublesolver"]["args"][0].endswith("mcp_stdio.py"))
        self.assertTrue(os.path.exists(os.path.join(td, ".mcp.json.bak")), "改动前应留备份")

        r = subprocess.run(["bash", hire, "--undo", td], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(td, ".agents", "troublesolver.md")))
        with open(os.path.join(td, ".mcp.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertNotIn("troublesolver", cfg["mcpServers"])
        self.assertIn("other", cfg["mcpServers"])

    def test_目标目录不存在时报错(self):
        hire = os.path.join(ROOT, "install", "hire.sh")
        r = subprocess.run(["bash", hire, "/definitely/not/here"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("目标目录不存在", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
