"""TroubleSolver —— 会自我证伪的建模助手（v0.2）。

命令：
    tsolve charter new  <charter.md>     生成《问题说明书》空白模板
    tsolve charter check <charter.md>    校验"问题是否问全"（卡点①）
    tsolve ledger show  <ledger.json>    查看台账
    tsolve ledger check <ledger.json>    交付前对账（P7）
    tsolve solve <case_dir>              跑通闭环：形式化 → 基线 → 建模 → 证伪 → 台账 → 交付
    tsolve audit <case_dir>              阶段 6 复核：临时目录独立重跑 + 逐数字对账
    tsolve agent <case_dir>              读 charter.md + 阶段指令，让 LLM 生成案例文件，再跑闭环
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from troublesolver import charter as ch          # noqa: E402
from troublesolver.case import Case              # noqa: E402
from troublesolver.ledger import Ledger          # noqa: E402
from troublesolver import orchestrate as orch     # noqa: E402


def _cmd_charter_new(a):
    if os.path.exists(a.path):
        print("已存在，不覆盖：%s" % a.path)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.path)), exist_ok=True)
    with open(a.path, "w", encoding="utf-8") as f:
        f.write(ch.blank_template())
    print("已生成模板：%s" % a.path)
    return 0


def _cmd_charter_check(a):
    rep = ch.check(a.path)
    print(rep.render())
    return 0 if rep.ok else 2


def _cmd_ledger_show(a):
    led = Ledger(a.path)
    print("台账：%s（共 %d 条）" % (a.path, len(led.entries)))
    print("状态分布：%s" % json.dumps(led.summary(), ensure_ascii=False))
    for e in led.entries:
        print("  [%-9s] %-10s %s" % (e["status"], e["id"], e["claim"][:64]))
    return 0


def _cmd_ledger_check(a):
    led = Ledger(a.path)
    problems = led.check()
    if problems:
        print("对账未通过（%d 项）：" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 2
    print("对账通过：%d 条台账，状态分布 %s"
          % (len(led.entries), json.dumps(led.summary(), ensure_ascii=False)))
    return 0


def _cmd_solve(a):
    rc, _, _ = Case(a.case).solve(echo=not a.quiet)
    return rc


def _cmd_audit(a):
    rc, _, _ = Case(a.case).audit(echo=not a.quiet)
    return rc


def _cmd_agent(a):
    """把 prompts/ 阶段指令接上 LLM：生成案例文件，再由引擎跑闭环 + 复核。

    不硬编码密钥：缺 key 时 ConfigLLMClient 直接报错。--mock 走零网络零密钥的 MockClient，
    用于离线演示 / CI 覆盖编排层（证明"生成→solve→audit"不依赖活 key）。
    """
    if a.dry_run:
        system, user = orch.assemble_model_prompt(a.case)
        print("===== SYSTEM =====\n%s\n\n===== USER =====\n%s" % (system, user))
        return 0
    if a.mock:
        client = orch.MockClient()
    else:
        try:
            client = orch.ConfigLLMClient(api_key=a.api_key,
                                           base_url=a.base_url, model=a.model)
        except ValueError as exc:
            print("配置错误：%s" % exc, file=sys.stderr)
            return 2
    rc, written = orch.run_agent(a.case, client, echo=not a.quiet, run_audit=not a.no_audit)
    return rc


def main(argv=None):
    p = argparse.ArgumentParser(prog="tsolve", description="会自我证伪的建模助手")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("charter", help="问题说明书：引导提问与完整性校验（卡点①）")
    cs = c.add_subparsers(dest="sub", required=True)
    s = cs.add_parser("new"); s.add_argument("path"); s.set_defaults(fn=_cmd_charter_new)
    s = cs.add_parser("check"); s.add_argument("path"); s.set_defaults(fn=_cmd_charter_check)

    l = sub.add_parser("ledger", help="可追溯台账")
    ls = l.add_subparsers(dest="sub", required=True)
    s = ls.add_parser("show"); s.add_argument("path"); s.set_defaults(fn=_cmd_ledger_show)
    s = ls.add_parser("check"); s.add_argument("path"); s.set_defaults(fn=_cmd_ledger_check)

    s = sub.add_parser("solve", help="跑通一个案例的完整闭环")
    s.add_argument("case"); s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(fn=_cmd_solve)

    s = sub.add_parser("audit", help="独立重跑 + 逐数字对账")
    s.add_argument("case"); s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(fn=_cmd_audit)

    ag = sub.add_parser("agent", help="LLM 编排：读 charter.md + 阶段指令，生成案例文件，再跑闭环")
    ag.add_argument("case", help="案例目录（需已有通过校验的 charter.md）")
    ag.add_argument("--mock", action="store_true", help="用零网络零密钥的 MockClient（离线/CI）")
    ag.add_argument("--api-key", default=None, help="LLM 密钥（默认读 $TSOLVE_LLM_API_KEY，不要硬编码）")
    ag.add_argument("--base-url", default=None, help="兼容端点（默认 $TSOLVE_LLM_BASE_URL 或 OpenAI）")
    ag.add_argument("--model", default=None, help="模型名（默认 $TSOLVE_LLM_MODEL 或 gpt-4o-mini）")
    ag.add_argument("--dry-run", action="store_true", help="只打印拼好的 system/user 提示，不调用")
    ag.add_argument("--no-audit", action="store_true", help="生成并 solve 后不跑独立复核")
    ag.add_argument("-q", "--quiet", action="store_true")
    ag.set_defaults(fn=_cmd_agent)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
