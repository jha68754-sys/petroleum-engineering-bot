# PROJECT HANDOVER — CURRENT STATE

**Document purpose:** Allow a future Manus session/agent to enter the existing Enterprise Petroleum AI Platform and continue development safely from EXACTLY where development stopped, without rebuilding, duplicating, or damaging verified work.

**Type:** READ-ONLY documentation. This document describes the CURRENT repository and live state as its sole source of truth.

**Date of handover:** 2026-08-09 (UTC+2)
**Updated:** 2026-08-13 — Phase 2 VLP implemented and merged (see ADDENDUM at the end)

---

## 1. PROJECT IDENTITY

| Item | Current state |
|---|---|
| Project name | Enterprise Petroleum AI Platform (Telegram) |
| Repository | `https://github.com/jha68754-sys/petroleum-engineering-bot` |
| Current main branch | `main` — latest commit `6e6fad2` (IPR) + **Phase 2 VLP commit** (deterministic VLP engine + `/calc vlp`, latest SHA in the ADDENDUM) |
| Production architecture | Modular Python app; entry point `main.py`; command dispatch via `handlers/command_registry.py` (Registry pattern); per-chat state in `state.py`; structured logging with token redaction; persistent long-polling offset survives Railway restarts; SIGTERM graceful shutdown; instance identity logging (PID, hostname, commit SHA); startup delay to prevent deploy-overlap 409 |
| Telegram bot architecture | `pvt_lab_ai_bot` (id 8930247827), long-polling Bot API, deterministic + AI-assisted modes, per-chat context state |
| Railway deployment architecture | One Railway service connected to the GitHub repo; **auto-deploys from `main`**. `railway.toml`: NIXPACKS builder, `python3 main.py` start, `ON_FAILURE` restart policy, max 5 retries, `LOG_LEVEL=INFO`, `POLLING_TIMEOUT=30`, `STARTUP_DELAY=45`. `Procfile` also defines worker/web (Railway's own config is authoritative) |
| Current entry point | `main.py` (worker process `python3 main.py`) |
| Python/runtime | Python 3.11 (`runtime.txt`); dependencies in `requirements.txt` (requests 2.32.3, python-dotenv, typing_extensions; Groq called via requests — no SDK) |
| AI provider | Groq (text) — `ai_service.py` calls the Groq API directly through `requests`; system prompt from `prompts/system_prompt.txt`, grounded in local knowledge base (`constants.py` rules + KB files) |
| ENGINE-FIRST architecture | `ai_service.py` appends an `ENGINE-FIRST POLICY` block to the LLM system context: whenever a question can be answered by a deterministic engine, the LLM MUST route the user to the exact command (`/calc`, `/estimate`, `/plot`, `/convert`) instead of computing in prose. Extended to cover IPR (`/calc ipr`) in commit `6e6fad2` |
| Deterministic engines | `services/pvt_engine.py` (correlations + unit conversion + EXACT formula runner), `services/production_engine.py` (IPR — Phase 1 complete), `services/vlp_engine.py` (VLP — **Phase 2 complete, Beggs-Brill 1973 segmented traverse**), `services/artificial_lift_engine.py` (ESP TDH, hydraulic HP, screening — reference helpers), `services/calculation_engine.py` (parsing/validation wrapper), `services/visualization.py` (Matplotlib PNG plots via `PVT_PLOT_RULES`) |
| Environment variables (NAMES ONLY) | `TELEGRAM_BOT_TOKEN`, `GPT_API_KEY`, `OPENAI_API_KEY` (Groq key), `GROQ_TEXT_MODEL`, `LOG_LEVEL`, `POLLING_TIMEOUT`, `OFFSET_STATE_FILE`, `TEMP_DIR` — **never print values** |

**Security rule for the next agent:** credentials are only in Railway secrets + GitHub Actions/repo secrets. Never log, print, or commit secret values.

---

## 2. COMPLETE DEVELOPMENT HISTORY

All items below are verifiable from the commit history, tests, and reports in the repository.

**A. Original capabilities (early commits).** The bot began as `bot.py`, then was professionally refactored into the current modular architecture: `main.py`, command registry, per-chat state (`state.py`), persistent offset, graceful shutdown, structured logging, deterministic + AI-assisted modes. `/start`, `/help`, `/analyze`, `/classify`, `/estimate`, `/calc`, `/convert`, `/plot` (file-based era), `/report`, `/cmg`, `/eclipse`, `/export_sim`, `/surface_separator`, `/check` (validate_pvt) were established.

**B. Later modules/features.** Professional PVT report generator (`/report`, commit `8c14e61`); expanded correlations including Vasquez-Beggs with separator conditions and Standing-Katz Z-factor; multi-series direct-data `/plot` (commits `8075e31`, `c98236c`); artificial lift engine (`services/artificial_lift_engine.py`, ESP TDH / hydraulic HP / screening); knowledge base and benchmarks under `petroleum_ai/`, `models/`, `prompts/`; many documentation/report files (`*_REPORT.md` family, ~50 md files in repo root).

**C. Engineering corrections.** See Section 8 for the full confirmed list (OGIP Bg units, PV/NPV separation, NPV comma parsing, Z-factor strict positivity, mud-weight safety note, etc.).

**D. Telegram/UI improvements.** `/glossary` was REMOVED per user request (commits `7d46397`, `19af292`) — the next agent must NOT reintroduce it. `/graph` was REMOVED (`f13b49b`, `e55bfe9`) — do not reintroduce. Startup/help messages localized to Arabic; enterprise-ready help with EIF capabilities (`1f1ea22`).

**E. Validation/guardrail improvements.** Hard-reject rules in calculators (e.g., DAK hard-reject, ppr/tpr strictly > 0), missing-data requirements that never invent values, ENGINE-FIRST behavior (`0c6a694`), startup `KeyError: 'shape'` hardening in `_build_engineering_context()` (`c959e3a`), parser resilience for non-numeric string keys (`6e6fad2`).

**F. AI/ENGINE-FIRST improvements.** Deterministic routing policy blocks LLM prose answers for calculatable questions; LLM may only interpret, explain, and contextualize engine outputs (`0c6a694`, extended to IPR in `6e6fad2`).

**G. Latest Production Engineering work (current).** **Phase 1 IPR is COMPLETE**: deterministic `services/production_engine.py` (Linear, Vogel, qmax inversion, Composite with C¹ continuity at Pb, deterministic model selection, guardrails, curve generation), `/calc ipr` + `/ipr` commands, calculated-IPR plotting (`plot=1`), ENGINE-FIRST IPR routing, and 37 new automated tests. Commit `6e6fad2`, pushed and deployed. **Phase 2 VLP is ALSO COMPLETE** (added 2026-08-13): `services/vlp_engine.py` (Beggs-Brill 1973 — flow pattern, holdup with inclination correction, two-phase friction with Lee-Gonzalez-Eakin gas viscosity, bracketed-bisection segmented traverse, static-gradient zero-rate fallback, hard guardrails), `/calc vlp` + `/vlp`, calculated VLP curve plots (`plot=1`, rate sweeps `q_min= q_max=`), ENGINE-FIRST routing extended to VLP, 29 tests in `tests/test_vlp_engine.py`, engineering documentation in `VLP_ENGINEERING_MODEL.md`; full suite 93/93 passing. Latest commit SHA in the ADDENDUM; live manual verification of VLP still PENDING.

---

## 3. CURRENT LIVE TELEGRAM CAPABILITIES

Registered commands (from `handlers/command_registry.py`; `glossary` and `graph` were removed and are NOT live):

| Command | Purpose | Supported types | Backend | Status |
|---|---|---|---|---|
| `/start` | Arabic welcome message | — | deterministic text | LIVE, verified |
| `/help` | Detailed command list (Arabic) | — | deterministic text (`constants.HELP_MESSAGE`) | LIVE |
| `/calc` | Deterministic exact formulas | see Section 4 | `services/calculation_engine.py` + `pvt_engine.run_exact_calculation`; IPR routed to `production_engine` | LIVE, verified |
| `/estimate` (alias `/corr`) | PVT correlations | see Section 5 | `pvt_engine.run_correlation` → `constants.CORRELATIONS` | LIVE, verified |
| `/plot` (alias `/pvt_plot`) | Direct numerical-data plotting (PNG via `reply_photo`) | bo, rs, bg, z, viscosity, mu_g, density, dropout, cgr, gor, wor, watercut, pressure, production, kr, ipr, vlp, nodal (+ aliases, see Section 7) | `handlers.text_handlers.handle_plot` + `services.visualization` | LIVE, verified (direct-data era) |
| `/classify` (alias `/classify_fluid`) | Fluid classification reasoning | — | AI reasoning with evaluation rules | LIVE |
| `/analyze` (alias `/document`) | Document analysis w/ file context (global state via `state.py`, commit `38d4e08`) | documents/files | AI + file processing | LIVE |
| `/report` (alias `/pvt_report`) | Professional engineering PVT report | PVT parameters | template-based report generator (commit `8c14e61`); strict "Not Provided" handling (commit `180221f`) | LIVE |
| `/convert` (aliases `/unit`, `/units`) | Unit conversion | length, pressure, temperature, rates, etc. | `pvt_engine.run_unit_conversion` | LIVE |
| `/reset` (aliases `/clear`) | Clear per-chat context | — | deterministic state reset | LIVE |
| `/check` (aliases `/validate`, `/validate_pvt`) | PVT data validation | PVT inputs | deterministic validation rules | LIVE |
| `/cmg`, `/eclipse`, `/export_sim` | Reservoir-simulator guidance/export hints | — | AI/knowledge | LIVE |
| `/surface_separator` | Separator calculations | separator data | deterministic engine | LIVE |
| `/pvto`, `/pvdg`, `/pvto`-family | PVT table generation guidance | table data | deterministic + AI bridge | LIVE |

Category distinction: **deterministic calculation** = `/calc`, `/convert`; **deterministic correlation** = `/estimate`; **plotting only** = `/plot`; **AI reasoning** = `/analyze`, `/classify`; **knowledge/reference** = `/help`, `/report`, `/cmg`, `/eclipse`, `/surface_separator`, `/pvdg` family.

---

## 4. DETERMINISTIC CALCULATORS (`/calc`)

All formula specs live in `constants.EXACT_FORMULAS`; runner in `services/pvt_engine.run_exact_calculation`; IPR is the exception handled by `services/production_engine.IPREngine` (`handle_calc_ipr` in `handlers/text_handlers.py`).

| Type | Command | Inputs & units | Output | Equation/model | Validation | Reference | File | Tests |
|---|---|---|---|---|---|---|---|---|
| API Gravity | `/calc api sg=<0.5–1.2>` | sg (SG) | deg API | API = 141.5/SG − 131.5 | sg range → light/medium/heavy classification | standard | constants.py | regression suite |
| OOIP | `/calc ooip area h phi sw bo` | acres, ft, fraction, fraction, rb/STB | STB | 7758·A·h·φ·(1−Sw)/Bo | positive finite inputs | Craft & Hawkins | constants.py | regression |
| OGIP | `/calc ogip` | area, h, phi, sw, bg | scf | 43560·A·h·φ·(1−Sw)/Bg | **Bg units: 43560 when Bg in ft³/scf; 7758 when Bg in rb/scf** (fixed commit `0c6a694`) | Craft & Hawkins | constants.py | regression |
| Darcy | `/calc darcy` | reservoir/rate params | STB/day | radial steady-state Darcy | positive, finite | standard | constants.py | regression |
| Productivity Index | `/calc productivity_index` | q, Pr, Pwf | STB/day/psi | J = q/(Pr−Pwf) | Pwf < Pr | standard | constants.py | regression |
| Recovery Factor | `/calc recovery_factor` | RF inputs | fraction | volumetric RF | bounds | standard | constants.py | regression |
| Hydrostatic | `/calc hydrostatic` | density, depth | psi | 0.052·ρ·D | positive | standard | constants.py | regression |
| Required Mud Weight | `/calc mud_weight_required` | pore pressure, depth | ppg | overbalance design | **includes safety note** (commit `0c6a694`) | standard | constants.py | regression |
| ECD | `/calc ecd` | mud weight, annular loss, depth | ppg | ECD = MW + losses | positive | standard | constants.py | regression |
| Water Cut | `/calc water_cut` | qw, qo | fraction | qw/(qw+qo) | positive | standard | constants.py | regression |
| WOR | `/calc wor` | qw, qo | ratio | qw/qo | positive | standard | constants.py | regression |
| Produced GOR | `/calc gor_produced` | qg, qo | scf/STB | qg/qo | positive | standard | constants.py | regression |
| PV | `/calc pv` | future cash flow, rate, periods | $ | single-cash-flow present value; **explicitly NOT a project NPV** (see note) | positive rate | finance | constants.py | `test_npv_z_regression.py` |
| NPV | `/calc npv rate cf=<comma list>` | rate, comma-separated cash flows | $ | true multi-cash-flow NPV; comma-list parsing hard fixed (commit `79acf0f`) | cf list fully valid finite | finance | constants.py | `test_npv_z_regression.py` |
| **IPR** | `/calc ipr [model=auto\|linear\|vogel\|composite] [plot=1] pr= [pb=] [j=] [qmax=] [q_test=] [pwf_test=] [pwf=]` | psia, STB/day | rate(s), qb, qo_max, model + reason | Linear PI; Vogel 1968 incl. qmax inversion; Composite (linear above Pb + Vogel below Pb, C¹ at Pb); deterministic CASE A/B/C selection; guardrails hard-reject PHYSICALLY_INVALID/OUTSIDE_ASSUMPTIONS/INSUFFICIENT_DATA | **Phase 1 COMPLETE — commit `6e6fad2`** | Vogel JPT 1968; Brown TAL Vol.1; Beggs | `services/production_engine.py` | **`tests/test_ipr_engine.py` — 37 tests, all passing** |

Additional notes: `parse_kv_args` (calculation_engine.py) tolerates comma-separated numeric lists and silently drops malformed/non-numeric values (fixed in `6e6fad2` so string keys like `model=vogel` never crash commands). IPR results always carry the "CALCULATED, not measured" note.

---

## 5. PVT / ESTIMATION ENGINE (`/estimate`)

Correlations live in `constants.CORRELATIONS` (keys + `func`, `formula_str`, `applicability`, validation); runner in `services/pvt_engine.run_correlation`.

| Correlation | Command | Inputs & units | Output | Reference | Validation | Tests |
|---|---|---|---|---|---|---|
| Standing Pb | `/estimate pb_standing` | Rs, gas_sg, T (°F), API | psia | Standing (1947) | input bounds via applicability | regression |
| Vasquez-Beggs Pb | `/estimate pb_vasquez_beggs` | Rs, gas_sg, T (°F), API, P_sep, **T_sep (required)** | psia | Vasquez & Beggs (1980) | **t_sep required** (commit `0c6a694`) | regression |
| Standing Rs | `/estimate rs_standing` | P, gas_sg, T, API | scf/STB | Standing (1947) | bounds | regression |
| Vasquez-Beggs Rs | `/estimate rs_vasquez_beggs` | P, gas_sg, T, API, P_sep, T_sep | scf/STB | Vasquez & Beggs (1980) | t_sep required | regression |
| Standing Bo | `/estimate bo_standing` | Rs, gas_sg, T, API | rb/STB | Standing (1947) | bounds | regression |
| Z-factor | `/estimate z_standing_katz` | Ppr, Tpr (pseudo-reduced) | Z | Standing-Katz (approximation per SPE & McCain; commit `b4582b7`) | **strict Ppr/Tpr > 0** (commit `79acf0f`); DAK hard-reject (`0c6a694`) | `test_npv_z_regression.py` |

Implementation location: `constants.py` (spec dicts, lines ~932+; VB helper functions ~1027–1090), `services/pvt_engine.py` (runner), `pvt_correlations.py` / `pvt_validators.py` (helpers). Test status: covered by the regression suite in `tests/` (all passing).

---

## 6. PRODUCTION ENGINEERING — CURRENT STATE (VERY IMPORTANT)

**Milestone:** Phase 1 IPR is **COMPLETE and manually verified on live Telegram**. **Phase 2 VLP is COMPLETE (implemented 2026-08-13, merged to main — live manual verification PENDING)**. Phase 3 Nodal is **NOT STARTED**.

Implementation details (commit `6e6fad2`):

| Component | File / function | Detail |
|---|---|---|
| Engine | `services/production_engine.py` — class `IPREngine` | `vogel_q`, `vogel_qmax_from_test`, `linear_j`, `linear_q`, `composite_segments`, `composite_q`, `select_model`, `_curve_pressures`, `build_curve`, `monotonicity_check`; model keys `vogel`/`linear`/`composite` with `MODEL_DISPLAY` names |
| Linear IPR | `linear_q`: q = J·(Pr−Pwf); `linear_j`: J = q/(Pr−Pwf) | Valid for Pwf ≥ Pb only |
| Vogel IPR | `vogel_q`: q/qmax = 1 − 0.2·(Pwf/Pr) − 0.8·(Pwf/Pr)² | Vogel, JPT (Jan 1968), pp. 83–92 |
| Vogel qmax inversion | `vogel_qmax_from_test`: qmax = q_test / [Vogel factor at Pwf_test] | Brown, TAL Vol. 1 — single test point calibration |
| Composite IPR | `composite_segments`: qb = J*·(Pr−Pb); qo_max = qb + qb·Pb/(1.8·(Pr−Pb)); `composite_q`: linear above Pb, Vogel-shaped below Pb anchored at (qb, Pb) extending to qo_max | Brown TAL Vol.1 Ch.5; Beggs Ch.3; Fetkovich SPE 4529 (1973). **C¹-continuous at Pb** (value and slope −J* match) |
| Model selection | `select_model(pr, pb, pwf)` | CASE A Pr≤Pb → Vogel; CASE B Pr>Pb & Pwf≥Pb → Linear; CASE C Pr>Pb & Pwf<Pb → Composite; curve-mode (no Pwf) with Pb → Composite, without Pb → Vogel with warning |
| Guardrails | `ValueError` with prefixes `PHYSICALLY_INVALID` / `OUTSIDE_ASSUMPTIONS` / `INSUFFICIENT_DATA` | Handler converts to "Engineering Guardrail" user messages; hard-reject: Pr≤0, Pb≤0, Pwf<0, Pwf>Pr, q_test≤0, J≤0, qmax≤0, composite with Pr≤Pb |
| Curve generation | `build_curve` | 10 deterministic pressure points from Pr to 0, Pb included for composite, monotonicity-checked; used by the plot path |
| Calculated IPR plot | `handle_calc_ipr` with `plot=1` | PNG via `generate_pvt_plot("ipr_plot", ...)` with label "Calculated — <model>"; text response always notes "CALCULATED (correlation-based), not measured" |
| Telegram commands | `handlers/text_handlers.py` — `handle_calc_ipr` (registry key `ipr`), routed from `/calc ipr` | Usage message lists all parameters + units; missing-data message lists exactly what is needed, never invents values |
| ENGINE-FIRST IPR routing | `services/ai_service.py` ~line 208 | LLM instructed to NEVER answer IPR questions in prose; always route to `/calc ipr` |

**Manually verified on live Telegram (consistent with current code/history):**

| Case | Inputs | Verified output |
|---|---|---|
| Linear IPR | Pr=3000, J=1.5, Pwf=2000 | q = 1500 STB/day |
| Vogel | Pr=3000, qmax=1500, Pwf=1200 | q = 1188 STB/day |
| Vogel qmax inversion | Pr=3000, q_test=600, Pwf_test=1500 | qmax ≈ 857.1 STB/day |
| Composite | Pr=3000, Pb=2200, q_test=900, Pwf_test=2400, Pwf=1200 | qb = 1200 STB/day, qo_max ≈ 3033.3 STB/day, q ≈ 2396.9 STB/day |
| Guardrail | Pr = −100 (negative) | Correctly REJECTED as PHYSICALLY_INVALID |

Automated coverage: `tests/test_ipr_engine.py` — 37 tests (Vogel factors, inversion round-trip, C¹ value and slope continuity at Pb, benchmarks, model selection cases A/B/C, guardrail rejects, curve monotonicity, display names) — all passing.

### Phase 2 VLP (implemented 2026-08-13)

**Module:** `services/vlp_engine.py` — correlation **Beggs-Brill (1973)** (Hagedorn-Brown explicitly deferred — see `VLP_ENGINEERING_MODEL.md`). Full model detail, benchmarks, and references live in that document.

| Component | File / function | Detail |
|---|---|---|
| Engine | `services/vlp_engine.py` — `traverse` | Field-unit Beggs-Brill: free-gas split (`max(GOR−Rs,0)×q_t`), Brown-form liquid density, real-gas ρg, Lee-Gonzalez-Eakin gas viscosity (**density converted to g/cm³ — published form**), Colebrook/Haaland, flow pattern (L1–L4), HL(θ) with transition weighting and inclination C = (1−λ)ln(d·λᵉ·N_LVᶠ / N_Reᵍ), two-phase friction f_tp = f_n·e^S; bracketed-bisection segment solver (80 segments, global cap 4000 iters); `static_gradient` for zero rate; hard-fail kinds PHYSICALLY_INVALID / NUMERICAL_NON_CONVERGENCE / CORRELATION_LIMITATION |
| Validation / requirements | `validate_inputs`, `missing_inputs`, `REQUIRED_INPUTS`/`OPTIONAL_INPUTS` | thp, tvd, id, q, gor, rs, api, gamma_g, mu_l, bo, t_wh, geothermal required; wc/qw/q consistency; guardrails per Section 8 style; curve needs ≥2 points |
| Curve generation | `vlp_curve` | Linear rate sweep `q_min → q_max`; zero-rate point resolved with `static_gradient` |
| Calculated VLP plot | `handle_calc_vlp` with `plot=1` | PNG via `generate_pvt_plot("vlp_plot", ...)` with label "Calculated — Beggs-Brill (1973)" |
| Telegram commands | `handlers/text_handlers.py` — `handle_calc_vlp` (registry key `vlp`), routed from `/calc vlp` and `/vlp` | Usage + missing-data messages; engine guardrails converted to user messages |
| ENGINE-FIRST VLP routing | `services/ai_service.py` | LLM instructed to NEVER answer VLP questions in prose; always route to `/calc vlp` |

**Automated benchmarks (hand/analytical, in `tests/test_vlp_engine.py`):** liquid-full well (GOR=Rs) Pwf 2412.7 (analytic 2412.78, agreement 0.03 psi); two-phase base case within ±2 psi of an independent marching model; deep stress case within ±15 psi; static column ~117 psia (analytic exponential gas column). Physics invariants enforced: Pwf ≥ THP always; friction = 0 at zero rate; deeper well / higher THP / higher water cut / narrower tubing never reduce required BHP; liquid-full monotonicity (gas-rich loading-region non-monotonicity is real physics — documented, not asserted away).

---

## 7. PLOTTING (`/plot`)

**Architecture:** `handlers/text_handlers.handle_plot` parses direct numerical arguments (`p=`/`x=` for X-axis, `v=`, `v2=`… for Y-series, `labels=`, `pb=`, `well=`), resolves the relationship key via `constants.PLOT_ALIASES` → `constants.PVT_PLOT_RULES`, then `services.visualization` renders a professional Matplotlib PNG sent via `reply_photo`. No document upload, no legacy routing.

**Supported plot types (direct user-data plotting):** bo, rs, bg, z, oil/gas viscosity, liquid dropout (CVD), CGR, P-T phase envelope, oil density, relative volume (CCE/CME), GOR, WOR, water cut, pressure (p_vs_t), production (q_vs_t), Kr (kro/krw vs Sw), ipr, vlp, nodal (ipr/vlp/nodal plot *types* exist as rules but **no deterministic VLP/nodal engines yet** — see Section 10).

**DISTINCTION — critical for the next agent:**

| Mode | Description | Trigger |
|---|---|---|
| **DIRECT USER-DATA PLOTTING** | Plots ONLY the user-supplied p=/v= values; fully backward compatible; MUST remain unchanged | `/plot <type> p=... v=...` |
| **CALCULATED ENGINEERING PLOTTING** | Engine-computed curves marked "Calculated — <model>" | e.g. `/calc ipr ... plot=1` (IPR), `/calc vlp ... plot=1` and rate sweeps (VLP) |

**Recent UI cleanup (commit `ccd46bb`):** `/plot` help message presents plot types without syntax notation, one clear example, organized categories. Do not revert.

**Verified live:** direct-data PNG plotting including the user's Rs curve command (`/plot rs p=500,1000,... v=180,350,... pb=2000` pattern).

---

## 8. IMPORTANT CORRECTIONS ALREADY COMPLETED (DO NOT UNDO)

| Correction | Commit | Detail |
|---|---|---|
| OGIP Bg unit handling | `0c6a694` | 43560 when Bg in ft³/scf; 7758 when Bg in rb/scf |
| PV vs true multi-cash-flow NPV separation | `0c6a694` | `/calc pv` is single-cash-flow present value only; `/calc npv` handles multiple cash flows |
| NPV comma-separated parsing | `79acf0f` | comma-list parsing hard-fixed |
| Z-factor strict validation | `79acf0f` | Ppr/Tpr must be **strictly > 0** (zero rejected) |
| DAK hard-reject + mud-weight safety note | `0c6a694` | guardrail messages, safety note on required mud weight |
| Vasquez-Beggs t_sep required | `0c6a694` | t_sep enforced as required input |
| Professional PVT report integrity | `180221f`, `5b6ee68`, `b4582b7` | no hallucinated fallback lab data; unprovided parameters marked; SPE/McCain/Craft&Hawkins/Whitson&Brulé grounding |
| `/plot` KeyError `'shape'` startup crash | `c959e3a` | `_build_engineering_context()` hardened; regression test added for rules without `shape` |
| `/plot` dynamic captions & per-type titles/labels | `8e08f20` | captions derived per plot type |
| `/plot` help presentation cleanup | `ccd46bb` | no syntax notation, one example, organized types |
| ENGINE-FIRST behavior | `0c6a694`, extended `6e6fad2` | deterministic routing for all calculatable questions incl. IPR |
| Parser resilience to non-numeric string keys | `6e6fad2` | `model=vogel`-style keys never crash `/calc` |
| `/ipr` no-args crash (IndexError) fix | `6e6fad2` | command prefix stripped safely |
| Lee-Gonzalez-Eakin gas viscosity units | VLP commit | density converted lbm/ft³ → g/cm³ (published form); unpatched use caused absurd friction and solver divergence |

---

## 9. TEST STATUS

**Automated test count: 93 tests, ALL PASSING** (`python3 -m unittest discover -s tests`, run with dummy env vars).

| Test file | Tests | Coverage |
|---|---|---|
| `tests/test_vlp_engine.py` | 29 | VLP engine: hand benchmarks (liquid-full, two-phase, deep stress, static), physics invariants, guardrail rejects, missing inputs, curve rules |
| `tests/test_ipr_engine.py` | 37 | IPR engine: Vogel, inversion, linear, composite (benchmarks, C¹ continuity + slope, model selection, guardrails, curves) |
| `tests/test_engineering_corrections.py` | 11 | OGIP units, DAK, mud-weight note, ENGINE-FIRST behavior, etc. |
| `tests/test_npv_z_regression.py` | 10 | NPV comma parsing, PV/NPV separation, Z-factor strict positivity |
| `tests/test_plot_shape_regression.py` | 2 | shape-key guardrail regression |
| `tests/test_artificial_lift.py` | 4 | ESP TDH / hydraulic HP helpers |

**Verification tiers:**

| Tier | Items |
|---|---|
| **AUTOMATED TESTED** | All 93 tests above; calculators, correlations, IPR engine, VLP engine, validations, regressions |
| **MANUALLY VERIFIED ON LIVE TELEGRAM** | OGIP (101,640,000,000), Z valid/invalid, NPV (−137,490.61), `/plot` direct-data PNG, Phase 1 IPR five cases (Section 6) |
| **NOT YET VERIFIED (manual)** | `/classify`, `/analyze`, `/report`, `/convert`, `/check`, `/cmg`/`/eclipse`, `/surface_separator`, most `/calc` production commands (darcy, hydrostatic, ecd, water_cut, wor, gor_produced, productivity_index, recovery_factor) |

---

## 10. CURRENT LIMITATIONS / MISSING FEATURES

Verified against current code (not assumed from old reports):

| Item | Status |
|---|---|
| **VLP deterministic engine** (Beggs-Brill, Hagedorn-Brown, pressure traverse, calculated VLP curve) | **IMPLEMENTED 2026-08-13**: Beggs-Brill segmented traverse in `services/vlp_engine.py`, `/calc vlp` + `/vlp`, calculated curve plots, ENGINE-FIRST routing, 29 tests — `Hagedorn-Brown deferred` (see `VLP_ENGINEERING_MODEL.md`); `vlp_plot` rule also still serves direct-data plotting |
| **Nodal solver** (IPR–VLP intersection, operating point) | **MISSING** — `nodal_plot` rule exists for direct data only |
| Choke optimization / production optimization / artificial lift optimization | **MISSING** (only ESP TDH/hydraulic-HP helper functions in `artificial_lift_engine.py`; gas-lift/ESP system design not implemented) |
| Fetkovich / AOF as standalone calculators | **MISSING** (composite IPR cites Fetkovich but no Fetkovich command exists) |
| Web dashboard | **MISSING** |
| Session/history persistence (cross-restart) | Partial — per-chat state in memory + persistent polling offset; no durable history DB |
| PDF/CSV export of results | **MISSING** (Excel simulator export exists as guidance only) |
| Multi-well reporting | **MISSING** |

---

## 11. EXACT CURRENT STOPPING POINT

Verified against the repository:

> **PRODUCTION ENGINEERING — Phase 1 IPR: COMPLETE + MANUALLY VERIFIED (commit `6e6fad2`). Phase 2 VLP: COMPLETE, MERGED (commit in ADDENDUM) — MANUAL LIVE VERIFICATION PENDING. Phase 3 Nodal Analysis: NOT STARTED.**

Nodal, choke, and optimization code do NOT exist. The next phase to start is **Phase 3: Nodal Analysis (IPR–VLP intersection)** — only after Phase 2 is manually verified on live Telegram (5 test commands in the ADDENDUM).

---

## 12. NEXT DEVELOPMENT ROADMAP (INTENDED SEQUENCE)

1. ~~Phase 2 — VLP deterministic engine~~ **DONE** (Beggs-Brill 1973; Hagedorn-Brown deferred; traverse + `/calc vlp` + curve plots + ENGINE-FIRST + 29 tests). Live manual verification PENDING (5 commands in ADDENDUM).
2. **Next: Phase 3 — Nodal Analysis** (IPR–VLP intersection solver, operating-point determination) — must reuse the IPR engine (linear/vogel/composite) and the new VLP engine, and must extend ENGINE-FIRST routing to `/calc nodal`.
3. Later: production optimization, artificial lift design, choke optimization, and other advanced capabilities.

**Do NOT implement these now. Do NOT begin Nodal until VLP is manually verified live.**

---

## 13. PROTECTED FUNCTIONALITY (DO-NOT-BREAK LIST)

The next agent must preserve, without regression, all of:

- All `/calc` calculators (api, ooip, ogip, darcy, recovery_factor, productivity_index, hydrostatic, mud_weight_required, ecd, water_cut, wor, gor_produced, pv, npv) including the OGIP Bg unit fix and PV/NPV separation
- All `/estimate` correlations (pb/rs_standing, pb/rs_vasquez_beggs, bo_standing, z_standing_katz) including strict Ppr/Tpr > 0 and t_sep requirements
- **The complete Phase 1 IPR engine** and `/calc ipr` + `/ipr` commands
- All guardrails and ENGINE-FIRST routing
- All live Telegram commands in Section 3 (including `/classify`, `/analyze`, `/report`, `/convert`, `/reset`, `/check`, `/cmg`, `/eclipse`)
- `/plot` **direct user-data plotting** with full backward compatibility, all plot types, and the help-message cleanup
- The `KeyError: 'shape'`-hardened AI context builder
- Deployment path: GitHub `main` → Railway auto-deploy (`railway.toml` start command, `Procfile`)
- Railway secrets and environment variables (names unchanged; values untouched)

**Also confirmed removed — do NOT reintroduce:** `/glossary` and `/graph`.

---

## 14. GITHUB / DEPLOYMENT STATE

| Item | State |
|---|---|
| Current branch | `main` |
| Latest commit | `6e6fad2` — pushed, verified on GitHub |
| Working tree | Clean (`git status` shows no modified tracked files) |
| GitHub push status | SUCCESS (`ccd46bb..6e6fad2 main -> main`) |
| Railway relationship | Existing Railway service connected to this repo; auto-deploys from `main`; NO Railway dashboard access available to agents — deploy only via GitHub push |
| Production bot | `pvt_lab_ai_bot` long-polling confirmed live (Telegram API 409 conflict = active polling instance right after deploy) |
| Deployment verification limit | Railway logs cannot be independently read without dashboard authentication; deployment confirmed indirectly via bot polling responsiveness |

---

## 15. INSTRUCTIONS FOR THE NEXT MANUS AGENT

1. Read this handover first, in full.
2. Inspect the current code before modifying anything; the repository is the source of truth, not any previous conversation.
3. Do not rebuild existing engines (PVT, calculators, IPR, plotting).
4. Do not alter verified engineering equations without written evidence from authoritative references (Vogel 1968; Brown, *The Technology of Artificial Lift Methods* Vol. 1; Beggs, *Production Optimization Using Nodal Analysis*; Fetkovich SPE 4529; Craft & Hawkins; SPE/McCain for Z-factor).
5. Preserve backward compatibility, especially `/plot` direct-data mode.
6. Never let the LLM invent numerical engineering results when a deterministic engine exists; extend ENGINE-FIRST routing for every new engine.
7. Run the full regression suite (`python3 -m unittest discover -s tests`, with dummy env vars) before AND after every change.
8. Do not reintroduce `/glossary` or `/graph`; do not touch Railway secrets.
9. Continue from **Phase 3: Nodal Analysis (IPR–VLP intersection)** — reuse `production_engine.IPREngine` and `vlp_engine.traverse`/`static_gradient`/`vlp_curve`.
10. First, complete the PENDING live manual verification of Phase 2 VLP (5 commands in the ADDENDUM) before starting Nodal.
11. After each push, wait for Railway auto-deploy and verify the live bot before declaring success.

---

## HANDOVER STATUS

| Field | Value |
|---|---|
| Repository | `https://github.com/jha68754-sys/petroleum-engineering-bot` |
| Current branch | `main` |
| Current commit | `6e6fad2` + **VLP commit** (see ADDENDUM; run `git log -1 --format='%H'` on main) |
| Current production milestone | Production Engineering — Phase 2 VLP |
| Last completed phase | Phase 2 VLP (deterministic Beggs-Brill engine + `/calc vlp` + `/vlp` + calculated VLP plots + ENGINE-FIRST routing + 29 tests) — manual live verification PENDING |
| Next phase | Phase 3 — Nodal Analysis (IPR–VLP intersection) |
| Application code changed | YES — Phase 2 VLP implementation (see ADDENDUM) |
| Deployment changed | VLP commit pushed; Railway auto-deploy expected; bot live-polling verified |
| Secrets exposed | NO |

**PROJECT HANDOVER COMPLETE — READY FOR NEXT AGENT**

---

## ADDENDUM — PHASE 2: VLP IMPLEMENTATION SUMMARY (2026-08-13)

**New files:** `services/vlp_engine.py` (deterministic Beggs-Brill 1973 VLP engine: flow-pattern determination, horizontal holdup + inclination correction with transition weighting, Lee-Gonzalez-Eakin gas viscosity with g/cm³ conversion, Colebrook two-phase friction, bracketed-bisection segmented pressure traverse with 80 segments and per-segment budgets, `static_gradient` for zero-rate, `vlp_curve` sweep, `validate_inputs`/`missing_inputs`, hard guardrail kinds), `tests/test_vlp_engine.py` (29 tests), `VLP_ENGINEERING_MODEL.md` (full model documentation with references and transparent limitations).

**Modified files:** `handlers/text_handlers.py` (`handle_calc_vlp`, `/calc vlp` + `/vlp` dispatch before the ipr branch, curve-mode rate sweep with zero-rate static fallback, `plot=1` PNG via existing `vlp_plot` rule), `services/ai_service.py` (ENGINE-FIRST routing extended to VLP).

**Benchmarks verified by hand/analytical calculation:** liquid-full well Pwf = 2412.7 psia (analytic 2412.78); two-phase base case 356 psia (independent marching model ±2 psi); deep stress case ~1948 psia (±15 psi); static column ~117 psia.

**Test suite:** 93/93 passing (29 new VLP + 64 existing).

**Deferred by design:** Hagedorn-Brown (see `VLP_ENGINEERING_MODEL.md` §6 — the reuse-ready traverse skeleton makes it an additive `model=hagedorn_brown` later).

**FIVE LIVE TELEGRAM VERIFICATION TESTS (PENDING owner execution):**

| # | Command | Expected |
|---|---|---|
| 1 | `/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5` | Two-phase Pwf ≈ 356 psia |
| 2 | `/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=600 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5` | Liquid-full Pwf ≈ 2413 psia |
| 3 | `/calc vlp thp=100 tvd=8000 id=1.995 q_min=0 q_max=8000 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 plot=1` | VLP curve table + PNG plot |
| 4 | `/calc vlp thp=-10 tvd=8000 id=1.995 q=3000 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5` | REJECTED — guardrail |
| 5 | `/calc vlp` | Missing-data requirement message |

**PHASE 2 IMPLEMENTED — AWAITING MANUAL VLP VERIFICATION**
