# Project Current State — Enterprise Petroleum AI Platform

**Baseline:** commit `c5fc976` (2026-08-13), branch `main`, repository [jha68754-sys/petroleum-engineering-bot](https://github.com/jha68754-sys/petroleum-engineering-bot), deployed on Railway with automatic GitHub→Railway deployment.

**Final regression suite: 146 tests, all passing, zero failures, zero test warnings.**

This document records the verified architecture as it stands after Phase 4 closeout. It is the single source of truth for what is implemented, tested, deployed, and live-verified.

---

## 1. Phases and status

| Phase | Capability | Status |
|---|---|---|
| Phase 1 | IPR engine (Linear PI, Vogel, Composite, Fetkovich-family AOF, auto model selection) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 2 | VLP engine (Beggs–Brill 1973, segmented pressure traverse, bisection Pwf solver) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 3 | Nodal Analysis (IPR–VLP coupling, grid-scan + bracketed bisection, 0/1/multiple intersections, calculated overlay plot) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |
| Phase 4 | Production Sensitivity & Optimization (deterministic sweeps, constraints, objectives, calculated plots) | IMPLEMENTED, TESTED, DEPLOYED, LIVE TELEGRAM VERIFIED, FROZEN |

## 2. Deterministic engines

| Engine | File | Models / correlations | Core numerical method |
|---|---|---|---|
| IPR | `services/production_engine.py` | Linear PI; Vogel (with qmax inversion); Composite (Pr > Pb with j* from test point); auto selection via `select_model` | Direct formulas + bracketed inversion |
| VLP | `services/vlp_engine.py` | Beggs–Brill (1973) multiphase; Lee–Gonzalez–Eakin gas viscosity; liquid-full friction; static fluid column | Segmented pressure traverse + bisection |
| Nodal | `services/nodal_engine.py` | Couples the two engines above (no equation duplication) | Grid scan + bracketed bisection; handles zero / unique / multiple operating points |
| Optimizer | `services/production_optimizer.py` | Delegated sweeps/optimization over the Nodal engine | Direct evaluation; FEASIBLE / INFEASIBLE / PHYSICALLY_INVALID classification |
| PVT | `services/pvt_engine.py` | Bo, Rs, Bg, Z, viscosities, correlations, fluid classification | Correlation estimates + trend validation |

## 3. Telegram command surface (verified live on @pvt_lab_ai_bot)

| Command | Purpose | Plot support |
|---|---|---|
| `/ipr` | Standalone IPR calculations | PNG overlay |
| `/vlp` | Standalone tubing performance | PNG |
| `/nodal` (`/ipr_vlp`, `/node`) | Direct-data nodal overlay | PNG |
| `/calc ipr`, `/calc vlp`, `/calc nodal` | Engine-first calculated production engineering | PNG (`plot=1`) |
| `/calc sensitivity` | THP / tubing ID / water cut / GOR sweeps with deltas | PNG (`plot=1`) |
| `/calc optimize` | Candidate comparison with min_pwf / max_liquid_rate / max_drawdown constraints | PNG (`plot=1`) |
| `/plot` | Direct-data plotting: Bo, Rs, Bg, Z, viscosity, GOR, WOR, water cut, pressure, production, Kr, IPR, VLP, Nodal, sensitivity, optimization | PNG |
| `/estimate`, `/convert`, `/check`, `/classify`, `/pvto`, `/pvdo`, `/pvtg`, `/pvdg`, `/report`, `/glossary`, `/analyze`, `/surface_separator`, `/eclipse`, `/cmg`, `/export_sim` | PVT laboratory, correlations, validation, exports | PNG where applicable |

AI routing (`services/ai_service.py`) enforces the **ENGINE-FIRST policy**: every calculable production-engineering command (`/calc ipr`, `/calc vlp`, `/calc nodal`, `/calc sensitivity`, `/calc optimize`) is never answered in prose — the AI layer lists required inputs and routes to the deterministic engine.

## 4. Guardrails

Both the deterministic and AI layers enforce engineering guardrails: positive pressure/PI/qmax sanity, z-factor and water-cut bounds, negative-rate rejection, correlation-range warnings (`CORRELATION_LIMITATION` in VLP), and graceful degradation at extreme rates (ValueError/TypeError from collapsed segment pressures are caught and reported, never crash). The q = 0 case always returns the static fluid column with friction exactly zero.

## 5. Verified benchmarks (frozen with the engines)

| Case | Verified value |
|---|---|
| Nodal base case (linear, Pr 3000, j 1.5, THP 100, 8000 ft, 1.995 in, GOR 1000, Rs 600, API 35, γg 0.65, μ 1, Bo 1.4) | q = 3944.22 STB/D, Pwf = 370.50 psia |
| THP sensitivity 200 / 300 psia | q = 3745.68 / 3534.30 STB/D |
| Tubing-ID sensitivity 2.5 / 3.0 in | q = 3990.37 / 4038.97 STB/D |
| Water-cut sensitivity 0.5 / 1.0 | q = 3825.00 / 3691.89 STB/D |
| Optimization BEST FEASIBLE (id 3.0 in) | q = 4038.97 STB/D, Pwf = 307.36 psia |
| min_pwf = 10000 psia constraint | ALL CANDIDATES INFEASIBLE, no best candidate |
| VLP liquid-full benchmark (thp 100, tvd 8000, q 3000, GOR = Rs) | Pwf = 2412.7 psia, hydrostatic 2312.7, friction 0.0 (verified single-phase liquid-full case) |

Full details: `PRODUCTION_ENGINEERING_PHASE1_IPR_MODEL.md` (Phase 1 doc), `VLP_ENGINEERING_MODEL.md`, `NODAL_ENGINEERING_MODEL.md`, `PRODUCTION_OPTIMIZATION_MODEL.md` (Section 7).

## 6. Test inventory (146 total)

| Module | Tests |
|---|---|
| IPR engine | 37 |
| VLP engine | 30 |
| Nodal engine | 18 |
| Production optimizer (incl. unit formatting) | 34 |
| Engineering corrections / NPV & Z-factor / plot shape / artificial-lift guards | 27 |

## 7. Known limitations (transparent)

1. **VLP single-correlation:** only Beggs–Brill (1973); no Hagedorn–Brown or other correlations yet.
2. **VLP fluid model:** constant Rs at average pressure; no pressure-dependent Rs evolution; vertical/uphill only (θ saturation).
3. **Nodal multiple intersections:** the non-monotonic (liquid-loading dip) path exists for future correlations; current Beggs–Brill configuration remains liquid-full monotonic in verified ranges.
4. **Auto IPR without Pb** defaults to Vogel and requires qmax or a test point — documented behavior, not a defect.
5. **Units:** field units throughout (psia, STB/D, ft, in); per-parameter unit metadata (`SENSUNIT_MAP`) governs output labels; no full unit-conversion architecture beyond `/convert`.
6. **Constraints supported:** min_pwf, max_liquid_rate, max_drawdown only.

## 8. Deployment

Railway auto-deploys every `main` commit via the existing GitHub→Railway integration. Bot identity `pvt_lab_ai_bot` (ID 8930247827) confirmed live via Telegram API. Engineering docs are versioned with the code in the repository.
