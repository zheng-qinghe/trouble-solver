"""可追溯台账（claim ledger）。

设计要点（来自实战教训）：
- 每条结论带状态；报告只能引用 verified 的条目；
- **refuted 也留痕**——被证伪的结论连同证据一起保留，这是可信度的一部分；
- **stale 传播**：上游参数一改，依赖它的结论自动作废，必须重验；
- 每个"对外数字"都必须有 recompute 命令（禁止手抄）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

STATUSES = ("new", "verifying", "verified", "refuted", "stale")


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path: str):
        self.path = path
        self.entries = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.entries = json.load(f)

    # ---------- 读写 ----------
    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def get(self, cid):
        for e in self.entries:
            if e["id"] == cid:
                return e
        return None

    # ---------- 增改 ----------
    def add(self, cid, claim, method="", protocols=None, caliber=None,
            evidence=None, recompute="", notes="", depends_on=None):
        if self.get(cid):
            raise KeyError("台账 id 重复：%s" % cid)
        self.entries.append({
            "id": cid,
            "claim": claim,
            "status": "new",
            "method": method,
            "protocols": protocols or [],
            "caliber": caliber or {"定义": "", "适用边界": "", "可外推": False},
            "evidence": evidence or [],
            "recompute": recompute,
            "depends_on": depends_on or [],
            "verified_at": None,
            "notes": notes,
        })
        return self

    def set_status(self, cid, status, evidence=None, notes=None):
        if status not in STATUSES:
            raise ValueError("非法状态：%s（可选 %s）" % (status, STATUSES))
        e = self.get(cid)
        if e is None:
            raise KeyError("台账无此 id：%s" % cid)
        e["status"] = status
        if evidence:
            e["evidence"] = sorted(set(e["evidence"]) | set(evidence))
        if notes:
            e["notes"] = (e["notes"] + "；" + notes) if e["notes"] else notes
        if status == "verified":
            e["verified_at"] = _now()
        return self

    def invalidate(self, cid, reason=""):
        """上游变更：把该条及其所有下游依赖链置为 stale。"""
        self.set_status(cid, "stale", notes="上游变更%s" % ("：" + reason if reason else ""))
        changed = [cid]
        frontier = [cid]
        while frontier:
            cur = frontier.pop()
            for e in self.entries:
                if cur in e.get("depends_on", []) and e["status"] != "stale":
                    e["status"] = "stale"
                    e["notes"] = (e["notes"] + "；" if e["notes"] else "") + \
                        "因依赖 %s 失效而作废" % cur
                    changed.append(e["id"])
                    frontier.append(e["id"])
        return changed

    # ---------- 校验 ----------
    def check(self):
        """交付前对账：返回问题列表（空 = 通过）。"""
        problems = []
        ids = [e["id"] for e in self.entries]
        if len(ids) != len(set(ids)):
            problems.append("存在重复 id")
        for e in self.entries:
            cid = e["id"]
            if e["status"] in ("verified",) and not e["evidence"]:
                problems.append("%s 标为 verified 但无证据文件" % cid)
            if e["status"] in ("verified",) and not e["recompute"]:
                problems.append("%s 标为 verified 但无 recompute 命令（违反 P7）" % cid)
            if e["status"] == "verified" and not e["caliber"].get("定义"):
                problems.append("%s 缺口径定义（P6）" % cid)
            for d in e.get("depends_on", []):
                if d not in ids:
                    problems.append("%s 依赖了不存在的 %s" % (cid, d))
                elif self.get(d)["status"] in ("refuted", "stale"):
                    problems.append("%s 依赖的 %s 状态为 %s，不能对外引用"
                                    % (cid, d, self.get(d)["status"]))
        return problems

    def summary(self):
        by = {}
        for e in self.entries:
            by[e["status"]] = by.get(e["status"], 0) + 1
        return by
