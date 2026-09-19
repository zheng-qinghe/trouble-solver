"""检查器引擎的测试：泛化机制是不是真的在起作用。

这里测的不是"检查器算得对不对"，而是**三件保证泛化的事**：
  1. 对抗搜索真的能抓到固定网格跳过的窄违例带（窄带陷阱的自动检测）；
  2. 「结论类型 → 必跑检查」矩阵真的会拦（不许一条全称断言只跑 P1 就自称已验证）；
  3. 检查不通过真的会把结论强制降级为 refuted（不许继续标 verified）。
另外验证**同一引擎跑四个不同领域的案例**都通过。

运行： python -m unittest discover -s tests
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

from troublesolver import checks as ck          # noqa: E402
from troublesolver.case import Case             # noqa: E402

EX_A = os.path.join(ROOT, "examples", "newsvendor_inventory")
EX_B = os.path.join(ROOT, "examples", "facility_coverage")
EX_C = os.path.join(ROOT, "examples", "loan_approval_threshold")
EX_D = os.path.join(ROOT, "examples", "fishery_msy")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


MIN_CHARTER = """# 问题说明书：最小测试案例

## 1 现象与触发
【已知】测试用。
## 2 目标
目标：测试。
## 3 决策
决策变量：x
## 4 约束
硬约束：无
## 5 数据
来源：无
## 6 成功标准
指标：通过
## 7 时间尺度
一次性
## 8 相关方
无
## 9 已有尝试
无
## 10 边界
无
## 11 风险与底线
底线：不得报假结论
## 12 口径表
| 术语 | 业务定义 | 财务定义 | 是否一致 | 本模型采用 |
|---|---|---|---|---|
| x | 测试量 | 同左 | 一致 | 测试量 |

用户确认：是
"""

MIN_SOLVE = """import json, os


def main():
    os.makedirs("out", exist_ok=True)
    m = {"baseline": {"Q": 10, "profit": 100.0}}
    with open(os.path.join("out", "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f)


if __name__ == "__main__":
    main()
"""

MIN_TEMPLATE = "# 报告\n\n基线 Q = {{m.baseline.Q}}\n"


def make_case(dirpath, claims, hooks="", metrics_extra=None, expected=None):
    """造一个最小可跑案例（用于测"引擎的强制机制"）。"""
    os.makedirs(dirpath, exist_ok=True)
    _write(os.path.join(dirpath, "charter.md"), MIN_CHARTER)
    _write(os.path.join(dirpath, "solve.py"), MIN_SOLVE)
    _write(os.path.join(dirpath, "verify.py"), hooks)
    _write(os.path.join(dirpath, "report.template.md"), MIN_TEMPLATE)
    _write(os.path.join(dirpath, "ledger.spec.json"),
           json.dumps({"case": "fixture", "claims": claims}, ensure_ascii=False, indent=2))
    if expected is not None:
        _write(os.path.join(dirpath, "expected.json"),
               json.dumps(expected, ensure_ascii=False, indent=2))
    return dirpath


def basic_claim(**over):
    c = {
        "id": "T-1", "kind": "等式", "claim": "基线 Q = {{m.baseline.Q}}",
        "status": "verified", "method": "枚举",
        "checks": [{"protocol": "P1", "name": "自比", "fn": ["hook_a", "hook_b"]}],
        "caliber": {"定义": "x", "适用边界": "测试", "可外推": False},
        "evidence": ["out/metrics.json"], "recompute": "python solve.py",
    }
    c.update(over)
    return c


HOOKS_EQUAL = "def hook_a():\n    return 10\n\n\ndef hook_b():\n    return 10\n"


class TestAdversarialSearch(unittest.TestCase):
    """P2 的执行体：窄带陷阱能不能自动抓出来。"""

    @staticmethod
    def _bump(center, width):
        def f(x):
            return 1.0 if abs(x - center) < width else -1.0
        return f

    def test_窄违例带被对抗搜索抓到且标记为窄带陷阱(self):
        """违例带 0.001 宽且中心刻意避开网格点：粗网格必然跳过，分辨率给够就得抓到。"""
        r = ck.p2_universal("窄带", self._bump(0.4321, 0.0005), 0.0, 1.0,
                            base_n=11, starts=4096)
        self.assertFalse(r.passed, "对抗搜索应当找到这个反例")
        self.assertTrue(r.flipped, "网格与对抗搜索结论不一致 → 必须标记为窄带陷阱")
        self.assertIn("窄带陷阱", r.detail)

    def test_违例带很宽时不算陷阱(self):
        r = ck.p2_universal("宽带", self._bump(0.5, 0.2), 0.0, 1.0,
                            base_n=11, starts=64)
        self.assertFalse(r.passed)
        self.assertFalse(r.flipped, "网格本来就能抓到，不该报窄带陷阱")

    def test_预算不足时如实报告分辨率而不是假装已证明(self):
        """无坡度的孤立尖峰 + 预算不够：必须把分辨率交出去，不许写成"断言成立"。"""
        r = ck.p2_universal("越预算", self._bump(0.4321, 0.00005), 0.0, 1.0,
                            base_n=11, starts=32)
        self.assertTrue(r.passed)
        self.assertIn("分辨率", r.detail)
        self.assertIn("未找到反例 ≠ 不存在", r.detail)

    def test_断言成立时通过(self):
        r = ck.p2_universal("成立", lambda x: -1.0, 0.0, 1.0, base_n=11)
        self.assertTrue(r.passed)
        self.assertLessEqual(r.worst, 0)

    def test_粗网格漏掉的尖峰预算给够就能抓回(self):
        f = self._bump(0.4321, 0.0001)   # 违例带 2e-4 宽；8192 点 → 步长 1.2e-4 必命中
        gx, gv, _ = ck.grid_argmax(f, 0.0, 1.0, 11)
        self.assertLessEqual(gv, -1.0, "粗网格应当完全没找到那个尖峰")
        ax, av = ck.adversarial_argmax(f, 0.0, 1.0, starts=8192)
        self.assertEqual(av, 1.0, "分辨率足够时对抗搜索应当找到它")
        self.assertAlmostEqual(ax, 0.4321, places=3)

    def test_有坡度的窄峰靠爬山即可精确收敛(self):
        """真实场景多是这种（分段线性/光滑）：无需暴力分辨率，爬山就能收敛到峰顶。"""
        ax, av = ck.adversarial_argmax(lambda x: -abs(x - 0.4321), 0.0, 1.0, starts=24)
        self.assertAlmostEqual(ax, 0.4321, places=6)
        self.assertAlmostEqual(av, 0.0, places=6)


class TestOtherCheckers(unittest.TestCase):
    def test_双路径交叉判据是相对误差(self):
        self.assertTrue(ck.p1_dual_path("x", 1.0, 1.0 + 1e-15).passed)
        r = ck.p1_dual_path("x", 1.0, 1.0000001)
        self.assertFalse(r.passed, "1e-7 的相对差超过 1e-9 判据，必须判不通过")
        self.assertIn("相对差", r.detail)

    def test_连续复核报区间(self):
        r = ck.p3_extremum("峰", lambda x: -(x - 1.0) ** 2, -5.0, 5.0, base_n=101)
        self.assertTrue(r.passed)
        self.assertIn("平台区间", r.detail)

    def test_极限检验会报出不退化的点(self):
        good = ck.p4_limit("极限", [(0.0, 11.0 / 19.0, 11.0 / 19.0)])
        self.assertTrue(good.passed)
        bad = ck.p4_limit("极限", [(0.0, 0.6, 11.0 / 19.0)])
        self.assertFalse(bad.passed)
        self.assertIn("期望退化", bad.detail)

    def test_翻转边界二分(self):
        r = ck.p5_flip_boundary("边界", lambda x: x - 0.25, 0.0, 1.0)
        self.assertTrue(r.passed)
        self.assertAlmostEqual(r.worst, 0.25, places=9)

    def test_找不到翻转必须如实报告未覆盖(self):
        r = ck.p5_flip_boundary("无翻转", lambda x: x + 1.0, 0.0, 1.0)
        self.assertTrue(r.passed)
        self.assertIn("未找到", r.detail)
        self.assertIn("不构成范围外的保证", r.detail)

    def test_口径混用会被拦(self):
        ok = ck.p6_caliber("同口径", [{"label": "a", "value": 1, "caliber": "口径B"},
                                      {"label": "b", "value": 2, "caliber": "口径B"}])
        self.assertTrue(ok.passed)
        bad = ck.p6_caliber("混口径", [{"label": "a", "value": 1, "caliber": "口径A"},
                                       {"label": "b", "value": 2, "caliber": "口径B"}])
        self.assertFalse(bad.passed)
        self.assertIn("禁止直接相减", bad.detail)


class TestEnforcement(unittest.TestCase):
    """泛化的强制机制：类型要求的检查没跑齐、protocols 自填、钩子写错，都必须报错。"""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.td, True)

    def _case(self, *a, **kw):
        return Case(make_case(os.path.join(self.td, "case"), *a, **kw))

    def test_全称断言只跑P1会被拦住(self):
        """这就是"泛化"的落点：结论类型决定了它至少要跑哪些检查。"""
        c = self._case([basic_claim(kind="全称断言")], HOOKS_EQUAL)
        rc, _, problems = c.solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("要求跑 P2+P5" in p for p in problems), problems)

    def test_未知结论类型会被拦住(self):
        c = self._case([basic_claim(kind="玄学")], HOOKS_EQUAL)
        rc, _, problems = c.solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("不在已知结论类型表里" in p for p in problems), problems)

    def test_没声明kind会被拦住(self):
        c = self._case([basic_claim(kind=None)], HOOKS_EQUAL)
        rc, _, problems = c.solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("没声明 kind" in p for p in problems), problems)

    def test_protocols_不许自填(self):
        c = self._case([basic_claim(protocols=["P2", "P5"])], HOOKS_EQUAL)
        rc, _, problems = c.solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("不许自填" in p for p in problems), problems)

    def test_钩子名写错会被拦住(self):
        c = self._case([basic_claim(checks=[{"protocol": "P1", "fn": ["hook_a", "不存在的钩子"]}])],
                       HOOKS_EQUAL)
        rc, _, problems = c.solve(echo=False)
        self.assertEqual(rc, 2)
        self.assertTrue(any("没有钩子函数" in p for p in problems), problems)

    def test_检查不通过会强制降级为refuted(self):
        """一条声称 verified 的断言，如果检查证伪了它，必须当场降级并留痕。"""
        hooks = ("def hook_a():\n    return 1.0\n\n\ndef hook_b():\n    return 2.0\n")
        c = self._case([basic_claim(checks=[{"protocol": "P1", "name": "自比",
                                             "fn": ["hook_a", "hook_b"]}])], hooks)
        rc, _, _ = c.solve(echo=False)
        self.assertEqual(rc, 2)
        led = _read_json(os.path.join(self.td, "case", "ledger.json"))
        e = led[0]
        self.assertEqual(e["status"], "refuted")
        self.assertIn("因检查不通过而降级", e["notes"])

    def test_protocols由实际检查决定(self):
        c = self._case([basic_claim()], HOOKS_EQUAL)
        rc, _, problems = c.solve(echo=False)
        self.assertEqual(rc, 0, problems)
        led = _read_json(os.path.join(self.td, "case", "ledger.json"))
        self.assertEqual(led[0]["protocols"], ["P1", "P7"],
                         "台账里的 protocols 必须是跑出来的，且 P7 自动带上")

    def test_加载钩子不在调用者目录留下副作用(self):
        """solve.py / verify.py 的**模块级副作用**不能落到调用者的当前目录。

        引擎为了拿钩子会把 solve.py 当模块 import，于是它模块级的
        `os.makedirs("out")` 会在"调用者的 cwd"执行 —— 实测踩过：
        在仓库根跑测试，根上凭空长出一个 out/。既然 solve.py 平时是以
        **案例目录**为 cwd 当子进程跑的，import 取钩子时也必须用同一个 cwd。
        """
        hooks_with_side_effect = (
            "import os\n"
            "os.makedirs('out', exist_ok=True)\n"      # 故意**不**放进 __main__ 里
            "def hook_a():\n    return 1\n\n\n"
            "def hook_b():\n    return 1\n")
        with tempfile.TemporaryDirectory() as outside:
            cwd0 = os.getcwd()
            os.chdir(outside)
            try:
                self._case([basic_claim()], hooks_with_side_effect).load_hooks()
                self.assertFalse(os.path.exists(os.path.join(outside, "out")),
                                 "加载钩子不该在调用者目录里建 out/")
            finally:
                os.chdir(cwd0)


class TestFourDomains(unittest.TestCase):
    """泛化的最终证据：同一引擎、零改动，跑通四个完全不同的领域。"""

    def test_案例A_库存随机优化族(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "a")
        shutil.copytree(EX_A, dst)
        case = Case(dst)
        rc, _, problems = case.solve(echo=False)
        self.assertEqual(rc, 0, problems)
        rc, _, problems = case.audit(echo=False)
        self.assertEqual(rc, 0, problems)

    def test_案例B_几何全称断言族(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "b")
        shutil.copytree(EX_B, dst)
        case = Case(dst)
        rc, _, problems = case.solve(echo=False)
        self.assertEqual(rc, 0, problems)
        rc, _, problems = case.audit(echo=False)
        self.assertEqual(rc, 0, problems)

    def test_案例C_消费信贷风控族(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "c")
        shutil.copytree(EX_C, dst)
        case = Case(dst)
        rc, _, problems = case.solve(echo=False)
        self.assertEqual(rc, 0, problems)
        rc, _, problems = case.audit(echo=False)
        self.assertEqual(rc, 0, problems)

    def test_案例D_渔业资源优化族(self):
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "d")
        shutil.copytree(EX_D, dst)
        case = Case(dst)
        rc, _, problems = case.solve(echo=False)
        self.assertEqual(rc, 0, problems)
        rc, _, problems = case.audit(echo=False)
        self.assertEqual(rc, 0, problems)

    def test_案例B的窄带陷阱被引擎抓到并留痕(self):
        """案例 B 里那条"实测半径下仍覆盖"的断言，必须被自动证伪并保留反例。"""
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "b")
        shutil.copytree(EX_B, dst)
        Case(dst).solve(echo=False)
        led = _read_json(os.path.join(dst, "ledger.json"))
        b1 = [e for e in led if e["id"] == "B-001"][0]
        self.assertEqual(b1["status"], "refuted")
        self.assertIn("窄带陷阱", b1["notes"])
        # 而按铭牌半径的那条（只差 0.067 m）必须成立 —— 两条对照才说明判据是精确的
        b2 = [e for e in led if e["id"] == "B-002"][0]
        self.assertEqual(b2["status"], "verified")

    def test_案例D的窄带陷阱被引擎抓到并留痕(self):
        """案例 D 里那条"有效口径下资源全程可续"的断言，必须被局部额外死亡带自动证伪并保留。

        与案例 B（几何缺口）、案例 C（统计越界带）是三种不同的窄带陷阱机理，
        同一引擎都抓到了 —— 这正是"通用"的铁证。
        """
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, True)
        dst = os.path.join(td, "d")
        shutil.copytree(EX_D, dst)
        Case(dst).solve(echo=False)
        led = _read_json(os.path.join(dst, "ledger.json"))
        f1 = [e for e in led if e["id"] == "F-001"][0]
        self.assertEqual(f1["status"], "refuted")
        self.assertIn("窄带陷阱", f1["notes"])
        # 而标称口径（不计局部额外死亡）同一条断言必须成立 —— 对照说明是口径在骗人
        f2 = [e for e in led if e["id"] == "F-002"][0]
        self.assertEqual(f2["status"], "verified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
