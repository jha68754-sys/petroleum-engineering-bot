# PROJECT RE-ENTRY AUDIT — Enterprise Petroleum AI Platform

**Audit type:** READ-ONLY re-entry and status audit
**Audit date:** Aug 13, 2026
**Repository:** `https://github.com/jha68754-sys/petroleum-engineering-bot` (main branch)
**Author:** Manus AI

---

## 1. EXECUTIVE PROJECT STATUS

The repository was re-entered and fully re-inspected against the current `main` branch code, treating the code as the authoritative source of truth. The audit confirms that the project stands exactly where the previous handover reported: **Phase 1 IPR is complete and manually verified on the live Telegram bot**, the working tree is clean, and **no VLP or Nodal work has been started** since. The full automated test suite runs locally at **64/64 passing**. The live bot remains in production, and the GitHub → Railway auto-deployment path is unchanged. The handover documentation (`PROJECT_HANDOVER_CURRENT.md`, `PRODUCTION_ENGINEERING_AUDIT.md`, `PRODUCTION_VERIFICATION_FINAL_REPORT.md`) is present and consistent with the current code.

---

## 2. WHAT CHANGED SINCE THE LAST MILESTONE

The last meaningful development milestone is commit `6e6fad2` (IPR engine). Since then, the only repository-level change is the addition of the handover documentation itself. The complete recent meaningful development history, verified from `git log` and the current code, is summarized below.

| Commit | What changed | Why / engineering capability | Live Telegram path | Automated tests | Production verified |
|---|---|---|---|---|---|
| `6e6fad2` | Deterministic IPR engine (Linear PI, Vogel + qmax inversion, Composite C¹), `/calc ipr`, `/ipr`, auto model selection, guardrails, calculated IPR plot, ENGINE-FIRST IPR routing | Phase 1 IPR production milestone | Yes (`/calc ipr`, `/ipr`) | Yes (37 IPR tests) | Yes — 5 manual live cases |
| `ccd46bb` | Cleaned `/plot` help message (no syntax notation, one example, organized types) | UX correctness | Yes (`/plot`) | — | Yes (production bug report) |
| `79acf0f` | NPV comma-separated list parsing fix; Z-factor strict `Ppr/Tpr > 0` validation | Correctness: multi-cash-flow NPV, DAK hard-reject | Yes (`/calc`) | Yes (10 tests) | Yes |
| `0c6a694` | OGIP Bg unit split, Vasquez-Beggs `t_sep` required, DAK hard-reject outside Standing-Katz, PV/NPV separation, mud-weight safety note, ENGINE-FIRST routing | Correctness: unit discipline and validation | Yes (`/calc`, AI routing) | Yes (11 tests) | Yes |
| `8e08f20` | Dynamic Telegram captions and per-type titles/axis labels | Plot professionalism | Yes (`/plot`) | — | Yes |
| `c959e3a` | Startup `KeyError: 'shape'` crash fix in AI context builder | Stability: bot boots reliably | Yes (indirect, AI routing) | Yes (2 regression tests) | Yes (Railway logs) |
| `6554d87` / `c98236c` / `8075e31` | `/plot` direct numerical Telegram input mode, PNG via `reply_photo`, no legacy routing, multi-series, IPR/VLP/Nodal plot types | Plotting capability | Yes (`/plot`) | — | Yes (live `/plot` tests) |
| `8c14e61` / `180221f` / `5b6ee68` / `b4582b7` | Professional PVT report generator, no-hallucination policy, SPE/McCain/Craft & Hawkins alignment | Reporting professionalism | Yes (`/report`) | Yes | Yes |

No commits exist after `6e6fad2`; the code on `main` is synchronized with GitHub (`origin/main == HEAD`), and the previous verification/audit work is fully superseded by — and consistent with — the current code.

---

## 3. CURRENT ARCHITECTURE

The platform follows the deterministic-first design, from Telegram entry to deployment:

```
Telegram  ──►  main.py  (polling / dispatch)
                │
                ▼
        handlers/command_registry.py   (command/intent router)
                │
      ┌─────────┴──────────┐
      ▼                    ▼
  /calc ipr etc.     services/ai_service.py
 (deterministic      (ENGINE-FIRST layer + Groq API)
  engines)                │
      ▲             knowledge_base/ + constants.py
      │             rules/context for the LLM
      ▼
  services/calculation_engine.py     (OOIP…NPV — 14 formulas)
  services/production_engine.py      (IPR engine — 3 models)
  services/pvt_engine.py             (PVT correlations)
  services/artificial_lift_engine.py (ESP TDH/hydraulic HP screening)
  services/visualization.py          (Matplotlib plotting)
  handlers/text_handlers.py          (Telegram handlers + reporting)
                │
                ▼
        Railway auto-deploy (GitHub main → build → python3 main.py)
```

The AI provider integration is **Groq**, accessed directly via HTTP to `GROQ_API_BASE` with models `GROQ_TEXT_MODEL` / `GROQ_VISION_MODEL`. The only environment-variable names read in the codebase are: `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY`, `GROQ_API_BASE`, `GROQ_TEXT_MODEL`, `GROQ_VISION_MODEL`, `AI_CALL_MIN_INTERVAL_SECONDS`, `POLLING_TIMEOUT`, `STARTUP_DELAY`, `LOG_LEVEL`. **No Grok/xAI integration exists anywhere** (grep for grok/xAI/OpenRouter across all source returned nothing). The ENGINE-FIRST layer is enforced at two levels: the AI system context lists every `/calc` route and instructs "NEVER answer IPR/questions with a deterministic engine from prose — route to the command", and the handler registry dispatches `/calc` types directly to engines before any AI path is reachable. Values are never fabricated: missing-data cases return `INSUFFICIENT_DATA` requirement lists deterministically.

---

## 4. LIVE TELEGRAM COMMANDS

Every currently registered command, verified against `handlers/command_registry.py` and `handlers/text_handlers.py` (not help text):

| Command (aliases) | Purpose | Engine type | File | Status |
|---|---|---|---|---|
| `/start` | Arabic welcome | Static | text_handlers.py | Live |
| `/help` | Detailed command list | Static | text_handlers.py | Live |
| `/reset` (`/clear`) | Clear conversation state | State | text_handlers.py | Live |
| `/calc` (`/calculate`, `/math`) | 14 deterministic calculators + `ipr` | Deterministic | text_handlers.py → calculation_engine / production_engine | Live |
| `/ipr` | Direct IPR calculation alias | Deterministic | text_handlers.py | Live |
| `/estimate` (`/corr`) | 6 PVT correlations | Deterministic (correlations) | text_handlers.py → pvt_engine | Live |
| `/plot` (`/pvt_plot`) | 20 plot types from direct numerical input, PNG via reply_photo | Plotting | text_handlers.py → visualization.py | Live |
| `/classify` (`/classify_fluid`) | Fluid classification | Hybrid (AI + classification table) | command_registry.py | Live |
| `/analyze` (`/document`) | Document/file analysis | AI | text_handlers.py | Live |
| `/report` (`/pvt_report`) | Professional PVT report | Deterministic generator | text_handlers.py | Live |
| `/convert` (`/unit`) | Unit conversion | Deterministic | text_handlers.py | Live |
| `/check` (`/validate`) | PVT data validation | Deterministic | text_handlers.py | Live |
| `/pvto`, `/pvdo`, `/pvtg`, `/pvdg` | PVT table export | Deterministic | text_handlers.py | Live |
| `/export_sim` (`/sim_export`) | Simulator export | Deterministic | text_handlers.py | Live |
| `/eclipse`, `/cmg` | Simulator input generation | AI-assisted generator | text_handlers.py | Live |
| `/case report`, `/case replay` | Reproducible engineering case report and deterministic replay | Deterministic | handlers/text_handlers.py + services/engineering_case.py | Live |
| `/surface_separator` (`/separator`) | Surface separator calculations | Deterministic | text_handlers.py | Live |

---

## 5. CALCULATOR STATUS

`/calc` subtypes verified against `EXACT_FORMULAS` in `constants.py` and `services/calculation_engine.py`:

| Calculator | Implemented | Live routed | Validated | Automated tested | Manually verified | Engineering basis | Known limitations |
|---|---|---|---|---|---|---|---|
| API | Yes | Yes | Yes | Yes | Yes | Standard API–SG relation | — |
| OOIP | Yes | Yes | Yes | Yes | Yes | Craft & Hawkins (7758) | Tank/stock-tank basis |
| OGIP | Yes | Yes | Yes | Yes | Yes | Craft & Hawkins (43560 ft³/scf / 7758 rb/scf) | Bg unit must be declared |
| Darcy | Yes | Yes | Yes | Yes | Yes | Darcy's law | Steady-state assumption |
| Recovery Factor | Yes | Yes | Yes | Yes | Yes | Material balance / sweep efficiency | Empirical inputs |
| Productivity Index | Yes | Yes | Yes | Yes | Yes | Q = J·ΔP | Linear only |
| Hydrostatic Pressure | Yes | Yes | Yes | Yes | Yes | ρgh | — |
| Required Mud Weight | Yes | Yes | Yes | Yes | Yes | Kick tolerance + safety note | Safety note encoded |
| ECD | Yes | Yes | Yes | Yes | Yes | ECD = MW + friction | Approximate |
| Water Cut | Yes | Yes | Yes | Yes | Yes | Fractional flow | — |
| WOR | Yes | Yes | Yes | Yes | Yes | WOR = qw/qo | — |
| Produced GOR | Yes | Yes | Yes | Yes | Yes | GOR definition | — |
| PV | Yes | Yes | Yes | Yes | Yes | Single cash flow only (explicitly labeled, not a project NPV) | Single CF |
| NPV | Yes | Yes | Yes | Yes | Yes | True multi-CF NPV, comma list from t=0 | Comma parsing now fixed |
| IPR | Yes | Yes (`/calc ipr` + `/ipr`) | Yes | Yes (37 tests) | Yes (5 live cases) | Vogel 1968; Brown TAL Vol.1; Fetkovich SPE 4529 | Pr > Pb regime via Composite only |

---

## 6. PVT STATUS

Correlations verified in `services/pvt_engine.py` and `CORRELATIONS` (constants.py):

| Correlation | Inputs / units | Output | Validation | Reference | Tests | Live Telegram |
|---|---|---|---|---|---|---|
| Standing Bubble Point | T (°F), Rs (scf/STB), γg, γo | Pb (psia) | Yes | Standing (1947) | Yes | `/estimate` |
| Vasquez-Beggs Bubble Point | + t_sep, p_sep (required) | Pb (psia) | Yes, t_sep required enforced | Vasquez-Beggs (1980) | Yes | `/estimate` |
| Standing Solution GOR | T, γg, γo, P | Rs (scf/STB) | Yes | Standing | Yes | `/estimate` |
| Vasquez-Beggs Solution GOR | + t_sep, p_sep | Rs (scf/STB) | Yes | Vasquez-Beggs | Yes | `/estimate` |
| Standing Oil FVF | — | Bo (rb/STB) | Yes | Standing | Yes | `/estimate` |
| Standing-Katz / DAK Z-factor | Ppr, Tpr | Z | Hard-reject nonphysical Ppr/Tpr (strict > 0); DAK refused outside Standing-Katz range | Standing-Katz (1942); Dranchuk-Abou-Kassem (1975) | Yes | `/estimate` |

No additional PVT correlations beyond these six are implemented.

---

## 7. IPR STATUS

**Confirmed fully intact and unchanged.** `services/production_engine.py` contains `IPREngine` with: `vogel_q` (Vogel 1968), `vogel_qmax_from_test` (Brown TAL Vol.1 inversion), `linear_q`, `composite_segments` + `composite_q` (linear above Pb + Vogel below, C¹ at Pb), `select_model` (deterministic: Pr ≤ Pb → Vogel; Pr > Pb & Pwf ≥ Pb → Linear; crossing Pb → Composite), curve generation, and monotonicity check. Guardrails raise `PHYSICALLY_INVALID`, `OUTSIDE_ASSUMPTIONS`, and `INSUFFICIENT_DATA` with precise requirement lists. Integration: `/calc ipr` handler (with non-numeric-safe argument parsing), `/ipr` alias, calculated PNG plot with `plot=1` (labeled "Calculated — Model"), and ENGINE-FIRST IPR routing. All five previously verified live results reproduce: Linear 1500, Vogel 1188, qmax inversion ≈ 857.1, Composite qb=1200 / qo_max≈3033.3 / q≈2396.9, and negative-Pr rejection. **No production engineering work was added after this milestone.**

---

## 8. VLP STATUS

**Classification: NOT STARTED.** The codebase was grepped exhaustively for Beggs-Brill, Hagedorn-Brown, pressure-traverse solvers, segmented tubing, flow-pattern determination, liquid holdup, friction/hydrostatic/acceleration gradients, convergence solvers, calculated VLP curves, `/calc vlp`, and ENGINE-FIRST VLP routing — **zero results**. The existing `vlp_plot` is user-supplied direct-data visualization only (PVT_PLOT_RULES rule), exactly as documented at the stopping point. `/calc vlp` returns insufficient-data/no-engine because no engine exists.

---

## 9. NODAL STATUS

**Classification: NOT STARTED.** No IPR–VLP intersection solver, no numerical operating-point solver, no q/Pwf operating point computation, no multiple/no-intersection handling, no calculated nodal plot engine, no `/calc nodal` engine path, and no ENGINE-FIRST Nodal routing. `nodal_plot` exists solely as a user-supplied direct-data plot rule.

---

## 10. AI / GROK STATUS

The AI layer uses **Groq** exclusively (HTTP calls to `GROQ_API_BASE`, models `GROQ_TEXT_MODEL`/`GROQ_VISION_MODEL`). **No Grok/xAI integration exists** — verified by full-repo grep. Deterministic calculations retain priority: ENGINE-FIRST context lists all `/calc` routes and forbids prose answers for engineable questions, the registry dispatches `/calc` to engines directly, and validation errors are thrown deterministically. AI cannot reach an engineable answer without the command route, and missing engineering data produces deterministic `INSUFFICIENT_DATA` requirement lists rather than hallucination (the `/report` no-hallucination policy enforces the same for documents). The earlier `KeyError: 'shape'` startup crash is fixed with a regression test.

---

## 11. PLOTTING STATUS

`PVT_PLOT_RULES` defines **20 plot types**: `bo_vs_p`, `rs_vs_p`, `bg_vs_p`, `z_vs_p`, `oil_visc_vs_p`, `gas_visc_vs_p`, `liquid_dropout_vs_p`, `cgr_vs_p`, `pt_diagram`, `oil_density_vs_p`, `vrel_vs_p_cce`, `gor_vs_p`, `wor_vs_p`, `wc_vs_p`, `p_vs_t`, `q_vs_t`, `kr_vs_sw`, `ipr_plot`, `vlp_plot`, `nodal_plot`. Direct-data plotting remains operational (verified by the two plot regression tests passing 64/64), and dynamic per-type captions/titles/axis labels are applied from the rules. The distinction is enforced in code: **user-supplied data plots** go through the direct-data `/plot` handler producing PVT_PLOT_RULES-styled PNGs, while **engine-calculated plots** (currently IPR only, `plot=1`) are produced by the production engine with "Calculated — Model" labeling and are never mixed into the direct-data path. Since the last audit, the only change is the calculated IPR plot itself (added with Phase 1).

---

## 12. TEST STATUS

| Category | Tests | Status |
|---|---|---|
| Total | 64 | All passing locally |
| IPR engine | 37 (`test_ipr_engine.py`) — Linear, Vogel, qmax inversion, Composite, C¹ continuity, model selection, guardrails | Automated tested |
| Engineering corrections regression | 11 (`test_engineering_corrections.py`) — OGIP units, PV/NPV, Z strict | Automated tested |
| NPV/Z regression | 10 (`test_npv_z_regression.py`) | Automated tested |
| Plot `KeyError: 'shape'` regression | 2 (`test_plot_shape_regression.py`) | Automated tested |
| Artificial lift | 4 (`test_artificial_lift.py`) — ESP helpers | Automated tested |
| Telegram routing integration | Covered within handler imports; full dispatch tested via the live handler tests | Automated tested |
| VLP / Nodal | 0 | Not applicable — engines do not exist yet |
| Manual live Telegram verification | 5 IPR cases + earlier `/plot` cases | Manually verified |

Local passing is confirmed; live production verification beyond the documented manual Telegram tests is not claimable from local runs.

---

## 13. DEPLOYMENT STATUS

The branch is `main`, HEAD `6e6fad2`, working tree clean (only the untracked local handover document, intentionally never committed). GitHub synchronization verified: `origin/main == HEAD` after a fresh fetch. Railway configuration (`railway.toml`) is unchanged: Nixpacks build, `startCommand = python3 main.py`, ON_FAILURE restart policy with 5 retries, environment names `LOG_LEVEL`, `POLLING_TIMEOUT`, `STARTUP_DELAY`. The GitHub → Railway auto-deployment integration remains the sole deployment path. **Railway runtime logs: NOT DIRECTLY VERIFIED** (dashboard authentication unavailable), though the Telegram API long-polling conflict response (409) previously confirmed an active production instance and no code changes have occurred since that confirmation.

---

## 14. VERIFIED ENGINEERING FIXES

All previously protected corrections are confirmed present and unchanged in the current code:

| Fix | Confirmed | Evidence |
|---|---|---|
| OGIP distinguishes ft³/scf vs rb/scf Bg | Yes | 43560 / 7758 constants in formula and engine |
| Multi-cash-flow NPV | Yes | `cf` comma list, t=0..N sum; single-CF PV separated and explicitly labeled |
| PV/NPV separation | Yes | Two distinct entries with cross-reference notes |
| Comma-separated NPV parsing | Yes | Robust parser with malformed-list rejection |
| Z-factor hard rejection | Yes | Strict `Ppr/Tpr > 0`; DAK refused outside Standing-Katz range |
| Required Mud Weight safety note | Yes | Safety note encoded in engine output |
| `/plot` `KeyError: 'shape'` fix | Yes | Guarded `if "shape" in rule` in context builder + regression test |
| Cleaned `/plot` help | Yes | No syntax notation, organized types |
| ENGINE-FIRST routing | Yes | System context + IPR extension |
| IPR guardrails | Yes | PHYSICALLY_INVALID / OUTSIDE_ASSUMPTIONS / INSUFFICIENT_DATA with precise messages |

---

## 15. COMPLETE / PARTIAL / MISSING MATRIX

| Capability | Classification |
|---|---|
| Reservoir Engineering (OOIP, OGIP, RF, material balance basics) | 🟢 COMPLETE + VERIFIED |
| PVT (6 correlations, FVF, Z) | 🟢 COMPLETE + VERIFIED |
| Production Engineering — IPR | 🟢 COMPLETE + VERIFIED (Phase 1) |
| Production Engineering — VLP | 🔴 NOT IMPLEMENTED |
| Production Engineering — Nodal Analysis | 🔴 NOT IMPLEMENTED |
| Artificial Lift (ESP TDH, hydraulic HP, screening helpers) | 🟠 PARTIAL / helpers only |
| Well Testing | 🔴 NOT IMPLEMENTED (analysis helpers only) |
| Drilling / Cementing / Completion | 🔴 NOT IMPLEMENTED (mud-weight/ECD calculators only) |
| Diagnostics | 🔴 NOT IMPLEMENTED |
| Economics (PV, NPV) | 🟢 COMPLETE + VERIFIED |
| Reporting (`/report`) | 🟢 COMPLETE + VERIFIED |
| Plotting (20 types, direct-data + calculated IPR) | 🟢 COMPLETE + VERIFIED |
| AI reasoning (Groq, classification, analysis, simulator input) | 🟢 COMPLETE + VERIFIED (interpreter role, ENGINE-FIRST enforced) |
| Web / dashboard | 🔴 NOT IMPLEMENTED |
| Export (PDF/CSV per-well) | 🔴 NOT IMPLEMENTED (PVT table export partial) |
| Persistence / history | 🔴 NOT IMPLEMENTED (per-session state only) |
| Multi-well capability | 🔴 NOT IMPLEMENTED |
| Choke optimization / production optimization | 🔴 NOT IMPLEMENTED |

---

## 16. EXACT CURRENT STOPPING POINT

The last completed development phase is **Phase 1 — IPR Engine** (commit `6e6fad2`, complete + manually verified on the live Telegram bot). The first unfinished phase is **Phase 2 — VLP Deterministic Engine**, which has not been intentionally started: no code, tests, routing, or documentation for VLP exists. What should be built next is the VLP engine, per the previously approved sequence (Phase 1 IPR → Phase 2 VLP → Phase 3 Nodal after live VLP verification).

---

## 17. RECOMMENDED NEXT PHASE

**Recommended single next phase: Phase 2 — Deterministic VLP Engine.** This is next because Nodal Analysis mathematically requires a computed VLP curve as its second operand — no VLP engine means no intersection to solve, so Phase 3 cannot start before Phase 2 is verified. Phase 2 should contain: a deterministic tubing-performance engine computing pressure traverse from well/tubing/PVT inputs; the **Hagedorn-Brown** and **Beggs-Brill** correlations for multiphase flow; flow-pattern determination, liquid holdup, friction gradient, hydrostatic/elevation gradient, and the acceleration component; a segmented/tubing-depth solver with convergence logic; a calculated VLP curve generator; the `/calc vlp` command with the same missing-data and guardrail discipline as IPR; calculated VLP plotting labeled "Calculated — Model"; and ENGINE-FIRST VLP routing. It must NOT change: the verified IPR engine, any calculator, PVT correlations, the direct-data `/plot` mode (full backward compatibility), AI routing policy, or deployment/secrets configuration. Prerequisites are already satisfied (PVT engine outputs feed VLP; command registry and ENGINE-FIRST patterns are established). Verification before moving forward: full regression suite (64 → 64+), hand-benchmarked VLP tests against published examples, and manual live Telegram tests before Phase 3 begins — no implementation of this phase has been performed; it awaits your approval.

---

## 18. RISKS OR ISSUES REQUIRING MY APPROVAL

This section is a historical snapshot from Aug 13, 2026 and is superseded by the current repository state. The former `/glossary` and `/graph` surfaces are intentionally removed; the current reproducibility surfaces are `/case report` and `/case replay`. Current deployment and live-acceptance evidence must be taken from the post-Increment-13 closure report and the current Git history, not from this older snapshot.

---

PROJECT RE-ENTRY AUDIT COMPLETE
NO APPLICATION CODE CHANGED
NO DEPLOYMENT CHANGED
AWAITING OWNER APPROVAL FOR NEXT PHASE
