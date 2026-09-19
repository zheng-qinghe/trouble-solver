"""TroubleSolver 的回归测试：把"防护真的会拦"当成测试来跑。

运行： python -m unittest discover -s tests -v
不需要安装：测试自己把 src/ 放进 sys.path。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from troublesolver import charter as ch          # noqa: E402
from troublesolver import report as rp           # noqa: E402
from troublesolver.case import Case              # noqa: E402
from troublesolver.ledger import Ledger          # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "newsvendor_inventory")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TempCaseMixin:
    def copy_example(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "case")
        shutil.copytree(EXAMPLE, dst)
        return dst

    @staticmethod
    def patch(path, old, new):
        text = _read(path)
        assert old in text, "待替换文本不存在：%r" % old
        _write(path, text.replace(old, new))


class TestCharter(unittest.TestCase):
    def test_blank_template_不通过(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "charter.md")
            _write(p, ch.blank_template())
            rep = ch.check(p)
            self.assertFalse(rep.ok, "空白模板必须被判为不通过")
            self.assertTrue(rep.unknown_without_plan, "空白模板里每个【未知】都没有处理计划")
            self.assertEqual(rep.caliber_incomplete, 1, "空口径表行应算'未填完'")
            self.assertFalse(rep.confirmed)

    def test_示例问题说明书_通过(self):
        rep = ch.check(os.path.join(EXAMPLE, "charter.md"))
        self.assertTrue(rep.ok, rep.render())
        self.assertGreaterEqual(rep.caliber_rows, 1)
        self.assertTrue(rep.confirmed)

    def test_未知项没有处理计划_不通过(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "charter.md")
            with open(os.path.join(EXAMPLE, "charter.md"), encoding="utf-8") as f:
                src = f.read()
            _write(p, src + "\n【未知】某件没人管的事\n")
            rep = ch.check(p)
            self.assertFalse(rep.ok)
            self.assertEqual(len(rep.unknown_without_plan), 1)


class TestLedger(unittest.TestCase):
    def _ledger(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        return Ledger(os.path.join(td, "ledger.json"))

    def test_verified_缺证据或缺重算命令会被拦(self):
        led = self._ledger()
        led.add("C-1", "某结论", recompute="", evidence=[], caliber={"定义": "x"})
        led.set_status("C-1", "verified")
        problems = led.check()
        self.assertTrue(any("无证据" in p for p in problems), problems)
        self.assertTrue(any("无 recompute" in p for p in problems), problems)

    def test_verified_缺口径定义会被拦(self):
        led = self._ledger()
        led.add("C-1", "某结论", recompute="python x.py", evidence=["a.json"])
        led.set_status("C-1", "verified")
        self.assertTrue(any("缺口径定义" in p for p in led.check()))

    def test_stale_沿依赖链传播(self):
        led = self._ledger()
        led.add("C-1", "上游参数")
        led.add("C-2", "结论", depends_on=["C-1"])
        led.add("C-3", "下游结论", depends_on=["C-2"])
        led.add("C-4", "无关结论")
        changed = led.invalidate("C-1", reason="参数改了")
        self.assertEqual(set(changed), {"C-1", "C-2", "C-3"})
        self.assertEqual(led.get("C-4")["status"], "new", "无关条目不应被牵连")

    def test_依赖已证伪条目会被拦(self):
        led = self._ledger()
        led.add("C-1", "被推翻的说法")
        led.set_status("C-1", "refuted")
        led.add("C-2", "引用它的结论", depends_on=["C-1"])
        problems = led.check()
        self.assertTrue(any("状态为 refuted" in p for p in problems), problems)

    def test_refuted_条目本身不触发告警(self):
        """被证伪的结论是要留痕的，不是错误——不能因为它是 refuted 就报错。"""
        led = self._ledger()
        led.add("C-1", "被推翻的说法")
        led.set_status("C-1", "refuted")
        self.assertEqual(led.check(), [])


class TestReport(unittest.TestCase):
    def test_占位符能取到值(self):
        out, problems = rp.render("Q = {{m.a.b}} 件", {"m": {"a": {"b": 133}}})
        self.assertEqual(out, "Q = 133 件")
        self.assertEqual(problems, [])

    def test_占位符取不到值必须报错而不是留空(self):
        out, problems = rp.render("{{m.a.nope}}", {"m": {"a": {}}})
        self.assertEqual(problems, ["m.a.nope"])
        self.assertIn("{{", out, "取不到值时应保留原样，好让人看见漏在哪")

    def test_格式化与下标(self):
        ctx = {"m": {"x": 0.703703, "s": [132, 135]}}
        out, _ = rp.render("{{m.x|.2%}} / {{m.s.1}}", ctx)
        self.assertEqual(out, "70.37% / 135")

    def test_路径写错也要报错而不是静默放过(self):
        """占位符路径里可以有中文——必须照样被正则捕获，否则错别字会静默漏过。"""
        out, problems = rp.render("{{m.需求}}", {"m": {"mean": 1}})
        self.assertEqual(problems, ["m.需求"])
        self.assertEqual(out, "{{m.需求}}")

    def test_模板开头的说明注释不参与渲染也不进交付物(self):
        with tempfile.TemporaryDirectory() as td:
            tpl = os.path.join(td, "t.md")
            out = os.path.join(td, "o.md")
            _write(tpl, "<!--\n  示例：{{m.路径}} 由脚本注入\n-->\n正文 {{m.a}}\n")
            txt = rp.render_file(tpl, out, {"m": {"a": 7}})
            self.assertEqual(_read(out), "正文 7\n")
            self.assertEqual(txt, "正文 7\n")

    def test_口径字段里的占位符也要被渲染(self):
        """caliber 里写死数字同样违反 P7，必须一起渲染。"""
        problems = []
        got = rp.render_obj({"适用边界": "概率 ≥ {{m.p}} 时失效"}, {"m": {"p": 0.25}},
                            problems, "C-1")
        self.assertEqual(got["适用边界"], "概率 ≥ 0.25 时失效")
        self.assertEqual(problems, [])


class TestCaseEndToEnd(TempCaseMixin, unittest.TestCase):
    def test_示例案例_闭环与复核都通过(self):
        d = self.copy_example()
        case = Case(d)
        rc, _, problems = case.solve(echo=False)
        self.assertEqual(rc, 0, problems)
        self.assertTrue(os.path.exists(os.path.join(d, "report.md")))
        self.assertTrue(os.path.exists(os.path.join(d, "ledger.json")))
        rc, _, problems = case.audit(echo=False)
        self.assertEqual(rc, 0, problems)

    def test_参数一改_audit_必须报警(self):
        d = self.copy_example()
        case = Case(d)
        case.solve(echo=False)
        self.patch(os.path.join(d, "solve.py"), "P_PRICE = 25.0", "P_PRICE = 26.0")
        rc, _, problems = case.audit(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("数字漂移" in p for p in problems), problems)

    def test_用户未确认_卡点一必须拦住(self):
        d = self.copy_example()
        self.patch(os.path.join(d, "charter.md"), "用户确认：是", "用户确认：否")
        rc, _, problems = Case(d).solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("卡点①" in p for p in problems), problems)

    def test_模板里写不存在的键_必须报错(self):
        d = self.copy_example()
        tpl = os.path.join(d, "report.template.md")
        _write(tpl, _read(tpl) + "\n参考：{{m.nonexistent.key}}\n")
        rc, _, problems = Case(d).solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("无法从 metrics.json 取值" in p for p in problems), problems)

    def test_台账里的数字确实来自_json(self):
        d = self.copy_example()
        Case(d).solve(echo=False)
        led = Ledger(os.path.join(d, "ledger.json"))
        with open(os.path.join(d, "out", "metrics.json"), encoding="utf-8") as f:
            metrics = json.load(f)
        c007 = led.get("C-007")["claim"]
        self.assertIn(str(metrics["result"]["recommend_Q"]), c007,
                      "结论文本里的备货量必须等于 metrics.json 的值")


if __name__ == "__main__":
    unittest.main(verbosity=2)
