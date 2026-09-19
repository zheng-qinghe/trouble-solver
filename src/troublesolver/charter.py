"""问题说明书（charter.md）的完整性与质量校验。

为什么放在代码里而不是只写在提示词里：**"问全了没有"必须可机器校验**，
否则 agent 很容易自认为问全了。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# 与 prompts/00_intake.md 的第四节严格一致
REQUIRED_SECTIONS = [
    "1 现象与触发", "2 目标", "3 决策", "4 约束", "5 数据", "6 成功标准",
    "7 时间尺度", "8 相关方", "9 已有尝试", "10 边界", "11 风险与底线",
    "12 口径表",
]

MARK = {
    "known": "【已知】",
    "unknown": "【未知】",
    "assume": "【假设】",
}


@dataclass
class CharterReport:
    path: str
    missing: List[str] = field(default_factory=list)
    n_known: int = 0
    n_unknown: int = 0
    n_assume: int = 0
    caliber_rows: int = 0
    caliber_inconsistent: int = 0
    caliber_incomplete: int = 0
    confirmed: bool = False
    unknown_without_plan: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """卡点① 的判据：12 节齐全 + 口径表填满 + 未知项都有处理计划 + 用户已确认。"""
        return (not self.missing) and self.caliber_rows >= 1 \
            and self.caliber_incomplete == 0 and self.confirmed \
            and not self.unknown_without_plan

    def render(self) -> str:
        lines = [
            "问题说明书校验：%s" % self.path,
            "  缺失小节      : %s" % (self.missing or "无"),
            "  已知/未知/假设 : %d / %d / %d" % (self.n_known, self.n_unknown,
                                                 self.n_assume),
            "  口径表        : %d 行（未填完 %d 行，判定不一致/需双算 %d 行）"
            % (self.caliber_rows, self.caliber_incomplete,
               self.caliber_inconsistent),
            "  用户已确认    : %s" % ("是" if self.confirmed else "否"),
            "  未处理的未知项: %s" % (self.unknown_without_plan or "无"),
            "  结论          : %s" % ("通过" if self.ok else "不通过"),
        ]
        return "\n".join(lines)


def _split_sections(text: str) -> dict:
    """按 '## <n> 标题' 切分小节。"""
    out = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s*(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(line)
    return out


def check(path: str) -> CharterReport:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    secs = _split_sections(text)
    rep = CharterReport(path=path)

    for s in REQUIRED_SECTIONS:
        if not any(s == k or k.startswith(s) for k in secs):
            rep.missing.append(s)

    rep.n_known = text.count(MARK["known"])
    rep.n_unknown = text.count(MARK["unknown"])
    rep.n_assume = text.count(MARK["assume"])

    # 口径表：统计 markdown 表格数据行（排除表头与分隔行）
    cal = []
    for k, body in secs.items():
        if k.startswith("12 口径表"):
            rows = [b for b in body if b.strip().startswith("|")]
            # 分隔行必须含至少一个 '-'；否则"全空格的数据行"会被误当成分隔行吃掉，
            # 导致"口径表没填"被漏判（空白模板里正是这一行）。
            rows = [r for r in rows if not re.match(r"^\|[\s\-:|]*\-[\s\-:|]*\|$", r.strip())]
            cal = rows[1:] if rows else []      # 去掉表头
    rep.caliber_rows = len(cal)
    for r in cal:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        # 任一格为空 → 口径表没填完（不要把"没填"混进"填了但两边不一致"）
        if len(cells) < 5 or not cells[0] or not cells[4]:
            rep.caliber_incomplete += 1
        # 第 4 列 = "是否一致"；不是"一致/是"的都算需要双算
        if len(cells) >= 4 and cells[3] not in ("一致", "是", "一致 ✓", "一致✓"):
            rep.caliber_inconsistent += 1

    rep.confirmed = bool(re.search(r"用户确认[:：]\s*(是|yes|ok)", text, re.I))

    # 【未知】项必须在"处理计划"里出现（允许在同一行内用箭头说明）
    for line in text.splitlines():
        if MARK["unknown"] in line and "→" not in line and "->" not in line:
            rep.unknown_without_plan.append(line.strip()[:60])
    return rep


def blank_template(title: str = "<一句话标题>") -> str:
    secs = [
        "1 现象与触发", "2 目标", "3 决策", "4 约束", "5 数据", "6 成功标准",
        "7 时间尺度", "8 相关方", "9 已有尝试", "10 边界", "11 风险与底线",
    ]
    out = ["# 问题说明书：%s\n" % title]
    for s in secs:
        out.append("## %s\n【未知】\n" % s)
    out.append("## 12 口径表\n")
    out.append("| 术语 | 业务定义 | 财务/其他定义 | 是否一致 | 本模型采用 |")
    out.append("|---|---|---|---|---|")
    out.append("|  |  |  |  |  |\n")
    out.append("用户确认：否\n")
    return "\n".join(out)
