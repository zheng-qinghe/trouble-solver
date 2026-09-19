"""验证钩子（案例：园区步道照明覆盖）。

同一套引擎、同一套检查器——这里只做"把可检查的对象交出去"这件事。
注意钩子里没有一处提到库存、报童、促销：领域知识全在本文件，**引擎不需要知道**。

本案例的结论类型覆盖了：全称断言 / 最优性 / 稳健性 / 口径相关 ——
与案例 A 的 统计量 / 等式 / 极值 完全不同的组合，走的是同一张 `REQUIRED_BY_KIND` 表。
"""
from __future__ import annotations

import solve

# ------------------------------------------------------------
# P2 全称断言：∀x ∈ [0, L]，x 被某根灯杆照亮
#   约定 margin(x) > 0 表示该点违反（离最近灯杆比照明半径还远）
# ------------------------------------------------------------


def cover_margin_rated(x):
    """按**出厂标称半径**判：现状布点是否照亮全长。"""
    return solve.nearest_gap(x, solve.stations(solve.N_NOW)) - solve.R_RATED


def cover_margin_aged(x):
    """按**实测光衰半径**判：同一组布点是否还照得亮。

    这个函数就是本案例的主角：违例带只有 0.067 m 宽（约 7 cm），
    任何固定网格都可能整段跳过它——P2 的对抗搜索会把它揪出来。
    """
    return solve.nearest_gap(x, solve.stations(solve.N_NOW)) - solve.R_AGED


def cover_margin_plan8(x):
    """拟采用的 8 点方案在新半径下的裕度——用来确认"它也恰好是零余量"。

    这不是废话：它说明"把点加密到刚好够"同样没有工程余量，
    结论必须写成"要么留裕度、要么按有效口径折算"。
    """
    return solve.nearest_gap(x, solve.stations(8)) - solve.r_needed_from_layout(solve.stations(8))


# ------------------------------------------------------------
# P1 双路径：同一结论的两条独立实现
# ------------------------------------------------------------
def r_needed_analytic_7():
    """路径A：解析式 L/(2(n−1))。"""
    return solve.r_needed_analytic(solve.N_NOW)


def r_needed_scan_7():
    """路径B：完全不用解析式，直接在 [0, L] 上细扫找最坏点。"""
    return solve.r_needed_by_scan(solve.N_NOW, step=0.01)


def r_needed_analytic_8():
    return solve.r_needed_analytic(8)


def r_needed_scan_8():
    return solve.r_needed_by_scan(8, step=0.01)


# ------------------------------------------------------------
# P3 连续复核：把"布点整体偏移"当连续变量检验（等间距是否真的是最优）
# ------------------------------------------------------------
def neg_radius_after_shift(t):
    """目标函数：取负的所需半径（把"最小化半径"变成"最大化 −半径"）。

    为什么这样测：如果等间距是最优的，那么任何整体偏移都只会让所需半径变大；
    这个函数还能顺带给出"偏移多少会开始明显变差"——也就是施工偏差的容忍度。
    """
    return -solve.r_needed_uniform_shift(solve.N_NOW, t)


def neg_radius_after_shift_8(t):
    """同上，但对拟采用的 8 点方案。"""
    return -solve.r_needed_uniform_shift(8, t)


# ------------------------------------------------------------
# P4 极限与量纲
# ------------------------------------------------------------
def limit_samples():
    """① 只剩 2 根灯杆：退化为"单段覆盖"，半径必须是全长的一半；
       ② 灯杆足够多（11 根）时，半径必须严格小于 3 根灯杆时的一半（单调性+可算）。"""
    return [(2.0, solve.r_needed_analytic(2), solve.L / 2.0),
            (11.0, solve.r_needed_analytic(11), solve.L / 20.0)]


# ------------------------------------------------------------
# P5 翻转边界
# ------------------------------------------------------------
_WORST_GAP = {}


def _worst_gap(n):
    """现状布点的最坏点距离——与 r 无关，所以缓存（否则二分 80 次要重扫 80 遍）。"""
    if n not in _WORST_GAP:
        _WORST_GAP[n] = solve.r_needed_by_scan(n, step=0.05)
    return _WORST_GAP[n]


def flip_margin_r(r):
    """半径的翻转判据：给定半径 r，最坏点的缺口。>0 表示覆盖被打破。"""
    return _worst_gap(solve.N_NOW) - r


def flip_margin_n(n):
    """灯杆数量的翻转判据：在采购半径上限约束下，n 根灯杆是否够用。"""
    return solve.r_needed_analytic(n) - solve.R_TARGET


# ------------------------------------------------------------
# P6 口径
# ------------------------------------------------------------
def caliber_geo_vs_eff():
    """口径对照：同一套布点，几何口径与有效口径要买的灯杆半径完全不同。

    这一组数字**故意**来自两套口径，所以必须各自标口径、并列报出、不许相减。
    """
    return [
        {"label": "n=7 几何所需半径", "value": solve.r_needed_analytic(solve.N_NOW),
         "caliber": "几何口径：按照明半径的几何边界判定覆盖"},
        {"label": "n=7 有效口径所需标称半径", "value": solve.r_needed_analytic(solve.N_NOW) / solve.EFF_RATIO,
         "caliber": "有效口径：标称半径 × %.1f 折减后才算有效覆盖" % solve.EFF_RATIO},
    ]
