# TroubleSolver — a modeling assistant that tries to falsify itself

> Every "AI modeling" tool solves **how to produce an answer**. Nobody solves **how to know it is right**.
> TroubleSolver does only the latter: given a business problem, it produces a solution package with a
> **verifiable ledger whose numbers a third party can recompute from a script**, and it
> **tells you the conditions under which its own conclusions break**.

> **Positioning (one line)**: an **open-source, self-falsifying modeling assistant** — it first helps you
> ask the problem completely (a 12-dimension problem charter + checkpoint review), then models it,
> then **actively hunts for its own counterexamples** (seven executable verification protocols P1–P7);
> no hand-copied numbers, every delivered figure recomputable.

```
0 Formalize ─▶ [human: confirm the caliber]   business problem → math object / objective / constraints / calibers / acceptance criteria
1 Baseline  ─▶ [human: baseline reproducible] start with the dumbest trustworthy baseline; otherwise "how much did we improve" is meaningless
2 Model      analytic first (closed form if possible), numeric as fallback — write both paths independently
3 Falsify ★  run seven verification protocols, actively construct counterexamples; on flip, change the conclusion and keep the trace   ← the dividing line vs. every peer tool
4 Robustify  parameter ranges / worst case / caliber comparison (different calibers give different answers — report them side by side)
5 Deliver    ledger → report + scripts, with a mandatory "limitations & failure boundaries" section
6 Review     rerun in a different directory, reconcile number by number; drift is rejected
```

Only two human checkpoints (**caliber confirmation**, **baseline reproducibility**) — get these wrong and
everything downstream is wasted. Everything else is automatic.

> 📄 **Landing page / usage guide (with mind map)**: open `docs/index.html` in a browser
> (single file, zero dependencies, works offline). It covers the four-step usage, the seven protocols,
> the ledger state machine, the zero-handwritten-numbers mechanism, and real outputs showing
> "the guards actually fire".

## What it does NOT do (up front)

- ❌ **It does not write competition papers.** Saturated space, and it conflicts with academic integrity.
  It outputs business solution packages, not contest submissions.
- ❌ **It does not promise an "optimal solution".** It promises "**the optimal solution under explicit
  calibers and assumptions + its failure boundaries**".
- ❌ **It does not choose the caliber for you.** When a business caliber and a finance caliber disagree,
  it computes both and reports them side by side. The call is yours.
- ❌ No web UI / multi-agent role-play / database / account system.

## Core mechanisms

### Seven verification protocols (the product itself, not prompt tricks)

| # | Protocol | Criterion |
|---|---|---|
| P1 | Dual-path cross-check | Two **independent** implementations of the same conclusion, relative error < 1e-9 |
| P2 | Adversarial worst-case audit | Any "holds for all / never fails" claim must be re-tested by an **adversarial search that does not depend on a single grid**, plus actively constructed worst cases |
| P3 | Continuous review | An extremum found on a discrete grid must be re-checked by continuous/adaptive search; report an **interval**, not a point |
| P4 | Limit & dimension | As parameters → 0/∞/critical values, results must degenerate to known values; dimensions must be consistent |
| P5 | Counterexample search | Actively search the parameter region where the conclusion flips; report the **flip boundary** |
| P6 | Caliber declaration | Every number carries: source / definition / scope / extrapolability |
| P7 | Ledger reconciliation | Every externally quoted number can be recomputed by one command — **hand-copying is forbidden** |

P2 / P3 / P5 are "**actively find your own mistake**". They are not the same as conventional QA that only
checks format — these three are the bar.

### Traceable ledger + zero handwritten numbers

Each conclusion is one entry, driven by a state machine: `new → verifying → verified / refuted / stale`.
Deliverables **may only cite `verified`**; refuted entries **stay in the ledger together with their evidence**
(deleting them is exactly how the same mistake happens twice); change an upstream parameter and everything
depending on it goes `stale` automatically.

Every number in the report and the falsification record is a `{{m.path}}` placeholder injected from
`out/metrics.json`. **If a value cannot be resolved, the build fails** — there is no back door for
"just type a number in".

### Generality: the engine does not know your domain

The protocols are not prose in a prompt; they are **runnable checkers** (`src/troublesolver/checks.py`).
The engine only knows **conclusion types** (equality / extremum / universal claim / optimality /
caliber-dependent / …). It does not know inventory, lighting, credit scoring, or fisheries. Each conclusion
declares its type, and the engine **forces** the protocols that type requires:

```jsonc
{ "kind": "universal claim",                          // ← type decides the mandatory P2 + P5
  "checks": [{"protocol": "P2", "fn": "cover_margin_aged",
              "lo": 0, "hi": 2000, "base_n": 51}] }    // ← fn is a hook in the case's verify.py
```

So adding a **brand-new domain** takes three steps:
write `charter.md` (the problem charter) → write `solve.py` + `verify.py` (hooks) → declare `kind` / `checks`.
**Not a single line of the engine changes.** The `protocols` recorded in the ledger are not hand-written
either — they are decided by the checks that actually ran and passed.

→ Details in [`docs/generalization.md`](docs/generalization.md) (including an honest "what can and cannot be generalized").

### LLM orchestration (`tsolve agent`)

The stage instructions under `prompts/` are wired to an LLM orchestration layer. `tsolve agent <case_dir>`
reads `charter.md` plus the stage instructions, lets a (pluggable) LLM generate the case files
(`solve.py`, `verify.py`, `ledger.spec.json`, the templates, `expected.json`), and then runs the **identical**
engine loop over them. The generated artifacts get **no shortcuts**: the same checkpoints, the same seven
protocols, the same ledger, the same number reconciliation, the same independent review.

The division of labor is therefore: **the LLM turns the problem into code; the engine proves the code's
conclusions are not cheating.** Keys are **only** read from environment variables — `grep -r 'sk-' src/` finds
nothing. `--mock` runs a zero-network, zero-key client so CI can cover the orchestration layer without an LLM quota.

## 30-second quickstart

```bash
# Case A: inventory / stochastic optimization (single-SKU weekly stocking, newsvendor)
PYTHONPATH=src python3 -m troublesolver.cli solve examples/newsvendor_inventory
PYTHONPATH=src python3 -m troublesolver.cli audit examples/newsvendor_inventory

# Case B: geometry / universal claims (park trail lighting coverage) — same engine, zero changes
PYTHONPATH=src python3 -m troublesolver.cli solve examples/facility_coverage
PYTHONPATH=src python3 -m troublesolver.cli audit examples/facility_coverage

# Case C: statistics / universal claims / calibers (consumer-credit approval threshold)
PYTHONPATH=src python3 -m troublesolver.cli solve examples/loan_approval_threshold
PYTHONPATH=src python3 -m troublesolver.cli audit examples/loan_approval_threshold

# Case D: biology / resource management (fisheries maximum sustainable yield, MSY)
PYTHONPATH=src python3 -m troublesolver.cli solve examples/fishery_msy
PYTHONPATH=src python3 -m troublesolver.cli audit examples/fishery_msy

# LLM orchestration: generate the case files from charter.md, then run the loop (needs $TSOLVE_LLM_API_KEY)
PYTHONPATH=src python3 -m troublesolver.cli agent path/to/newcase
# Offline demo / CI: zero network, zero key
PYTHONPATH=src python3 -m troublesolver.cli agent path/to/newcase --mock
# Only print the assembled prompt, do not call the model
PYTHONPATH=src python3 -m troublesolver.cli agent path/to/newcase --dry-run

# Inspect a ledger
PYTHONPATH=src python3 -m troublesolver.cli ledger show examples/facility_coverage/ledger.json
```

Real output (excerpt):

```
【阶段 0 形式化】问题说明书：通过
【阶段 1-2 基线与建模】求解脚本已运行，数字出口 out/metrics.json
  基线 Q0=150 件，周期望利润=1007.35 元（键 baseline）
【阶段 3-5 证伪与交付】台账 9 条，状态分布 {"verified": 8, "refuted": 1}
  已生成 report.md
  已生成 falsify.md
闭环通过：报告/证伪记录里的每个数字都来自 out/metrics.json（P7）
```

`tsolve audit` reruns the solver in a **temporary directory**, then compares the frozen numbers and check
verdicts one by one, and checks that no conclusion status drifted. Change one parameter and it stops you:

```
  - 数字漂移：result.recommend_Q 期望 133，实测 134（容差 1e-09）
```

## Repository layout

```
trouble-solver/
├── prompts/                    Stage instructions for the agent (stages 0 / 2 / 3 / 5)
│   ├── 00_intake.md            Guided intake: 12 dimensions to fully ask the problem
│   ├── 20_model.md             Baseline & modeling: dual path, zero handwritten numbers
│   ├── 30_falsify.md           Falsification: the seven protocols and three real blood examples
│   └── 50_deliver.md           Delivery: package checklist and hard rules
├── src/troublesolver/
│   ├── cli.py                  tsolve charter / ledger / solve / audit / agent
│   ├── charter.py              Problem-charter completeness check (checkpoint ①)
│   ├── ledger.py               Ledger state machine + pre-delivery reconciliation (P7)
│   ├── checks.py               ★ Runnable checkers + conclusion-type → mandatory-protocol matrix (the core of generality)
│   ├── orchestrate.py          LLM orchestration: prompts + charter.md → case files → engine loop
│   ├── case.py                 Case orchestration: the loop and the independent review
│   └── report.py               Template rendering: numbers can only come from metrics.json
├── examples/
│   ├── newsvendor_inventory/   Case A: inventory / stochastic optimization (9 ledger entries)
│   ├── facility_coverage/      Case B: geometry / universal claims (7 entries, automatically caught a narrow-band trap)
│   ├── loan_approval_threshold/ Case C: statistics / calibers (6 entries, consumer credit)
│   └── fishery_msy/            Case D: biology / resource management (5 entries, narrow-band trap from a localized mortality band)
├── tests/                      53 tests: "the guards actually fire" treated as tests
└── docs/{methods.md,ledger.md,generalization.md,index.html}
```

### One case = one directory

```
charter.md           Problem charter (12 sections, machine-checked; the checkpoint ① artifact)
solve.py             Solver script, the sole number outlet out/metrics.json
verify.py            ★ Verification hooks: expose "checkable objects" to the generic checkers
ledger.spec.json     Conclusion list (declarative: kind + checks + {{m.path}} number references)
report.template.md   Report template (handwritten numbers forbidden)
falsify.template.md  Falsification-record template
expected.json        Frozen numbers (golden file) for tsolve audit regression
out/                 Script outputs, not committed
```

## Status & roadmap

| Version | Content | Status |
|---|---|---|
| v0.1 | Skeleton + three stages + ledger + one case end-to-end + independent review | **Done** |
| v0.2 | **Protocol engine** (`checks.py`: seven runnable checkers) + **conclusion-type → mandatory-protocol matrix** + three heterogeneous cases (inventory / facility coverage / credit) + check verdicts in the golden regression | **Done** (44 tests) |
| v0.3 | **LLM orchestration** (`tsolve agent`: prompts + charter.md → case files → loop) + 4th domain case (biology / resources) + English README | **Done** (53 tests) |
| v0.4 | Report/chart output module (high-DPI, colored text banned, missing-glyph detection) + delivery-compliance mode | Planned |
| v0.5 | Technical write-up + first public release | Planned |

**Current boundary (judge for yourself whether it fits)**: the four stage prompts under `prompts/` are now
wired to an LLM through `tsolve agent` — the LLM reads `charter.md` and generates
`solve.py` / `verify.py` / `ledger.spec.json` / templates / `expected.json`, but these artifacts still go
through the **exact same engine loop as hand-written cases** (checkpoints, seven protocols, ledger, number
reconciliation, independent review — none are skipped). So the split is: **the LLM turns the problem into
code; the engine proves the code's conclusions are not cheating.** It still does not guarantee the LLM thinks
correctly — but any conclusion it produces is independently verified by the seven protocols and reconciled
number by number by `audit`; if it is wrong it is demoted to `refuted` on the spot and kept as a trace
(see cases B / C / D). Keys are read only from environment variables; the source contains none.

## Design trade-offs (why it is so "small")

- **Local files are the only state**: no database, no hidden state; `git diff` is the entire change history.
- **Cases are tests**: `expected.json` freezes key numbers; change a prompt or the code and it alarms,
  preventing conclusions from drifting silently.
- **Every feature first asks "is it really needed?"**: if not, delete it. The value of this repo is in its
  constraints, not in its feature count.

## Lineage

Every criterion of the seven protocols and the ledger design comes from a real incident: a coarse step size
skipping an entire 2°-wide violation band and still printing "holds for all"; a continuous supremum only
0.15% above the grid peak yet enough to flip the conclusion; a self-built simulation's virtual time nearly
ending up in the same table as official test numbers… Turning these into machine-executable checks is the
reason this repo exists.

## License

Apache-2.0 (see `LICENSE`, includes a patent grant, friendly to corporate adoption).
