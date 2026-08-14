# Phase 5B Black-Oil V1 Engineering Specification

**Status:** Documentation and independent-reference freeze only. No production provider is authorized by this document.

**Baseline:** `ed51346d2b4a15be917d5e05b92ed5cc0288f728`

**Package identity:** `pvt_mode=pressure_dependent`, `pvt_model=black_oil_v1`

## 1. Scope and composition

Black-Oil V1 is an explicit multi-correlation package. The aggregate label is never sufficient provenance: every returned property must expose its model, source, units, validity range, branch, warnings, and fallback status.

| Property | Frozen model | Source tier | Branch or scope |
|---|---|---:|---|
| `Pb` | Vasquez–Beggs, 1980 | Tier 3 with primary-paper identification | Reservoir bubble point |
| `Rs` | Vasquez–Beggs, 1980 | Tier 3 government workbook cross-checked by IHS | Saturated/at-bubble-point solution GOR |
| Saturated `Bo` | Vasquez–Beggs, 1980 | Tier 3 IHS with coefficient table | `P ≤ Pb` |
| Undersaturated `Bo` | `Bob exp[co(Pb-P)]` | Tier 3 IHS | `P > Pb` |
| `co`, `P > Pb` | Vasquez–Beggs, 1980 | Tier 3 technical reproduction cross-checked by IHS | Undersaturated oil |
| `co`, `P ≤ Pb` | Villena–Lanzi, 1985 | Tier 3 technical reproduction; original thesis identified | Saturated effective oil compressibility; explicit fallback to avoid unsupported V-B derivative transcription |
| Dead-oil viscosity | Beggs–Robinson, 1975 | Tier 3 IHS/Pengtools cross-check | All supported temperatures in stated range |
| Saturated-oil viscosity | Beggs–Robinson, 1975 | Tier 3 technical reproduction | `P ≤ Pb` |
| Undersaturated-oil viscosity | Vasquez–Beggs pressure correction, 1980 | Tier 3 technical reproduction | `P > Pb`; explicit limitation if source inputs are outside range |
| `Z` | Dranchuk–Abou–Kassem, 1975 | Tier 2/3 technical references | Sweet/low-impurity gas |
| Pseudo-critical properties | Sutton, 1985/2007 convention | Tier 1/2 publication record and technical reproduction | Sweet/low-impurity gas |
| `Bg` | Definition from `Z`, `P`, and absolute `T` | Tier 3 university reference | Canonical internal unit `rb/scf` |
| `μg` | Lee–Gonzalez–Eakin, 1966 | Tier 2/3 university and technical references | Sweet/low-nonhydrocarbon gas |
| Water properties | Out of scope | — | Not returned by V1 |

The explicit Villena–Lanzi selection for saturated `co` is not silent mixing. It is recorded as `compressibility_model=Villena-Lanzi-1985-saturated` and exists because the accessible Vasquez–Beggs saturated derivative expression is not sufficiently unambiguous for safe implementation.

## 2. Units and required inputs

The canonical units are psia for pressure, °F for input temperature, °R for absolute-temperature calculations, °API for oil gravity, dimensionless gas/oil specific gravity, scf/STB for `Rs`, rb/STB for `Bo`, `1/psi` for `co`, cP for viscosity, dimensionless `Z`, and rb/scf for `Bg`.

Required inputs are pressure `P`, reservoir temperature `T`, oil API gravity, gas specific gravity, and enough separator/reference information to calculate the corrected gas gravity used by the selected Vasquez–Beggs `Pb`, `Rs`, and `Bo` equations. `Pb` and `Rsb` may be supplied or calculated, but the source of each value must be recorded. Inputs must be positive and physically plausible before equation evaluation.

## 3. Vasquez–Beggs `Pb`, `Rs`, and saturated `Bo`

The deterministic API boundary is **API ≤ 30** for the lower coefficient group and **API > 30** for the upper group.

The corrected gas gravity convention is frozen for V1 as the public Oklahoma/IHS implementation:

\[
SG_c = SG_i\left[1+0.00005912\,API\,T_i\,\log_{10}\left(\frac{P_i}{114.7}\right)\right]
\]

where `SG_i` is separator gas specific gravity, `T_i` is separator temperature in °F, and `P_i` is separator pressure in psia. The package must expose `separator_gas_gravity`, `separator_temperature_f`, `separator_pressure_psia`, and the resulting `SGc`. If separator values are absent, the provider must return `INSUFFICIENT_DATA` rather than silently inventing them.

For the selected API group, the coefficients are:

| API group | `C1` | `C2` | `C3` |
|---|---:|---:|---:|
| API ≤ 30 | 0.0362 | 1.0937 | 25.7240 |
| API > 30 | 0.0178 | 1.1870 | 23.9310 |

The solution-GOR equation is:

\[
R_s=C_1 SG_c^{C_2}P^{C_2}\exp\left(\frac{C_3 API}{T+460}\right)
\]

The bubble-point inversion is:

\[
P_b=\left[\frac{R_{sb}}{C_1 SG_c^{C_2}\exp\left(\frac{C_3 API}{T+460}\right)}\right]^{1/C_2}
\]

For saturated oil FVF:

\[
B_o=1+A_1R_s+A_2(T-60)\left(\frac{SG_c}{SG_o}\right)+A_3R_s(T-60)\left(\frac{SG_c}{SG_o}\right)
\]

where `SG_o = 141.5/(API+131.5)`. The coefficients are:

| API group | `A1` | `A2` | `A3` |
|---|---:|---:|---:|
| API ≤ 30 | `4.677×10⁻⁴` | `1.751×10⁻⁵` | `−1.811×10⁻⁸` |
| API > 30 | `4.670×10⁻⁴` | `1.100×10⁻⁵` | `1.337×10⁻⁹` |

The equation source is the IHS Harmony rendered Vasquez–Beggs page, cross-checked against the Oklahoma DEQ public workbook and Petroleum Office reproduction. The source is recorded as a public technical reproduction rather than the paywalled SPE paper itself.

## 4. Oil compressibility

### 4.1 Undersaturated branch: Vasquez–Beggs

For `P > Pb`:

\[
c_o=\frac{-1433+5R_{sb}+17.2T-1180SG_g+12.61API}{10^5P}
\]

The result is `1/psi`. `Rsb` is scf/STB, `T` is °F, `P` is psia, and gas gravity is relative to air.

### 4.2 Saturated branch: Villena–Lanzi fallback

For `P ≤ Pb`, V1 uses the explicitly named Villena–Lanzi (1985) effective saturated oil-compressibility correlation:

\[
c_o=\exp[-0.664-1.430\ln(P)-0.395\ln(P_b)+0.390\ln(T)+0.455\ln(R_{sb})+0.262\ln(API)]
\]

The result is `1/psi`; `P` and `Pb` are psia, `T` is °F, `Rsb` is scf/STB, and `API` is °API. This branch is an explicit source-backed substitution for the unresolved Vasquez–Beggs saturated derivative transcription. The provider must report the substitution and must not label it Vasquez–Beggs.

At `P=Pb`, the implementation uses the saturated branch deterministically and records `phase_region=bubble_point`. Continuity of `Bo` is required; compressibility itself is permitted to change sharply at saturation because the physical effective compressibility changes when gas evolves.

## 5. Undersaturated `Bo`

For `P > Pb`:

\[
B_o(P)=B_{ob}\exp[c_o(P_b-P)]
\]

where `Bob` is saturated `Bo` evaluated at `Rsb` and `Pb`, and `co` is the selected undersaturated Vasquez–Beggs compressibility. The sign is frozen as written: for positive `co` and `P>Pb`, `Bo(P) < Bob`. The identity test must prove:

\[
\lim_{P\to P_b^+}B_o(P)=B_{ob}
\]

within equation-reproduction tolerance.

## 6. Oil viscosity package

Dead-oil viscosity uses Beggs–Robinson:

\[
\mu_{od}=10^x-1,
\qquad
x=T^{-1.163}\exp\left(13.108-\frac{6.591}{SG_o}\right)
\]

For saturated oil:

\[
\mu_{os}=A\mu_{od}^{B}
\]

\[
A=10.715(R_s+100)^{-0.515},
\qquad
B=5.44(R_s+150)^{-0.338}
\]

For undersaturated oil, the approved Vasquez–Beggs pressure correction is:

\[
\mu_o=\mu_{os}\left(\frac{P}{P_b}\right)^m
\]

\[
m=2.6P^{1.187}\exp(-11.513-8.98\times10^{-5}P)
\]

At `P=Pb`, the correction equals `μos`. The stated Beggs–Robinson development range is approximately 16–58°API and 70–295°F; the public technical reproduction additionally gives `Rs` 20–2070 scf/STB, `SG_o` 0.75–0.96, and pressure 0–5250 psia. Outside these limits the provider returns a limitation warning.

## 7. DAK `Z` and Sutton pseudo-critical contract

V1 uses Sutton pseudo-critical properties:

\[
T_{pc}=169.2+349.5SG_g-74.0SG_g^2
\]

\[
P_{pc}=756.8-131.0SG_g-3.6SG_g^2
\]

`Tpc` is °R and `Ppc` is psia. Reduced properties are:

\[
T_{pr}=\frac{T_R}{T_{pc}},\qquad P_{pr}=\frac{P}{P_{pc}}
\]

Reduced density is:

\[
\rho_r=\frac{0.27P_{pr}}{ZT_{pr}}
\]

The DAK coefficients are:

| Coefficient | Value | Coefficient | Value |
|---|---:|---|---:|
| `A1` | 0.3265 | `A7` | −0.7361 |
| `A2` | −1.0700 | `A8` | 0.1844 |
| `A3` | −0.5339 | `A9` | 0.1056 |
| `A4` | 0.01569 | `A10` | 0.6134 |
| `A5` | −0.05165 | `A11` | 0.7210 |
| `A6` | 0.5475 |  |  |

The implicit DAK equation is:

\[
Z=1+\left(A_1+\frac{A_2}{T_{pr}}+\frac{A_3}{T_{pr}^3}+\frac{A_4}{T_{pr}^4}+\frac{A_5}{T_{pr}^5}\right)\rho_r
+\left(A_6+\frac{A_7}{T_{pr}}+\frac{A_8}{T_{pr}^2}\right)\rho_r^2
-\frac{A_9\left(\frac{A_7}{T_{pr}}+\frac{A_8}{T_{pr}^2}\right)\rho_r^5}{T_{pr}^0}
+A_{10}(1+A_{11}\rho_r^2)\frac{ho_r^2}{T_{pr}^3}e^{-A_{11}\rho_r^2}
\]

The implementation contract is fixed as follows. The solver variable is `rho_r`; the initial guess is `max(0.01, 0.27 Ppr/Tpr)`; Newton iteration uses a central finite-difference derivative, step clipping to ±50% of the current positive density, absolute residual tolerance `1e-10`, maximum step tolerance `1e-10` in reduced density, and maximum 100 iterations. A failed positive-density solve returns `NUMERICAL_NON_CONVERGENCE`; no stale or default `Z` may be returned. The public applicability warning is raised outside approximately `0.2 ≤ Ppr < 30` and `1.0 < Tpr ≤ 3.0`, with the low-pressure branch warning outside `Ppr < 1.0`, `0.7 < Tpr ≤ 1.0`.

## 8. Gas FVF and viscosity

The canonical internal/public unit is `bg_rb_scf`:

\[
B_g=0.00505\frac{Z(T+460)}{P}\quad [rb/scf]
\]

The presentation unit `rb/Mscf` is derived by multiplying `bg_rb_scf` by 1000. The standard-condition convention is 14.7 psia and 60°F, and `T+460` is the absolute-temperature conversion used by the field-unit constant. The unit identity test is:

\[
1\ rb/Mscf=0.001\ rb/scf
\]

Lee–Gonzalez–Eakin is frozen for sweet/low-nonhydrocarbon gas:

\[
\mu_g=\frac{K\exp(X\rho_g^Y)}{10000}
\]

\[
K=\frac{(9.4+0.02M_g)T_R^{1.5}}{209+19M_g+T_R},\quad X=3.5+\frac{986}{T_R}+0.001M_g,\quad Y=2.4-0.2X
\]

\[
M_g=28.967SG_g,
\qquad
\rho_g=\frac{28.967SG_gP}{10.732ZT_R\,62.428}
\]

`ρg` is g/cm³ and `μg` is cP. Material CO₂, H₂S, or N₂ returns `CORRELATION_LIMITATION`; no sour-gas correction is silently applied. The public applicability warning is approximately 100–8000 psia and 100–340°F, with reduced accuracy for gas gravity above 1.0.

## 9. Provider result and provenance schema

The future provider must return `PvtResult` fields for `Pb`, `Rs`, `Bo`, `co`, `μo`, `Z`, `Bg`, and `μg`, plus `phase_region`, `status`, `warnings`, `limitations`, and `input_defaults`.

The provenance object must contain:

```text
package_version
pvt_mode
pvt_model
pb_model
rs_model
bo_model
compressibility_model
dead_oil_viscosity_model
saturated_oil_viscosity_model
undersaturated_oil_viscosity_model
pseudo_critical_model
z_model
bg_definition
gas_viscosity_model
standard_conditions
source_versions
validity_warnings
fallback_models
```

The provider must be pure with respect to the rest of the application. It must not import VLP, nodal, optimization, handlers, Telegram transport, plotting, or the frozen Hagedorn–Brown/Beggs–Brill implementations.

## 10. Independent benchmark matrix

Reference calculations are stored separately from production services in `references/phase5b_black_oil_reference.py`, and generated values are stored in `references/phase5b_black_oil_benchmarks.json`. The reference code imports no production modules.

The frozen minimum matrix is:

| ID | Case |
|---:|---|
| 1–2 | `Pb`, API ≤30 and API >30 |
| 3–4 | `Rs`, API ≤30 and API >30 |
| 5–6 | Saturated `Bo`, API ≤30 and API >30 |
| 7 | Undersaturated `Bo` |
| 8 | `co` above `Pb` and saturated fallback |
| 9–11 | Dead, saturated, and undersaturated oil viscosity |
| 12–14 | DAK `Z`, low/medium/high `Ppr` |
| 15 | `Bg` and rb/scf ↔ rb/Mscf identity |
| 16 | Lee–Gonzalez–Eakin gas viscosity |
| 17–19 | Complete state below, at, and above `Pb` |

The current independent reference artifact executes representative cases for both API branches, undersaturated oil, and low/medium/high DAK conditions. It produced **6 cases and 20 sanity checks, all 20 passed**. Its generated values are not production expected values.

## 11. Frozen tolerances

| Tolerance class | Frozen value |
|---|---|
| Algebraic equation reproduction | Absolute and relative `1e-8` for the independent reference artifact |
| DAK residual | Absolute residual `<1e-10` |
| DAK maximum iterations | 100 |
| DAK density step | Central-difference Newton step clipped to ±50%; convergence requires density step and residual criteria |
| Integrated VLP | Not an acceptance target for V1; to be frozen during future VLP integration |

## 12. Sanity checks and failure behavior

The provider must reject impossible inputs before evaluation. It must enforce `Rs ≥ 0`, `Rs ≤ Rsb` on the saturated branch, `Bo > 0`, `Bg > 0`, `μo > 0`, `μg > 0`, and `Z > 0`. At `Pb`, `Rs` must reach `Rsb`, `Bo` must reach `Bob`, and the selected viscosity branch must be continuous. Above `Pb`, `Rs` remains on the selected black-oil convention and `Bo` decreases with pressure for positive `co` under the frozen sign convention.

Statuses are `OK`, `INVALID_INPUT`, `INSUFFICIENT_DATA`, `CORRELATION_LIMITATION`, and `NUMERICAL_NON_CONVERGENCE`. Warnings never silently change the selected model.

## 13. Protected repository areas and future integration

This document does not authorize changes to `services/hagedorn_brown.py`, existing Beggs–Brill equations, IPR, nodal root-finding, optimization, `vlp_model` behavior, existing default PVT behavior, frozen expected values, handlers, AI routing, Telegram transport, `/plot`, or the preserved `/plot` worktree.

The future VLP integration must be optional and additive. The default path must remain unchanged. `vlp_model` and `pvt_model` must remain independent selectors. V1 is provider/reference work only; no VLP, nodal, sensitivity, optimization, handler, or live-bot changes are part of this freeze.

## 14. Source hierarchy

Tier 1 sources are the original Vasquez–Beggs SPE-6719-PA record, Beggs–Robinson SPE-5434-PA, the original DAK publication, Sutton gas-property publications, Lee–Gonzalez–Eakin, and Villena–Lanzi thesis record. Tier 2 sources are recognized petroleum-engineering textbooks. Tier 3 sources are IHS Harmony, the Oklahoma DEQ workbook, Penn State teaching material, and recognized technical implementations. Tier 4 sources were used only to cross-check transcription and were not used alone to select a model.

## 15. Known risks

The original Vasquez–Beggs paper is not openly readable in the retrieved publisher record. The selected public IHS rendering resolves the main `Pb`, `Rs`, and `Bo` equation forms, but the corrected-gas-gravity notation is tied to a public technical implementation rather than a directly readable primary-paper equation. Saturated `co` is deliberately assigned to Villena–Lanzi because its effective saturated behavior is physically distinct and the accessible Vasquez–Beggs derivative rendering is not implementation-safe. LGE is limited to sweet/low-impurity gas. The DAK/Sutton combination is a correlation package, not an EOS, and requires explicit validity warnings.

These risks are documented provenance, not hidden defaults. They do not authorize production implementation in this task.

## References

1. [Vasquez and Beggs, SPE-6719-PA publisher record](https://onepetro.org/JPT/article-abstract/32/06/968/121824/Correlations-for-Fluid-Physical-Property?redirectedFrom=fulltext)
2. [IHS Harmony oil correlations](https://www.ihsenergy.ca/support/documentation_ca/Harmony/content/html_files/reference_material/calculations_and_correlations/oil_correlations.htm)
3. [Oklahoma DEQ Vasquez–Beggs workbook](https://oklahoma.gov/content/dam/ok/en/deq/documents/air-quality/PG_Vasquez_Beggs_Equation_Spreadsheet.xls)
4. [Beggs–Robinson oil viscosity](https://wiki.pengtools.com/index.php?title=Beggs_and_Robinson_Oil_Viscosity_correlation)
5. [Vasquez–Beggs oil compressibility reproduction](https://wiki.pengtools.com/index.php?title=Vasquez_and_Beggs_Oil_Compressibility_correlation)
6. [Villena–Lanzi saturated compressibility reproduction and thesis citation](https://petroleumoffice.com/doc/pvt-oil-compressibility)
7. [Dranchuk–Abou–Kassem](https://wiki.pengtools.com/index.php?title=Dranchuk_correlation)
8. [Sutton pseudo-critical convention](https://aegis4048.github.io/GasCompressibility-py/sutton.html)
9. [Lee–Gonzalez–Eakin](https://courses.ems.psu.edu/png520/m19_p4.html)
10. [Black-oil property units and Bg definition](https://production-technology.org/pvt-properties-correlations/)
