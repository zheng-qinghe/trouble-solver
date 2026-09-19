#!/usr/bin/env python3
"""免安装启动器：直接把仓库里的 TroubleSolver MCP server 跑起来。

不想 `pip install` 也行 —— 让宿主指向本文件即可：

    {
      "mcpServers": {
        "troublesolver": {
          "command": "python3",
          "args": ["/abs/path/to/trouble-solver/install/mcp_stdio.py"]
        }
      }
    }

（`bash install/hire.sh <你的项目>` 会自动把这段配置写进目标项目。）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from troublesolver.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
