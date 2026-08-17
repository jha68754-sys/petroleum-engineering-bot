"""Deterministic continuous Gas-Lift V1 calculation engine.

Scope
-----
This service is intentionally independent from ``ArtificialLiftEngine``.  The
latter remains a screening/recommendation component; this module performs a
bounded steady-state pressure-balance calculation for continuous gas lift.

V1 model and assumptions
------------------------
* Field units are explicit: psia, ft, in, STB/day, Mscf/day, degF, and psi/ft.
* Gas pressure in the injection annulus follows the isothermal ideal-gas
  pressure relation ``p(z) = p0 * exp(k*z)`` where
  ``k = 0.01875 * gamma_g / (z_factor * T_R)`` [1/ft].
* The pre-lift tubing pressure relation is linear:
  ``p_tubing(z) = THP + tubing_gradient * z``.
* The operating injection point is the deepest pressure-balanced point.  If
  available annulus pressure reaches the tubing pressure at total depth, TVD
  is reported as the available maximum point.
* In-situ injected gas volume is computed with the ideal-gas volume relation at
  a representative tubing pressure.  A homogeneous mixture-gradient model
  then gives a transparent first-order lift response.  No valve, choke,
  transient unloading, or multiphase VLP is modeled.  When explicitly enabled,
  the existing Black-Oil provider supplies pressure-dependent Z and Bo values
  without changing the V1 pressure-balance architecture.
* If reservoir pressure and productivity index are supplied, a linear IPR
  response is evaluated with the lifted bottom-hole pressure.  Otherwise the
  production response is explicitly unavailable rather than invented.

The model is deliberately bounded and is not a substitute for valve design,
full VLP/Nodal coupling, or field operating instructions.  Pressure-dependent
PVT is strictly opt-in through the optional ``pvt_provider``/``pvt_context``
seam; the no-provider path retains the released Increment 8 behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional


class GasLiftError(ValueError):
    """Typed, user-safe engineering failure for Gas-Lift V1."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


@dataclass(frozen=True)
class GasLiftInput:
    """Validated Gas-Lift V1 input contract in field units."""

    thp_psia: float
    tvd_ft: float
    injection_pressure_psia: float
    gas_injection_rate_mscfd: float
    gas_specific_gravity: float
    average_temperature_f: float
    liquid_rate_stbd: float
    tubing_gradient_psi_ft: float = 0.045
    injection_depth_ft: Optional[float] = None
    reservoir_pressure_psia: Optional[float] = None
    productivity_index_stbd_psi: Optional[float] = None
    water_cut: float = 0.0
    oil_api: Optional[float] = None
    z_factor: float = 0.90
    oil_fvf_rb_stb: float = 1.20
    water_fvf_rb_stb: float = 1.02


@dataclass(frozen=True)
class GasLiftResult:
    """Deterministic Gas-Lift V1 result and engineering provenance."""

    status: str
    thp_psia: float
    tvd_ft: float
    gas_injection_rate_mscfd: float
    injection_pressure_psia: float
    injection_depth_ft: Optional[float]
    tubing_pressure_at_injection_psia: Optional[float]
    required_surface_injection_pressure_psia: Optional[float]
    pressure_margin_at_injection_psi: Optional[float]
    representative_pressure_psia: float
    injected_gas_in_situ_bpd: float
    liquid_in_situ_bpd: float
    gas_fraction: float
    base_gradient_psi_ft: float
    lifted_gradient_psi_ft: float
    bottomhole_pressure_without_lift_psia: float
    bottomhole_pressure_with_lift_psia: float
    predicted_liquid_rate_stbd: Optional[float]
    predicted_oil_rate_stbd: Optional[float]
    limitations: List[str] = field(default_factory=list)
    provenance: str = "GasLiftEngine V1 — steady-state pressure-balance and homogeneous mixture-gradient model"
    pvt_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def rate_response_supported(self) -> bool:
        return self.predicted_liquid_rate_stbd is not None


class GasLiftEngine:
    """Bounded deterministic continuous Gas-Lift V1 calculation engine."""

    GAS_CONSTANT = 0.01875  # field-unit gas pressure-gradient constant
    STANDARD_TEMPERATURE_R = 520.0

    def calculate(
        self,
        inputs: GasLiftInput,
        *,
        pvt_provider: Any = None,
        pvt_context: Optional[Dict[str, Any]] = None,
    ) -> GasLiftResult:
        """Calculate a steady-state Gas-Lift V1 response.

        The provider/context seam is explicitly opt-in.  With no provider the
        released Increment 8 constants and equations are used unchanged.  With
        a provider, only the existing Black-Oil provider contract is consumed.
        """
        self._validate(inputs)
        if pvt_provider is None and pvt_context is not None:
            raise GasLiftError(
                "INVALID_INPUT",
                "pvt_context cannot be supplied without an explicit PVT provider.",
            )
        if pvt_provider is not None and not callable(getattr(pvt_provider, "evaluate", None)):
            raise GasLiftError(
                "INVALID_INPUT",
                "Black-Oil/PVT integration is reserved for Increment 9; "
                "pvt_provider must expose evaluate(state).",
            )

        temp_r = inputs.average_temperature_f + 459.67
        representative_pressure = inputs.thp_psia + 0.5 * inputs.tubing_gradient_psi_ft * inputs.tvd_ft
        representative_pressure = max(representative_pressure, inputs.thp_psia)
        pvt_tracker: Dict[str, Any] = {
            "pressures": [], "temperatures": [], "phase_regions": set(),
            "statuses": set(), "bubble_points": set(), "warnings": [],
            "limitations": [], "evaluation_points": [], "provenance": {},
        }
        if pvt_provider is None:
            z_factor = inputs.z_factor
            oil_fvf = inputs.oil_fvf_rb_stb
        else:
            representative = self._evaluate_pvt(
                pvt_provider,
                pvt_context,
                representative_pressure,
                "representative_tubing",
                pvt_tracker,
            )
            z_factor = representative["z"]
            oil_fvf = representative["bo"]

        gas_k = self.GAS_CONSTANT * inputs.gas_specific_gravity / (
            z_factor * temp_r
        )
        base_tubing_pwf = inputs.thp_psia + inputs.tubing_gradient_psi_ft * inputs.tvd_ft

        injection_depth = self._resolve_injection_depth(inputs, gas_k)
        if injection_depth is None:
            raise GasLiftError(
                "NUMERICAL_NON_CONVERGENCE",
                "no pressure-balanced injection point was found within the supplied TVD; "
                "increase available injection pressure or reduce the requested depth.",
            )

        tubing_at_injection = (
            inputs.thp_psia + inputs.tubing_gradient_psi_ft * injection_depth
        )
        required_surface = tubing_at_injection * math.exp(-gas_k * injection_depth)
        annulus_at_injection = inputs.injection_pressure_psia * math.exp(
            gas_k * injection_depth
        )
        pressure_margin = annulus_at_injection - tubing_at_injection

        if pvt_provider is not None:
            self._evaluate_pvt(
                pvt_provider,
                pvt_context,
                tubing_at_injection,
                "injection_point",
                pvt_tracker,
            )

        gas_in_situ_bpd = (
            inputs.gas_injection_rate_mscfd
            * 1000.0
            * z_factor
            * temp_r
            / (representative_pressure * self.STANDARD_TEMPERATURE_R)
            / 5.615
        )
        oil_surface = inputs.liquid_rate_stbd * (1.0 - inputs.water_cut)
        water_surface = inputs.liquid_rate_stbd * inputs.water_cut
        liquid_in_situ_bpd = (
            oil_surface * oil_fvf
            + water_surface * inputs.water_fvf_rb_stb
        )
        total_in_situ = liquid_in_situ_bpd + gas_in_situ_bpd
        gas_fraction = gas_in_situ_bpd / total_in_situ if total_in_situ > 0.0 else 0.0
        gas_gradient = (
            self.GAS_CONSTANT
            * inputs.gas_specific_gravity
            * representative_pressure
            / (z_factor * temp_r)
        )
        lifted_gradient = (
            (1.0 - gas_fraction) * inputs.tubing_gradient_psi_ft
            + gas_fraction * gas_gradient
        )
        lifted_pwf = inputs.thp_psia + lifted_gradient * inputs.tvd_ft

        predicted_liquid = None
        predicted_oil = None
        if inputs.reservoir_pressure_psia is not None:
            if inputs.productivity_index_stbd_psi is None:
                raise GasLiftError(
                    "INSUFFICIENT_INPUT",
                    "productivity_index_stbd_psi is required when "
                    "reservoir_pressure_psia is supplied.",
                )
            predicted_liquid = max(
                0.0,
                inputs.productivity_index_stbd_psi
                * (inputs.reservoir_pressure_psia - lifted_pwf),
            )
            predicted_oil = predicted_liquid * (1.0 - inputs.water_cut)

        limitations = [
            "V1 uses a steady-state ideal-gas annulus pressure balance.",
            "V1 uses a homogeneous mixture-gradient response; valve, choke, transient unloading, and full VLP are outside scope.",
        ]
        pvt_metadata: Dict[str, Any] = {}
        if pvt_provider is None:
            # Preserve the exact Increment 8 limitation disclosure in legacy mode.
            limitations.append(
                "Black-Oil PVT integration is not implemented in Increment 8; the provider seam is reserved for Increment 9."
            )
        else:
            limitations.extend(pvt_tracker["limitations"])
            pressures = pvt_tracker["pressures"]
            temperatures = pvt_tracker["temperatures"]
            bubble_points = sorted(pvt_tracker["bubble_points"])
            pressure_min = min(pressures)
            pressure_max = max(pressures)
            pvt_metadata = {
                "enabled": True,
                "mode": "pressure_dependent",
                "evaluation_strategy": "representative_tubing_and_injection_point",
                "provider": pvt_provider.__class__.__name__,
                "pressure_psia": pressures[0],
                "pressure_range_psia": [pressure_min, pressure_max],
                "temperature_range_f": [min(temperatures), max(temperatures)],
                "pvt_evaluations": len(pressures),
                "unique_pressure_states": len(set(pressures)),
                "statuses": sorted(pvt_tracker["statuses"]),
                "phase_regions": sorted(pvt_tracker["phase_regions"]),
                "bubble_point_psia": bubble_points[0] if len(bubble_points) == 1 else bubble_points,
                "pb_crossed": any(
                    pressure_min < pb < pressure_max for pb in bubble_points
                ),
                "provenance": pvt_tracker["provenance"],
                "warnings": list(pvt_tracker["warnings"]),
                "limitations": list(pvt_tracker["limitations"]),
                "properties_consumed": ["z_factor", "bo_rb_stb"],
                "evaluation_points": list(pvt_tracker["evaluation_points"]),
            }
        if inputs.injection_depth_ft is None:
            limitations.append(
                "Injection depth is the deepest pressure-balanced point under the supplied surface injection pressure."
            )

        return GasLiftResult(
            status="OK",
            thp_psia=inputs.thp_psia,
            tvd_ft=inputs.tvd_ft,
            gas_injection_rate_mscfd=inputs.gas_injection_rate_mscfd,
            injection_pressure_psia=inputs.injection_pressure_psia,
            injection_depth_ft=injection_depth,
            tubing_pressure_at_injection_psia=tubing_at_injection,
            required_surface_injection_pressure_psia=required_surface,
            pressure_margin_at_injection_psi=pressure_margin,
            representative_pressure_psia=representative_pressure,
            injected_gas_in_situ_bpd=gas_in_situ_bpd,
            liquid_in_situ_bpd=liquid_in_situ_bpd,
            gas_fraction=gas_fraction,
            base_gradient_psi_ft=inputs.tubing_gradient_psi_ft,
            lifted_gradient_psi_ft=lifted_gradient,
            bottomhole_pressure_without_lift_psia=base_tubing_pwf,
            bottomhole_pressure_with_lift_psia=lifted_pwf,
            predicted_liquid_rate_stbd=predicted_liquid,
            predicted_oil_rate_stbd=predicted_oil,
            limitations=limitations,
            pvt_metadata=pvt_metadata,
        )

    def _evaluate_pvt(
        self,
        pvt_provider: Any,
        pvt_context: Optional[Dict[str, Any]],
        pressure_psia: float,
        point_name: str,
        tracker: Dict[str, Any],
    ) -> Dict[str, float]:
        """Evaluate the explicit provider at one physically meaningful V1 point."""
        if not pvt_context:
            raise GasLiftError(
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
            raise GasLiftError(
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
            raise GasLiftError(
                "PHYSICALLY_INVALID_STATE",
                "Black-Oil PVT pressure and temperature state must be finite numeric values.",
            )
        if float(context_pressure) <= 0.0 or float(context_temperature) <= -459.67:
            raise GasLiftError(
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
            raise GasLiftError(
                status,
                f"Black-Oil provider failed at {pressure_psia:.6g} psia.",
            )

        values = {
            "bo": getattr(result, "bo_rb_stb", None),
            "z": getattr(result, "z_factor", None),
        }
        missing = [
            name for name, value in values.items()
            if value is None or not math.isfinite(float(value)) or float(value) <= 0.0
        ]
        if missing:
            raise GasLiftError(
                "INSUFFICIENT_DATA",
                "Black-Oil provider returned missing/non-positive properties: "
                + ", ".join(missing) + ".",
            )
        resolved = {name: float(value) for name, value in values.items()}
        tracker["evaluation_points"].append({
            "name": point_name,
            "pressure_psia": float(pressure_psia),
            "temperature_f": float(context_temperature),
            "z_factor": resolved["z"],
            "bo_rb_stb": resolved["bo"],
        })
        return resolved

    def _validate(self, inputs: GasLiftInput) -> None:
        numeric_positive = {
            "thp_psia": inputs.thp_psia,
            "tvd_ft": inputs.tvd_ft,
            "injection_pressure_psia": inputs.injection_pressure_psia,
            "gas_injection_rate_mscfd": inputs.gas_injection_rate_mscfd,
            "gas_specific_gravity": inputs.gas_specific_gravity,
            "average_temperature_f + 459.67": inputs.average_temperature_f + 459.67,
            "liquid_rate_stbd": inputs.liquid_rate_stbd,
            "tubing_gradient_psi_ft": inputs.tubing_gradient_psi_ft,
            "z_factor": inputs.z_factor,
            "oil_fvf_rb_stb": inputs.oil_fvf_rb_stb,
            "water_fvf_rb_stb": inputs.water_fvf_rb_stb,
        }
        for name, value in numeric_positive.items():
            if not math.isfinite(value) or value <= 0.0:
                raise GasLiftError("INVALID_INPUT", f"{name} must be positive and finite.")
        if inputs.tvd_ft > 30000.0:
            raise GasLiftError(
                "CORRELATION_LIMITATION",
                "tvd_ft above 30000 ft is outside the bounded Gas-Lift V1 applicability range.",
            )
        if not 0.45 <= inputs.gas_specific_gravity <= 1.40:
            raise GasLiftError(
                "CORRELATION_LIMITATION",
                "gas_specific_gravity must be between 0.45 and 1.40 for Gas-Lift V1.",
            )
        if not 0.20 <= inputs.z_factor <= 1.50:
            raise GasLiftError(
                "CORRELATION_LIMITATION",
                "z_factor must be between 0.20 and 1.50 for Gas-Lift V1.",
            )
        if not 0.0 <= inputs.water_cut <= 1.0:
            raise GasLiftError("INVALID_INPUT", "water_cut must be between 0 and 1.")
        if inputs.injection_depth_ft is not None:
            if not math.isfinite(inputs.injection_depth_ft) or not 0.0 < inputs.injection_depth_ft <= inputs.tvd_ft:
                raise GasLiftError(
                    "INVALID_INPUT",
                    "injection_depth_ft must be greater than 0 and no deeper than tvd_ft.",
                )
        if inputs.reservoir_pressure_psia is not None:
            if not math.isfinite(inputs.reservoir_pressure_psia) or inputs.reservoir_pressure_psia <= 0.0:
                raise GasLiftError("INVALID_INPUT", "reservoir_pressure_psia must be positive.")
            if inputs.productivity_index_stbd_psi is None or not math.isfinite(inputs.productivity_index_stbd_psi) or inputs.productivity_index_stbd_psi <= 0.0:
                raise GasLiftError("INVALID_INPUT", "productivity_index_stbd_psi must be positive when supplied.")
        elif inputs.productivity_index_stbd_psi is not None:
            raise GasLiftError(
                "INVALID_INPUT",
                "reservoir_pressure_psia is required when productivity_index_stbd_psi is supplied.",
            )
        if inputs.oil_api is not None and not 0.0 < inputs.oil_api < 100.0:
            raise GasLiftError("INVALID_INPUT", "oil_api must be between 0 and 100 when supplied.")

    def _resolve_injection_depth(self, inputs: GasLiftInput, gas_k: float) -> Optional[float]:
        if inputs.injection_depth_ft is not None:
            tubing = inputs.thp_psia + inputs.tubing_gradient_psi_ft * inputs.injection_depth_ft
            annulus = inputs.injection_pressure_psia * math.exp(gas_k * inputs.injection_depth_ft)
            if annulus < tubing:
                raise GasLiftError(
                    "PHYSICALLY_INVALID_STATE",
                    "available injection pressure is below tubing pressure at the requested injection depth.",
                )
            return inputs.injection_depth_ft

        def margin(depth: float) -> float:
            tubing = inputs.thp_psia + inputs.tubing_gradient_psi_ft * depth
            annulus = inputs.injection_pressure_psia * math.exp(gas_k * depth)
            return annulus - tubing

        surface_margin = margin(0.0)
        bottom_margin = margin(inputs.tvd_ft)
        if bottom_margin >= 0.0:
            return inputs.tvd_ft
        if surface_margin < 0.0:
            return None

        # Find the deepest sign change on a deterministic fixed grid, then use
        # bisection to the pressure-balance tolerance.
        grid = 80
        previous_depth = 0.0
        previous_margin = surface_margin
        crossing: Optional[tuple[float, float]] = None
        for i in range(1, grid + 1):
            depth = inputs.tvd_ft * i / grid
            current_margin = margin(depth)
            if previous_margin >= 0.0 and current_margin < 0.0:
                crossing = (previous_depth, depth)
            previous_depth, previous_margin = depth, current_margin
        if crossing is None:
            return None
        lo, hi = crossing
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if margin(mid) >= 0.0:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1e-6:
                break
        return 0.5 * (lo + hi)


__all__ = ["GasLiftError", "GasLiftInput", "GasLiftResult", "GasLiftEngine"]
