# Nodal Analysis Engineering Model — Phase 3

**Module:** `services/nodal_engine.py`
**Telegram commands:** `/calc nodal`, `/nodal` (aliases: `/ipr_vlp`, `/node`)
**Plots:** `/calc nodal ... plot=1` (calculated IPR+VLP overlay), `/plot nodal p=... v=...` (direct data)

---

## 1. Design Principle — Zero Equation Duplication

The nodal orchestrator owns **no equations of its own**. Inflow math comes
from the verified Phase-1 engine (`IPREngine` in `services/production_engine.py`)
and outflow math comes from the verified Phase-2 engine
(`vlp_engine.traverse()` — Beggs–Brill 1973, `services/vlp_engine.py`).

The orchestrator owns only three things:

| Ownership | Item |
|---|---|
| Calibration | Selection of the IPR model and resolution of its parameters (`_resolve_ipr`, `_ipr_params`) — including the `j_star` inversion of the measured test point for the Composite model, reused from `IPREngine` |
| Search | A deterministic root-finding loop over a rate grid (`grid-scan + bracketed bisection`) |
| Coupling | `F(q) = Pwf,IPR(q) − Pwf,VLP(q)`, evaluated through the two engines' public rate↔pressure inverters |

`NodalEngine.pwf_ipr_from_rate` / `rate_at` and `NodalEngine.pwf_vlp` are the
**single public bridge** used by both the Telegram handler's curve builder
and the plot generator, so plots can never drift from the solved curves.

## 2. Inflow (IPR) — Resolved Exactly as Phase 1

The same `select_model` / `auto_q_max` policies and `C¹`-continuous
Composite inversion from Phase 1 are reused without change.

| Mode | Inputs | Effective curve |
|---|---|---|
| `linear` | `pr`, `j` | `Pwf = Pr − q/j`, AOF = j·Pr |
| `vogel` | `pr`, `qmax` | Vogel (1968) with `qmax` as AOF |
| `composite` | `pr`, `pb`, `q_test`, `pwf_test` | Test-point inversion → `j_star`; composite for `Pwf < Pb` |
| `auto` | `pr` + (`pb` & test pair **or** `j` **or** `qmax`) | `select_model` policy: undersaturated with a valid test point → Composite; else Vogel with `qmax` inversion |

Automatic `qmax` derivation (Phase 1 behavior): for a requested model that
only supplies a partial parameter set, `auto_q_max` reconstructs the missing
AOF by evaluating the other Phase-1 curves — including
`IPREngine().composite_q(pr, pb, j_star, 0)` for the Composite case.

The search range is **never invented**: it is the minimum of the IPR's
maximum sustainable rate (AOF) and any user-supplied `q_min`/`q_max`.

## 3. Outflow (VLP) — Phase 2, Untouched

A single `vlp_engine.traverse()` call per rate: wellhead → bottomhole,
segmented Beggs–Brill (1973) with midpoint property evaluation, bracketed
bisection per segment, Colebrook friction, Lee–Gonzalez–Eakin gas
viscosity, Brown–etal liquid density. Water cut, brine, and surface
tension are carried through unchanged.

Two deliberate extensions for the zero-rate boundary:

> **q = 0 is the static fluid column** (friction contribution exactly
> zero, by definition). Both `_pwf_vlp` and the public `pwf_vlp` return
> `vlp_engine.static_gradient(...)` at `q ≤ 0`, matching the documented
> Phase-2 convention used in `vlp_engine.curve()`.

Non-convergence artefacts (e.g. Lee–Gonzalez–Eakin complex arithmetic at
collapsed segment pressures for unphysically high rates) are classified
as grid artefacts — never operating points — and can never crash a solve.

## 4. Coupling and Solver

```
F(q) = Pwf,IPR(q) − Pwf,VLP(q)      rate on X, pressure on Y
```

1. **Grid scan** — `n_points` (default 101, cap 501) uniform rates in the
   documented range; every point is evaluated, skipped points recorded in
   `warnings`.
2. **Root detection** — sign changes between consecutive grid points, plus
   near-zero grid points re-bracketed with neighbors so bisection always
   has a genuine bracket.
3. **Refinement** — bracketed bisection to the pressure tolerance
   (default 0.1 psi), with a final quality gate: the root is only reported
   if `|F(q_root)|` and the re-evaluated `|Pwf,IPR − Pwf,VLP|` both sit
   within tolerance **and** `0 ≤ Pwf ≤ Pr`.
4. **Deduplication** — near-zero and bracket detections of the same root
   are merged within the documented q-tolerance.

### Classification

| Status | Meaning |
|---|---|
| `UNIQUE_OPERATING_POINT` | One root; `stability = stable`/`unstable` from the slope sign of F at the root |
| `NO_OPERATING_POINT` | No root in range; reason distinguishes "IPR below VLP" (reservoir too weak) from "insufficient analyzed range" |
| `MULTIPLE_OPERATING_POINTS` | ≥2 roots returned in rate order — a non-monotonic VLP (e.g. severe liquid loading) can cross a monotonically decreasing IPR more than once. All crossings are reported; the AI layer is told the highest-rate crossing is normally the stable operating point |

### Multiple Intersections

The physical Beggs–Brill VLP used here is monotonic at the documented
well conditions (verified in `tests/test_vlp_engine.py`), so a natural
multi-root case was not available for the regression suite. The
`MULTIPLE` code path is exercised by `TestNodalMultipleIntersections`,
which injects a documented synthetic surrogate — `F(q) = (q−1000)(q−3000)(q−5000)·10⁻⁹`
with three analytic roots — into the private inverters. This is the only
place in the system where a non-monotonic `F(q)` can exist, and the test
asserts all three roots are detected and deduplicated correctly.

## 5. Result Contract

```python
NodalResult:
  status, roots (NodalRoot: q, pwf, residual, stability), reason
  ipr_model          # "linear" | "vogel" | "composite"
  vlp_model          # "beggs_brill"
  root_method        # "grid_scan + bracketed_bisection"
  ipr_params         # (kind, tuple) — reproducible params used
  vlp_kwargs         # traverse() kwargs used
  inputs_summary     # pr, pb, qmax, j, q_test, pwf_test, thp, tvd, ...
  n_scan_points, warnings
```

Every result is reproducible: the handler's calculated plot uses exactly
`pwf_ipr_from_rate(ipr_params, q)` and `pwf_vlp(q, ipr_params, vlp_kwargs)` —
the same inverters as the solver.

## 6. Validation and Guardrails (deterministic, before any solve)

| Rule | Rejection |
|---|---|
| `Pr ≤ 0`, `Pb ≤ 0`, `Pb ≥ Pr` | `PHYSICALLY_INVALID` |
| `q_test ≤ 0`, `pwf_test ≤ 0`, `pwf_test ≥ Pr` | `PHYSICALLY_INVALID` |
| `tvd ≤ 0`, `id ≤ 0`, negative PVT inputs | delegated to `vlp_engine.validate_inputs()` |
| `0 ≤ q_min < q_max`, `q_max ≤ 1e6` | `PHYSICALLY_INVALID` |
| Unphysical `z`, `gamma_g`, `sigma`, `wc ∉ [0,1]` | delegated validation |

When required data is missing, the Telegram handler returns the exact
minimal list (never a vague "missing parameters") — and for `auto` mode
it mirrors the engine's own policy (without `Pb`, the engine lands on
Vogel, which requires `qmax` or a test pair).

## 7. Telegram Interface

```
/calc nodal [model=auto|linear|vogel|composite] [plot=1] key=value ...
/nodal ... (alias)

Reservoir:    pr= (psia)  pb= (psia)
IPR:          j= (Linear) | qmax= (Vogel) | q_test= pwf_test= (Composite)
VLP (Phase-2 required set):
  thp= tvd= id= gor= rs= api= gamma_g= mu_l= bo= t_wh= geothermal=
  [wc= gamma_w= bw= z= sigma= segments=]
Optional:     q_min= q_max= n_points= plot=1
```

Output: status banner, operating point (`q`, `Pwf`, residual), stability
interpretation, the analyzed rate range, curve table, and the PNG overlay
when `plot=1`.

## 8. Tests

`tests/test_nodal_engine.py` — 18 tests covering guardrail rejection, the
three unique-IPR cases with cross-checks against the exact Phase-1 curves
(`Pwf = Pr − q/j` identity; `vogel_q` round-trip; composite test-point
reproduction), both no-solution branches, the documented synthetic
multiple-root surrogate, curve-builder consistency, result metadata, and
the zero-rate static-column regression. Full suite: **112 tests, all green**.

## 9. AI Routing (ENGINE-FIRST)

`services/ai_service.py` now routes operating-point questions to
`/calc nodal ...` with the full syntax and a prohibition on answering in
prose. The handler keeps the verified IPR/VLP routing intact.

## References

1. Beggs, H.D. & Brill, J.P. (1973). "A Study of Two-Phase Flow in
   Inclined Pipes." *JPT*, 25(5), 607–617.
2. Vogel, J.V. (1968). "Inflow Performance Relationships for Solution-Gas
   Drive Wells." *JPT*, 20(1), 83–92.
3. Lee, A.L., Gonzalez, M.H. & Eakin, B.E. (1966). "The Viscosity of
   Natural Gases." *JPT*, 18(8), 997–1000. SPE-1340.
4. Brown, K.E. (1977). *The Technology of Artificial Lift Methods*, Vol. 1.
   PennWell. (liquid density formulation)
5. Economides, M.J. et al. (1994). *Petroleum Production Systems*.
   Prentice Hall. (IPR/VLP conventions, nodal analysis method)
