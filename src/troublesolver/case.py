"""案例目录编排：`tsolve solve`（跑通闭环）与 `tsolve audit`（独立重跑对账）。

一个「案例」= 一个可复现的建模问题，目录约定：

    charter.md            问题说明书（阶段 0 产物；卡点① 由人确认）
    solve.py              求解脚本：唯一数字出口 out/metrics.json（P7）
    verify.py             ★ 验证钩子：把"可检查的对象"暴露给检查器引擎
    ledger.spec.json      结论清单（声明式）：id / kind / claim / checks / caliber / …
    report.template.md    报告模板（数字一律写 {{m.路径}} 占位符）
    falsify.template.md   证伪记录模板（同上，可选）
    expected.json         冻结的关键数字 + 台账状态 + 检查结论，供 `tsolve audit` 回归比对
    out/                  脚本产出（metrics.json / checks.json），不入库

## 泛化怎么体现（本模块最重要的一件事）

`ledger.spec.json` 里每条结论必须声明 **`kind`（结论类型）**，并给出 **`checks`（要跑的检查）**。
引擎据此做两件事：

1. **按声明真跑**：从 `verify.py` 取钩子函数，交给 `troublesolver.checks` 里的通用检查器执行；
   台账里的 `protocols` **由"实际跑过且通过"决定，不许自填**；
2. **强制完备**：`kind` → 必跑协议（见 `troublesolver.checks.REQUIRED_BY_KIND`）没跑全，直接报错——
   **不许一条"全称断言"只跑 P1 就自称已验证**。

于是加一个新领域的难题，只需：写 `solve.py` + 写 `verify.py` 钩子 + 声明 `kind`/`checks`。
**引擎不需要认识这个领域，一行也不用改。**
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

from troublesolver import charter as ch
from troublesolver import checks as ck
from troublesolver import report as rp
from troublesolver.ledger import Ledger

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

    def load_spec(self) -> dict:
        with open(self.p("ledger.spec.json"), encoding="utf-8") as f:
            return json.load(f)

    # ---------------- 验证钩子 ----------------
    def load_hooks(self) -> dict:
        """加载案例的 verify.py，返回其中的公开函数（检查器只通过名字调用它们）。

        ⚠️ **必须做模块作用域隔离**：verify.py 里总写 `import solve`，而 `solve` 是个
        极普通的名字——同一个进程里跑两个案例时，第二次会命中 sys.modules 里
        **第一个案例的 solve**，钩子全部指向错误的数据（实测会直接 AttributeError，
        更坏的情况是静默用错数据）。所以这里临时把本案例的 solve.py 装到 `solve` 名下，
        用完还原。
        """
        path = self.p("verify.py")
        if not os.path.exists(path):
            return {}
        saved_solve = sys.modules.get("solve")
        sys.path.insert(0, self.dir)
        try:
            solve_path = self.p("solve.py")
            if os.path.exists(solve_path):
                sspec = importlib.util.spec_from_file_location("solve", solve_path)
                smod = importlib.util.module_from_spec(sspec)
                sspec.loader.exec_module(smod)
                sys.modules["solve"] = smod
            name = "mm_verify_%d" % abs(hash(self.dir))
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError("无法加载 verify.py：%s" % path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(self.dir)
            if saved_solve is not None:
                sys.modules["solve"] = saved_solve
            else:
                sys.modules.pop("solve", None)
        hooks = {}
        skip_mods = ("builtins", "math", "json", "os", "sys", "random")
        for k, v in vars(mod).items():
            if k.startswith("_") or not callable(v):
                continue
            if getattr(v, "__module__", "") in skip_mods:
                continue
            hooks[k] = v
        return hooks

    # ---------------- 检查器执行 ----------------
    def collect_checks(self):
        """按 ledger.spec.json 的声明跑检查（不写任何文件）。

        返回 (results_by_id, problems, all_results)。
        """
        spec = self.load_spec()
        hooks = self.load_hooks()
        results_by_id, problems, all_results = {}, [], []
        for c in spec["claims"]:
            res, probs = ck.run_checks(c["id"], c.get("checks") or [], hooks)
            results_by_id[c["id"]] = res
            all_results += res
            problems += probs
        return results_by_id, problems, all_results

    def write_checks(self, all_results, cwd=None):
        """检查结果落盘为机器可读证据（不落盘就只能靠嘴说）。"""
        cwd = cwd or self.dir
        out = os.path.join(cwd, "out")
        os.makedirs(out, exist_ok=True)
        data = [{"protocol": r.protocol, "name": r.name, "passed": r.passed,
                 "detail": r.detail, "worst": r.worst, "worst_at": r.worst_at,
                 "narrow_band_trap": r.flipped} for r in all_results]
        with open(os.path.join(out, "checks.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    # ---------------- 台账 ----------------
    def build_ledger(self, metrics: dict, results_by_id: dict):
        """由 ledger.spec.json 生成 ledger.json。

        · claim / 口径里的占位符在此被钉成 metrics.json 里的真实数字；
        · `protocols` 由**实际跑过的检查**决定，spec 里写了不算数；
        · 检查不通过 → 结论强制降级为 refuted，并把反例写进 notes（留痕）。
        """
        spec = self.load_spec()
        led = Ledger(self.ledger_path)
        led.entries = []
        ctx = {"m": metrics, "ledger": {}}
        problems = []

        for c in spec["claims"]:
            cid = c["id"]
            res = results_by_id.get(cid, [])
            ran = {r.protocol for r in res if r.passed}
            ran_all = {r.protocol for r in res}
            claim = rp.render_obj(c["claim"], ctx, problems, cid)

            declared = set(c.get("protocols") or [])
            status = c.get("status", "new")
            kind = c.get("kind")
            notes = rp.render_obj(c.get("notes", ""), ctx, problems, cid)

            # ① 检查结果先落地（这是"真跑过"的唯一凭据）
            if res:
                notes = (notes + "；" if notes else "") + \
                    " | ".join(r.line() for r in res)

            # ② 不许自填：声称跑过的协议必须在实际跑过的集合里
            fake = sorted(declared - ran_all)
            if fake and status == "verified":
                problems.append("%s 自称跑过 %s，但 checks 里并未执行（protocols 不许自填）"
                                % (cid, "、".join(fake)))

            # ③ 强制完备：结论类型要求的协议必须都跑过且通过
            if status == "verified":
                if not kind:
                    problems.append("%s 标为 verified 却没声明 kind（结论类型）——"
                                    "不声明类型，就无从判断它该验什么" % cid)
                else:
                    need = ck.REQUIRED_BY_KIND.get(kind)
                    if need is None:
                        problems.append("%s 的 kind『%s』不在已知结论类型表里：%s"
                                        % (cid, kind, "、".join(sorted(ck.REQUIRED_BY_KIND))))
                    else:
                        miss = [p for p in need if p not in ran]
                        if miss:
                            problems.append(
                                "%s 的类型『%s』要求跑 %s，实际通过 %s —— 缺 %s"
                                % (cid, kind, "+".join(need),
                                   "+".join(sorted(ran)) or "无", "+".join(miss)))

            # ④ 检查失败 → 强制 refuted（连反例一起留痕）
            failed = [r for r in res if not r.passed]
            if failed and status == "verified":
                status = "refuted"
                notes = (notes + "；" if notes else "") + \
                    "因检查不通过而降级：%s" % "；".join(r.line() for r in failed)

            led.add(cid, claim,
                    method=rp.render_obj(c.get("method", ""), ctx, problems, cid),
                    protocols=sorted(ran | {"P7"}),      # P7 由"数字来自脚本"天然成立
                    caliber=rp.render_obj(c.get("caliber"), ctx, problems, cid),
                    evidence=sorted(set(c.get("evidence") or []) |
                                    ({"out/checks.json"} if res else set())),
                    recompute=c.get("recompute", ""),
                    notes=notes,
                    depends_on=c.get("depends_on"))
            if status != "new":
                led.set_status(cid, status)

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
        say("  基线 %s（键 baseline）"
            % "、".join("%s=%s" % (k, v) for k, v in b.items() if isinstance(v, (int, str))))

        # 阶段 3：证伪（真跑检查器，而不是照着提示词"应该跑一下"）
        results_by_id, problems, all_results = self.collect_checks()
        n_pass = sum(1 for r in all_results if r.passed)
        say("【阶段 3 证伪】自动执行检查 %d 条：通过 %d，不通过 %d"
            % (len(all_results), n_pass, len(all_results) - n_pass))
        for r in all_results:
            if not r.passed or r.flipped:
                say("  ⚠️ " + r.line())
        self.write_checks(all_results)

        # 阶段 4-5：台账 + 交付
        led, probs2 = self.build_ledger(metrics, results_by_id)
        problems += probs2
        say("【阶段 4-5 台账与交付】台账 %d 条，状态分布 %s"
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
        say("闭环通过：数字全部来自 out/metrics.json，protocols 全部由实际检查得出（P7）")
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
                tmp = Case(work)
                res_by_id, probs, all_results = tmp.collect_checks()
                problems += probs
                tmp.write_checks(all_results, cwd=work)
        except RuntimeError as exc:
            return 2, log, ["独立重跑失败：%s" % exc]
        say("【阶段 6 复核】已在临时目录独立重跑 solve.py 与全部检查")

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

        # 3) 检查结论对账：本轮跑出的每条检查结果必须与冻结值一致
        got_verdicts = {"%s/%s" % (cid, r.protocol): bool(r.passed)
                        for cid, rs in res_by_id.items() for r in rs}
        for key, want in expected.get("check_verdicts", {}).items():
            if key not in got_verdicts:
                problems.append("冻结的检查 %s 本轮没跑出来（声明被删了？）" % key)
            elif got_verdicts[key] != bool(want):
                problems.append("检查结论漂移：%s 期望 %s，本轮 %s"
                                % (key, want, got_verdicts[key]))
        say("  检查结论对账 %d 条" % len(expected.get("check_verdicts", {})))

        # 4) 引用完整性：报告只能引用 verified；成品里不许剩占位符
        if not os.path.exists(self.ledger_path):
            problems.append("ledger.json 不存在：先跑 tsolve solve")
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
        say("复核通过：数字可复算、检查结论与台账状态均未漂移")
        return 0, log, []
