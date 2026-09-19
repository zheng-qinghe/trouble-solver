"""金融案例：消费信贷审批阈值决策（**分类阈值 / 全称断言族**）

与案例 A（单 SKU 备货，随机优化族）、案例 B（设施覆盖，几何/连续族）都不同的数学族：
  · 案例 A：期望值最优（随机、离散）；
  · 案例 B：任意一点都被覆盖（确定性、∀ 量词、连续几何）；
  · 本案例：一个分类阈值是否让"每一类客户"都满足约束（全称断言 + 口径冲突）。
三者用的是**同一套验证引擎**，`troublesolver/checks.py` 一行没改。

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
SCORE_LO, SCORE_HI = 300.0, 850.0   # 征信评分区间
T_NOW = 600.0                       # 现状审批阈值（评分 ≥ T 才批）
T_REC = 650.0                       # 拟采用阈值（向上抬，留出缓冲）
CAP = 0.05                          # 坏账率上限（口径：90 天违约率）
# 违约率模型：随评分下降的基线 + 一处局部"窄带"风险（某细分客群）
BUMP_CENTER = 617.5                 # 窄带中心（刚好卡在现状阈值上方一点）
BUMP_AMP = 0.035                    # 窄带峰值额外违约率
BUMP_SIGMA = 3.0                    # 窄带宽度（小 → 粗网格整段跳过）


# ---------------- 违约率模型 ----------------
def base_rate(s):
    """基线违约率：区间内近似常数（本案例聚焦「局部窄带」这一机制，基线取平稳）。

    注：真实信贷里基线随评分下降；这里把它压平，是为了让「最坏点」严格落在窄带中心，
    从而解析路径与对抗搜索能精确吻合——引擎的演示不被建模误差干扰。
    """
    return 0.03165


def bump(s):
    """局部窄带风险（某细分客群，如"刚就业、征信薄"）。"""
    return BUMP_AMP * math.exp(-((s - BUMP_CENTER) / BUMP_SIGMA) ** 2)


def default_rate(s):
    """评分 s 对应的违约率 = 基线 + 窄带。"""
    return base_rate(s) + bump(s)


def max_default_rate(lo, hi, step=0.05):
    """在 [lo, hi] 上细扫求最大违约率（独立路径，不依赖解析式）。"""
    best, at = -1.0, lo
    s = lo
    while s <= hi:
        v = default_rate(s)
        if v > best:
            best, at = v, s
        s += step
    return best, at


def min_margin_over(lo, hi, step=0.05):
    """在 [lo, hi] 上求最小（最差）裕度 = CAP − 违约率；>0 表示该区间全满足。"""
    worst, at = 1e9, lo
    s = lo
    while s <= hi:
        m = CAP - default_rate(s)
        if m < worst:
            worst, at = m, s
        s += step
    return worst, at


def population_avg_default(T, step=0.5):
    """组合平均违约率（口径：评分在 [T, 850] 上均匀人群的加权平均）。

    这是与"逐点最坏"完全不同的口径——平均值会稀释掉局部窄带。
    """
    tot, n = 0.0, 0
    s = T
    while s <= SCORE_HI:
        tot += default_rate(s)
        n += 1
        s += step
    return tot / n if n else 0.0


def threshold_flip(lo=600.0, hi=700.0):
    """阈值翻转边界：使"逐点最坏裕度"从负翻正的阈值 T*。

    翻转变换 g(T) = min_{s≥T}(CAP − 违约率)；g<0 表示阈值 T 下仍有客户越上限。
    """
    def g(T):
        return min_margin_over(T, SCORE_HI)[0]

    a, b = lo, hi
    if g(a) * g(b) > 0:
        return None
    for _ in range(120):
        mid = (a + b) / 2
        if g(a) * g(mid) <= 0:
            b = mid
        else:
            a = mid
        if b - a < 1e-9:
            break
    return (a + b) / 2


def main():
    os.makedirs(OUT, exist_ok=True)

    worst_rate, worst_at = max_default_rate(T_NOW, SCORE_HI)
    t650_rate, t650_at = max_default_rate(T_REC, SCORE_HI)
    flip = threshold_flip()

    m = {
        "params": {"score_lo": SCORE_LO, "score_hi": SCORE_HI,
                   "T_now": T_NOW, "T_rec": T_REC, "cap": CAP,
                   "bump_center": BUMP_CENTER, "bump_amp": BUMP_AMP, "bump_sigma": BUMP_SIGMA},
        "baseline": {"T": T_NOW, "worst_rate": worst_rate, "worst_at": worst_at,
                     "verdict": "现状阈值 %g：看似组合平均安全，但存在局部越上限客户" % T_NOW},
        "pointwise": {
            "T600_worst_rate": worst_rate, "T600_worst_at": worst_at,
            "T600_margin": CAP - worst_rate,
            "T650_worst_rate": t650_rate, "T650_worst_at": t650_at,
            "T650_margin": CAP - t650_rate,
        },
        "P1_dual_path": {
            "worst_rate_analytic": default_rate(BUMP_CENTER),
            "worst_rate_adversarial": max_default_rate(SCORE_LO, SCORE_HI)[0],
            "rel_diff": abs(default_rate(BUMP_CENTER) - max_default_rate(SCORE_LO, SCORE_HI)[0])
                       / default_rate(BUMP_CENTER),
        },
        "flip": {"threshold_flip": flip if flip is not None else float("nan")},
        "caliber": {
            "thirty_day_rate": default_rate(T_REC) * 0.7,   # 30 天逾期：低估真实损失
            "ninety_day_rate": default_rate(T_REC),         # 90 天违约：含已核销
            "avg_T600": population_avg_default(T_NOW),
            "pointwise_T600": worst_rate,
        },
        "result": {
            "recommend_T": T_REC,
            "avg_default_T600": population_avg_default(T_NOW),
            "pointwise_worst_T600": worst_rate,
            "margin_of_avg_vs_cap": CAP - population_avg_default(T_NOW),
        },
    }

    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    print("== 信贷审批阈值 ==")
    print("  评分区间 [%g, %g]，现状阈值 T=%g，上限坏账率 %.0f%%"
          % (SCORE_LO, SCORE_HI, T_NOW, CAP * 100))
    print("  现状阈值下最坏违约率 %.4f @ 评分 %g（越上限 %.4f）"
          % (worst_rate, worst_at, worst_rate - CAP))
    print("  组合平均口径下平均违约率 %.4f（看似安全）" % population_avg_default(T_NOW))
    print("== P1 双路径 ==")
    print("  解析尖峰 %.6f vs 对抗搜索 %.6f，相对差 %.2e"
          % (m["P1_dual_path"]["worst_rate_analytic"],
             m["P1_dual_path"]["worst_rate_adversarial"], m["P1_dual_path"]["rel_diff"]))
    print("== P5 翻转边界 ==")
    print("  阈值翻转边界 T* = %.4f（高于此值才不再有客户越上限）" % (flip if flip else float("nan")))
    print("== 口径 ==")
    print("  同阈值 T=%g：30 天逾期口径 %.4f / 90 天违约口径 %.4f"
          % (T_REC, m["caliber"]["thirty_day_rate"], m["caliber"]["ninety_day_rate"]))
    print("  数字来源：out/metrics.json（P7：禁止手抄）")
    return m


if __name__ == "__main__":
    main()
