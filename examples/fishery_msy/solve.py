"""生物 / 资源案例：渔业最大可持续产量 MSY（**连续优化 / 全称断言 / 口径相关族**）

与案例 A（单 SKU 备货，随机优化族）、案例 B（设施覆盖，几何/连续族）、案例 C（消费信贷，
统计量/口径族）都不同的数学族：
  · 案例 A：期望值最优（随机、离散）；
  · 案例 B：任意一点都被覆盖（确定性、∀、连续几何）；
  · 案例 C：一个分类阈值是否让"每一类客户"满足约束（∀ + 口径冲突）；
  · 本案例：一个连续控制变量（捕捞努力度 E）使"每一档努力下资源都可续"——**最优性 + 全称断言 + 口径**。
四者用的是**同一套验证引擎**，`troublesolver/checks.py` 一行没改。

数字全部写入 out/metrics.json（P7：报告里的数字一律从这儿取，禁止手抄）。
运行： python solve.py
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ---- 问题说明书里确认下来的参数（见 charter.md）----
K = 1000.0        # 环境承载力（吨）
R = 0.4           # 内禀增长率（1/年）
Q = 0.001         # 可捕系数（1/(船·年)）
E_NOW = 120.0     # 现状捕捞努力度（船·年）
B_MIN = 240.0     # 产卵群体生物量下限（吨，保护性口径）
# 局部额外死亡带：某细分渔场（如产卵集聚区）在特定努力档位附近有额外死亡
E_SPIKE = 183.0   # 额外死亡带中心（恰好卡在两网格点 180 / 186 之间）
AMP = 320.0       # 额外死亡带幅度（吨）
SIGMA = 8.0       # 额外死亡带宽度（小 → 粗网格整段跳过）


# ---------------- 种群动力学 ----------------
def x_star(E):
    """开捕平衡生物量（无局部额外死亡）：x* = K(1 − qE/r)，qE>r 时崩溃为 0。"""
    if Q * E <= R:
        return K * (1.0 - Q * E / R)
    return 0.0


def bump(E):
    """局部额外死亡带（某细分渔场的产卵集聚区，努力档位附近额外减员）。"""
    return AMP * math.exp(-((E - E_SPIKE) / SIGMA) ** 2)


def effective(E):
    """有效产卵群体生物量 = 平衡生物量 − 局部额外死亡（不得为负）。"""
    return max(x_star(E) - bump(E), 0.0)


def yield_at(E):
    """捕捞产量（基于平衡生物量；局部额外死亡是保护约束，不计入产量优化）。"""
    return Q * E * x_star(E)


def y_max_analytic():
    """闭式 MSY：rK/4，对应努力度 E* = r/(2q)。"""
    return R * K / 4.0


def y_max_numeric(lo=0.0, hi=400.0, step=0.05):
    """**不依赖解析式**的独立算法：在 [0, r/q] 上细扫求产量最大值。"""
    best, at = -1.0, lo
    E = lo
    while E <= hi:
        v = yield_at(E)
        if v > best:
            best, at = v, E
        E += step
    return best, at


def stock_margin(E):
    """保护性口径下的余量：>0 表示该档位有效生物量低于下限（违反保护）。"""
    return B_MIN - effective(E)


def flip_margin_stock(E):
    """P5 用的翻转判据：有效生物量 − 下限；>0 表示高于下限（安全侧）。"""
    return effective(E) - B_MIN


def flip_yield(E):
    """P5 用的翻转判据：产量对努力的导数符号（零点即 MSY 努力度）。"""
    return Q * K * (1.0 - 2.0 * Q * E / R)


def scan_stock_margin(lo, hi, step=0.05):
    """在 [lo, hi] 上细扫求最坏（最大）余量及所在努力度。"""
    worst, at = -1e9, lo
    E = lo
    while E <= hi:
        m = stock_margin(E)
        if m > worst:
            worst, at = m, E
        E += step
    return worst, at


def nominal_margin(E):
    """标称口径余量（**不计**局部额外死亡）：>0 表示标称生物量低于下限。"""
    return B_MIN - x_star(E)


def scan_nominal_margin(lo, hi, step=0.05):
    """标称口径下的最坏余量——用于对照"有效口径才失守"。"""
    worst, at = -1e9, lo
    E = lo
    while E <= hi:
        m = nominal_margin(E)
        if m > worst:
            worst, at = m, E
        E += step
    return worst, at


def main():
    os.makedirs(OUT, exist_ok=True)

    yA = y_max_analytic()
    yB, eB = y_max_numeric()
    worst_m, worst_at = scan_stock_margin(0.0, 300.0)
    worst_m_lo, worst_at_lo = scan_stock_margin(0.0, E_NOW)
    worst_nom, worst_nom_at = scan_nominal_margin(0.0, 300.0)

    m = {
        "params": {"K": K, "r": R, "q": Q, "E_now": E_NOW, "B_min": B_MIN,
                   "E_spike": E_SPIKE, "amp": AMP, "sigma": SIGMA},
        "baseline": {"E": E_NOW, "x_now": x_star(E_NOW),
                     "yield_now": yield_at(E_NOW),
                     "verdict": "现状努力度 %g：产量 %g 吨/年，但存在局部不可续窗口" % (E_NOW, yield_at(E_NOW))},
        "msy": {"E_star_analytic": R / (2.0 * Q), "E_star_numeric": eB,
                "y_max_analytic": yA, "y_max_numeric": yB,
                "rel_diff": abs(yA - yB) / yA},
        "P1_dual_path": {"y_max_analytic": yA, "y_max_numeric": yB,
                         "rel_diff": abs(yA - yB) / yA},
        "pointwise": {
            "worst_margin": worst_m, "worst_margin_at": worst_at,
            "worst_margin_now": worst_m_lo, "worst_margin_now_at": worst_at_lo,
        },
        "caliber": {
            "eff_at_spike": effective(E_SPIKE),
            "nominal_at_spike": x_star(E_SPIKE),
        },
        "nominal": {
            "worst_margin": worst_nom,
            "worst_at": worst_nom_at,
            "margin_at_spike": nominal_margin(E_SPIKE),
        },
        "flip": {"E_star_yield": R / (2.0 * Q)},
        "limit": {"E0_yield": yield_at(0.0), "E400_x": x_star(400.0)},
        "result": {
            "recommend_E": R / (2.0 * Q),
            "yield_max": yA,
            "yield_now": yield_at(E_NOW),
            "gain_to_msy": yA - yield_at(E_NOW),
        },
    }

    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    print("== 渔业最大可持续产量 ==")
    print("  承载力 K=%g，内禀增长率 r=%g，可捕系数 q=%g" % (K, R, Q))
    print("  MSY = %.4f 吨/年 @ 努力度 E* = %.4f（船·年）" % (yA, R / (2 * Q)))
    print("  解析式 %.6f vs 细扫 %.6f，相对差 %.2e" % (yA, yB, abs(yA - yB) / yA))
    print("  现状努力度 E=%g：产量 %.4f 吨/年" % (E_NOW, yield_at(E_NOW)))
    print("  局部额外死亡带（中心 E=%g）：有效生物量在 E=%g 处降到 %.4f 吨（下限 %g）"
          % (E_SPIKE, E_SPIKE, effective(E_SPIKE), B_MIN))
    print("  全程最坏余量 %.4f @ E=%g（违反保护）" % (worst_m, worst_at))
    print("  数字来源：out/metrics.json（P7：禁止手抄）")
    return m


if __name__ == "__main__":
    main()
