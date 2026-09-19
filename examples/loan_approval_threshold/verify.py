"""验证钩子（案例：消费信贷审批阈值）。

同一套引擎、同一套检查器——这里只把"可检查的对象"交出去。
钩子里没有一处提到库存、报童、覆盖：领域知识全在本文件，**引擎不需要知道**。

本案例的结论类型覆盖了：全称断言 / 极值 / 稳健性 / 口径相关 ——
与案例 A（统计量/等式/极值）、案例 B（全称断言/覆盖/极限）不同的组合，走同一张 REQUIRED_BY_KIND 表。
"""
from __future__ import annotations

import solve
from troublesolver import checks


# ------------------------------------------------------------
# P2 全称断言：∀s ≥ T，违约率(s) ≤ CAP
#   约定 margin(s) = CAP − 违约率(s)；margin < 0 表示该客户越上限（越大越坏用负值）
#   这里给"越上限"判据：default_rate(s) − CAP > 0 表示违反；
#   为与 P2 约定（margin>0 违反）一致，钩子返回 违约率 − CAP。
# ------------------------------------------------------------
def default_margin(s):
    """评分 s 的越上限裕度：>0 表示违约率超过上限（违反断言）。"""
    return solve.default_rate(s) - solve.CAP


# ------------------------------------------------------------
# P1 双路径：最坏违约率的两种独立求法
# ------------------------------------------------------------
def worst_rate_analytic():
    """路径A：已知窄带中心即解析尖峰位置，直接代入模型。"""
    return solve.default_rate(solve.BUMP_CENTER)


def worst_rate_adversarial():
    """路径B：**完全不假设**窄带在哪，在全评分域上对抗搜索求最大值。"""
    x, v = checks.adversarial_argmax(solve.default_rate, solve.SCORE_LO, solve.SCORE_HI,
                                     starts=256, refine=3)
    return v


def default_rate_curve(s):
    """目标函数：给定评分返回违约率（检查器只把它当普通的 f(x) 做连续复核）。"""
    return solve.default_rate(s)


# ------------------------------------------------------------
# P5 翻转边界：阈值 T 从"仍有客户越上限"翻到"全部满足"
# ------------------------------------------------------------
def flip_threshold(T):
    """g(T) = min_{s≥T}(CAP − 违约率(s))；g<0 表示 T 下仍有客户越上限。"""
    return solve.min_margin_over(T, solve.SCORE_HI)[0]


# ------------------------------------------------------------
# P6 口径声明
# ------------------------------------------------------------
def caliber_two():
    """同一阈值下两种违约口径：30 天逾期（低估）vs 90 天违约（含核销）。"""
    return [
        {"label": "30 天逾期口径坏账率", "value": solve.default_rate(solve.T_REC) * 0.7,
         "caliber": "30 天逾期，未含已核销，低估真实损失"},
        {"label": "90 天违约口径坏账率", "value": solve.default_rate(solve.T_REC),
         "caliber": "90 天违约，含已核销，本模型采用"},
    ]


def caliber_avg_vs_point():
    """同一阈值下两种"是否安全"口径：组合平均 vs 逐点最坏。"""
    return [
        {"label": "组合平均口径平均违约率(T=%g)" % solve.T_NOW,
         "value": solve.population_avg_default(solve.T_NOW),
         "caliber": "均匀人群加权平均，稀释了局部窄带"},
        {"label": "逐点最坏口径最大违约率(T=%g)" % solve.T_NOW,
         "value": solve.max_default_rate(solve.T_NOW, solve.SCORE_HI)[0],
         "caliber": "最不利单客户违约率，保留局部窄带"},
    ]
