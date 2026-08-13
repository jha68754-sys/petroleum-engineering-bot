# VLP Engineering Model — Phase 2 (Deterministic)

**Module:** `services/vlp_engine.py` — correlation: **Beggs-Brill (1973)** [1] [2]
**Telegram interface:** `/calc vlp ...` and `/vlp ...` (alias)
**Plotting:** calculated VLP curve PNG via the existing `vlp_plot` rule (`/calc vlp ... plot=1` or a rate sweep `q_min= q_max=`)
**Tests:** `tests/test_vlp_engine.py` — 29 tests, all passing (93 repo tests total)
**Commit:** Phase 2 delivery commit on `main`

## 1. What the engine computes

For a given well specification (wellhead pressure, true vertical depth, tubing
size, fluids, and production rate) the engine marches from the wellhead down to
the bottomhole and returns the **required flowing bottomhole pressure (Pwf)**
that lifts the fluid to the given THP, together with:

| Output | Meaning |
|---|---|
| `pwf` | Required flowing BHP, psia |
| `components.elevation` / `friction` / `acceleration` | Pressure-loss breakdown, psi |
| `flow_pattern_counts` | Histogram of Beggs-Brill flow patterns along the pipe |
| `water_cut`, `rate`, `gor` | Echoed well conditions for traceability |
| `status` | `CONVERGED` or a hard-fail kind (never a silent wrong answer) |

A rate sweep returns the full VLP curve (Pwf vs total rate). The zero-rate
point is computed with `static_gradient` (static gas/liquid column, zero
friction) because multiphase friction correlations are undefined at zero flow.

## 2. Correlation: Beggs-Brill (1973)

Chosen over Hagedorn-Brown because the original 1973 SPE paper [1] and the
Brill & Beggs textbook restatement [2] provide complete, self-consistent
equations for flow-pattern determination, horizontal holdup, the inclination
correction, and the two-phase friction factor. (Hagedorn-Brown is deferred —
see Section 6.)

### 2.1 Local state per segment

At each depth station, evaluated at the arithmetic-mean segment pressure
(midpoint method):

- Free-gas rate: `q_g_free = max(GOR − Rs, 0) × (q_o + q_w)` — solution gas
  above the bubble point stays dissolved.
- Superficial velocities `vsl`, `vsg` (field units: rb/ft³ per day ÷ 86400 ÷ area).
- Liquid density (Brown, TAL Vol. 1 form used in Economides [3]):
  `ρ_L = (350·SG_o + Rs·SG_g·0.0764) / (Bo·5.615)` lbm/ft³, blended with the
  water phase by water cut.
- Gas density: real-gas law `ρ_g = 2.7·γ_g·p / (z·(T+460))`.
- Gas viscosity: **Lee-Gonzalez-Eakin (1966)** [4] — with the gas density
  converted to **g/cm³** (published form requirement; a field-unit density fed
  raw causes catastrophic overflow).
- Mixture Reynolds number with the 1488 cP→lbm/(ft·s) factor.

### 2.2 Flow pattern, holdup, friction

Flow pattern from the original L1–L4 boundaries (segregated / intermittent /
distributed / transition). Holdup `HL(θ)` = `HL(0)·ψ` with:

- `HL(0) = N_Fr^c · λ^b` (pattern coefficients from [1]); transition regime
  weighted between the L2/L3 boundary values with `η = (L3 − N_Fr)/(L3 − L2)`.
- Inclination correction `C = (1 − λ)·ln(d·λᵉ·N_LVᶠ / N_Reᵍ)` — the Reynolds
  term **divides** (Brill & Beggs 1991, Ch. 3), which keeps the logarithm
  argument positive with the published signed coefficients.
- Two-phase friction `f_tp = f_n·e^S`, `S = ln y / (−0.0523 + 3.182·ln y − 0.8725·ln²y + 0.01853·ln⁴y)` with `y = λ/HL²`.

### 2.3 Segmented pressure traverse

The tubing is divided into `n_segments` (default 80) and the solver marches
wellhead → bottomhole. Per segment, `p₂ = p₁ + Δp(p_avg)·ΔL` is solved by a
**bracketed bisection** on the local fixed-point equation with the upstream
gradient as the initial bracket; each segment has a per-iteration budget and a
global cap of 4000 iterations. Exceeding the budget returns
`NUMERICAL_NON_CONVERGENCE` — the engine never emits an unconverged value.
Acceleration is computed from the kinetic-energy change between consecutive
stations (usually negligible).

## 3. Guardrails (hard rejections, never silently wrong)

| Rejection | Trigger | Kind |
|---|---|---|
| Negative depth / diameter / pressure | e.g. `tvd=-100`, `thp=-10` | `PHYSICALLY_INVALID` |
| Free gas below solution GOR while producing | `GOR < Rs` and `q > 0` | `PHYSICALLY_INVALID` |
| Water cut outside 0–1; z outside 0.1–1.5 | | `PHYSICALLY_INVALID` |
| Non-finite inputs (inf, nan) | | `PHYSICALLY_INVALID` |
| Inconsistent `q`/`q_w`/`wc` | | `PHYSICALLY_INVALID` |
| Gas viscosity overflow (pathological density/z) | Lee-Gonzalez-Eakin | `NUMERICAL_NON_CONVERGENCE` |
| Solver budget exceeded | traverse | `NUMERICAL_NON_CONVERGENCE` |

## 4. Benchmarks (hand/analytical verification)

| Case | Well | Result | Verification |
|---|---|---|---|
| Liquid-full (GOR=Rs, no free gas) | THP 100, TVD 8000 ft, 2-in ID, 3000 STB/d, API 35 | Pwf = 2412.7 psia | Analytic hydrostatic + friction with same Brown-form ρ_L = 41.6 lbm/ft³, gradient 0.289 psi/ft → 2412.78 (agreement 0.03 psi) |
| Two-phase base | + GOR 1000, Rs 600 | Pwf ≈ 356 psia | Independent marching model, same property set → 356.7 (±2 psi) |
| Deep stress | THP 1000, TVD 15000 ft, 3.5-in ID, 8000 STB/d | Pwf ≈ 1948 psia | Engine-verified; marching cross-check within ±15 psi (z treatment spread) |
| Static column, q = 0 | THP 100, TVD 8000 ft | Pwf ≈ 117 psia | Analytic exponential gas column |

Physics invariants enforced by tests: Pwf ≥ THP always; friction = 0 at zero
rate; deeper well / higher THP / added water-cut / narrower tubing never
reduce required BHP; the liquid-full case is strictly monotonic in rate.
Note: in **gas-rich** flow the Pwf-vs-rate curve can be non-monotonic at low
rates (liquid-loading behavior) — this is real physics, not a bug; only the
liquid-full and static cases are asserted monotonic.

## 5. Known limitations (transparent, never disguised)

1. **Constant Rs assumption.** Rs is supplied at the average pressure; in-situ
   gas release below the bubble point is modeled only as `max(GOR−Rs,0)`. For
   wells where the pressure crosses Pb along the tubing, use the Rs at the
   average in-situ pressure or flag the result as approximate. (A pressure-
   dependent Rs variant is a candidate for a later phase — not implemented.)
2. **Beggs-Brill validity.** Published ranges: 70–1500 psia, D < 5 in, GVF < 98%,
   L/G ≤ 150,000 scf/STB. Results far outside these ranges carry a
   `CORRELATION_LIMITATION` warning.
3. **Vertical/uphill only** for the inclination correction; vertical wells use
   θ = 90° (sin terms saturate ψ ≥ 1, standard practice).
4. **No temperature profile effect on PVT beyond linear geothermal**; no
   hydrocarbon-water emulsion model; surface tension defaults to 30 dyne/cm.
5. **Single pipe, no restrictions.** No annular flow, no gas-lift, no choke.

## 6. Deferred: Hagedorn-Brown

Per the Phase-2 task spec, Hagedorn-Brown is **NOT implemented** because a
defensible implementation requires the Brown-Roscoe correlation-set
interpolation and published correction factors not available for exact
reproduction here; Beggs-Brill covers the standard field range and is
self-documenting. Adding it later as `model=hagedorn_brown` to `/calc vlp`
would reuse the same traverse skeleton.

## 7. AI routing

The AI layer (`services/ai_service.py`, ENGINE-FIRST policy) now routes all
VLP questions to `/calc vlp` and never answers VLP numerics in prose.

## References

[1]: https://onepetro.org/SPEATCE/proceedings/73FM/All-73FM/SPE-4007-MS/178974 "Beggs & Brill, 'A Study of Two-Phase Flow in Inclined Pipes', SPE-4007, 1973"
[2]: https://onepetro.org/books/book/38/chapter/10943148/Intermittent-Flow "Brill & Beggs, 'Two-Phase Flow in Pipes', 1991 (inclination correction coefficients)"
[3]: https://onlinelibrary.wiley.com/doi/10.1002/9783433602379 "Economides, Hill, Ehlig-Economides, 'Petroleum Production Systems'"
[4]: https://onepetro.org/SPEMEOS/proceedings/66FM/All-66FM/SPE-1340-MS/169301 "Lee, Gonzalez, Eakin, 'The Viscosity of Natural Gases', SPE-1340, 1966"

- [1] Beggs & Brill, SPE-4007, 1973 — original two-phase inclined-pipe correlation.
- [2] Brill & Beggs, 1991 textbook restatement — flow-pattern boundaries, transition weighting, inclination C coefficients.
- [3] Economides et al., *Petroleum Production Systems* — liquid-density mass-balance form and VLP workflow.
- [4] Lee, Gonzalez & Eakin, SPE-1340, 1966 — gas viscosity correlation (density in g/cm³).
