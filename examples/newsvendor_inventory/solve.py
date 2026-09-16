"""业务案例：单 SKU 每周备货量决策（报童模型）

演示本 agent 的完整闭环：基线 → 解析/数值双路径 → 连续复核 → 反例搜索 → 口径对照 → 台账。
所有对外数字写入 out/metrics.json（P7：禁止手抄）。

运行： python solve.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics as st
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
LEDGER = os.path.join(HERE, "ledger.json")

# ---- 问题说明书里确认下来的参数（见 charter.md）----
P_PRICE = 25.0      # 售价（元/件）
C_COST = 14.0       # 进价（元/件）
V_SALVAGE = 6.0     # 滞销处理价（元/件）
L_STOCKOUT = 8.0    # 缺货惩罚（元/件）：口径B"含客户流失"；口径A 取 0
Q_MAX = 500         # 供应商周产能（硬约束，charter §4）


# ============ 数据 ============
@lru_cache(maxsize=1)          # 检查器会反复调用目标函数，数据只读一次
def load_demand():
    with open(os.path.join(HERE, "data", "demand.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [float(r["demand"]) for r in rows], [r.get("note", "") == "promo" for r in rows]


# ============ 期望利润 ============
def weekly_profit(q, d, L=L_STOCKOUT):
    """单周利润：售出收入 + 滞销残值 − 进货成本 − 缺货惩罚"""
    sold = min(q, d)
    leftover = max(q - d, 0.0)
    short = max(d - q, 0.0)
    return P_PRICE * sold + V_SALVAGE * leftover - C_COST * q - L * short


def expected_profit(q, demands, L=L_STOCKOUT):
    return sum(weekly_profit(q, d, L) for d in demands) / len(demands)


# ============ 基线（现状做法）============
def baseline_q(demands):
    return int(round(st.mean(demands) * 1.2))


# ============ 路径 A：临界分位数（解析）============
def fractile(L):
    return (P_PRICE - C_COST + L) / (P_PRICE - V_SALVAGE + L)


def quantile(sorted_d, level, continuous=False):
    """经验分位数；continuous=True 时用线性插值（把阶梯函数连续化）"""
    n = len(sorted_d)
    if n == 0:
        return 0.0
    h = level * (n - 1)
    lo = int(math.floor(h))
    hi = min(lo + 1, n - 1)
    if continuous:
        return sorted_d[lo] + (h - lo) * (sorted_d[hi] - sorted_d[lo])
    return float(sorted_d[lo])


def q_path_a(demands, L=L_STOCKOUT):
    return int(round(quantile(sorted(demands), fractile(L), continuous=True)))


# ============ 路径 B：数值最大化（独立实现）============
def q_path_b(demands, L=L_STOCKOUT, hi=Q_MAX):
    best_q, best_v = 0, -1e18
    for q in range(0, hi + 1):
        v = expected_profit(float(q), demands, L)
        if v > best_v:
            best_q, best_v = q, v
    return best_q, best_v


# ============ 促销混合分布（P5 反例搜索用）============
def mixture_demands(demands, promo_prob, promo_mult=3.1, seed=7):
    """把"促销周会发生"显式建成混合分布：以 promo_prob 的概率落入促销档。"""
    import random
    rnd = random.Random(seed)
    normal = [d for d in demands if d < 250]        # 剔除样本里那唯一促销周
    promo = [min(1200.0, d * promo_mult) for d in normal]
    out = []
    for _, dn, dp in zip(range(20000), normal * 200, promo * 200):
        out.append(dp if rnd.random() < promo_prob else dn)
        if len(out) >= 20000:
            break
    return out


# ============ P5 精修：连续翻转边界 ============
def mix_quantile(promo_prob, level, normal, promo):
    """促销混合分布的**精确**分位数：对加权 CDF 做反演（不抽样，所以是连续可微的）。

    与上面 P5 的"6 档离散扫描"是两套口径：
      · 离散档位回答"哪个扫描档位上翻了"（工程上够用，但答案被档位宽度锁死）；
      · 本函数回答"翻转点到底在哪"（连续），才配写进"失效边界"。
    **两者口径不同，不得互相替代或相减。**
    """
    import bisect
    ns, ps = sorted(normal), sorted(promo)
    lo, hi = min(ns[0], ps[0]), max(ns[-1], ps[-1])

    def cdf(x):
        return ((1 - promo_prob) * bisect.bisect_right(ns, x) / len(ns)
                + promo_prob * bisect.bisect_right(ps, x) / len(ps))

    for _ in range(80):
        mid = (lo + hi) / 2
        if cdf(mid) < level:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def flip_boundary(demands, q0, L=L_STOCKOUT, lo=0.0, hi=0.6):
    """二分找"基线偏保守 → 偏激进"的连续翻转边界。

    判据函数 g(p) = 该促销概率下的最优订货量 − 基线订货量；
    g 关于 p 单调增，故可在 [lo, hi] 上二分。
    """
    normal = [d for d in demands if d < 250]          # 常态周
    promo = [min(1200.0, d * 3.1) for d in normal]    # 促销档（与 solve 主流程同构）
    level = fractile(L)

    def g(p):
        return mix_quantile(p, level, normal, promo) - q0

    if g(lo) * g(hi) > 0:
        return None
    a, b = lo, hi
    for _ in range(120):
        m = (a + b) / 2
        if g(a) * g(m) <= 0:
            b = m
        else:
            a = m
        if b - a < 1e-12:
            break
    return (a + b) / 2


def main():
    demands, is_promo = load_demand()
    n = len(demands)
    sorted_d = sorted(demands)
    os.makedirs(OUT, exist_ok=True)

    m = {"n_weeks": n, "mean": st.mean(demands), "median": st.median(demands),
         "min": min(demands), "max": max(demands),
         "n_promo_weeks": sum(is_promo),
         "params": {"p": P_PRICE, "c": C_COST, "v": V_SALVAGE,
                    "L_caliberA": 0.0, "L_caliberB": L_STOCKOUT, "Q_max": Q_MAX}}

    # ---- 基线 ----
    q0 = baseline_q(demands)
    m["baseline"] = {"Q": q0,
                     "profit_caliberB": expected_profit(q0, demands, L_STOCKOUT),
                     "profit_caliberA": expected_profit(q0, demands, 0.0)}

    # ---- P1 双路径 ----
    qa = q_path_a(demands, L_STOCKOUT)
    qb, vb = q_path_b(demands, L_STOCKOUT)
    vA_at_qa = expected_profit(qa, demands, L_STOCKOUT)
    m["P1_dual_path"] = {
        "critical_fractile_caliberB": fractile(L_STOCKOUT),
        "critical_fractile_caliberA": fractile(0.0),
        "Q_pathA_fractile": qa, "Q_pathB_numeric": qb,
        "profit_pathA": vA_at_qa, "profit_pathB": vb,
        "rel_diff_profit": abs(vA_at_qa - vb) / abs(vb),
        "verdict": "两路径在利润口径下等价（差 <0.1%）" if abs(vA_at_qa - vb) / abs(vb) < 1e-3
                   else "两路径结论不一致，需排查",
    }

    # ---- P3 连续复核：最优值不是单点，而是一个区间 ----
    best_cont = expected_profit(float(qb), demands, L_STOCKOUT)
    band = [q for q in range(0, Q_MAX + 1)
            if expected_profit(float(q), demands, L_STOCKOUT) >= best_cont * (1 - 1e-3)]
    smoothed_q = quantile(sorted_d, fractile(L_STOCKOUT), continuous=True)
    m["P3_continuous"] = {
        "Q_discrete_opt": qb,
        "Q_continuous_quantile": smoothed_q,
        # 键名里禁止出现点号（会把 {{m.路径}} 占位符切断），故写成 0p1
        "profit_band_0p1pct": [min(band), max(band)] if band else None,
        "note": "样本含 1 个促销异常周，经验分位数落在两个样本之间；应报区间而非单点",
    }

    # ---- P5 反例搜索：促销概率改变时，最优订货量是否翻转 ----
    scan = []
    for pi in (0.02, 0.05, 0.10, 0.15, 0.25, 0.40):
        dd = mixture_demands(demands, pi)
        q_opt, _ = q_path_b(dd, L_STOCKOUT)
        scan.append({"promo_prob": pi, "Q_opt": q_opt,
                     "Q_opt_vs_baseline": q_opt - q0})
    flip = next((s["promo_prob"] for s in scan if s["Q_opt_vs_baseline"] > 0), None)
    fb = flip_boundary(demands, q0, L_STOCKOUT)
    m["P5_counterexample"] = {
        "scan": scan,
        "flip_point": flip,                 # 离散档口径：哪个扫描档位上翻了
        "flip_boundary_cont": fb,           # 连续口径：翻转点到底在哪（P5 精修）
        "reading": ("促销概率低于 %s 时，基线（均值×1.2）偏保守；高于它则偏激进——"
                    "基线的对错完全取决于促销是否会发生"
                    % ("%.4f" % fb if fb is not None else "—")),
    }

    # ---- P6 口径对照：缺货惩罚怎么算，直接改变最优解 ----
    qA = q_path_a(demands, 0.0)
    qB = qa
    # 口径选错的代价：按 A 备货、真实成本结构是 B 时，每周期望利润的损失（正数 = 损失）
    loss_if_wrong = (expected_profit(qB, demands, L_STOCKOUT)
                     - expected_profit(qA, demands, L_STOCKOUT))
    m["P6_caliber"] = {
        "Q_caliberA_L0": qA, "Q_caliberB_L8": qB,
        "Q_diff": qB - qA,
        "weekly_loss_if_use_A_but_true_is_B": loss_if_wrong,
        "annual_loss_if_use_A_but_true_is_B": loss_if_wrong * 52,
    }

    # ---- 结论与改善 ----
    gain = expected_profit(qB, demands, L_STOCKOUT) - expected_profit(q0, demands, L_STOCKOUT)
    m["result"] = {
        "recommend_Q": qB,
        "Q_vs_baseline": qB - q0,
        "gain_vs_baseline_per_week": gain,
        "gain_vs_baseline_annual": gain * 52,
        "gain_vs_baseline_pct": gain / expected_profit(q0, demands, L_STOCKOUT) * 100,
    }

    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    # ---- 打印（正文数字一律来自上面这份 JSON）----
    print("== 数据 ==")
    print("  周期数 %d，均值 %.1f，中位 %.1f，最大 %.0f（促销周 %d 个）"
          % (n, m["mean"], m["median"], m["max"], m["n_promo_weeks"]))
    print("== 基线（现状：均值×1.2）==")
    print("  Q0 = %d，周期望利润（口径B） %.2f 元" % (q0, m["baseline"]["profit_caliberB"]))
    print("== P1 双路径 ==")
    print("  临界分位数（口径B） %.4f  →  路径A Q=%d；路径B Q=%d；利润相对差 %.2e"
          % (m["P1_dual_path"]["critical_fractile_caliberB"], qa, qb,
             m["P1_dual_path"]["rel_diff_profit"]))
    print("  判定：%s" % m["P1_dual_path"]["verdict"])
    print("== P3 连续复核 ==")
    print("  最优 Q 的 0.1%% 平台区间 = %s（连续分位数 %.2f）"
          % (m["P3_continuous"]["profit_band_0p1pct"], smoothed_q))
    print("== P5 反例搜索（促销概率改变，最优解是否翻转）==")
    for s in scan:
        print("  促销概率 %4.0f%% → 最优 Q=%3d（相对基线 %+d）"
              % (s["promo_prob"] * 100, s["Q_opt"], s["Q_opt_vs_baseline"]))
    print("  翻转点：促销概率 %s" % m["P5_counterexample"]["flip_point"])
    print("== P6 口径对照 ==")
    print("  口径A（L=0）最优 Q=%d；口径B（L=8）最优 Q=%d；差 %d 件"
          % (qA, qB, qB - qA))
    print("  若按口径A备货、而真实成本结构是口径B：每周损失 %.2f 元（年化 %.0f 元）"
          % (loss_if_wrong, loss_if_wrong * 52))
    print("== 结论 ==")
    print("  建议 Q* = %d 件/周；相对现状基线每周多赚 %.2f 元（+%.1f%%）"
          % (qB, gain, m["result"]["gain_vs_baseline_pct"]))
    print("  数字来源：out/metrics.json（P7：禁止手抄）")
    return m


if __name__ == "__main__":
    main()
