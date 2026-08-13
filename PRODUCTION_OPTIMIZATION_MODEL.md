# Production Optimization & Nodal Sensitivity — Engineering Model

**Phase 4 · Enterprise Petroleum AI Platform**
Author: Manus AI · Date: August 13, 2026
Supersedes no prior model; extends `PRODUCTION_ENGINEERING_PHASES_1_3`.

---

## 1. Purpose and scope

Phase 4 extends the deterministic production workflow with two analysis capabilities built **on top of** the verified IPR (Phase 1), Beggs–Brill VLP (Phase 2), and Nodal (Phase 3) engines:

1. **Nodal Sensitivity Analysis** (`/calc sensitivity`) — sweeps one production parameter (THP, tubing ID, water cut, or produced GOR) through a list of values or a bounded range, resolves the nodal operating point for every scenario, and reports the change in rate and flowing BHP relative to a base case.
2. **Production Optimization** (`/calc optimize`) — evaluates a discrete set of engineering candidates for the same four parameters against the current operating point, classifies each candidate as feasible or infeasible under user-supplied engineering constraints, and identifies the best feasible candidate.

The guiding principle is **zero equation duplication**: neither handler nor optimizer implements any IPR or VLP mathematics. All rate–pressure mathematics is delegated to `services/production_engine.py`, `services/vlp_engine.py`, and `services/nodal_engine.py`, exactly as in Phases 1–3.

---

## 2. Sensitivity analysis model

### 2.1 Problem statement

Given a base well configuration whose nodal operating point is known (rate `q_b`, flowing BHP `pwf_b`, residual `r_b`), evaluate scenarios that differ in exactly one parameter `x ∈ {thp, id, wc, gor}`. Each scenario `x_i` is a fully determined nodal problem and is solved with the Phase-3 grid-scan + bracketed-bisection solver. The response quantities are:

- `q_i` — the scenario operating rate (STB/D)
- `pwf_i` — the scenario flowing BHP (psia)
- `Δq_i = q_i − q_b`, `Δq%_i = 100·Δq_i / q_b` (when `q_b > 0`)
- `Δpwf_i = pwf_i − pwf_b`

### 2.2 Variable mapping

The Telegram interface uses short keys for convenience; the engine uses canonical names consistent with the VLP/nodal input vocabulary.

| Telegram key | Engine variable | VLP parameter | Physical range guardrail |
|---|---|---|---|
| `thp` | `thp` | tubing-head pressure (psia) | `thp ≥ 0` |
| `id` | `tubing_id` | inside diameter (in) | `id > 0` |
| `wc` | `water_cut` | fraction 0–1 | `0 ≤ wc ≤ 1` |
| `gor` | `gor` | produced GOR (scf/STB) | `gor ≥ 0` |

### 2.3 Base case selection

The base case is the first supplied candidate value (for an explicit list) or `x_min` (for a bounded range `x_min … x_max` with `n_points`). An optional `base_<var>` token overrides this selection. Every scenario reports its deltas versus that same base, so the comparison is internally consistent even when the user supplies the candidate list in arbitrary order.

### 2.4 Status propagation

Sensitivity preserves the full nodal status vocabulary — `UNIQUE_OPERATING_POINT`, `NO_OPERATING_POINT`, `MULTIPLE_OPERATING_POINTS`, `PHYSICALLY_INVALID`, `INSUFFICIENT_DATA` — per scenario. The classification text for each non-unique status is copied verbatim from the Phase-3 engine so the Telegram output never drifts from the underlying diagnosis.

### 2.5 Bounded-range sweeps

When the user supplies `x_min`, `x_max`, `n_points` instead of an explicit list, the sweep uses `n_points` uniformly spaced values in `[x_min, x_max]`. The engine rejects degenerate ranges (`x_min > x_max`, `n_points < 2`) through the standard guardrail path.

---

## 3. Optimization model

### 3.1 Candidate evaluation

Optimization evaluates a discrete candidate set `{x₁ … xₙ}` (`n ≥ 2` required) with `objective = max_oil_rate`. Every candidate is a solved nodal problem identical to a sensitivity scenario. The current operating point is computed from the **unperturbed** well configuration and serves as the benchmark for all reported deltas.

### 3.2 Engineering constraints

Candidates are screened against optional constraints before ranking. The constraint vocabulary mirrors standard field practice for tubing-design decisions:

| Constraint | Type | Feasibility rule |
|---|---|---|
| `min_pwf` | absolute (psia) | `pwf_i ≥ min_pwf` |
| `max_drawdown` | fractional | `(pr − pwf_i) / pr ≤ max_drawdown` (requires `pr > 0`) |
| `max_liquid_rate` | absolute (STB/D) | `q_i ≤ max_liquid_rate` |
| `max_water_cut` | fractional | scenario `wc ≤ max_water_cut` |
| `min_thp`, `max_thp` | absolute (psia) | `min_thp ≤ thp_i ≤ max_thp` |
| `max_gor` | absolute (scf/STB) | scenario `GOR ≤ max_gor` |

A candidate whose nodal solve does not yield a unique operating point, or whose solution violates any constraint, is marked **infeasible** but never silently discarded from the report — its status and reason are displayed so the engineer sees the full trade space. The **best feasible candidate** is the feasible candidate with the maximum operating rate; if every candidate is infeasible, the response states `ALL CANDIDATES INFEASIBLE` with no false recommendation.

### 3.3 Output contract

For every candidate the handler prints `q_i`, `pwf_i`, residual, feasibility status, and `Δq`/`Δq%` versus the current operating point. The best feasible candidate is also summarized with its absolute operating values and deltas, followed by the stability slope sign (same convention as Phase 3).

---

## 4. Calculated plots

Both commands support `plot=1`, delegated to `services/visualization.py` through two new plot rules registered in `constants.py`:

| Rule | Content |
|---|---|
| `sensitivity_plot` | Bar/line of operating rate per scenario versus the base case, with `Δq%` annotations. |
| `optimization_plot` | Candidate operating rates annotated with feasibility status and the best feasible candidate highlighted. |

Plots use the professional style already established for Phase-1/2/3 figures (white background, Matplotlib default palette, absolute file paths, no web fonts).

---

## 5. Telegram interface

```
/calc sensitivity type=<var> <var>=<a>,<b>,<c>
                    [<var>_min=X <var>_max=Y n_points=N]
                    [base_<var>=X] [plot=1]
                    <IPR inputs: identical to /calc nodal>
                    <VLP inputs: identical to /calc nodal>

/calc optimize type=<var> <var>=<a>,<b>,<c>
                  objective=max_oil_rate
                  [min_pwf= max_drawdown= max_liquid_rate= max_water_cut=
                   min_thp= max_thp= max_gor=] [plot=1]
                  <IPR inputs> <VLP inputs>
```

Top-level aliases `/sensitivity` and `/optimize` behave identically through the command registry.

### 5.1 Duplicate-key resolution

Because the swept parameter is also a VLP input (e.g. `type=id` together with `id=1.995` for the tubing inside diameter), the parser applies a deterministic rule: **a comma-separated list for a key always beats a plain single value for the same key**. This lets the user write the natural command `type=id id=1.995,2.5,3.0 … id=1.995` unambiguously — the list drives the sweep and the single value seeds the base VLP configuration when it appears after the list (last-value-wins otherwise).

### 5.2 Missing data

Missing IPR or VLP inputs reuse the Phase-3 missing-data builder, so the user sees the same familiar one-set-required IPR guidance followed by the missing VLP key names.

---

## 6. ENGINE-FIRST routing

`services/ai_service.py` was extended with `/calc sensitivity` and `/calc optimize` entries inside `_build_engineering_context()`. Sensitivity and optimization questions are treated with the same NEVER-answer-in-prose policy as IPR/VLP/nodal: the AI layer lists required inputs and routes to the deterministic engine, never inventing values.

---

## 7. Verification

The regression suite `tests/test_production_optimizer.py` (added in this phase) covers: guardrail acceptance/rejection, base-case computation versus the standalone nodal solver, monotonicity of the THP sweep, candidate feasibility classification, constraint elimination, the all-infeasible response, duplicate-key parsing, and the handler's missing-data and invalid-value paths. Full repository regression (130+ tests across Phases 1–4) passes before every push.

### 7.1 Live verification cases (post-deploy)

| # | Command (abbreviated) | Expected |
|---|---|---|
| 1 | `/calc sensitivity type=thp thp=100,200,300 … plot=1` | base q ≈ 3944 STB/D, lower THP → higher rate, PNG bar/line |
| 2 | `/calc sensitivity type=id id=1.995,2.5,3.0 …` | larger ID → higher rate, deltas vs base 3944 |
| 3 | `/calc sensitivity type=wc wc=0,0.5,1 …` | higher WC → lower rate, all feasible |
| 4 | `/calc optimize type=id id=1.995,2.5,3.0 objective=max_oil_rate …` | BEST FEASIBLE = 3.0 in (q ≈ 4039 STB/D) |
| 5 | `/calc optimize type=id id=1.995,2.5,3.0 objective=max_oil_rate min_pwf=1000 …` | ALL CANDIDATES INFEASIBLE (Pwf < 1000 for all) |

---

## 8. File map

| File | Role |
|---|---|
| `services/production_optimizer.py` | `ProductionOptimizer` — deterministic sweep and candidate evaluation; delegates all math to the Phase 1–3 engines |
| `handlers/text_handlers.py` | `handle_calc_sensitivity`, `handle_calc_optimize`, `_ipr_kwargs_for_optimizer`, `_vlp_kwargs_for_optimizer` |
| `constants.py` | `sensitivity_plot`, `optimization_plot` rules in `PVT_PLOT_RULES` |
| `services/ai_service.py` | ENGINE-FIRST routing entries |
| `tests/test_production_optimizer.py` | Phase-4 regression suite |
