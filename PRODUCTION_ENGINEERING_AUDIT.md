# Production Engineering Audit — Read-Only Technical Report

**Repository:** jha68754-sys/petroleum-engineering-bot | **Branch:** main | **HEAD:** ccd46bb | **Date:** Aug 8, 2026
**Scope:** Read-only audit. No code modified, no commit, no push, no deploy.
**Author:** Manus AI — Senior Technical Lead review

---

## 1. Executive Findings (answers to the four questions)

| Question | Answer | Evidence |
|---|---|---|
| Can the platform calculate a complete IPR curve from engineering inputs? | **No.** It can only plot user-supplied rate/pressure data | `/plot ipr` is data-driven only (`handlers/text_handlers.py:handle_plot` + `constants.py` rules `ipr_plot`/`vlp_plot`/`nodal_plot`) |
| Can it auto-select Linear PI vs Vogel vs Composite IPR by Pr, Pb, Pwf? | **No.** No model-selection logic exists anywhere in the live path | Only reference text exists; no comparator in `services/` or `handlers/` |
| Can it calculate VLP from well/tubing/PVT inputs? | **No.** No vertical-flow calculation engine exists | No Hagedorn–Brown / Beggs–Brill / GLR code in the codebase |
| Can it solve the IPR–VLP intersection (operating point)? | **No.** `/plot nodal` draws two user-supplied curves; no solver | No root-finding or intersection code anywhere |

## 2. Classification of every Production Engineering capability

### 2.1 Fully implemented calculation engine (accessible from the live Telegram bot)

| Capability | Module / Function | Inputs | Output | Equation | Validation | Tests | Telegram |
|---|---|---|---|---|---|---|---|
| Linear Productivity Index | `constants.py` EXACT_FORMULAS `"productivity_index"`, executed by `services/pvt_engine.py:run_exact_calculation` | q (STB/day), Pr, Pwf (psi) | J (STB/day/psi) | J = q/(Pr−Pwf) | pr>pwf, q>0 | Covered by `test_engineering_corrections.py` | `/calc productivity_index` — **LIVE** |
| Linear PI via radial Darcy (single-point) | `constants.py` `"darcy"` | k, A, dP, μ, L | q (bbl/day) | q = 0.001127·k·A·dP/(μ·L) (field units, horizontal linear) | all > 0 | Same regression suite | `/calc darcy` — **LIVE** |

The two equations above are technically correct per Craft & Hawkins and Tiab & Donaldson field-unit conventions.

### 2.2 Partially implemented (exists but NOT wired into the live bot)

All of these live inside `petroleum_ai/`, which is **never imported** by `main.py`, `services/*`, `handlers/*`, or `config.py` (verified by full-grep: zero import paths into the bot runtime). They are a dormant legacy/experimental codebase.

| Capability | Module | Status |
|---|---|---|
| Vogel IPR single-point q from q_max | `petroleum_ai/calculators/vogel.py:calculate_vogel_ipr(p_wf, p_r, q_max)` | Correct equation (Vogel 1968), not reachable from Telegram |
| Vogel q_max from a test point | `petroleum_ai/calculators/production_calculators.py:calculate_vogel_q_max` | Correct algebra, not reachable |
| PI, Arps DCA (exponential/hyperbolic/harmonic) | `petroleum_ai/calculators/production_calculators.py` | Correct, not reachable |
| Radial Darcy inflow with skin (linear IPR form) | `petroleum_ai/calculators/darcy.py:calculate_radial_darcy_flow` | Correct (Tiab & Donaldson), not reachable |
| Skin factor, radius of investigation, transmissibility | `petroleum_ai/calculators/well_testing_calculators.py` | Correct, not reachable |
| Production engine + plugin system | `petroleum_ai/engines/production_engine.py`, `core/plugins/production_plugin.py` | Runs only PI + vogel_q_max internally; never launched |
| Knowledge base (Vogel, PI, DCA, Nodal, WC, GOR, choke texts) | `petroleum_ai/knowledge/production/production_kb.py`, `core/index/knowledge_index.py` | Reference content only; AI context builder (`services/ai_service.py:_build_engineering_context`) does NOT inject it |

### 2.3 Plotting/visualization only

`/plot ipr | vlp | nodal` (and `/check` with the same aliases) use user-supplied `p=` (rate) and `v=` (pressure) series only. Rules in `constants.py:538–564` define titles/axes/colors; `services/visualization.py` draws a professional PNG with dynamic caption. No inflow, lift, or intersection physics. This is exactly what was delivered and verified live earlier this week.

### 2.4 Knowledge / reference content only

The AI text layer (system prompt `prompts/system_prompt.txt` line ~105; ENGINE-FIRST policy in `services/ai_service.py`) contains prose about Vogel, Darcy, and PI, and `engineering_reasoner.py`/`reasoning/framework.py` mention "Fetkovich Multirate" as placeholder strings. The AI may explain IPR/VLP concepts in prose, but it is explicitly constrained by ENGINE-FIRST to route calculable questions to commands — and **no production command exists to route to**. Note: the ENGINE-FIRST list does not expose any production-equation inputs to the LLM, so a user asking "what is my q_max at Pr=3000, Pb=2200, test point q=500@1800" would get prose only.

### 2.5 Missing entirely

| Gap | Reference basis |
|---|---|
| **Composite IPR** (linear above Pb + Vogel below Pb for Pr > Pb with Pwf < Pb) | Economides, *Petroleum Production Systems*; Ahmed, *Reservoir Engineering Handbook* |
| **Fetkovich deliverability** (gas backpressure n-model, AOF) | Fetkovich 1973; Rawlins–Schellhardt backpressure test |
| **AOF** (absolute open flow potential) | Backpressure test methodology |
| **VLP / tubing performance** from inputs (diameter, depth, GLR, fluid PVT) | Hagedorn–Brown, Beggs–Brill (horizontal/multiphase) |
| **Operating-point solver** (IPR–VLP intersection, root-finding) | Brown *The Technology of Artificial Lift*; Economides nodal analysis |
| **Model auto-selection** (Linear PI vs Vogel vs Composite by Pr/Pb/Pwf) | Standard production-engineering workflow |
| **Choke performance, gas lift, ESP, production optimization** | No implementations |
| **Units/boilerplate handling for production inputs** | Consistent with existing /calc units (field) |

### 2.6 Validation rules & unit handling (live path)

Live `/calc` validation is per-formula lambda checks (e.g., `pr>pwf` for PI) with specific error messages (implemented this week). Units are field units (STB/day, psi, bbl/day, ppg, ft) and are documented per-input. Production plotting takes pure numeric arrays (unit-less by design). No production-unit conversions exist in `/convert` beyond general units.

### 2.7 Tests

`tests/` (bot CI surface): 7 files including `test_engineering_corrections.py`, `test_npv_z_regression.py`, `test_plot_shape_regression.py` (asserts ipr/vlp/nodal plot rules lack `shape`/`pivot` — consistent with the startup fix). `petroleum_ai/tests/` (dormant codebase): `test_production.py`, `test_petroleum_ai.py` (Vogel test) — **not run by any CI** (no `.github/workflows`, no test step in Procfile/Dockerfile). **Coverage of Production Engineering on the live path: 0% — nothing production-related executes in production tests because nothing exists in the live path.**

### 2.8 Integration summary

| Layer | IPR/VLP/Nodal integration |
|---|---|
| Telegram commands | Only data-driven plotting (`/plot ipr/vlp/nodal`) |
| AI / ENGINE-FIRST | No production calc commands to route to; prose guidance only |
| Calculation engine | `pvt_engine.py` has no production section |
| Knowledge/context injection | Not injected into AI context |

---

## 3. Gap Analysis Conclusion

| Category | Items |
|---|---|
| **CURRENTLY IMPLEMENTED** (live) | Linear PI (`/calc productivity_index`), linear Darcy rate (`/calc darcy`), data-driven IPR/VLP/Nodal plotting with dynamic captions |
| **PARTIALLY IMPLEMENTED** (dormant) | Vogel point calc, Vogel q_max, Arps DCA, radial Darcy w/ skin, skin/well-test calcs, production knowledge base — all in `petroleum_ai/`, unreachable from the bot |
| **PLOTTING ONLY** | IPR / VLP / Nodal curves (user data) |
| **KNOWLEDGE / AI TEXT ONLY** | ENGINE-FIRST prose; knowledge_index equations; kb articles |
| **MISSING** | Composite IPR, Vogel curve generation, Fetkovich, AOF, VLP engine, operating-point solver, model auto-selection, optimization/choke/artificial lift |
| **TEST COVERAGE** | Bot tests: none for production calculations; petroleum_ai tests: dormant, unrun |

## 4. Recommended Next Development Step

Build and wire a **production engine into the live bot path**: add `services/production_engine.py` exposing `/plot ipr`, `/plot vlp`, `/plot nodal` **auto-calculation** — composite IPR (linear above Pb, Vogel below Pb) from Pr, Pb, PI/q_max; a simplified multiphase VLP from depth/diameter/GLR/PVT; and a bisection/Newton **operating-point solver** returning the true nodal intersection. Register ENGINE-FIRST routing (`/ipr`, `/vlp`, `/nodal` or extended `/plot`), add regression tests in `tests/`, and preserve the existing user-data plotting mode for measured data. Dormant `petroleum_ai/` code should be audited separately before reuse.

---

**STOP — awaiting approval. No code was modified, committed, pushed, or deployed.**
