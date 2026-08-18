"""Deterministic surface-choke performance engine, Increment 10 V1.

Scope
-----
This module implements one deliberately narrow published model: the Gilbert
(1954) critical-flow empirical choke correlation.  The legacy no-provider path
remains independent from GasLiftEngine, VLP, Nodal, and BlackOilPvtProvider;
an explicit optional provider/context seam supplies Black-Oil validation and
provenance without changing the Gilbert calculation.

Frozen field-unit equation
--------------------------
The accessible published Gilbert form is:

    Pwh_psig = 435 * GLR_mscf_per_bbl**0.546 * q_liquid_bpd
               / choke_64ths**1.89

where pressure is gauge pressure in psig, GLR is Mscf/bbl (equivalently
10**3 scf/STB), liquid rate is bbl/day, and choke size is 64ths of an inch.
The public input pressure contract is psia; the engine converts upstream psia
to psig before evaluating the equation and converts the calculated pressure
back to psia for reporting.

Gilbert's critical-flow criterion is used exactly as documented by the source:
flow is critical only when downstream/upstream pressure ratio is below 0.70.
The correlation is not extrapolated to the non-critical branch.  Instead, the
engine returns a visible CORRELATION_LIMITATION result.

Black-Oil PVT is not required by the frozen Gilbert V1 equation.  When the
released pressure-dependent selector binds a provider, the provider is
explicitly evaluated at upstream choke pressure for state validation and
provenance; no PVT property is injected into the Gilbert equation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional


class ChokeError(ValueError):
    """Typed, user-safe engineering failure for Choke V1."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


@dataclass(frozen=True)
class ChokeInput:
    """Validated Gilbert V1 input contract in field units."""

    upstream_pressure_psia: float
    downstream_pressure_psia: float
    choke_size_64th_in: float
    gor_scf_stb: float
    liquid_rate_bpd: Optional[float] = None
    oil_api: Optional[float] = None
    gas_specific_gravity: Optional[float] = None
    choke_model: str = "gilbert_1954"


@dataclass(frozen=True)
class ChokeResult:
    """Deterministic choke result with visible provenance and limitations."""

    status: str
    choke_model: str
    upstream_pressure_psia: float
    downstream_pressure_psia: float
    choke_size_64th_in: float
    gor_scf_stb: float
    calculated_rate_bpd: Optional[float]
    supplied_rate_bpd: Optional[float]
    correlation_pressure_psia: Optional[float]
    pressure_ratio: float
    flow_regime: str
    provenance: str
    source: str
    units: str
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    input_defaults: List[str] = field(default_factory=list)
    pvt_metadata: Dict[str, Any] = field(default_factory=dict)


class ChokeEngine:
    """Small deterministic surface-choke performance engine."""

    MODEL_NAME = "gilbert_1954"
    MODEL_DISPLAY = "Gilbert (1954) critical-flow choke correlation"
    SOURCE = "W. E. Gilbert (1954), Flowing and Gas-Lift Well Performance, API Drilling and Production Practice"
    CRITICAL_PRESSURE_RATIO = 0.70
    ATMOSPHERIC_PRESSURE_PSIA = 14.7
    COEFFICIENT = 435.0
    GLR_EXPONENT = 0.546
    CHOKE_EXPONENT = 1.89
    MIN_GLR_SCF_STB = 300.0
    MAX_GLR_SCF_STB = 50_000.0
    MIN_CHOKE_64TH_IN = 8.0
    MAX_CHOKE_64TH_IN = 64.0

    def calculate(
        self,
        inputs: ChokeInput,
        *,
        pvt_provider: Any = None,
        pvt_context: Optional[Dict[str, Any]] = None,
    ) -> ChokeResult:
        self._validate(inputs)
        if pvt_provider is None and pvt_context is not None:
            raise ChokeError(
                "INVALID_INPUT",
                "pvt_context cannot be supplied without an explicit PVT provider.",
            )
        if pvt_provider is not None and not callable(getattr(pvt_provider, "evaluate", None)):
            raise ChokeError(
                "INVALID_INPUT",
                "pvt_provider must expose evaluate(state).",
            )

        pvt_tracker: Dict[str, Any] = {
            "pressures": [], "temperatures": [], "phase_regions": set(),
            "statuses": set(), "bubble_points": set(), "warnings": [],
            "limitations": [], "evaluation_points": [], "provenance": {},
        }
        if pvt_provider is not None:
            self._evaluate_pvt(
                pvt_provider,
                pvt_context,
                inputs.upstream_pressure_psia,
                "upstream_choke",
                pvt_tracker,
            )
        pvt_metadata = self._build_pvt_metadata(pvt_provider, pvt_tracker)
        pressure_ratio = (
            inputs.downstream_pressure_psia / inputs.upstream_pressure_psia
        )
        if pressure_ratio >= self.CRITICAL_PRESSURE_RATIO:
            return ChokeResult(
                status="CORRELATION_LIMITATION",
                choke_model=self.MODEL_NAME,
                upstream_pressure_psia=inputs.upstream_pressure_psia,
                downstream_pressure_psia=inputs.downstream_pressure_psia,
                choke_size_64th_in=inputs.choke_size_64th_in,
                gor_scf_stb=inputs.gor_scf_stb,
                calculated_rate_bpd=None,
                supplied_rate_bpd=inputs.liquid_rate_bpd,
                correlation_pressure_psia=None,
                pressure_ratio=pressure_ratio,
                flow_regime="SUBCRITICAL / NON-CRITICAL",
                provenance=self._provenance(),
                source=self.SOURCE,
                units=self._units(),
                warnings=[
                    "Gilbert V1 is not applicable when downstream/upstream pressure ratio is >= 0.70."
                ],
                limitations=[
                    "No subcritical choke equation is implemented in Increment 10 V1; no rate is extrapolated."
                ],
                input_defaults=self._input_defaults(inputs),
                pvt_metadata=pvt_metadata,
            )

        upstream_psig = inputs.upstream_pressure_psia - self.ATMOSPHERIC_PRESSURE_PSIA
        glr_mscf_per_bbl = inputs.gor_scf_stb / 1000.0
        denominator = self.COEFFICIENT * glr_mscf_per_bbl ** self.GLR_EXPONENT
        choke_factor = inputs.choke_size_64th_in ** self.CHOKE_EXPONENT
        calculated_rate = (
            upstream_psig * choke_factor / denominator
        )
        correlation_pressure_psia = None
        if inputs.liquid_rate_bpd is not None:
            correlation_pressure_psig = (
                self.COEFFICIENT
                * glr_mscf_per_bbl ** self.GLR_EXPONENT
                * inputs.liquid_rate_bpd
                / choke_factor
            )
            correlation_pressure_psia = (
                correlation_pressure_psig + self.ATMOSPHERIC_PRESSURE_PSIA
            )

        if not math.isfinite(calculated_rate) or calculated_rate < 0.0:
            raise ChokeError(
                "NUMERICAL_NON_CONVERGENCE",
                "Gilbert V1 produced a non-finite or negative rate.",
            )
        return ChokeResult(
            status="OK",
            choke_model=self.MODEL_NAME,
            upstream_pressure_psia=inputs.upstream_pressure_psia,
            downstream_pressure_psia=inputs.downstream_pressure_psia,
            choke_size_64th_in=inputs.choke_size_64th_in,
            gor_scf_stb=inputs.gor_scf_stb,
            calculated_rate_bpd=calculated_rate,
            supplied_rate_bpd=inputs.liquid_rate_bpd,
            correlation_pressure_psia=correlation_pressure_psia,
            pressure_ratio=pressure_ratio,
            flow_regime="CRITICAL",
            provenance=self._provenance(),
            source=self.SOURCE,
            units=self._units(),
            warnings=self._validity_warnings(inputs),
            limitations=[
                "Gilbert V1 is an empirical critical-flow correlation developed from California field data.",
                "Black-Oil PVT: Not required by Choke V1 model.",
            ],
            input_defaults=self._input_defaults(inputs),
            pvt_metadata=pvt_metadata,
        )

    def _evaluate_pvt(
        self,
        pvt_provider: Any,
        pvt_context: Optional[Dict[str, Any]],
        pressure_psia: float,
        point_name: str,
        tracker: Dict[str, Any],
    ) -> None:
        """Evaluate the explicit provider at the physically relevant choke state."""
        if not pvt_context:
            raise ChokeError(
                "INSUFFICIENT_DATA",
                "pvt_context with explicit Black-Oil state is required when "
                "pvt_provider is enabled.",
            )
        try:
            from services.black_oil_pvt import PvtState
            state_kwargs = dict(pvt_context)
            context_pressure = state_kwargs.pop("pressure_psia")
            context_temperature = state_kwargs.pop("temperature_f")
        except (KeyError, TypeError, ValueError) as exc:
            raise ChokeError(
                "PHYSICALLY_INVALID_STATE",
                "pvt_context must contain explicit pressure_psia and temperature_f.",
            ) from exc

        numeric_values = (context_pressure, context_temperature, pressure_psia)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in numeric_values
        ):
            raise ChokeError(
                "PHYSICALLY_INVALID_STATE",
                "Black-Oil PVT pressure and temperature state must be finite numeric values.",
            )
        if float(context_pressure) <= 0.0 or float(context_temperature) <= -459.67:
            raise ChokeError(
                "PHYSICALLY_INVALID_STATE",
                "Black-Oil PVT context pressure/temperature is physically invalid.",
            )

        state = PvtState(
            pressure_psia=float(pressure_psia),
            temperature_f=float(context_temperature),
            **state_kwargs,
        )
        result = pvt_provider.evaluate(state)
        status = getattr(result, "status", "UNKNOWN")
        status = getattr(status, "value", status)
        status = str(status)
        tracker["pressures"].append(float(pressure_psia))
        tracker["temperatures"].append(float(context_temperature))
        tracker["statuses"].add(status)
        phase_region = getattr(result, "phase_region", None)
        if phase_region is not None:
            tracker["phase_regions"].add(str(phase_region))
        bubble_point = getattr(result, "pb_psia", None)
        if bubble_point is not None and math.isfinite(float(bubble_point)):
            tracker["bubble_points"].add(float(bubble_point))
        tracker["provenance"] = getattr(result, "provenance", {}) or {}
        for key in ("warnings", "limitations"):
            for item in getattr(result, key, ()) or ():
                if item not in tracker[key]:
                    tracker[key].append(item)
        if status not in ("OK", "CORRELATION_LIMITATION"):
            raise ChokeError(
                status,
                f"Black-Oil provider failed at {pressure_psia:.6g} psia.",
            )
        tracker["evaluation_points"].append({
            "name": point_name,
            "pressure_psia": float(pressure_psia),
            "temperature_f": float(context_temperature),
        })

    def _build_pvt_metadata(
        self,
        pvt_provider: Any,
        tracker: Dict[str, Any],
    ) -> Dict[str, Any]:
        if pvt_provider is None:
            return {}
        pressures = tracker["pressures"]
        temperatures = tracker["temperatures"]
        bubble_points = sorted(tracker["bubble_points"])
        pressure_min = min(pressures)
        pressure_max = max(pressures)
        return {
            "enabled": True,
            "mode": "pressure_dependent",
            "evaluation_strategy": "upstream_choke_pressure",
            "provider": pvt_provider.__class__.__name__,
            "pressure_psia": pressures[0],
            "pressure_range_psia": [pressure_min, pressure_max],
            "temperature_range_f": [min(temperatures), max(temperatures)],
            "pvt_evaluations": len(pressures),
            "unique_pressure_states": len(set(pressures)),
            "statuses": sorted(tracker["statuses"]),
            "phase_regions": sorted(tracker["phase_regions"]),
            "bubble_point_psia": bubble_points[0] if len(bubble_points) == 1 else bubble_points,
            "pb_crossed": any(
                pressure_min < pb < pressure_max for pb in bubble_points
            ),
            "provenance": tracker["provenance"],
            "warnings": list(tracker["warnings"]),
            "limitations": list(tracker["limitations"]),
            "properties_consumed": [],
            "evaluation_points": list(tracker["evaluation_points"]),
        }

    def _validate(self, inputs: ChokeInput) -> None:
        numeric_fields = {
            "upstream_pressure_psia": inputs.upstream_pressure_psia,
            "downstream_pressure_psia": inputs.downstream_pressure_psia,
            "choke_size_64th_in": inputs.choke_size_64th_in,
            "gor_scf_stb": inputs.gor_scf_stb,
        }
        if inputs.liquid_rate_bpd is not None:
            numeric_fields["liquid_rate_bpd"] = inputs.liquid_rate_bpd
        if inputs.oil_api is not None:
            numeric_fields["oil_api"] = inputs.oil_api
        if inputs.gas_specific_gravity is not None:
            numeric_fields["gas_specific_gravity"] = inputs.gas_specific_gravity
        for name, value in numeric_fields.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ChokeError("INVALID_INPUT", f"{name} must be finite numeric.")

        if str(inputs.choke_model).strip().lower() != self.MODEL_NAME:
            raise ChokeError(
                "INVALID_INPUT",
                "unsupported choke_model. Use exactly choke_model=gilbert_1954.",
            )
        if inputs.upstream_pressure_psia <= 0.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "upstream_pressure_psia must be positive.")
        if inputs.downstream_pressure_psia < 0.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "downstream_pressure_psia must be non-negative.")
        if inputs.upstream_pressure_psia <= inputs.downstream_pressure_psia:
            raise ChokeError(
                "PHYSICALLY_INVALID_STATE",
                "upstream_pressure_psia must be greater than downstream_pressure_psia.",
            )
        if inputs.upstream_pressure_psia <= self.ATMOSPHERIC_PRESSURE_PSIA:
            raise ChokeError(
                "PHYSICALLY_INVALID_STATE",
                "upstream_pressure_psia must exceed 14.7 psia for the Gilbert psig equation.",
            )
        if inputs.choke_size_64th_in <= 0.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "choke_size_64th_in must be positive.")
        if inputs.gor_scf_stb < 0.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "gor_scf_stb must be non-negative.")
        if inputs.gor_scf_stb == 0.0:
            raise ChokeError(
                "CORRELATION_LIMITATION",
                "Gilbert V1 requires a positive gas-liquid ratio.",
            )
        if inputs.liquid_rate_bpd is not None and inputs.liquid_rate_bpd < 0.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "liquid_rate_bpd must be non-negative.")
        if inputs.oil_api is not None and not 0.0 < inputs.oil_api < 100.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "oil_api must be between 0 and 100.")
        if inputs.gas_specific_gravity is not None and inputs.gas_specific_gravity <= 0.0:
            raise ChokeError("PHYSICALLY_INVALID_STATE", "gas_specific_gravity must be positive.")

    def _validity_warnings(self, inputs: ChokeInput) -> List[str]:
        warnings: List[str] = []
        if not self.MIN_GLR_SCF_STB <= inputs.gor_scf_stb <= self.MAX_GLR_SCF_STB:
            warnings.append(
                "GOR is outside the published Gilbert-type applicability range of 300 .. 50,000 scf/STB."
            )
        if not self.MIN_CHOKE_64TH_IN <= inputs.choke_size_64th_in <= self.MAX_CHOKE_64TH_IN:
            warnings.append(
                "Choke size is outside the published Gilbert-type applicability range of 8/64 .. 64/64 in."
            )
        return warnings

    def _provenance(self) -> str:
        return "Gilbert (1954) critical-flow empirical choke correlation"

    def _units(self) -> str:
        return "pressure=psia input / psig in Gilbert equation; rate=bbl/day; GOR=scf/STB; choke=64ths of inch"

    def _input_defaults(self, inputs: ChokeInput) -> List[str]:
        defaults: List[str] = []
        if inputs.oil_api is None:
            defaults.append("API not required by Gilbert V1")
        if inputs.gas_specific_gravity is None:
            defaults.append("gas gravity not required by Gilbert V1")
        if inputs.liquid_rate_bpd is None:
            defaults.append("liquid rate solved from upstream pressure")
        return defaults
