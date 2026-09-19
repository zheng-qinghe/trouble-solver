#!/usr/bin/env python3
"""TroubleSolver MCP server 入口（专家包内置版）。引擎在同一目录的 troublesolver/ 下。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from troublesolver.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
