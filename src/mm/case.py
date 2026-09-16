"""案例目录编排：`mm solve`（跑通闭环）与 `mm audit`（独立重跑对账）。

一个「案例」= 一个可复现的建模问题，目录约定：

    charter.md            问题说明书（阶段 0 产物；卡点① 由人确认）
    solve.py              求解脚本：唯一数字出口 out/metrics.json（P7）
    ledger.spec.json      结论清单（声明式）：id/claim/method/protocols/caliber/…
    report.template.md    报告模板（数字一律写 {{m.路径}} 占位符）
    falsify.template.md   证伪记录模板（同上，可选）
    expected.json         冻结的关键数字 + 台账状态，供 `mm audit` 回归比对
    out/                  脚本产出，不入库

工具不做的事：不替你想模型，不替你写数字。它只做两件事——
**卡住不该往下走的（两个人工卡点）**，以及**把结论钉在脚本上（台账 + 占位符）**。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

from mm import charter as ch
from mm import report as rp
from mm.ledger import Ledger

REQUIRED = ("charter.md", "solve.py", "ledger.spec.json", "report.template.md")


def _cmp(a, b, rtol: float, atol: float = 1e-9) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= atol + rtol * abs(b)
    return a == b


class Case:
    def __init__(self, path: str):
        self.dir = os.path.abspath(path)
        self.ledger_path = self.p("ledger.json")
        self.metrics_path = self.p("out", "metrics.json")

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    # ---------------- 基础 ----------------
    def missing(self):
        return [f for f in REQUIRED if not os.path.exists(self.p(f))]

    def run_solver(self, cwd=None) -> str:
        cwd = cwd or self.dir
        r = subprocess.run([sys.executable, "solve.py"], cwd=cwd,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("solve.py 失败（退出码 %d）：\n%s"
                               % (r.returncode, (r.stderr or r.stdout)[-2000:]))
        return r.stdout

    def load_metrics(self, cwd=None) -> dict:
        cwd = cwd or self.dir
        with open(os.path.join(cwd, "out", "metrics.json"), encoding="utf-8") as f:
            return json.load(f)

    # ---------------- 台账 ----------------
    def build_ledger(self, metrics: dict):
        """由 ledger.spec.json 生成 ledger.json；claim 文本里的占位符此时就被钉死成真实数字。"""
        with open(self.p("ledger.spec.json"), encoding="utf-8") as f:
            spec = json.load(f)
        led = Ledger(self.ledger_path)
        led.entries = []
        ctx = {"m": metrics, "ledger": {}}
        problems = []
        for c in spec["claims"]:
            claim = rp.render_obj(c["claim"], ctx, problems, c["id"])
            led.add(c["id"], claim,
                    method=rp.render_obj(c.get("method", ""), ctx, problems, c["id"]),
                    protocols=c.get("protocols"),
                    caliber=rp.render_obj(c.get("caliber"), ctx, problems, c["id"]),
                    evidence=c.get("evidence"),
                    recompute=c.get("recompute", ""),
                    notes=rp.render_obj(c.get("notes", ""), ctx, problems, c["id"]),
                    depends_on=c.get("depends_on"))
            st = c.get("status", "new")
            if st != "new":
                led.set_status(c["id"], st, notes=c.get("status_note"))
        led.save()
        return led, problems

    def check_evidence(self, led: Ledger):
        problems = []
        for e in led.entries:
            for ev in e["evidence"]:
                if not os.path.exists(self.p(ev)):
                    problems.append("%s 的证据文件不存在：%s" % (e["id"], ev))
        return problems

    # ---------------- 阶段 0~5：跑通闭环 ----------------
    def solve(self, echo=True):
        log = []

        def say(s):
            log.append(s)
            if echo:
                print(s)

        miss = self.missing()
        if miss:
            return 2, log, ["案例目录缺少：%s" % "、".join(miss)]

        # 卡点① 口径确认：问题说明书不完整 = 后面全白做
        rep = ch.check(self.p("charter.md"))
        say("【阶段 0 形式化】问题说明书：%s" % ("通过" if rep.ok else "未通过"))
        if not rep.ok:
            say(rep.render())
            return 2, log, ["卡点① 未通过：问题说明书不完整，禁止进入建模"]

        # 卡点② 基线可复现：算得出来才算数
        try:
            self.run_solver()
        except RuntimeError as exc:
            say(str(exc))
            return 2, log, [str(exc)]
        metrics = self.load_metrics()
        if "baseline" not in metrics:
            return 2, log, ["卡点② 未通过：metrics.json 没有 baseline 段（基线必须可复现）"]
        b = metrics["baseline"]
        say("【阶段 1-2 基线与建模】求解脚本已运行，数字出口 out/metrics.json")
        say("  基线 Q0=%s 件，周期望利润=%.2f 元（键 baseline）"
            % (b.get("Q"), b.get("profit_caliberB", float("nan"))))

        # 阶段 3-5：台账 + 交付
        led, problems = self.build_ledger(metrics)
        say("【阶段 3-5 证伪与交付】台账 %d 条，状态分布 %s"
            % (len(led.entries), json.dumps(led.summary(), ensure_ascii=False)))

        ctx = rp.build_context(metrics, led.entries)
        for tpl, out_name in (("report.template.md", "report.md"),
                              ("falsify.template.md", "falsify.md")):
            if not os.path.exists(self.p(tpl)):
                continue
            try:
                rp.render_file(self.p(tpl), self.p(out_name), ctx)
                say("  已生成 %s" % out_name)
            except rp.RenderError as exc:
                problems.append(str(exc))

        # 交付物都落地之后再对账（台账的证据可能就指向报告本身）
        problems += self.check_evidence(led)
        problems += led.check()

        if problems:
            say("对账未通过（%d 项）：" % len(problems))
            for x in problems:
                say("  - %s" % x)
            return 2, log, problems
        say("闭环通过：报告/证伪记录里的每个数字都来自 out/metrics.json（P7）")
        return 0, log, []

    # ---------------- 阶段 6：独立复核 ----------------
    def audit(self, echo=True):
        log = []

        def say(s):
            log.append(s)
            if echo:
                print(s)

        problems = []
        exp_path = self.p("expected.json")
        if not os.path.exists(exp_path):
            return 2, log, ["缺少 expected.json：无法做数字回归对账"]
        with open(exp_path, encoding="utf-8") as f:
            expected = json.load(f)
        rtol = float(expected.get("tolerance", {}).get("default", 1e-9))
        tol_map = expected.get("tolerance", {})

        # 1) 复制到临时目录独立重跑——不污染案例目录，也防止"读了上次的产物"
        try:
            with tempfile.TemporaryDirectory() as td:
                work = os.path.join(td, "case")
                shutil.copytree(self.dir, work,
                                ignore=shutil.ignore_patterns("out", "__pycache__", "*.pyc"))
                self.run_solver(cwd=work)
                fresh = self.load_metrics(cwd=work)
        except RuntimeError as exc:
            return 2, log, ["独立重跑失败：%s" % exc]
        say("【阶段 6 复核】已在临时目录独立重跑 solve.py")

        # 2) 逐数字对账
        n_cmp = 0
        for path, want in expected.get("metrics", {}).items():
            try:
                got = rp.lookup({"m": fresh}, "m." + path)
            except KeyError:
                problems.append("expected.json 里的 %s 在新一轮 metrics.json 中不存在" % path)
                continue
            n_cmp += 1
            if not _cmp(got, want, float(tol_map.get(path, rtol))):
                problems.append("数字漂移：%s 期望 %r，实测 %r（容差 %g）"
                                % (path, want, got, tol_map.get(path, rtol)))
        say("  逐数字对账 %d 项" % n_cmp)

        # 3) 引用完整性：报告只能引用 verified；成品里不许剩占位符
        if not os.path.exists(self.ledger_path):
            problems.append("ledger.json 不存在：先跑 mm solve")
        else:
            led = Ledger(self.ledger_path)
            problems += led.check()
            for e in led.entries:
                for ev in e["evidence"]:
                    if not os.path.exists(self.p(ev)):
                        problems.append("%s 的证据文件不存在：%s" % (e["id"], ev))
            for cid, st in expected.get("ledger_status", {}).items():
                e = led.get(cid)
                if e is None:
                    problems.append("expected.json 声明了不存在的台账条目 %s" % cid)
                elif e["status"] != st:
                    problems.append("台账状态变了：%s 期望 %s，实际 %s" % (cid, st, e["status"]))
            say("  台账 %d 条，状态分布 %s"
                % (len(led.entries), json.dumps(led.summary(), ensure_ascii=False)))

        for name in ("report.md", "falsify.md", "ledger.json"):
            k = rp.unresolved_markers(self.p(name))
            if k:
                problems.append("%s 里还剩 %d 个未解析占位符（数字没钉到脚本上）" % (name, k))

        if problems:
            say("复核未通过（%d 项）：" % len(problems))
            for x in problems:
                say("  - %s" % x)
            return 2, log, problems
        say("复核通过：数字可复算、结论状态未漂移")
        return 0, log, []
