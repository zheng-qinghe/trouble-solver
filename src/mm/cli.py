"""mm —— 会自我证伪的建模助手（MVP 骨架 v0.1）。

命令：
    mm charter new  <charter.md>     生成《问题说明书》空白模板
    mm charter check <charter.md>    校验"问题是否问全"（卡点①）
    mm ledger show  <ledger.json>    查看台账
    mm ledger check <ledger.json>    交付前对账（P7）
    mm solve <case_dir>              跑通闭环：形式化 → 基线 → 建模 → 证伪 → 台账 → 交付
    mm audit <case_dir>              阶段 6 复核：临时目录独立重跑 + 逐数字对账
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mm import charter as ch          # noqa: E402
from mm.case import Case              # noqa: E402
from mm.ledger import Ledger          # noqa: E402


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


def main(argv=None):
    p = argparse.ArgumentParser(prog="mm", description="会自我证伪的建模助手")
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

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
