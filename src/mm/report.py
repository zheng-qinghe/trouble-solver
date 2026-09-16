"""交付物模板渲染 —— P7 台账对账的执行体。

机制：模板里**只允许**写 `{{m.路径}}` 或 `{{m.路径|格式}}` 占位符，
渲染时从 `out/metrics.json` 取值；**取不到就报错**，不给"手抄一个数字"留后路。

为什么这么设计：AI 建模最贵的错误不是算错，是**报告里的数字和脚本脱钩**——
改一行参数、报告里的旧数字照样印出去。把"数字只能来自 JSON"变成机器强制，
比在提示词里写一百遍"不要编数字"都管用。
"""
from __future__ import annotations

import os
import re

PH = re.compile(r"\{\{\s*([^{}\s|]+)\s*(?:\|\s*([^{}]*?)\s*)?\}\}")


class RenderError(Exception):
    """模板里有占位符取不到值。"""


def lookup(ctx: dict, path: str):
    """按点号路径取值，支持列表下标：m.P5_counterexample.scan.0.promo_prob"""
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise KeyError(path)
    return cur


def build_context(metrics: dict, entries: list) -> dict:
    by = {}
    for e in entries:
        by[e["status"]] = by.get(e["status"], 0) + 1
    return {
        "m": metrics,
        "ledger": {
            "n": len(entries),
            "verified": by.get("verified", 0),
            "refuted": by.get("refuted", 0),
            "stale": by.get("stale", 0),
            "by_status": by,
        },
    }


def render(text: str, ctx: dict):
    """返回 (渲染结果, 取不到值的占位符列表)。"""
    problems = []

    def sub(mo):
        path, fmt = mo.group(1), (mo.group(2) or "").strip()
        try:
            v = lookup(ctx, path)
        except KeyError:
            problems.append(path)
            return mo.group(0)
        if fmt:
            return format(v, fmt)
        if isinstance(v, bool):
            return "是" if v else "否"
        if isinstance(v, float):
            return "%.6g" % v
        return str(v)

    return PH.sub(sub, text), problems


def render_obj(obj, ctx: dict, problems: list, where: str = ""):
    """递归渲染任意结构里的字符串。

    为什么需要它：口径字段（caliber）里也会写数字（"促销概率 ≥ {{...}} 时失效"），
    如果只渲染 claim，口径里的数字就成了"手抄"——正是 P6/P7 要防的东西。
    """
    if isinstance(obj, str):
        out, bad = render(obj, ctx)
        for b in bad:
            problems.append("%s 的占位符取不到值：%s" % (where, b))
        return out
    if isinstance(obj, dict):
        return {k: render_obj(v, ctx, problems, where) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render_obj(v, ctx, problems, where) for v in obj]
    return obj


def render_file(template_path: str, out_path: str, ctx: dict) -> str:
    with open(template_path, encoding="utf-8") as f:
        text = f.read()
    # 模板开头的 HTML 注释是写给维护者看的（里面常带占位符写法示例），
    # 既不进交付物、也不参与渲染——否则注释里的示例会被当成本尊去找值。
    text = re.sub(r"\A\s*<!--.*?-->\s*", "", text, flags=re.S)
    out, problems = render(text, ctx)
    if problems:
        raise RenderError(
            "模板 %s 有 %d 个占位符无法从 metrics.json 取值：%s"
            % (os.path.basename(template_path), len(problems),
               "、".join(sorted(set(problems)))))
    d = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(d, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    return out


def unresolved_markers(path: str) -> int:
    """数一数成品文件里还剩几个没被解析的占位符（应为 0）。"""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return len(PH.findall(f.read()))
