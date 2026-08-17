# PHASE 5B INCREMENT 10 — CHOKE PERFORMANCE MODELING V1

## Engineering objective

Increment 10 adds a deterministic surface-choke performance screen through `/calc choke`. The feature estimates liquid rate from upstream pressure, choke size, and gas-liquid ratio using one explicitly frozen published empirical correlation. It is a screening calculation only; it is not a valve-sizing tool, a transient model, a facility-network solve, or an operating instruction.

## Selected correlation and source

The selected model is the **Gilbert (1954) critical-flow empirical choke correlation**, identified in W. E. Gilbert, *Flowing and Gas-Lift Well Performance*, API Drilling and Production Practice. The historical publication record is retained in the project research notes. Accessible technical reproductions were used only to cross-check the coefficient form and unit convention; the implementation does not combine coefficients from different models.

The frozen model name is `gilbert_1954`. No alternate choke correlation is exposed in Increment 10 V1.

## Exact equation

The implementation uses the published field-unit form:

> `Pchoke_psig = 435 × GLR_mscf_per_bbl^0.546 × q_liquid_bpd / choke_64ths^1.89`

For the forward rate calculation, the equation is rearranged as:

> `q_liquid_bpd = (Pupstream_psig × choke_64ths^1.89) / (435 × GLR_mscf_per_bbl^0.546)`

The supplied `gor` is in scf/STB and is converted internally to Mscf/bbl by dividing by 1,000. The public pressure contract is psia. The equation uses gauge pressure, so the engine converts upstream pressure using `Ppsig = Ppsia − 14.7` and converts calculated correlation pressure back to psia for reporting.

## Critical-flow logic

The pressure ratio is calculated as:

> `R = Pdownstream_psia / Pupstream_psia`

The Gilbert V1 critical-flow screen is classified as **CRITICAL** when `R < 0.70`. When `R >= 0.70`, the result is returned with status `CORRELATION_LIMITATION`, flow regime `SUBCRITICAL / NON-CRITICAL`, and no rate extrapolation. A subcritical equation is deliberately not invented in this increment.

## Input contract

The service-layer contract is `ChokeInput` and uses field units only. `upstream_pressure_psia`, `downstream_pressure_psia`, `choke_size_64th_in`, and `gor_scf_stb` are required. `liquid_rate_bpd` is optional; when supplied, the engine also reports the pressure implied by the Gilbert equation. `oil_api` and `gas_specific_gravity` are accepted only as optional descriptive inputs and are not used by the selected correlation. `choke_model` must equal `gilbert_1954`.

The Telegram contract accepts `/calc choke` with explicit key-value syntax. The primary names are `p_up`, `p_down`, `choke`, `gor`, and optional `q_liquid`, `api`, `gamma_g`, and `choke_model`. Clear aliases are supported for the same meanings, but one parameter is never assigned two unit meanings.

## Output contract

`ChokeResult` contains the typed status, selected model, pressure inputs, choke size, GOR, calculated rate, optional supplied rate, correlation pressure, pressure ratio, flow regime, provenance, source, units, warnings, limitations, and input notes. Telegram formatting exposes the result as `Choke Performance`, includes the model and units, and never returns a Python traceback.

The supported statuses are `OK`, `CORRELATION_LIMITATION`, `INVALID_INPUT`, `PHYSICALLY_INVALID_STATE`, and `NUMERICAL_NON_CONVERGENCE` where applicable.

## Validation and validity

The engine rejects non-finite values, non-positive upstream pressure, negative downstream pressure, upstream pressure not greater than downstream pressure, upstream pressure at or below atmospheric pressure for the psig equation, non-positive choke size, negative GOR, negative supplied liquid rate, and physically invalid optional API or gas-gravity values. Zero GOR returns a visible `CORRELATION_LIMITATION` because the selected gas-liquid correlation requires a positive gas-liquid ratio.

The implementation reports a visible warning when GOR is outside the screened Gilbert-type range of 300–50,000 scf/STB or choke size is outside the screened range of 8/64–64/64 in. These warnings do not silently change the equation or fall back to another model.

## Black-Oil and Gas-Lift boundaries

Black-Oil PVT is **not required by the selected Choke V1 model** and is not called. The result provenance states: `Black-Oil PVT: Not required by Choke V1 model`. Increment 10 does not connect ChokeEngine to GasLiftEngine, VLP, Nodal, Sensitivity, Optimize, or any choke-plus-gas-lift network solve.

## Independent benchmark cases

The focused test file contains three independent reference cases. Expected values are calculated from the equation above in a separate arithmetic section and are not obtained by importing or calling `ChokeEngine`.

| Case | Inputs | Expected output | Tolerance |
|---|---|---:|---:|
| A | `Pup=1000 psia`, `Pdown=200 psia`, `GOR=1000 scf/STB`, `choke=16/64 in` | `q=427.4309767 bbl/day`; ratio `0.2` | Rate `1e-9` relative; ratio `1e-12` absolute |
| B | `Pup=1500 psia`, `Pdown=1000 psia`, `GOR=2000 scf/STB`, `choke=32/64 in` | `q=1635.6711946 bbl/day`; ratio `0.6666667` | Rate `1e-9` relative; ratio `1e-12` absolute |
| C | `Pup=1000 psia`, `Pdown=100 psia`, `GOR=1000 scf/STB`, `choke=16/64 in`, `q=1000 bbl/day` | Correlation pressure `2319.8675095 psia`; ratio `0.1` | Pressure `1e-9` relative |

## Test matrix

The focused tests cover nominal calculation, repeatability, choke-size and upstream-pressure trends, subcritical classification, invalid pressure ordering, zero and negative choke sizes, invalid GOR/API/gas gravity, visible validity warnings, psia-to-psig interpretation, Telegram parsing, successful formatting, typed failure formatting, traceback absence, and preservation of the released Gas-Lift, VLP, Nodal, Sensitivity, and Optimize routes. Existing repository tests remain authoritative for the frozen Increment 9 behavior.

## Limitations and excluded scope

Gilbert V1 is an empirical critical-flow screening correlation with a source-specific unit convention. It does not model a subcritical branch, valve geometry, discharge coefficients, transient unloading, tubing or facility networks, compressor behavior, gas-lift valves, choke-plus-gas-lift coupling, multiphase mechanistic flow, Black-Oil PVT, dynamic unit conversion, PDF/Excel reporting, or optimization. Field use requires validation against representative well and facility data.

## References

[1]: https://cloud1.activelearner.com/contentcloud/portals/hosted3/PetroAcademy/PCE-NAW/API-54-126.pdf "W. E. Gilbert, Flowing and Gas-Lift Well Performance, API Drilling and Production Practice"

[2]: https://wiki.pengtools.com/index.php?title=Gilbert_choke_equation "Gilbert choke equation technical reproduction"

[3]: https://pmc.ncbi.nlm.nih.gov/articles/PMC10960849/ "Peer-reviewed choke-correlation discussion and critical-flow context"
