"""可执行检查器：与领域无关的验证动作（泛化的核心）。

## 为什么这是"泛化"

引擎**不认识你的领域**。它只认识「结论类型」——极值、全称断言、最优性、极限……
而"这类结论该怎么验"是与领域无关的知识。案例通过 `verify.py` 里的钩子函数
把可检查的对象交给引擎，于是：

    **加一个全新领域的难题 = 写解算脚本 + 声明结论类型 + 暴露几个钩子**
    引擎一行不用改。

## 反过来，说清楚什么**不能**泛化

"这个难题该用什么数学、怎么建模"穷举不了——那是模型与人的活。
能穷举、能沉淀、能交给机器的是它的对偶问题：**怎么知道它是对的**。
本模块只做后一件事，所以它能泛化；不要把它扩成"自动解题器"，
那会立刻退化成又一个"AI 写论文"。

## 三条与领域无关的能力

1. **对抗式最坏点搜索**（不是网格扫描）——这是 P2 的执行体：
   粗网格会整段跳过窄违例带，引擎会自动把"粗网格结论"和"对抗搜索结论"对账，
   **只要两者不一致就报警**（窄带陷阱的自动检测）。
2. **翻转边界二分**——P5 的执行体：不满足于"找到了一个反例"，
   直接给出参数空间里的翻转点。
3. **结论类型 → 必跑检查矩阵**——`REQUIRED_BY_KIND`：
   标了 verified 的结论，如果它这一类该跑的检查没跑，**直接报错**，
   不许自称已验证。
"""
from __future__ import annotations

import inspect
import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ============================================================
# 一、结论类型 → 必跑检查（泛化知识：与领域无关，可积累、可评审）
# ============================================================
# 依据：每类结论有它自己的"典型失效模式"，必须用对应的手段去打。
REQUIRED_BY_KIND: Dict[str, List[str]] = {
    # 结论类型            必跑        典型失效模式 → 对应手段
    "等式":       ["P1"],            # 单条推导写错 → 双路径交叉
    "恒等式":     ["P1", "P4"],      # 边界情形不成立 → 极限检验
    "极值":       ["P1", "P3"],      # 极值在窄峰上，网格取不到 → 连续复核
    "最优性":     ["P1", "P3", "P5"],# 局部最优冒充全局最优 → 反例搜索
    "全称断言":   ["P2", "P5"],      # 粗采样跳过窄违例带 → 对抗搜索+翻转边界
    "覆盖":       ["P2", "P3", "P5"],# 同上，且最坏点在边界上 → 加连续复核
    "存在性":     ["P5"],            # 只在特定区域存在 → 边界搜索
    "唯一性":     ["P4", "P5"],      # 退化情形下多重解 → 极限+边界
    "极限":       ["P4"],            # 收敛但不退化到已知结果 → 极限检验
    "单调性":     ["P1", "P5"],      # 区间内反向 → 边界搜索
    "单调":       ["P1", "P5"],
    "稳健性":     ["P5"],            # 扰动下翻转 → 翻转边界
    "统计量":     ["P6"],            # 口径混用（数字可复算由 P7 兜底）
    "预测":       ["P5", "P6"],      # 样本外失效 + 口径外推
    "口径相关":   ["P6"],
}
ALL_PROTOCOLS = ("P1", "P2", "P3", "P4", "P5", "P6", "P7")


class CheckError(Exception):
    pass


@dataclass
class Result:
    protocol: str
    name: str
    passed: bool
    detail: str
    worst: Optional[float] = None
    worst_at: Optional[float] = None
    flipped: bool = False          # 粗网格与对抗搜索结论不一致（窄带陷阱）

    def line(self) -> str:
        mark = "通过" if self.passed else "不通过"
        return "[%s] %s：%s —— %s" % (self.protocol, self.name, mark, self.detail)


# ============================================================
# 二、与领域无关的搜索工具（引擎不假设任何函数形态）
# ============================================================
def _linspace(lo: float, hi: float, n: int) -> List[float]:
    if n == 1:
        return [lo]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def grid_argmax(f: Callable[[float], float], lo: float, hi: float, n: int
                ) -> Tuple[float, float, int]:
    """固定网格取最大（这就是"粗步长扫描"——会骗人的那种）。"""
    xs = _linspace(lo, hi, n)
    vals = [f(x) for x in xs]
    k = max(range(n), key=lambda i: vals[i])
    return xs[k], vals[k], n


def adversarial_argmax(f: Callable[[float], float], lo: float, hi: float,
                       starts: int = 96, iters: int = 200, seed: int = 12345,
                       refine: int = 2) -> Tuple[float, float]:
    """对抗式最坏点搜索：均匀扫描 → 多起点爬山 → 局部多分辨率精修。

    刻意**不完全依赖网格**：固定网格会整段跳过窄违例带（实战里 3° 步长跳过了宽 2° 的违例带）。
    做法：
      1. 先在整个区间上**均匀扫描** starts 个点（确定性，不用随机数，结果可复现）；
      2. 取最好的 8 个点各自做变步长爬山（这一步能在**有坡度**的窄峰上精确收敛）；
      3. 在全局最优点附近再叠 refine 层逐步缩小的细网格。

    ⚠️ **诚实的边界**：有限预算的搜索**无法保证**找到任意窄的特征。
    如果目标是"平台上一个孤立的、无坡度的窄尖峰"，爬山没有梯度可用，只能靠扫描分辨率。
    所以调用方必须把搜索分辨率一起报出来（见 `p2_universal` 的 detail），
    并把"未找到"读作"在该分辨率下未找到"，而不是"不存在"。
    """
    span = hi - lo
    xs = _linspace(lo, hi, starts)
    vals = [f(x) for x in xs]
    order = sorted(range(starts), key=lambda i: -vals[i])[:8]
    best_x, best_v = xs[order[0]], vals[order[0]]
    for i in order:
        x, v = _climb(f, xs[i], vals[i], lo, hi, iters)
        if v > best_v:
            best_x, best_v = x, v
    step = span / max(starts - 1, 1)
    for _ in range(refine):
        step /= 5.0
        a, b = max(lo, best_x - 3 * step), min(hi, best_x + 3 * step)
        for x in _linspace(a, b, 25):
            v = f(x)
            if v > best_v:
                best_x, best_v = x, v
    return best_x, best_v


def _climb(f, x, v, lo, hi, iters, span_hint=None):
    """从 (x, v) 出发的变步长爬山（步长只缩不放，保证收敛）。"""
    lo, hi = float(lo), float(hi)
    step = max((hi - lo) / 64.0, 1e-12)
    for _ in range(iters):
        improved = False
        for dx in (step, -step):
            xn = min(hi, max(lo, x + dx))
            if xn == x:
                continue
            vn = f(xn)
            if vn > v:
                x, v, improved = xn, vn, True
        if not improved:
            step *= 0.5
            if step < (hi - lo) * 1e-15:
                break
    return x, v


def search_resolution(lo: float, hi: float, starts: int) -> float:
    """均匀扫描的名义分辨率——这个数字必须跟着结论一起交出去。"""
    return (hi - lo) / max(starts - 1, 1)


def adversarial_argmax_nd(f: Callable[[Sequence[float]], float],
                          bounds: Sequence[Tuple[float, float]],
                          starts: int = 240, iters: int = 60, seed: int = 12345
                          ) -> Tuple[List[float], float]:
    """多维对抗搜索：随机撒点 + 坐标方向变步长爬山（用于搜索"布点是否可以更优"）。"""
    rnd = random.Random(seed)
    dim = len(bounds)
    def clip(p):
        return [min(bounds[i][1], max(bounds[i][0], p[i])) for i in range(dim)]

    best_p = clip([(lo + hi) / 2 for lo, hi in bounds])
    best_v = f(best_p)
    for _ in range(starts):
        p = clip([bounds[i][0] + (bounds[i][1] - bounds[i][0]) * rnd.random()
                  for i in range(dim)])
        v = f(p)
        if v > best_v:
            best_p, best_v = p, v
    p, v = list(best_p), best_v
    steps = [(hi - lo) / math.sqrt(dim) / 8 for lo, hi in bounds]
    for _ in range(iters):
        improved = False
        for i in range(dim):
            for sgn in (1, -1):
                q = list(p)
                q[i] = p[i] + sgn * steps[i]
                q = clip(q)
                if q == p:
                    continue
                vq = f(q)
                if vq > v:
                    p, v, improved = q, vq, True
        if not improved:
            steps = [s * 0.5 for s in steps]
            if min(steps) < 1e-13:
                break
    return p, v


def bisect_flip(f: Callable[[float], float], lo: float, hi: float,
                iters: int = 80) -> Optional[float]:
    """二分找 f 的符号翻转点（f 在 [lo,hi] 上变号才存在）。

    80 次二分足以把区间压到双精度极限以下（2^-80 ≈ 8e-25），再多只是浪费算力。
    """
    fa, fb = f(lo), f(hi)
    if fa == 0:
        return lo
    if fb == 0:
        return hi
    if fa * fb > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm == 0:
            return mid
        if fa * fm < 0:
            hi, fb = mid, fm
        else:
            lo, fa = mid, fm
        if hi - lo < (abs(hi) + abs(lo) + 1) * 1e-15:
            break
    return (lo + hi) / 2


def _rel_diff(a, b) -> Optional[float]:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        denom = max(abs(a), abs(b), 1e-300)
        return abs(a - b) / denom
    return None


# ============================================================
# 三、七个检查器（每个都只依赖"结论类型"，不依赖领域）
# ============================================================
REGISTRY: Dict[str, Callable] = {}


def checker(protocol: str):
    def deco(fn):
        REGISTRY[protocol] = fn
        return fn
    return deco


@checker("P1")
def p1_dual_path(name: str, a, b, rtol: float = 1e-9) -> Result:
    """双路径交叉：同一结论两种独立实现必须吻合。

    支持标量 / 序列 / 字典（递归比）。**判据是相对误差 < rtol**，
    不是"看起来差不多"。
    """
    if isinstance(a, dict) and isinstance(b, dict):
        keys = sorted(set(a) | set(b))
        bad = []
        worst = 0.0
        for k in keys:
            if k not in a or k not in b:
                bad.append("%s 只在一条路径里有" % k)
                continue
            r = p1_dual_path(name, a[k], b[k], rtol)
            if not r.passed:
                bad.append("%s: %s" % (k, r.detail))
            worst = max(worst, r.worst or 0.0)
        return Result("P1", name, not bad,
                      "两路径一致" if not bad else "；".join(bad), worst=worst)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return Result("P1", name, False, "长度不一致：%d vs %d" % (len(a), len(b)))
        bad = [p1_dual_path(name, x, y, rtol) for x, y in zip(a, b)]
        worst = max([r.worst or 0.0 for r in bad] or [0.0])
        return Result("P1", name, all(r.passed for r in bad),
                      "两路径一致（%d 项）" % len(a) if all(r.passed for r in bad)
                      else "；".join(r.detail for r in bad if not r.passed), worst=worst)

    d = _rel_diff(a, b)
    if d is None:
        ok = (a == b)
        return Result("P1", name, ok, "路径A=%r / 路径B=%r" % (a, b))
    return Result("P1", name, d < rtol,
                  "路径A=%s / 路径B=%s，相对差 %.3e（判据 < %.0e）" % (a, b, d, rtol),
                  worst=d)


@checker("P2")
def p2_universal(name: str, margin: Callable[[float], float],
                 lo: float, hi: float, base_n: int = 61,
                 starts: int = 96, refine: int = 2) -> Result:
    """全称断言审计 —— 不是"再扫一遍"，是**怀疑采样本身在骗人**。

    约定：`margin(x) > 0` 表示该点违反断言（越大越坏）。
    同时用两种方法找最坏点：
      · 固定网格（粗步长，人最容易用的那种）
      · **对抗式搜索**（均匀扫描 + 多起点爬山 + 多分辨率精修，不依赖单一网格）
    两者结论不一致 → 判定为"窄带陷阱"，**结论以对抗搜索为准**。

    诚实声明写进 detail：**"没找到反例"只保证到搜索分辨率为止**，
    所以每次都把分辨率一起报出来。
    """
    gx, gv, n = grid_argmax(margin, lo, hi, base_n)
    ax, av = adversarial_argmax(margin, lo, hi, starts=starts, refine=refine)
    res = search_resolution(lo, hi, starts)
    passed = av <= 0
    flipped = (gv <= 0 < av)
    detail = ("网格(%d 点/步长 %.4g) 最坏裕度 %.3e → 对抗搜索(分辨率 %.4g) 最坏裕度 %.3e @ x=%.6g ⇒ %s"
              % (n, (hi - lo) / (n - 1) if n > 1 else 0.0, gv, res, av, ax,
                 "断言成立" if passed else "断言被证伪"))
    if flipped:
        detail += "；⚠️ 网格给出的是假结论（窄带陷阱：真反例落在网格点之间）"
    if passed:
        detail += "；注意：未找到反例 ≠ 不存在，本结论的保证范围只到该分辨率"
    return Result("P2", name, passed, detail, worst=av, worst_at=ax, flipped=flipped)


@checker("P3")
def p3_extremum(name: str, f: Callable[[float], float], lo: float, hi: float,
                base_n: int = 401, plateau_tol: float = 1e-3) -> Result:
    """连续复核：离散极值必须用连续搜索复核，**并且报区间不报单点**。

    `f` 是要取最大的目标函数。返回：网格峰值 / 连续最坏点 / 平台区间。
    """
    xs = _linspace(lo, hi, base_n)
    vals = [f(x) for x in xs]
    gx, gv = xs[max(range(base_n), key=lambda i: vals[i])], max(vals)
    ax, av = adversarial_argmax(f, lo, hi, starts=max(96, base_n // 4))
    band = [x for x, v in zip(xs, vals) if v >= gv * (1 - plateau_tol)]
    lo_b, hi_b = (min(band), max(band)) if band else (gx, gx)
    gap = _rel_diff(gv, av) or 0.0
    detail = ("网格峰值 %.6g；连续最坏点 %.6g @ x=%.6g（相对差 %.2e）；"
              "%.1f%% 平台区间 [%.4g, %.4g]" % (gx, av, ax, gap, plateau_tol * 100, lo_b, hi_b))
    return Result("P3", name, True, detail, worst=av, worst_at=ax)


@checker("P4")
def p4_limit(name: str, samples: Sequence[Tuple[float, float, float]],
             tol: float = 1e-6) -> Result:
    """极限与量纲：参数取极限时必须退化到已知结果。

    `samples` = [(参数值, 实测值, 期望退化值), …]（由案例的钩子提供）。
    """
    worst = 0.0
    bad = []
    for param, got, want in samples:
        d = _rel_diff(got, want) or 0.0
        worst = max(worst, d)
        if d > tol:
            bad.append("参数=%g 时实测 %.10g ≠ 期望退化 %.10g（相对差 %.2e）"
                       % (param, got, want, d))
    return Result("P4", name, not bad,
                  "极限退化全部通过（%d 个极限点，最大相对差 %.2e）" % (len(samples), worst)
                  if not bad else "；".join(bad), worst=worst)


@checker("P5")
def p5_flip_boundary(name: str, g: Callable[[float], float],
                     lo: float, hi: float, extra_probe: int = 7) -> Result:
    """反例搜索 → **翻转边界**（不是"找到了一个反例"就收工）。

    `g(param)` 的符号翻转点即为边界（g>0 表示该侧结论失效）。
    若在 [lo,hi] 内没有翻转，**必须如实报告"没找到"并声明搜索范围**——
    这比伪造一个反例有价值得多。
    """
    x = bisect_flip(g, lo, hi)
    if x is None:
        gl, gh = (g(v) for v in (lo, hi))
        return Result("P5", name, True,
                      "在 [%g, %g] 内**未找到**翻转（端点 g=%.4g / %.4g）——"
                      "结论在该范围内未被推翻，但不构成范围外的保证" % (lo, hi, gl, gh))
    span = hi - lo
    eps = span * 10 ** (-extra_probe)
    left, right = g(x - eps), g(x + eps)
    detail = ("翻转边界 ≈ %.10g（考察 %.6g ~ %.6g）；边界两侧 g=%.3e / %.3e"
              % (x, lo, hi, left, right))
    if left * right > 0:
        detail += "；⚠️ 边界过窄，二分点在当前精度下未分离两侧"
    return Result("P5", name, True, detail, worst=x, worst_at=x)


@checker("P6")
def p6_caliber(name: str, values: Sequence[dict], allow_cross: bool = False) -> Result:
    """口径声明：并列出现的数字必须各自带口径；不同口径不得直接相减。

    每项形式 {"label": str, "value": number, "caliber": str}。
    """
    bad = []
    calibers = set()
    for v in values:
        if not str(v.get("caliber", "")).strip():
            bad.append("%s 没有口径" % v.get("label", "?"))
        calibers.add(str(v.get("caliber", "")).strip())
    mixed = len([c for c in calibers if c]) > 1
    if mixed and not allow_cross:
        bad.append("同组数字含 %d 种口径（%s），禁止直接相减/比较"
                   % (len([c for c in calibers if c]), "、".join(sorted(c for c in calibers if c))))
    return Result("P6", name, not bad,
                  "口径齐备：%s" % ("、".join(sorted(c for c in calibers if c)) or "无")
                  if not bad else "；".join(bad))


# ============================================================
# 四、执行器：把声明式检查跑成真实结果
# ============================================================
# 检查器签名里的"槽位"：
#   · PROVIDER  —— 钩子是个**取数函数**（零参调用），返回值就是检查对象（如 P1 的两条路径取值）
#   · FUNCTION  —— 钩子本身就是**被检查器反复调用的函数**（如 P3 的目标函数 f(x)）
# 两类槽位都可在 spec 里内联给值（samples / values 支持内联数据表）。
PROVIDER_PARAMS = ("a", "b", "samples", "values")
FUNCTION_PARAMS = ("f", "g", "margin")
SLOT_PARAMS = PROVIDER_PARAMS + FUNCTION_PARAMS
# 纯数值/开关参数：原样透传给检查器
NUMERIC_KEYS = ("lo", "hi", "base_n", "rtol", "tol", "starts",
                "plateau_tol", "allow_cross", "extra_probe")


def run_checks(entry_id: str, specs: Sequence[dict],
               hooks: Dict[str, Callable]) -> Tuple[List[Result], List[str]]:
    """按声明执行检查。

    spec 形如：
        {"protocol": "P2", "name": "覆盖断言", "fn": "cover_margin",
         "lo": 0, "hi": 2000, "base_n": 101}
        {"protocol": "P1", "name": "双路径", "fn": ["path_a", "path_b"]}
    钩子名必须在案例的 verify.py 里真实存在，**找不到就报错**（不许假装跑过）。
    """
    results: List[Result] = []
    problems: List[str] = []
    for s in specs:
        proto = s.get("protocol")
        fn = REGISTRY.get(proto)
        if fn is None:
            problems.append("%s 声明了未知检查器 %s" % (entry_id, proto))
            continue
        name = s.get("name") or entry_id
        try:
            args, kw = _resolve_args(fn, s, hooks)
            results.append(fn(name, *args, **kw))
        except CheckError as exc:
            problems.append("%s 的 %s 检查无法执行：%s" % (entry_id, proto, exc))
        except Exception as exc:                       # noqa: BLE001
            problems.append("%s 的 %s 检查抛异常：%s: %s"
                            % (entry_id, proto, type(exc).__name__, exc))
    return results, problems


def _resolve_args(fn: Callable, s: dict, hooks: Dict[str, Callable]):
    """把检查器签名里的槽位参数解析成实参（内联值优先，其次 verify.py 钩子）。"""
    sig = inspect.signature(fn)
    params = [p.name for p in list(sig.parameters.values())[1:]]   # 跳过 name
    hook_names = s.get("fn")
    if isinstance(hook_names, str):
        hook_names = [hook_names]
    hook_names = list(hook_names or [])

    args = []
    kw = {}
    idx = 0
    for p in params:
        if p in NUMERIC_KEYS:
            if p in s:
                kw[p] = s[p]
            continue
        if p in s:                       # 内联数据（samples / values / 常量）
            args.append(s[p])
            continue
        if p in SLOT_PARAMS:             # 需要钩子
            hname = hook_names[idx] if idx < len(hook_names) else ""
            idx += 1
            h = _hook(hname, hooks)
            args.append(h() if p in PROVIDER_PARAMS else h)
            continue
        # 其他参数必须有默认值，否则视为声明错误
        d = sig.parameters[p].default
        if d is inspect.Parameter.empty:
            raise CheckError("检查器 %s 的参数 %s 既没内联也没给钩子" % (fn.__name__, p))
    return args, kw


def _hook(name: str, hooks: Dict[str, Callable]) -> Callable:
    if not name:
        raise CheckError("spec 里没有指定钩子函数名（fn）")
    if name not in hooks:
        raise CheckError("verify.py 里没有钩子函数 %s（可用：%s）"
                         % (name, "、".join(sorted(hooks)) or "无"))
    return hooks[name]
