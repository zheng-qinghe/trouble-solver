"""验证钩子：把"可检查的对象"交给通用检查器引擎。

**这个文件是"案例 ↔ 引擎"的唯一接口。**

引擎不知道库存、不知道报童模型、不知道促销——它只会按结论类型挑检查，
再回来调这里的函数。所以换一个领域时，改的是这个文件，**引擎一行都不用改**。

约定：这里的每个公开函数都是一个"钩子"，名字由 `ledger.spec.json` 的 `fn` 字段引用。
      检查器只认函数签名（`margin` / `f` / `g` / `samples` / `values` / `a` / `b`），
      不认它们内部是什么领域。
"""
from __future__ import annotations

import bisect
import math
import random
import statistics as st

import solve

SMALL_SAMPLE_CUT = 250.0      # 常态周 / 促销周的分界（与 solve.py 一致）
PROMO_MULT = 3.1


# ============================================================
# P1 双路径交叉：同一结论的两条**独立**实现
# ============================================================
def mean_via_stats():
    d, _ = solve.load_demand()
    return st.mean(d)


def mean_via_manual():
    """手写遍历求和——刻意不用 statistics，才算独立实现。"""
    d, _ = solve.load_demand()
    return sum(d) / len(d)


def baseline_profit_loop():
    """路径A：直接对 52 周逐周算利润求平均（solve.py 用的方式）。"""
    d, _ = solve.load_demand()
    return solve.expected_profit(solve.baseline_q(d), d, solve.L_STOCKOUT)


def baseline_profit_decomposition():
    """路径B：把期望利润拆成四个期望值再组合（完全不同的算式）。

        E[利润] = p·E[min(q,d)] + v·E[(q−d)⁺] − c·q − L·E[(d−q)⁺]
    """
    d, _ = solve.load_demand()
    q, n = solve.baseline_q(d), len(d)
    e_min = sum(min(q, x) for x in d) / n
    e_left = sum(max(q - x, 0.0) for x in d) / n
    e_short = sum(max(x - q, 0.0) for x in d) / n
    return (solve.P_PRICE * e_min + solve.V_SALVAGE * e_left
            - solve.C_COST * q - solve.L_STOCKOUT * e_short)


def q_by_fractile():
    """路径A：临界分位数闭式（解析）。"""
    d, _ = solve.load_demand()
    return solve.q_path_a(d, solve.L_STOCKOUT)


def q_by_enumeration():
    """路径B：对 Q ∈ [0, 产能] 逐点枚举（暴力，与解析式毫无共同代码）。"""
    d, _ = solve.load_demand()
    return solve.q_path_b(d, solve.L_STOCKOUT)[0]


# ============================================================
# P3 连续复核（以及"极值"类结论的 P1：两种求极值的方法）
# ============================================================
def profit_curve(q):
    """目标函数：给定备货量，返回周期望利润（检查器只把它当普通的 f(x)）。"""
    d, _ = solve.load_demand()
    return solve.expected_profit(float(q), d, solve.L_STOCKOUT)


def peak_by_enumeration():
    d, _ = solve.load_demand()
    return solve.q_path_b(d, solve.L_STOCKOUT)[1]


def peak_by_adversarial():
    """**不用枚举**求全局最优值：随机多起点 + 变步长爬山 + 局部精修。

    这条路径的意义：如果枚举因为上界写错或取值范围写错而漏掉了更优点，
    它与枚举的结论就会不一致——P1 会立刻把它抓出来。
    """
    from mm import checks
    lo, hi = 0.0, float(solve.Q_MAX)
    x, v = checks.adversarial_argmax(profit_curve, lo, hi, starts=256)
    for half in (0.5, 1e-3, 1e-6):
        xs = [min(hi, max(lo, x + half * (2 * i / 199 - 1))) for i in range(200)]
        ys = [profit_curve(t) for t in xs]
        k = max(range(200), key=lambda i: ys[i])
        if ys[k] > v:
            x, v = xs[k], ys[k]
    return v


# ============================================================
# P4 极限与量纲
# ============================================================
def limit_samples():
    """返回 [(参数值, 实测值, 期望退化值)]。

    ① 缺货惩罚 L → 0：临界分位数必须退化为经典报童比 (p−c)/(p−v)；
    ② 产能上界 → 10 倍：最优解不应改变（说明它不被上界截断，约束真的不起作用）。
    """
    d, _ = solve.load_demand()
    classic = (solve.P_PRICE - solve.C_COST) / (solve.P_PRICE - solve.V_SALVAGE)
    q_now = solve.q_path_b(d, solve.L_STOCKOUT)[0]
    big = 10 * solve.Q_MAX
    q_big = solve.q_path_b(d, solve.L_STOCKOUT, big)[0]
    return [(0.0, solve.fractile(0.0), classic),
            (float(big), float(q_big), float(q_now))]


# ============================================================
# P5 反例搜索 → 翻转边界（独立实现：确定性抽样的次序统计量）
# ============================================================
def mix_quantile_by_sample(promo_prob, level, normal, promo, n=4000):
    """与 `solve.mix_quantile`（对加权 CDF 做精确反演）**实现上完全独立**：

    这里按 promo_prob 的比例把两组合成一份确定性样本（固定置换，不用随机数），
    直接取次序统计量。两者算的是同一个量，但走的完全不是一条路。
    """
    rnd = random.Random(7)
    ns = sorted(normal)
    ps = sorted(promo)
    k = int(round(promo_prob * n))
    pick_n = [ns[rnd.randrange(len(ns))] for _ in range(n - k)]
    pick_p = [ps[rnd.randrange(len(ps))] for _ in range(k)]
    xs = sorted(pick_n + pick_p)
    idx = min(len(xs) - 1, max(0, int(math.ceil(level * len(xs))) - 1))
    return float(xs[idx])


def flip_margin(promo_prob):
    """翻转判据：最优订货量 − 基线订货量。>0 表示基线从"偏保守"变成"偏激进"。"""
    d, _ = solve.load_demand()
    q0 = solve.baseline_q(d)
    normal = [x for x in d if x < SMALL_SAMPLE_CUT]
    promo = [min(1200.0, x * PROMO_MULT) for x in normal]
    return (mix_quantile_by_sample(promo_prob, solve.fractile(solve.L_STOCKOUT),
                                   normal, promo) - q0)


def cover_assert_margin(_x=0.0):
    """占位：本案例没有全称断言类结论，P2 未触发（见 falsify.md 的显式声明）。"""
    return 0.0


# ============================================================
# P6 口径声明
# ============================================================
def caliber_basic():
    """样本统计量：并列出现的数字必须各自带口径。"""
    d, _ = solve.load_demand()
    cal = "实际售出量（截尾：缺货周的未满足需求未计入）"
    return [{"label": "52 周均值", "value": st.mean(d), "caliber": cal},
            {"label": "52 周中位数", "value": st.median(d), "caliber": cal},
            {"label": "52 周最大值", "value": max(d), "caliber": cal}]


def caliber_cross():
    """口径对照：这组数字**故意**来自两套口径的最优解，
    但都在同一个口径（口径B）下评估——所以它们可以相减，
    而这个差值就是"口径选错的代价"。"""
    d, _ = solve.load_demand()
    qa = solve.q_path_a(d, 0.0)
    qb = solve.q_path_a(d, solve.L_STOCKOUT)
    cal = "口径B：含缺货惩罚 %.0f 元/件，在口径B 下评估利润" % solve.L_STOCKOUT
    return [{"label": "按口径A 备货(%d 件)在口径B 下的利润" % qa,
             "value": solve.expected_profit(qa, d, solve.L_STOCKOUT), "caliber": cal},
            {"label": "按口径B 备货(%d 件)在口径B 下的利润" % qb,
             "value": solve.expected_profit(qb, d, solve.L_STOCKOUT), "caliber": cal}]
