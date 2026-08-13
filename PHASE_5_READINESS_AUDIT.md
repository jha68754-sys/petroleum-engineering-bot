# Phase 5 Readiness Audit — Enterprise Petroleum AI Platform

**Baseline:** commit `c5fc976` (Phase 4 closeout, 2026-08-13). **Phase 5 is NOT implemented.** This audit recommends scope based on the actual verified architecture and identifies what is still missing for a professional petroleum production engineering platform.

---

## 1. What the platform already has (verified)

The platform now runs a complete, deterministic production-engineering calculation pipeline: IPR (Linear / Vogel / Composite / auto selection), Beggs–Brill VLP, Nodal Analysis with a robust operating-point solver, and Production Sensitivity & Optimization with engineering constraints. All of it is regression-protected (146 tests), deployed on Railway, and live-verified on Telegram under the ENGINE-FIRST policy. The gap analysis below therefore starts from a genuine engineering core, not from placeholders.

## 2. Gap analysis against a professional production-engineering platform

| Candidate feature | Engineering value | Dependencies | Validation requirements | Implementation risk | Priority |
|---|---|---|---|---|---|
| **Hagedorn–Brown correlation (additional VLP)** | Covers small-diameter, higher-GLR wells where Beggs–Brill under-predicts gradient; industry standard alongside BB for comparison studies | VLP engine interface only (same traverse/solver skeleton) — engines are already correlation-agnostic at the traverse level | Compare against published H-B pressure-traverse examples and cross-check vs BB on the frozen benchmarks (3944.22 STB/D base must remain unchanged for BB) | Low — the traverse, bisection, and guardrail infrastructure already exists; new correlation module + correlation-selection routing | **P1 — recommended Phase 5a** |
| **Field-data calibration** (test-point matching: adjust j/j*, skin, or tubing roughness to match a measured q/Pwf) | Converts the calculator into a diagnostic tool: match the model to a measured rate test, then trust predictions | Nodal engine (already inverts j*); needs an objective-function wrapper and convergence reporting | Validate against a documented test-match example (e.g., published back-calculation cases) | Low–medium — mostly orchestration over verified inverters | **P1 — recommended Phase 5a (with H-B)** |
| **Report / export architecture** (PDF one-page well review: IPR+VLP+Nodal plots, operating point, constraints, timestamps) | Production engineers work with reports, not chat messages; enables handover to supervisors | Visualization + existing PNG assets; weasyprint already in environment | Format audits: figures legible, units correct, benchmarks reproduced | Low | **P2** |
| **Deviation / inclination support (non-vertical wells)** | Current BB inclination correction saturates vertical; a proper θ-based elevation term unlocks directional and J-tube wells | VLP traverse already carries θ math via Brill–Beggs Ch.3 coefficients; needs angle input and validation | Compare inclined cases vs published examples (Brown 1977, Table 3-1 style) | Low–medium | **P2** |
| **Choke / wellhead modeling** (bean equation, critical/subcritical flow, choke curves) | Closes the surface system: THP is currently an input; choke modeling predicts achievable THP from separator pressure and choke size | Separator handling exists (`/surface_separator`); choke equation is a single correlation set | Validate against Gilbert / Omana choke data tables | Low | **P2** |
| **PVT / property-model maturity** (pressure-dependent Rs, oil formation volume factor correlations with lab matching, oil gravity models) | Current VLP assumes constant Rs at average pressure — the one explicitly documented approximation in `VLP_ENGINEERING_MODEL.md` | PVT engine refactor; must preserve all 146 tests | Lab PVT report matching exercises | Medium | **P3** |
| **Artificial lift readiness** (ESP/gas-lift IPR-VLP coupling: pump curve overlay, injection-point analysis) | Natural next business capability; an `artificial_lift_engine.py` skeleton already exists as a guard module (4 regression tests) | Nodal coupling pattern already proven; lift-correlation set required | Compare vs published ESP design examples | Medium | **P3** |
| **Production constraints extension** (Gor/Water-handling limits as optimizer constraints, multi-objective ranking) | Extends the verified optimizer with facility-side limits already surfaced in handler text | Optimizer constraint interface (already generic: min_pwf/max_liquid_rate/max_drawdown) | Unit-test every new constraint against frozen benchmarks | Low | **P2–P3** |
| **Uncertainty / sensitivity methodology** (parameter error bars, Monte-Carlo over the deterministic engine) | Today's sensitivity is one-at-a-time; P10/P50/P90 operating-point ranges are standard for reserves discussions | Optimizer + PRNG; keep deterministic core untouched | Statistical sanity tests (reproducibility with seeds) | Low–medium | **P3** |
| **Units architecture** (SI/field toggle, per-parameter unit parsing) | Only `/convert` exists today; real lab data arrives mixed | Large surface change across all handlers | Full regression on unit toggle matrix | High — defer | **P4** |
| **Validation against published benchmark cases** (SPE/industry standard problems) | No formal external benchmark suite yet; internal benchmarks are self-consistent only | Test harness additions | Document each case source | Low | **P1 (ongoing, with every new correlation)** |
| **Web platform / API readiness** (REST API over the deterministic engines, sessionless endpoints) | Telegram is the interface; an API unlocks dashboards and third-party integration | Engines are already pure functions — good shape; auth/rate-limiting needed | Contract tests per endpoint | Medium | **P3** |

## 3. Recommended Phase 5 scope

**Phase 5a (recommended next step):** multi-correlation VLP — add the **Hagedorn–Brown (1965)** correlation behind a `model=` selector, keep Beggs–Brill as default, and add **field-data calibration** (`/calc match`) that inverts skin/j* or roughness to reproduce a measured test point using the already-proven Nodal inverters. Both build exclusively on frozen, verified infrastructure, carry low implementation risk, and ship with a published-benchmark validation package and a regression gate (the frozen benchmarks in `PROJECT_CURRENT_STATE.md` must remain exactly reproducible).

**Phase 5b (following):** surface-system closure (choke modeling), inclined-well VLP, and the PDF report generator.

Not recommended before 5a: the SI/field units architecture (high-risk, low immediate value) and full Monte-Carlo uncertainty (needs stable correlations first).

## 4. Readiness verdict

The platform is **ready for Phase 5a**: engines are frozen baselines with 146 green tests, the ENGINE-FIRST routing and handler patterns for new commands are proven twice (Phases 3 and 4), and the VLP architecture already isolates correlations behind the traverse. The single most valuable move is completing the explicit, documented approximation in `VLP_ENGINEERING_MODEL.md` (constant Rs) — via the Hagedorn–Brown correlation and calibration workflow — because that is where real production-engineering value and published-validation evidence both concentrate.
