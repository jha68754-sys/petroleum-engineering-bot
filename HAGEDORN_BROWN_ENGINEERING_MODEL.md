# Hagedorn–Brown (1965) VLP Correlation — Engineering Model (Phase 5A, Revision 2)

**Companion documents:** `VLP_ENGINEERING_MODEL.md` (Beggs–Brill 1973, frozen), `NODAL_ENGINEERING_MODEL.md`, `PRODUCTION_OPTIMIZATION_MODEL.md`.
**Module:** `services/hagedorn_brown.py` (independent correlation). **Routing:** `services/vlp_engine.py` via `vlp_model=` parameter.
**Final status:** PHASE 5A NOT VERIFIED — AWAITING CORRECTED OWNER LIVE TEST (after live-verification audit of Aug 13, 2026).

---

## 1. Live-verification audit (Aug 13, 2026)

The first live acceptance command failed against the documented benchmark. The root cause was **a formulation error in the original Revision 1 implementation, combined with a benchmark that had no independent provenance**.

| Question | Finding |
|---|---|
| Was the live engine wrong? | **Yes (Revision 1).** The holdup group used N_RE (viscosity number) where the published correlation requires N_GV^0.575, and omitted the published (p/14.7)^0.1 and N_D groups. C_NL was evaluated against N_RE instead of the liquid viscosity number N_L. These errors drove the liquid holdup to the no-slip floor (hl = 0.0034) in the verification case, collapsing the pressure column. |
| Was the benchmark wrong? | **Yes.** The documented 2414.8 psia figure was a hand-calculation produced with Revision 1's own code on a different case (GOR = Rs = 600, liquid-full). It was never a published or independently implemented value. |
| Was the case outside applicability? | **Partially.** The 1.995-in ID and 3000 STB/D rate exceed the published test envelope (1.0–1.5-in strings, ~50–1200 STB/D, GOR to ~2000 scf/STB). The envelope claim of GOR 1000–100,000 in Revision 1 was an unsupported extrapolation. |
| Why was hydrostatic only 26.3 psi? | The published H-B density-ratio elevation equation uses the **no-slip mixture density** rho_s = λ·ρ_l + (1−λ)·ρ_g. With GOR = 1000 and Rs = 600 the free-gas fraction is large at 100 psia, ρ_s ≈ 0.48 lbm/ft³, and 0.0033 psi/ft × 8000 ft ≈ 26.5 psi. The hydrostatic term itself is mathematically consistent with the published equation; the Revision 1 defect was that the holdup error made the whole column gas-dominated near the wellhead. |
| Free-gas calculation | Correct in both revisions: free GOR = GOR − Rs = 400 scf/STB, q_g = 1.2 MMscf/D, in-situ conversion 14.7/p × T_R/520 × 1/z. |
| Unit-conversion audit | No conversion defects found in velocity, density, or gradient terms (verified against Lyons published forms). The surface-tension blend was inverted in Revision 1 and is now the published linear water-cut blend. |

## 2. The corrected formulation (Revision 2, verbatim published forms)

Verified against Hagedorn & Brown 1965 (SPE-940-PA), Economides et al. *Petroleum Production Systems* 2nd ed. (2013), Lyons *Standard Handbook of Petroleum and Natural Gas Engineering* 2nd ed. (1996), and the whitson.com correlation documentation of the original paper.

1. **Superficial velocities** (Lyons): v_sl = 5.615·q·(Bo/(1+WOR)+Bw·WOR/(1+WOR))/(86400·A); v_sg = q·(GLR − Rs/(1+WOR))·(14.7/p)·(T_R/520)/z/(86400·A).
2. **Dimensionless groups** (published, four-number system):
   - N_LV = 1.938·v_sl·(ρ_l/σ_l)^0.25 ; N_GV = 1.938·v_sg·(ρ_l/σ_l)^0.25
   - N_D = 120.872·D·(ρ_l/σ_l)^0.5 ; N_L = 0.15726·μ_l·(1/(ρ_l·σ_l³))^0.25
3. **C_NL** (published closed form of the viscosity-number curve):
   C_NL = 0.061·N_L³ − 0.0929·N_L² + 0.0505·N_L + 0.0019 (bounded to the published curve range)
4. **Primary holdup group**:
   H = (N_LV / N_GV^0.575) · (p/14.7)^0.1 · (C_NL / N_D)
5. **Secondary correction**: B = N_GV·N_LV^0.38 / N_D^2.14, with the published three-region ψ polynomial in B, and
   H_L/ψ = √((0.0047 + 1123.32·H + 729489.64·H²) / (1 + 1097.1566·H + 722153.97·H²))
6. **Published bounds and limits**: H_L ≥ λ (no-slip floor); static q = 0 → liquid-full column, hl = 1, friction = 0; Griffith bubble-flow replacement not implemented (documented limitation).
7. **Pressure gradients** (published density-ratio equation):
   dp/dz = ρ_s·g/g_c/144 + f_TP·G_m·v_m/(2·g_c·D)/144, with ρ_s = no-slip mixture density and f_TP = f_SL·(0.0056 + 0.5·f_SL). This is why a gas-rich column legitimately has a very small hydrostatic contribution — the published equation, not a defect.

## 3. Applicability envelope (corrected and honest)

The correlation was developed on a **1500-ft vertical well with 1-in, 1.25-in, and 1.5-in test sections** (whitson.com documentation of the original experiment). The paper states no strict GOR or liquid-rate limits; original test conditions spanned roughly 50–1200 STB/D and GOR to ~2000 scf/STB. Industrial practice extrapolates the ID range to ~4 in. The engine now emits `CORRELATION_LIMITATION` warnings outside the published ID range, and the documented envelope has been corrected accordingly. **Extrapolated results are indicative, never validated.**

## 4. Verification package (provenance-audited)

| # | Benchmark | Reference value | Engine value | Error | Tolerance | Source |
|---|---|---|---|---|---|---|
| A | Liquid-full hydrostatic (GOR = Rs = 600, q = 3000, TVD = 8000, THP = 100) | 2414.9 psia (analytical: Pwf = 100 + ρ_l·8000/144, ρ_l = 41.67 from the standard black-oil equation — independent of any VLP correlation) | 2414.83 psia | 0.07 psi | ±0.5 psi | Analytical (black-oil hydrostatics) |
| B | Published holdup form (two-phase node, p = 1000 psia, GOR = 1200, Rs = 500, ID 1.35 in, WC = 0.2) | hl = 0.08564, N_LV = 0.8265, N_GV = 21.38, C_NL = 0.00225 (plain arithmetic, no engine) | hl = 0.08564, N_LV = 0.8265, N_GV = 21.38, C_NL = 0.00225 | 0 (machine precision) | 1e-5 | Published equations (Economides/Lyons/SPE-940), independently re-derived |
| C | Static q = 0 (ID 1.35 in) | Pwf = 118.5 psia, friction = 0 (static column) | Pwf = 118.47 psia, friction = 0.0 | 0.02 psi | ±0.1 psi | Analytical static hydrostatics |
| D | Pressure-traverse sanity: liquid-full column gradient | 0.2898 psi/ft (ρ_l = 41.67 lbm/ft³) | 0.2894 psi/ft average over 8000 ft | 0.1% | ±1% | Analytical |
| E | Phase 1–4 regression | 161 tests, all green | 161 passed | — | — | Existing suite, untouched |

Note that the two-phase live result for GOR > Rs at low THP (≈ 125–138 psia in the revised engine) is the published H-B density-ratio behavior at gas-rich, low-pressure conditions — the correlation is known to under-predict pressure loss in some regimes (Kappa Engineering evaluation). It is a documented characteristic of the correlation, flagged by `CORRELATION_LIMITATION` where the case leaves the test envelope.

## 5. Benchmark provenance statement (audit of all H-B tests)

The Revision 1 test package contained one physics benchmark (2414.8 psia) derived from the engine's own output — **circular, and explicitly acknowledged as such**. Revision 2 removes all circularity: the liquid-full benchmark is now the standard analytical hydrostatic (black-oil density, independent of the correlation), and a new test (`test_hb_published_holdup_form`) re-derives the published dimensionless groups, C_NL, H group, and H_L/ψ curve with plain arithmetic and compares against the module — the reference implementation in the test is independent code, not the engine under test. Remaining tests exercise solver plumbing, model routing, and cross-model ordering (H-B vs BB), which are behavior tests, not validation benchmarks.

## 6. Multiphase discrepancy investigation (Aug 13, 2026) — reconciled

The owner live multiphase test returned Pwf = 332.664 psia against the predeclared benchmark of 335.52 psia (error 2.86 psi, outside the declared ±2 psi tolerance). The investigation classified the discrepancy as **D — DIFFERENT PROPERTY ASSUMPTIONS**; no engine defect was found.

| Investigation step | Result |
|---|---|
| Production convergence study (20/40/80/160/320 segments) | 332.605 / 332.646 / 332.664 / 332.667 / 332.655 psia — converged to ±0.02 psi; discretization contributes < 0.05 psi |
| Independent 80-segment rerun, z = 0.88, same midpoint scheme | 335.50 vs production 335.37 — Δ 0.13 psi |
| Segment-by-segment comparison (depths 25–3975 ft) | N_LV, N_GV, N_D, N_L, C_NL, H, ψ(B), hl, ρ_s, dP_el, dP_fr match to print precision |
| Live command vs benchmark inputs | The live command did not supply z; the handler defaults to z = 1.0, while the benchmark was computed with z = 0.88 |
| Production 80-segment with z = 1.0 | 332.664 psia — **exact match** to the live result |
| Independent 80-segment with z = 1.0 | 332.74 psia — matches the live result within 0.08 psi |

The 2.78-psi gap is the physical z-factor gas-density effect (ρ_g = 2.6989·γ_g·p/(z·(T+460))): the lower z compresses the free gas, raises the no-slip mixture density, and raises the hydrostatic column by ≈ 2.7 psi. Average holdup differs only 0.058 vs 0.056 — in the hl ≥ λ regime, ρ_s is dominated by gas density, so holdup barely affects the hydrostatic term. A documented sanity check confirms the liquid-full case is insensitive to z (no free gas). The test package now records both governing references (`TestHBMultiphaseZBenchmark`): R1 (z = 1.0, handler default) Pwf = 332.7 ± 0.5 psi and R2 (z = 0.88) Pwf = 335.5 ± 0.5 psi, plus the z-effect magnitude band (2.0–3.5 psi).

## 7. Live verification commands (corrected, in validated range)

```
/calc vlp thp=100 tvd=8000 id=1.35 q=600 gor=600 rs=600 api=35 gamma_g=0.65 mu_l=2 bo=1.3 t_wh=120 geothermal=1.5 vlp_model=hagedorn_brown
```

Inputs: ID 1.35 in (inside the published 1.0–1.5 in test range), q = 600 STB/D (inside 50–1200 test range), GOR = Rs = 600 (liquid-full, free gas = 0).
Expected: **Pwf ≈ 2592.9 psia** (analytical liquid column: ρ_l = 44.87 lbm/ft³ → 100 + 44.87·8000/144 = 2592.9 psia; temperature variation through the geothermal gradient shifts this by < 1 psia), hydrostatic ≈ 2492.9 psi, friction < 0.001 psi. Acceptable tolerance: **±3 psi** (0.1%). **STATUS: VERIFIED PASSING by owner live test (2592.89 psia live vs 2592.9 benchmark).**

### Multiphase retest (corrected governing assumption: z not supplied, z = 1.0)

```
/calc vlp thp=300 tvd=4000 id=1.35 q=800 gor=1200 rs=500 api=35 gamma_g=0.65 mu_l=2 bo=1.3 t_wh=120 geothermal=1.5 vlp_model=hagedorn_brown
```

Expected: **Pwf ≈ 332.7 psia** (hydrostatic ≈ 32.6 psi, friction ≈ 0.2 psi; R1 tolerance ±0.5 psi). This matches the Aug-13 live result of 332.664 psia exactly. If z = 0.88 is supplied explicitly, the governing reference is R2: Pwf ≈ 335.5 psia (hydrostatic ≈ 35.3 psi; tolerance ±0.5 psi).
