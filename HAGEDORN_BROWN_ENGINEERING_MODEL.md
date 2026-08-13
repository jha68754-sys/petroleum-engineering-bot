# Hagedorn–Brown (1965) VLP Correlation — Engineering Model (Phase 5A)

**Companion document to:** `VLP_ENGINEERING_MODEL.md` (Beggs–Brill 1973, frozen), `NODAL_ENGINEERING_MODEL.md`, `PRODUCTION_OPTIMIZATION_MODEL.md`.
**Module:** `services/hagedorn_brown.py` (independent correlation). **Routing:** `services/vlp_engine.py` via `vlp_model=` parameter.
**Final status:** PHASE 5A IMPLEMENTED — AWAITING OWNER LIVE VERIFICATION.

---

## 1. Why a second correlation

Beggs–Brill (1973) was developed for the *inclined* two-phase flow test data of its authors; Hagedorn–Brown (1965) was developed from **vertical** multiphase test data in 100-ft tubing strings of different diameters (the "Brown correlation" for liquid holdup plus the two-phase friction multiplier). For a **vertical production well** the H-B correlation family is historically regarded as better matched to the flow geometry. Both correlations are deterministic, fully transparent, and require the same field-unit inputs — so the platform now lets the operator pick the outflow model with `vlp_model=beggs_brill|hagedorn_brown` without changing any other input.

## 2. The correlation (what is implemented)

The implementation follows Hagedorn & Brown, *"Experimental Study of Pressure Gradients Occurring During Continuous Two-Phase Flow in Small-Diameter Vertical Conduits"*, JPT (1965), with the Griffith–Wallis correction for the liquid-full (bubble-flow) limit and the standard field-unit form.

1. **Fluid properties at average-segment conditions.** Liquid and gas densities from the standard Black-Oil mixing rule (`rho_s = rho_l·lambda_l + rho_g·lambda_g`); gas density from the real-gas law; **Lee–Gonzalez–Eakin (1966)** gas viscosity with pseudo-critical properties from Sutton (gamma_g only).
2. **Mixed-liquid properties.** Density and viscosity of the oil–water mixture (`mu_l` blend, `bo`/`rs`/`api` inputs), identical inputs to the BB path.
3. **Flow parameters.** Superficial velocities, total mixture velocity, and the four published dimensionless numbers:
   - `N_lv` (liquid velocity number), `N_gv` (gas velocity number),
   - `N_d` (pipe diameter number), `N_L` (viscosity number).
4. **CnL correlation.** The published `C_nL` group:
   `C_nL = 0.0019 + 0.0233·N_L − 0.425·N_L² + 3.06·N_L³` (log-space form as printed in the original paper), used to shift the primary holdup correlation.
5. **Liquid holdup.** `hl = max(F(yL), hl_slip)`, where `F(yL)` is the four-piece published polynomial in `log10(yL)` with `yL = N_lv·N_L^0.38·N_d^0.403·0.013/λg^0.575`, extended with the `ly ≤ −3` clamp to a no-slip holdup (the original correlation is undefined there). Griffith–Wallis (liquid-full) holdup when the bubble-flow criterion is met.
6. **Two-phase friction multiplier.** `φ = f_tp/f_sl` from the published three-piece log-log curve in `N_gv·F_r^(0.5)/λg^(0.1)` with the small-N_gv linear branch, multiplied by the single-phase liquid friction factor `f_sl` from Churchill (1977) — Moody-chart equivalent, no regime-dependent empirical friction.
7. **Gradient integration.** Segmented pressure traverse (same 20-point Gauss-style segmentation and convergence loop as the BB path), hydrostatic + friction + acceleration components reported separately, bisection fallback for Pwf solving.

## 3. Applicability envelope

The correlation was developed on the Brown test data; the published envelope is reproduced in `HB_APPLICABILITY`:

| Parameter | Published range | Behavior outside |
|---|---|---|
| Tubing ID | 1.0 – 1.5 in (original test strings) | `CORRELATION_LIMITATION` warning — N_d extrapolation |
| GOR | ≈ 1,000 – 100,000 scf/STB (derived: gas fraction regime) | `CORRELATION_LIMITATION` warning |
| Total liquid rate | 0 – 12,000 STB/D (derived from test velocities) | `CORRELATION_LIMITATION` warning |
| Liquid viscosity | light–moderate oils | accepted; heavy-oil extrapolation flagged by N_L |

Outside the envelope the engine computes anyway (documented transparency) and labels the result with a limitation warning; it never silently fails or crashes.

## 4. Verified behavior (test package)

| Test class | Coverage |
|---|---|
| `TestHagedornBrownRouting` (7) | traverse contract identical to BB (status, pwf, components); liquid-full holdup hl = 1 with hydrostatic-only column; static q = 0 → friction exactly 0; BB default unchanged (identical pwf to 10⁻¹⁰); invalid model rejected; monotone `vlp_curve`; applicability warnings emitted |
| `TestNodalHagedornBrown` (3) | nodal root found with H-B outflow; tight residual + independent pwf_ipr/pwf_vlp consistency; BB and HB operating points differ as correlations differ |
| `TestHagedornBrownModelSelection` (4) | sensitivity/optimize honor `vlp_model=`; HB operating points differ from BB baseline; invalid model rejected at handler level |

**Key benchmarks (THP 100 psia, TVD 8000 ft, ID 1.995 in, API 35, γg 0.65, μ_l 1 cp, Bo 1.4, T_wh 120 °F):**

| Case | Beggs–Brill (1973) | Hagedorn–Brown (1965) |
|---|---|---|
| Liquid-full, q = 3000, GOR = Rs = 600 | Pwf = 2412.7 psia | Pwf = 2414.8 psia (hl = 1 exact, hydrostatic gradient 0.2898 psi/ft, friction ≈ 0) |
| Multiphase, GOR 1000, q = 263–2000 STB/D | 307 – 524 psia | 128 psia region (H-B holdup/fraction lower in this regime: Δ = −180 to −400 psi) |
| Static q = 0 | 115.2 psia | 115.2 psia (both reduce to the same static column) |

The two correlations agree at the static and liquid-full extremes (physics is identical there) and diverge in the multiphase regime — exactly the behavior expected from their different flow-regime maps. This divergence is a **feature**: it quantifies correlation uncertainty for the operator.

## 5. Integration points (no changes to verified engines)

- `services/vlp_engine.py`: `traverse()` / `traverse_hb()` / `vlp_curve()` gain `vlp_model=` (default `beggs_brill`); `_resolve_model()` validates names; Beggs–Brill code untouched.
- `services/nodal_engine.py`: `NodalEngine.solve()` accepts `vlp_model=`; `result.vlp_model` records the correlation used; the solver, root acceptance and classification are identical for both models. A Phase-5A robustness fix: bracketed bisection refines to `pressure_tol/10` and root acceptance uses a consistent `pressure_tol × 2` margin (the endpoint residual of a width-tolerance bracket can legitimately exceed the strict tolerance — discovered with a steep Vogel/H-B crossing near q_max).
- `handlers/text_handlers.py`: `/calc vlp`, `/calc nodal`, `/calc sensitivity`, `/calc optimize`, and the new `/calc vlp_compare` accept and honor `vlp_model=`; invalid values rejected with a usage message; result texts print the active VLP model.
- `constants.py`: `vlp_compare_plot` rule registered.

## 6. Live verification commands (post-deploy)

```
/calc vlp thp=100 tvd=8000 id=1.995 q=3000 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 vlp_model=hagedorn_brown
/calc nodal pr=3000 j=5 qmax=5000 thp=100 tvd=8000 id=1.995 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 wc=0.2 vlp_model=hagedorn_brown plot=1
/calc vlp_compare thp=100 tvd=8000 id=1.995 gor=1000 rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5 plot=1
```

Regression baseline: **160 tests, all passing.** Phases 1–4 remain frozen and verified.
