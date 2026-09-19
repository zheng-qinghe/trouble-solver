"""把 `prompts/` 的阶段指令接上 LLM 编排。

之前（v0.2）这个环节是**确定性闭环**：卡点校验、七条协议、台账、数字对账全自动，
但"模型把问题想对、写出 solve.py / verify.py"那一步还是人/agent 自己写。
本模块补上这一环：**让 LLM 读取 charter.md + 阶段指令，生成案例文件，再由引擎跑闭环。**

设计要点（与引擎一致的克制）：
  · **不硬编码任何密钥**。LLM 客户端只从环境变量 / 显式参数读取配置；代码里搜不到 "sk-"。
  · **可替换的客户端**。给一个 `LLMClient` 协议即可；测试用 `MockClient`（零网络、零密钥）
    证明"生成 → solve → audit"整条链路能跑通，且不依赖任何活 key。
  · **生成物仍是普通案例文件**。LLM 写完文件后，走的还是和手写案例**完全相同**的
    `Case.solve` / `Case.audit`——编排层不绕开任何一道卡点 / 协议 / 对账。
  · **不做"AI 自动写论文"**。`prompts/` 明确要求模型只产出可复算的代码与占位符模板，
    结论的真伪仍由引擎的七条协议判定，不是由模型自己说了算。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
from typing import Dict, List, Protocol, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPTS_DIR = os.path.join(ROOT, "prompts")

# 生成物里要求 LLM 输出的文件（顺序即建议输出顺序）
GENERATED_FILES = (
    "solve.py",
    "verify.py",
    "ledger.spec.json",
    "report.template.md",
    "falsify.template.md",
    "expected.json",
)

# LLM 输出文件的分隔符格式（在阶段指令里明确要求）：
#   === solve.py ===
#   <文件内容>
#   === verify.py ===
#   <文件内容>
#   ...
_FILE_RE = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)


class LLMClient(Protocol):
    """可替换的 LLM 客户端：只需实现一个方法。"""

    def complete(self, system: str, user: str) -> str:
        """返回模型的完整文本输出。"""
        ...


class MockClient:
    """离线 / 测试用的客户端：不联网、不读密钥，直接吐一份已知有效的案例文件。

    证明"生成 → solve → audit"整条链路在**没有活 key** 时也能跑通；
    也让 CI 在没有 LLM 配额时仍能覆盖编排层。
    """

    def __init__(self, files: Dict[str, str] | None = None):
        self.files = files

    def complete(self, system: str, user: str) -> str:
        files = self.files
        if files is None:
            files = _demo_case_files()
        parts = ["下面按 === 文件名 === 格式给出案例文件：\n"]
        for name in GENERATED_FILES:
            if name in files:
                parts.append("=== %s ===\n%s\n" % (name, files[name].rstrip("\n")))
        return "\n".join(parts)


class ConfigLLMClient:
    """OpenAI 兼容的聊天补全客户端，**零硬编码密钥**。

    配置来源（优先级：显式参数 > 环境变量；都不给就报错）：
      · TSOLVE_LLM_API_KEY   密钥（必填，否则构造即报错）
      · TSOLVE_LLM_BASE_URL  兼容端点，默认 https://api.openai.com/v1
      · TSOLVE_LLM_MODEL     模型名，默认 gpt-4o-mini
    用标准库 urllib 直接 POST，不引入 openai 依赖。
    """

    ENV_KEY = "TSOLVE_LLM_API_KEY"
    ENV_BASE = "TSOLVE_LLM_BASE_URL"
    ENV_MODEL = "TSOLVE_LLM_MODEL"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None):
        self.api_key = api_key or os.environ.get(self.ENV_KEY)
        if not self.api_key:
            raise ValueError(
                "缺少 LLM 密钥：请设置环境变量 %s 或在调用时传入 api_key"
                "（不要把密钥写进代码）" % self.ENV_KEY)
        self.base_url = (base_url or os.environ.get(self.ENV_BASE)
                         or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.environ.get(self.ENV_MODEL) or "gpt-4o-mini"

    def complete(self, system: str, user: str) -> str:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json",
            })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError("LLM 请求失败（HTTP %d）：%s" % (exc.code, body)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("LLM 请求无法连接：%s" % exc) from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM 返回结构异常：%r" % data) from exc


def _read_stage(name: str) -> str:
    path = os.path.join(PROMPTS_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def assemble_model_prompt(case_dir: str) -> Tuple[str, str]:
    """把阶段指令（建模 / 证伪 / 交付）与 charter.md 拼成 system + user。

    只取"产出代码"相关的阶段 20/30/50；阶段 0（引导提问）已在 charter.md 里完成。
    """
    stages = [
        _read_stage("20_model.md"),
        _read_stage("30_falsify.md"),
        _read_stage("50_deliver.md"),
    ]
    system = (
        "你是 TroubleSolver 的建模编排器。下面的阶段指令定义了你要产出的文件格式与铁律。"
        "严格遵守：数字只能从脚本出来、报告里禁止手写数字（用 {{m.路径}} 占位符）、"
        "每个数字必须标口径、出现「恒成立/一定/总是」的断言必须有对抗搜索记录。\n\n"
        + "\n\n".join(stages)
    )
    charter_path = os.path.join(case_dir, "charter.md")
    with open(charter_path, encoding="utf-8") as f:
        charter = f.read()

    fmt = "\n".join("  === %s ===" % f for f in GENERATED_FILES)
    user = (
        "# 问题说明书（已通过卡点①，用户已确认口径）\n\n%s\n\n"
        "# 任务\n请基于上面的《问题说明书》与系统提示里的阶段指令，**生成以下 6 个文件**，"
        "严格按照 `=== 文件名 ===` 开头、下一行起为文件完整内容的格式输出（不要额外解释，"
        "文件内容之外最多一行说明）：\n%s\n\n"
        "硬性格式要求：\n"
        "  · `solve.py`：求解脚本，唯一出口 `out/metrics.json`，且必须含 `baseline` 键；"
        "键名不得含点号；JSON 必须是合法 JSON。\n"
        "  · `verify.py`：验证钩子；`ledger.spec.json` 里 `checks[].fn` 引用的钩子必须在此文件真实存在。\n"
        "  · `ledger.spec.json`：声明式结论清单，每条 claim 用 `{{m.路径}}` 引用真实数字；"
        "结论类型 `kind` 决定必跑协议（见系统提示）。\n"
        "  · `report.template.md` / `falsify.template.md`：每个数字写成 `{{m.路径|格式}}` 占位符，禁止裸数字。\n"
        "  · `expected.json`：冻结关键数字（golden），供 `tsolve audit` 回归；"
        "含 `metrics` / `ledger_status` / `check_verdicts` 三段。\n"
        "  · 不要把任何 Python 代码包在 Markdown 代码块里——直接给裸文件内容。"
    ) % (charter, fmt)
    return system, user


def parse_generated(text: str) -> Dict[str, str]:
    """把 LLM 的 `=== 文件名 ===` 分隔输出解析成 {文件名: 内容}。"""
    matches = list(_FILE_RE.finditer(text))
    out: Dict[str, str] = {}
    if not matches:
        return out
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip("\n")
        out[name] = content
    return out


def _extract_json_substring(text: str) -> str | None:
    """从可能夹带前后说明文字的文本里抠出第一个配平的 {...} JSON 块。

    让生成物对"文件后面多写了一句说明"这类 LLM 常见越界更鲁棒。
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def generate_case(case_dir: str, client: LLMClient, echo: bool = True) -> List[str]:
    """调用 LLM 把案例文件写到 case_dir，返回实际写入的文件列表。"""
    system, user = assemble_model_prompt(case_dir)
    raw = client.complete(system, user)
    files = parse_generated(raw)
    if not files:
        raise RuntimeError("LLM 输出里没有解析出任何 `=== 文件名 ===` 文件块")
    written = []
    for name, content in files.items():
        # 只允许生成白名单内的文件，避免 LLM 乱写无关文件
        if name not in GENERATED_FILES:
            if echo:
                print("  ⚠️ 跳过非案例文件：%s" % name)
            continue
        path = os.path.join(case_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(name)
        if echo:
            print("  ✔ 已写入 %s（%d 字节）" % (name, len(content)))
    # 校验 JSON 类文件可解析（容忍文件后多写的一句说明：抠配平 {...} 块）
    for name in ("ledger.spec.json", "expected.json"):
        if name in written:
            with open(os.path.join(case_dir, name), encoding="utf-8") as f:
                raw = f.read()
            sub = _extract_json_substring(raw)
            json.loads(sub if sub is not None else raw)  # 解析失败会直接抛出
    return written


def run_agent(case_dir: str, client: LLMClient, echo: bool = True,
              run_audit: bool = True) -> Tuple[int, List[str]]:
    """编排主入口：生成案例文件 → 跑闭环 →（可选）独立复核。返回 (rc, 写入的文件)。"""
    from troublesolver.case import Case  # 延迟导入，避免与测试循环依赖

    written = generate_case(case_dir, client, echo=echo)
    case = Case(case_dir)
    rc, _, _ = case.solve(echo=echo)
    if rc != 0:
        return rc, written
    if run_audit:
        rc, _, _ = case.audit(echo=echo)
    return rc, written


# ----------------------------------------------------------------------------
# 一份可被 MockClient 直接吐出的、经过真实引擎验证的最小案例文件
# （仅用于测试 / 离线演示，证明生成→solve→audit 链路不依赖活 key）
# ----------------------------------------------------------------------------
def _demo_case_files() -> Dict[str, str]:
    # 注意：副作用一律放进 main() 并用 __main__ 守卫 —— 引擎会把 solve.py 当模块
    # import 来取钩子，模块级语句会在**调用者的目录**执行（会在人家工作目录里建 out/）。
    solve = (
        "import json, os\n"
        "\n"
        "def main():\n"
        "    os.makedirs('out', exist_ok=True)\n"
        "    m = {'baseline': {'Q': 10, 'profit': 100.0},\n"
        "         'result': {'recommend_Q': 10}}\n"
        "    with open(os.path.join('out', 'metrics.json'), 'w', encoding='utf-8') as f:\n"
        "        json.dump(m, f)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    verify = (
        "def hook_a():\n"
        "    return 10.0\n\n"
        "def hook_b():\n"
        "    return 10.0\n"
    )
    ledger = json.dumps({
        "case": "gen_demo",
        "claims": [{
            "id": "G-1", "kind": "等式",
            "claim": "基线 Q = {{m.baseline.Q}}",
            "status": "verified", "method": "枚举",
            "checks": [{"protocol": "P1", "name": "自比", "fn": ["hook_a", "hook_b"]}],
            "caliber": {"定义": "x", "适用边界": "测试", "可外推": False},
            "evidence": ["out/metrics.json"], "recompute": "python solve.py",
        }],
    }, ensure_ascii=False, indent=2)
    report = "# 报告\n\n基线 Q = {{m.baseline.Q}}\n"
    falsify = "# 证伪记录\n\n基线 Q = {{m.baseline.Q}}\n"
    expected = json.dumps({
        "tolerance": {"default": 1e-9},
        "metrics": {"baseline.Q": 10, "result.recommend_Q": 10},
        "ledger_status": {"G-1": "verified"},
        "check_verdicts": {"G-1/P1": True},
    }, ensure_ascii=False, indent=2)
    return {
        "solve.py": solve,
        "verify.py": verify,
        "ledger.spec.json": ledger,
        "report.template.md": report,
        "falsify.template.md": falsify,
        "expected.json": expected,
    }


# 让 CLI 在 import 失败时也能给出可读错误（例如缺 charter.md）
if __name__ == "__main__":
    sys.exit(1)
