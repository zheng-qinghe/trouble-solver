"""LLM 编排层的测试：证明"生成 → solve → audit"整条链路能跑通，且不依赖活 key。

重点不是"LLM 多聪明"，而是：编排层有没有把 prompts/ 接到对的地方、
生成物是不是仍走和手写案例完全相同的引擎闭环、密钥有没有被硬编码。
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

from troublesolver import orchestrate as orch   # noqa: E402

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


def _make_case_dir():
    td = tempfile.mkdtemp()
    with open(os.path.join(td, "charter.md"), "w", encoding="utf-8") as f:
        f.write(MIN_CHARTER)
    return td


class TestParseGenerated(unittest.TestCase):
    def test_解析出分隔的文件块(self):
        text = ("前言一句。\n=== solve.py ===\nprint(1)\n=== verify.py ===\ndef h():\n    return 1\n"
                "=== ledger.spec.json ===\n{}")
        files = orch.parse_generated(text)
        self.assertEqual(set(files), {"solve.py", "verify.py", "ledger.spec.json"})
        self.assertEqual(files["solve.py"], "print(1)")
        self.assertEqual(files["verify.py"], "def h():\n    return 1")
        self.assertEqual(files["ledger.spec.json"], "{}")

    def test_抠出配平JSON块容忍前后说明文字(self):
        text = "下面是文件：\n{\n  \"a\": 1\n}\n以上为生成结果。"
        self.assertEqual(json.loads(orch._extract_json_substring(text)), {"a": 1})
        self.assertIsNone(orch._extract_json_substring("没有 JSON 块"))

    def test_格式不对照样返回空(self):
        self.assertEqual(orch.parse_generated("没有任何文件块"), {})


class TestMockGenerate(unittest.TestCase):
    def test_mock生成并跑通闭环与复核(self):
        td = _make_case_dir()
        self.addCleanup(shutil.rmtree, td, True)
        rc, written = orch.run_agent(td, orch.MockClient(), echo=False)
        self.assertEqual(rc, 0, "Mock 生成的案例应当 solve+audit 全过")
        # 生成物必须是白名单内的案例文件，且引擎真正用它们跑出了台账与报告
        self.assertIn("solve.py", written)
        self.assertTrue(os.path.exists(os.path.join(td, "ledger.json")))
        self.assertTrue(os.path.exists(os.path.join(td, "report.md")))
        self.assertTrue(os.path.exists(os.path.join(td, "out", "metrics.json")))

    def test_mock生成物不含活key(self):
        td = _make_case_dir()
        self.addCleanup(shutil.rmtree, td, True)
        orch.generate_case(td, orch.MockClient(), echo=False)
        blob = ""
        for name in orch.GENERATED_FILES:
            p = os.path.join(td, name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    blob += f.read()
        self.assertNotIn("sk-", blob, "生成的案例文件里不该出现 API key")


class TestConfigClient(unittest.TestCase):
    def test_源码不含硬编码密钥(self):
        import re
        src = open(os.path.join(os.path.dirname(orch.__file__), "orchestrate.py"),
                   encoding="utf-8").read()
        # 真正的密钥形如 sk- 后跟一长串字母数字；文档里提到 "sk-" 前缀不算
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{20,}", src),
                          "orchestrate.py 绝不能硬编码任何密钥")
        self.assertNotIn("api_key=\"", src, "密钥只能从参数/环境变量读取")

    def test_缺密钥时直接报错(self):
        old = os.environ.pop(orch.ConfigLLMClient.ENV_KEY, None)
        try:
            with self.assertRaises(ValueError):
                orch.ConfigLLMClient()
        finally:
            if old is not None:
                os.environ[orch.ConfigLLMClient.ENV_KEY] = old

    def test_仅从环境变量读配置(self):
        os.environ[orch.ConfigLLMClient.ENV_KEY] = "env-key-not-hardcoded"
        os.environ[orch.ConfigLLMClient.ENV_MODEL] = "env-model"
        try:
            c = orch.ConfigLLMClient()
            self.assertEqual(c.api_key, "env-key-not-hardcoded")
            self.assertEqual(c.model, "env-model")
            self.assertTrue(c.base_url.startswith("https://"))
        finally:
            os.environ.pop(orch.ConfigLLMClient.ENV_KEY, None)
            os.environ.pop(orch.ConfigLLMClient.ENV_MODEL, None)


class TestAssemblePrompt(unittest.TestCase):
    def test_系统提示含阶段指令用户提示含charter(self):
        td = _make_case_dir()
        self.addCleanup(shutil.rmtree, td, True)
        system, user = orch.assemble_model_prompt(td)
        self.assertIn("阶段", system)
        self.assertIn("charter.md", system.lower())  # 阶段指令引用了 charter 校验
        self.assertIn("问题说明书", user)
        for name in orch.GENERATED_FILES:
            self.assertIn(name, user, "user 提示必须要求输出每个生成文件")


if __name__ == "__main__":
    unittest.main(verbosity=2)
