"""案例 B：2 km 管廊的传感器布点覆盖设计（**几何 / 全称断言族**）

与案例 A（单 SKU 备货，随机优化族）完全不同的数学族：
  · 案例 A 的结论是"期望值最优"（随机、离散）；
  · 案例 B 的结论是"任意一点都被覆盖"（确定性、全称量词、连续）。
但两者用的是**同一套验证引擎**，`mm/checks.py` 一行没改——
这个案例的存在本身就是"泛化"的证据。

数字全部写入 out/metrics.json（P7：报告里的数字一律从这儿取，禁止手抄）。
运行： python solve.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ---- 问题说明书里确认下来的参数（见 charter.md）----
L = 2000.0          # 管廊长度（m）
W = 4.0             # 管廊宽度（m）
N_NOW = 7           # 现状传感器数量
R_RATED = 166.667   # 铭牌标称探测半径（m，工程取三位小数）
R_AGED = 166.6      # 实测探测半径（m，使用两年后衰减）
R_TARGET = 150.0    # 采购约束：能买到的传感器半径上限（m）
EFF_RATIO = 0.8     # 有效口径折减系数（标称 → 现场有效）


# ---------------- 几何 ----------------
def stations(n):
    """n 个等间距布点（含两端）：0, d, 2d, …, L，d = L/(n-1)。"""
    return [L * i / (n - 1) for i in range(n)]


def gaps(xs):
    """相邻间距（含两端到管廊端点的距离）。"""
    xs = sorted(xs)
    return ([xs[0] - 0.0]
            + [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
            + [L - xs[-1]])


def r_needed_from_layout(xs):
    """给定布点，覆盖全长所需的**最小**半径 = 最大间距的一半。

    依据：相邻两传感器之间的最不利点在中点，到最近站点的距离 = 间距/2；
    端点外延同理。所以 max 间距决定所需半径。
    """
    return max(gaps(xs)) / 2.0


def r_needed_analytic(n):
    """等间距布点的解析解：r* = L / (2(n−1))。"""
    if n <= 1:
        return float("inf")
    return L / (2.0 * (n - 1))


def nearest_gap(x, xs):
    """点 x 到最近站点的距离。"""
    return min(abs(x - p) for p in xs)


def r_needed_by_scan(n, step=0.05):
    """**不依赖解析式**的独立算法：在 [0, L] 上细扫求 max_x 最近距离。

    与 `r_needed_analytic` 构成 P1 的两条路径（解析式 vs 数值扫描）。
    """
    xs = stations(n)
    x, best = 0.0, 0.0
    while x <= L:
        g = nearest_gap(x, xs)
        if g > best:
            best = g
        x += step
    return best


def bounded_min_stations(r_target):
    """在"探测半径上限 r_target"的约束下，所需**最少**传感器数（连续值）。

    解 L/(2(n−1)) = r_target → n = 1 + L/(2 r_target)。取整即工程上要买几个。
    """
    return 1.0 + L / (2.0 * r_target)


def r_needed_uniform_shift(n, t):
    """把中间 n−2 个点整体平移 t（两端固定贴端点），返回所需半径。

    用于检验"等间距是否最优、以及布点对整体偏移有多敏感"。
    """
    xs = [0.0] + [i * L / (n - 1) + t for i in range(1, n - 1)] + [L]
    return r_needed_from_layout(xs)


def main():
    os.makedirs(OUT, exist_ok=True)
    xs_now = stations(N_NOW)
    d_now = L / (N_NOW - 1)

    # 现状布点的最坏点：相邻站点中点（用细扫找，避免"我以为"）
    step = 0.01
    worst_x, worst_gap = 0.0, 0.0
    k = 0
    while k * step <= L:
        x = k * step
        g = nearest_gap(x, xs_now)
        if g > worst_gap:
            worst_x, worst_gap = x, g
        k += 1

    m = {
        "params": {"L": L, "W": W, "n_now": N_NOW, "spacing_now": d_now,
                   "r_rated": R_RATED, "r_aged": R_AGED,
                   "r_target": R_TARGET, "eff_ratio": EFF_RATIO},
        "baseline": {"n": N_NOW, "spacing": d_now,
                     "r_needed_exact": worst_gap,
                     "worst_point_x": worst_x,
                     "verdict": "现状 7 点等间距：理论所需半径 = 间距的一半"},
        "coverage_now": {
            "r_needed_exact": worst_gap,
            "worst_point_x": worst_x,
            "shortfall_at_rated": worst_gap - R_RATED,     # 铭牌标称下：负值=尚有微余量
            "shortfall_at_aged": worst_gap - R_AGED,       # 实测衰减后：正值=已经失守
            "margin_at_rated": R_RATED - worst_gap,
        },
        "P1_dual_path": {
            "r_needed_analytic_n7": r_needed_analytic(N_NOW),
            "r_needed_scan_n7": r_needed_by_scan(N_NOW),
            "rel_diff": abs(r_needed_analytic(N_NOW) - r_needed_by_scan(N_NOW))
                        / r_needed_analytic(N_NOW),
        },
        "plan_8": {"n": 8, "spacing": L / 7.0,
                   "r_needed": r_needed_analytic(8),
                   "margin_gain_vs_now": r_needed_analytic(N_NOW) - r_needed_analytic(8)},
        "n_for_target": {"r_target": R_TARGET,
                         "n_exact": bounded_min_stations(R_TARGET),
                         "n_ceil": int(-(-bounded_min_stations(R_TARGET) // 1)),
                         "r_at_n_ceil": r_needed_analytic(
                             int(-(-bounded_min_stations(R_TARGET) // 1)))},
        "caliber": {
            "geom_r_n7": r_needed_analytic(N_NOW),
            "nominal_needed_n7": r_needed_analytic(N_NOW) / EFF_RATIO,
            "geom_r_n8": r_needed_analytic(8),
            "nominal_needed_n8": r_needed_analytic(8) / EFF_RATIO,
        },
        "limit": {"n2_r": r_needed_analytic(2), "n3_r": r_needed_analytic(3),
                  "n11_r": r_needed_analytic(11)},
        "result": {
            "recommend_n": int(-(-bounded_min_stations(R_TARGET) // 1)),
            "r_needed": r_needed_analytic(int(-(-bounded_min_stations(R_TARGET) // 1))),
            "margin_gain_vs_now": (r_needed_analytic(N_NOW)
                                   - r_needed_analytic(int(-(-bounded_min_stations(R_TARGET) // 1)))),
        },
    }

    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    print("== 管廊覆盖 ==")
    print("  长度 %.0f m，现状 %d 点等间距（间距 %.4f m）"
          % (L, N_NOW, d_now))
    print("  理论所需半径 %.4f m；细扫最坏点 x=%.4f m（距最近站 %.4f m）"
          % (worst_gap, worst_x, worst_gap))
    print("  铭牌标称半径 %.3f m → 余量 %.4f m（纸面上成立，实际是零余量）"
          % (R_RATED, R_RATED - worst_gap))
    print("  实测半径 %.1f m → 缺口 %.4f m（已经失守）"
          % (R_AGED, worst_gap - R_AGED))
    print("== P1 双路径 ==")
    print("  解析式 %.6f vs 细扫 %.6f（相对差 %.2e）"
          % (r_needed_analytic(N_NOW), m["P1_dual_path"]["r_needed_scan_n7"],
             m["P1_dual_path"]["rel_diff"]))
    print("== 方案 ==")
    print("  8 点等间距：所需半径 %.4f m，比现状多出 %.4f m 余量"
          % (m["plan_8"]["r_needed"], m["plan_8"]["margin_gain_vs_now"]))
    print("  在半径 ≤ %.0f m 约束下，最少需要 %.4f 个 → 取整 %d 个"
          % (R_TARGET, m["n_for_target"]["n_exact"], m["n_for_target"]["n_ceil"]))
    print("== 口径 ==")
    print("  几何口径 / 有效口径（折减 %.1f）：n=7 需标称 %.2f m；n=8 需标称 %.2f m"
          % (EFF_RATIO, m["caliber"]["nominal_needed_n7"], m["caliber"]["nominal_needed_n8"]))
    print("  数字来源：out/metrics.json（P7：禁止手抄）")
    return m


if __name__ == "__main__":
    main()
