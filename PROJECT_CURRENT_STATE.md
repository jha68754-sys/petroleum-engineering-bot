# Project Current State — Enterprise Petroleum AI Platform

**Baseline:** commit `c5fc976` (2026-08-13), branch `main`, repository [jha68754-sys/petroleum-engineering-bot](https://github.com/jha68754-sys/petroleum-engineering-bot), deployed on Railway with automatic GitHub→Railway deployment.

**Final regression suite: 177 tests, all passing, zero failures, zero test warnings.**

**FINAL STATUS: PHASE 5A — HAGEDORN-BROWN IMPLEMENTED + INDEPENDENTLY VALIDATED + LIVE TELEGRAM VERIFIED + FROZEN** (Revision 2 holdup formulation independently verified against two external arithmetic benchmarks, Aug 14, 2026; owner live Telegram multiphase verification PASSED with Pwf = 332.664 psia matching the z = 1.0 default reference within 0.08 psi; the Aug 13 discrepancy was traced to the Z-factor default — z = 1.0 default vs z = 0.88 benchmark — and resolved with explicit z-factor provenance reporting — see `HAGEDORN_BROWN_ENGINEERING_MODEL.md`)

This document records the verified architecture as it stands after Phase 4 closeout. It is the single source of truth for what is implemented, tested, deployed, and live-verified.

---

## 1. Phases and status

| Phase | Capability | Status |
|---|---|---|
| Phase 1 | IPR engine (Linear PI, Vogel, Composite, Fetkovich-family AOF, auto model selection) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 2 | VLP engine (Beggs–Brill 1973, segmented pressure traverse, bisection Pwf solver) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 3 | Nodal Analysis (IPR–VLP coupling, grid-scan + bracketed bisection, 0/1/multiple intersections, calculated overlay plot) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 4 | Production Sensitivity & Optimization (deterministic sweeps, constraints, objectives, calculated plots) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 5A | Hagedorn–Brown (1965) VLP correlation (Revision 2 after live-verification audit): independent module, `vlp_model=` selection across all production commands, `/calc vlp_compare` dual-model overlay, z-factor provenance + input-default transparency in all VLP outputs | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |

## 2. Deterministic engines

| Engine | File | Models / correlations | Core numerical method |
|---|---|---|---|
| IPR | `services/production_engine.py` | Linear PI; Vogel (with qmax inversion); Composite (Pr > Pb with j* from test point); auto selection via `select_model` | Direct formulas + bracketed inversion |
| VLP | `services/vlp_engine.py` + `services/hagedorn_brown.py` | Beggs–Brill (1973, default, FROZEN); Hagedorn–Brown (1965, independent correlation via `vlp_model=`); Lee–Gonzalez–Eakin gas viscosity; liquid-full friction; static fluid column | Segmented pressure traverse + bisection; model dispatch in `traverse()` / `vlp_curve()` |
| Nodal | `services/nodal_engine.py` | Couples the two engines above (no equation duplication) | Grid scan + bracketed bisection; handles zero / unique / multiple operating points |
| Optimizer | `services/production_optimizer.py` | Delegated sweeps/optimization over the Nodal engine | Direct evaluation; FEASIBLE / INFEASIBLE / PHYSICALLY_INVALID classification |
| PVT | `services/pvt_engine.py` | Bo, Rs, Bg, Z, viscosities, correlations, fluid classification | Correlation estimates + trend validation |

## 3. Telegram command surface (verified live on @pvt_lab_ai_bot)

| Command | Purpose | Plot support |
|---|---|---|
| `/ipr` | Standalone IPR calculations | PNG overlay |
| `/vlp` | Standalone tubing performance | PNG |
| `/nodal` (`/ipr_vlp`, `/node`) | Direct-data nodal overlay | PNG |
| `/calc ipr`, `/calc vlp`, `/calc nodal` | Engine-first calculated production engineering; VLP accepts `vlp_model=beggs_brill|hagedorn_brown` | PNG (`plot=1`) |
| `/calc vlp_compare` | Dual-correlation VLP comparison (BB vs HB): rate sweep, Δ table, overlay PNG | PNG |
| `/calc sensitivity` | THP / tubing ID / water cut / GOR sweeps with deltas | PNG (`plot=1`) |
| `/calc optimize` | Candidate comparison with min_pwf / max_liquid_rate / max_drawdown constraints | PNG (`plot=1`) |
| `/plot` | Direct-data plotting: Bo, Rs, Bg, Z, viscosity, GOR, WOR, water cut, pressure, production, Kr, IPR, VLP, Nodal, sensitivity, optimization | PNG |
| `/estimate`, `/convert`, `/check`, `/classify`, `/pvto`, `/pvdo`, `/pvtg`, `/pvdg`, `/report`, `/analyze`, `/case report`, `/case replay`, `/surface_separator`, `/eclipse`, `/cmg`, `/export_sim` | PVT laboratory, correlations, validation, reproducible cases, exports | PNG where applicable |

AI routing (`services/ai_service.py`) enforces the **ENGINE-FIRST policy**: every calculable production-engineering command (`/calc ipr`, `/calc vlp`, `/calc nodal`, `/calc sensitivity`, `/calc optimize`) is never answered in prose — the AI layer lists required inputs and routes to the deterministic engine.

## 4. Guardrails

Both the deterministic and AI layers enforce engineering guardrails: positive pressure/PI/qmax sanity, z-factor and water-cut bounds, negative-rate rejection, correlation-range warnings (`CORRELATION_LIMITATION` in VLP), and graceful degradation at extreme rates (ValueError/TypeError from collapsed segment pressures are caught and reported, never crash). The q = 0 case always returns the static fluid column with friction exactly zero.

## 5. Verified benchmarks (frozen with the engines)

| Case | Verified value |
|---|---|
| Nodal base case (linear, Pr 3000, j 1.5, THP 100, 8000 ft, 1.995 in, GOR 1000, Rs 600, API 35, γg 0.65, μ 1, Bo 1.4) | q = 3944.20 STB/D, Pwf = 370.53 psia (re-verified after Phase 5A root-acceptance tightening) |
| THP sensitivity 200 / 300 psia | q = 3745.70 / 3534.30 STB/D |
| Tubing-ID sensitivity 2.5 / 3.0 in | q = 3990.37 / 4038.97 STB/D |
| Water-cut sensitivity 0.5 / 1.0 | q = 3825.00 / 3691.89 STB/D |
| Optimization BEST FEASIBLE (id 3.0 in) | q = 4038.97 STB/D, Pwf = 307.36 psia |
| min_pwf = 10000 psia constraint | ALL CANDIDATES INFEASIBLE, no best candidate |
| VLP liquid-full benchmark (thp 100, tvd 8000, q 3000, GOR = Rs = 600, id 1.995 — extrapolation) | BB: Pwf = 2412.7 psia; HB: Pwf = 2414.8 psia (hl = 1 exact, friction ≈ 0; matches independent analytical hydrostatic 2414.9 psia) |
| VLP two-phase GOR > Rs (thp 100, tvd 8000, id 1.995, GOR 1000, Rs 600) | HB: Pwf ≈ 128 psia — published H-B density-ratio behavior (no-slip ρ_s in elevation; gas-dominated column); outside the published test envelope, flagged `CORRELATION_LIMITATION` |
| HB correction audit (Aug 13, 2026) | Revision 1 holdup group (N_RE-based, missing pressure/diameter groups) replaced by the verbatim published form (N_GV^0.575, (p/14.7)^0.1, N_D, C_NL from N_L); circular 2414.8 benchmark replaced by independent analytical hydrostatic; published-form test added |
| HB multiphase discrepancy investigation (Aug 13, 2026) | Multiphase result mismatch traced to Z-factor defaults: handler/engine default z = 1.0 vs predeclared benchmark z = 0.88; physical gas-density effect (lower z compresses free gas, raises ρ_g and hydrostatic column, ΔPwf ≈ +2.8 psi) — NOT a defect; reconciled |
| HB owner live multiphase verification (Aug 14, 2026) | thp 300, tvd 4000, q 800, GOR 1200 > Rs 500, id 1.35 in (inside published 1.0–1.5 in range), z default 1.0: Pwf = 332.664 psia, elevation ≈ 32.5 psi, friction ≈ 0.18 psi — matches independent z = 1.0 arithmetic reference 332.74 psia within 0.08 psi (tolerance ±0.5) |
| HB z-factor provenance transparency (Aug 14, 2026) | All VLP outputs report active Z-factor and its provenance ("user supplied" vs "default — not user supplied") plus the list of engine defaults used; metadata additions provably change no numerical results (guarded by regression tests) |

Full details: `PRODUCTION_ENGINEERING_PHASE1_IPR_MODEL.md` (Phase 1 doc), `VLP_ENGINEERING_MODEL.md`, `NODAL_ENGINEERING_MODEL.md`, `PRODUCTION_OPTIMIZATION_MODEL.md` (Section 7), `HAGEDORN_BROWN_ENGINEERING_MODEL.md` (Phase 5A).

## 6. Test inventory (177 total)

| Module | Tests |
|---|---|
| IPR engine | 37 |
| VLP engine | 50 (incl. 8 Hagedorn–Brown routing/regression tests including an independent published-holdup-form check, 3 reconciled-multiphase Z-benchmark tests, and 7 Phase-5A closeout tests: z-factor provenance labels, input-default propagation, metadata-immunity guardrail, locked accepted benchmark 332.664 psia, frozen BB baselines) |
| Nodal engine | 21 (incl. 3 Hagedorn–Brown nodal tests) |
| Production optimizer (incl. unit formatting) | 38 (incl. 4 Hagedorn–Brown model-selection tests) |
| Engineering corrections / NPV & Z-factor / plot shape / artificial-lift guards | 31 (incl. 4 Hagedorn–Brown / liquid-friction closeout regression tests) |

## 7. Known limitations (transparent)

1. **VLP correlations:** Beggs–Brill (1973, default) plus Hagedorn–Brown (1965, Revision 2) via `vlp_model=`; H-B inputs outside its published applicability envelope (tubing ID 1.0–1.5 in, liquid rate 50–1200 STB/D, GOR 0–2000 scf/STB) emit `CORRELATION_LIMITATION` warnings — results at those edges are indicative, not authoritative.
2. **VLP fluid model:** constant Rs at average pressure; no pressure-dependent Rs evolution; vertical/uphill only (θ saturation).
3. **Nodal multiple intersections:** the non-monotonic (liquid-loading dip) path exists for future correlations; the verified Beggs–Brill and H-B configurations remain monotonic in tested ranges.
4. **Auto IPR without Pb** defaults to Vogel and requires qmax or a test point — documented behavior, not a defect.
5. **Units:** field units throughout (psia, STB/D, ft, in); per-parameter unit metadata (`SENSUNIT_MAP`) governs output labels; no full unit-conversion architecture beyond `/convert`.
6. **Constraints supported:** min_pwf, max_liquid_rate, max_drawdown only.

## 8. Deployment

Railway auto-deploys every `main` commit via the existing GitHub→Railway integration. Bot identity `pvt_lab_ai_bot` (ID 8930247827) confirmed live via Telegram API. Engineering docs are versioned with the code in the repository.
