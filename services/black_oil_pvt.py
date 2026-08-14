"""Isolated Phase 5B Black-Oil V1 PVT provider.

This module is intentionally unreachable from the current production flow.
It imports only Python standard-library modules and contains no VLP, nodal,
IPR, optimization, Telegram, plotting, or AI-routing dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any


class PVTStatus(str, Enum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    CORRELATION_LIMITATION = "CORRELATION_LIMITATION"
    NUMERICAL_NON_CONVERGENCE = "NUMERICAL_NON_CONVERGENCE"


@dataclass(frozen=True)
class PvtState:
    pressure_psia: float
    temperature_f: float
    oil_api: float
    gas_specific_gravity: float
    bubble_point_psia: float | None = None
    solution_gor_scf_stb: float | None = None
    separator_pressure_psia: float | None = None
    separator_temperature_f: float | None = None
    non_hydrocarbon_fraction: float | None = None


@dataclass(frozen=True)
class PvtResult:
    pressure_psia: float | None
    temperature_f: float | None
    pb_psia: float | None
    rs_scf_stb: float | None
    bo_rb_stb: float | None
    co_1_psi: float | None
    mu_o_cp: float | None
    z_factor: float | None
    bg_rb_scf: float | None
    mu_g_cp: float | None
    phase_region: str | None
    provenance: dict[str, Any] = field(default_factory=dict)
    input_defaults: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    status: str = PVTStatus.OK.value


@dataclass(frozen=True)
class _ResolvedState:
    sg_corrected: float
    pb: float
    rsb: float
    bob: float
    phase_region: str
    rs: float
    co: float
    bo: float
    mu_o: float


class BlackOilPvtProvider:
    """Deterministic, isolated Black-Oil V1 property provider."""

    PACKAGE_VERSION = "black_oil_v1"
    STANDARD_CONDITIONS = {"pressure_psia": 14.7, "temperature_f": 60.0}
    DAK_RESIDUAL_TOLERANCE = 1.0e-10
    DAK_STEP_TOLERANCE = 1.0e-10
    DAK_MAX_ITERATIONS = 100

    def evaluate(self, state: PvtState) -> PvtResult:
        invalid = self._validate_state(state)
        if invalid:
            return self._empty_result(state, PVTStatus.INVALID_INPUT, warnings=invalid)

        missing = self._missing_state_data(state)
        if missing:
            return self._empty_result(state, PVTStatus.INSUFFICIENT_DATA, warnings=missing)

        warnings: list[str] = []
        limitations: list[str] = []
        defaults: dict[str, Any] = {}
        try:
            sgc = self._corrected_gas_gravity(state)
            pb, rsb = self._resolve_pb_rsb(state, sgc)
            bob = self._vb_bo_saturated(state.oil_api, rsb, sgc, state.temperature_f)
            resolved = self._resolve_oil_state(state, sgc, pb, rsb, bob)
            z, _iterations, residual = self._dak_z(state.pressure_psia, state.temperature_f, state.gas_specific_gravity)
            bg = 0.00505 * z * (state.temperature_f + 460.0) / state.pressure_psia
            mu_g = self._lee_gonzalez_eakin(z, state.pressure_psia, state.temperature_f, state.gas_specific_gravity)
        except _NonConvergence:
            return self._empty_result(state, PVTStatus.NUMERICAL_NON_CONVERGENCE, warnings=["DAK solver did not converge within the frozen iteration contract."])
        except (ArithmeticError, OverflowError, ValueError) as exc:
            return self._empty_result(state, PVTStatus.INVALID_INPUT, warnings=[f"Correlation evaluation failed safely: {exc}"])

        self._validity_warnings(state, z, warnings, limitations)
        if state.non_hydrocarbon_fraction is not None and state.non_hydrocarbon_fraction > 0.0:
            limitations.append("Lee-Gonzalez-Eakin V1 policy is limited to sweet/low-nonhydrocarbon gas; no sour-gas correction was applied.")
        if residual and abs(residual) >= self.DAK_RESIDUAL_TOLERANCE:
            limitations.append("DAK residual is outside the frozen reference tolerance.")

        provenance = self._provenance()
        status = PVTStatus.CORRELATION_LIMITATION.value if limitations else PVTStatus.OK.value
        return PvtResult(
            pressure_psia=state.pressure_psia,
            temperature_f=state.temperature_f,
            pb_psia=resolved.pb,
            rs_scf_stb=resolved.rs,
            bo_rb_stb=resolved.bo,
            co_1_psi=resolved.co,
            mu_o_cp=resolved.mu_o,
            z_factor=z,
            bg_rb_scf=bg,
            mu_g_cp=mu_g,
            phase_region=resolved.phase_region,
            provenance=provenance,
            input_defaults=defaults,
            warnings=tuple(warnings),
            limitations=tuple(limitations),
            status=status,
        )

    @staticmethod
    def _validate_state(state: PvtState) -> list[str]:
        values = {
            "pressure_psia": state.pressure_psia,
            "temperature_f": state.temperature_f,
            "oil_api": state.oil_api,
            "gas_specific_gravity": state.gas_specific_gravity,
        }
        errors = [f"{key} must be finite." for key, value in values.items() if not math.isfinite(value)]
        if state.pressure_psia <= 0:
            errors.append("pressure_psia must be positive.")
        if state.temperature_f <= -459.67:
            errors.append("temperature_f must be above absolute zero.")
        if not 0.0 < state.oil_api <= 100.0:
            errors.append("oil_api must be in (0, 100].")
        if state.gas_specific_gravity <= 0:
            errors.append("gas_specific_gravity must be positive.")
        if state.bubble_point_psia is not None and state.bubble_point_psia <= 0:
            errors.append("bubble_point_psia must be positive when supplied.")
        if state.solution_gor_scf_stb is not None and state.solution_gor_scf_stb < 0:
            errors.append("solution_gor_scf_stb cannot be negative.")
        if state.non_hydrocarbon_fraction is not None and not 0.0 <= state.non_hydrocarbon_fraction <= 1.0:
            errors.append("non_hydrocarbon_fraction must be between 0 and 1.")
        return errors

    @staticmethod
    def _missing_state_data(state: PvtState) -> list[str]:
        missing: list[str] = []
        if state.separator_pressure_psia is None or state.separator_temperature_f is None:
            missing.append("separator_pressure_psia and separator_temperature_f are required for the approved corrected gas-gravity convention.")
        if state.bubble_point_psia is None and state.solution_gor_scf_stb is None:
            missing.append("bubble_point_psia or solution_gor_scf_stb is required to resolve saturation state.")
        return missing

    @staticmethod
    def _empty_result(state: PvtState, status: PVTStatus, warnings: list[str]) -> PvtResult:
        return PvtResult(
            pressure_psia=state.pressure_psia,
            temperature_f=state.temperature_f,
            pb_psia=None,
            rs_scf_stb=None,
            bo_rb_stb=None,
            co_1_psi=None,
            mu_o_cp=None,
            z_factor=None,
            bg_rb_scf=None,
            mu_g_cp=None,
            phase_region=None,
            provenance=BlackOilPvtProvider._provenance(),
            warnings=tuple(warnings),
            status=status.value,
        )

    @staticmethod
    def _provenance() -> dict[str, Any]:
        return {
            "package_version": "black_oil_v1",
            "pb_model": "Vasquez-Beggs-1980",
            "rs_model": "Vasquez-Beggs-1980",
            "bo_model": "Vasquez-Beggs-1980-saturated; exponential-pressure-extension-undersaturated",
            "compressibility_model": "Villena-Lanzi-1985-saturated; Vasquez-Beggs-1980-undersaturated",
            "dead_oil_viscosity_model": "Beggs-Robinson-1975",
            "saturated_oil_viscosity_model": "Beggs-Robinson-1975",
            "undersaturated_oil_viscosity_model": "Vasquez-Beggs-1980-pressure-correction",
            "pseudo_critical_model": "Sutton",
            "z_model": "Dranchuk-Abou-Kassem-1975",
            "bg_definition": "0.00505*Z*(T_F+460)/P_psia [rb/scf]",
            "gas_viscosity_model": "Lee-Gonzalez-Eakin-1966",
            "standard_conditions": {"pressure_psia": 14.7, "temperature_f": 60.0},
            "source_versions": {
                "engineering_spec": "PHASE_5B_BLACK_OIL_V1_ENGINEERING_SPEC.md",
                "baseline": "ed51346d2b4a15be917d5e05b92ed5cc0288f728",
            },
            "validity_warnings": "component-level warnings are returned on each result",
        }

    @staticmethod
    def _corrected_gas_gravity(state: PvtState) -> float:
        return state.gas_specific_gravity * (1.0 + 0.00005912 * state.oil_api * state.separator_temperature_f * math.log10(state.separator_pressure_psia / 114.7))

    @staticmethod
    def _vb_constants(api: float) -> tuple[float, float, float]:
        return (0.0362, 1.0937, 25.7240) if api <= 30.0 else (0.0178, 1.1870, 23.9310)

    @classmethod
    def _resolve_pb_rsb(cls, state: PvtState, sgc: float) -> tuple[float, float]:
        if state.bubble_point_psia is not None and state.solution_gor_scf_stb is not None:
            return state.bubble_point_psia, state.solution_gor_scf_stb
        c1, c2, c3 = cls._vb_constants(state.oil_api)
        factor = c1 * sgc**c2 * math.exp(c3 * state.oil_api / (state.temperature_f + 460.0))
        if state.solution_gor_scf_stb is not None:
            pb = (state.solution_gor_scf_stb / factor) ** (1.0 / c2)
            return pb, state.solution_gor_scf_stb
        pb = state.bubble_point_psia
        rsb = factor * pb**c2
        return pb, rsb

    @classmethod
    def _rs_at_pressure(cls, api: float, sgc: float, pressure: float, temperature_f: float) -> float:
        c1, c2, c3 = cls._vb_constants(api)
        return c1 * sgc**c2 * pressure**c2 * math.exp(c3 * api / (temperature_f + 460.0))

    @classmethod
    def _vb_bo_saturated(cls, api: float, rs: float, sgc: float, temperature_f: float) -> float:
        if api <= 30.0:
            a1, a2, a3 = 4.677e-4, 1.751e-5, -1.811e-8
        else:
            a1, a2, a3 = 4.670e-4, 1.100e-5, 1.337e-9
        sgo = 141.5 / (api + 131.5)
        return 1.0 + a1 * rs + a2 * (temperature_f - 60.0) * (sgc / sgo) + a3 * rs * (temperature_f - 60.0) * (sgc / sgo)

    @classmethod
    def _resolve_oil_state(cls, state: PvtState, sgc: float, pb: float, rsb: float, bob: float) -> _ResolvedState:
        if state.pressure_psia < pb:
            phase = "saturated"
            rs = min(rsb, cls._rs_at_pressure(state.oil_api, sgc, state.pressure_psia, state.temperature_f))
            bo = cls._vb_bo_saturated(state.oil_api, rs, sgc, state.temperature_f)
            co = cls._villena_lanzi_co(state.pressure_psia, pb, state.temperature_f, rsb, state.oil_api)
            mu_o = cls._beggs_robinson_saturated(state.oil_api, state.temperature_f, rs)
        elif math.isclose(state.pressure_psia, pb, rel_tol=0.0, abs_tol=1.0e-10):
            phase = "bubble_point"
            rs = rsb
            bo = bob
            co = cls._villena_lanzi_co(state.pressure_psia, pb, state.temperature_f, rsb, state.oil_api)
            mu_o = cls._beggs_robinson_saturated(state.oil_api, state.temperature_f, rs)
        else:
            phase = "undersaturated"
            rs = rsb
            co = cls._vb_co_undersaturated(rsb, state.temperature_f, state.gas_specific_gravity, state.oil_api, state.pressure_psia)
            bo = bob * math.exp(co * (pb - state.pressure_psia))
            mu_os = cls._beggs_robinson_saturated(state.oil_api, state.temperature_f, rsb)
            mu_o = cls._vb_oil_viscosity_undersaturated(mu_os, state.pressure_psia, pb)
        if min(rs, bo, mu_o) < 0 or bo <= 0 or mu_o <= 0:
            raise ValueError("oil property sanity condition failed")
        return _ResolvedState(sgc, pb, rsb, bob, phase, rs, co, bo, mu_o)

    @staticmethod
    def _villena_lanzi_co(pressure: float, pb: float, temperature_f: float, rsb: float, api: float) -> float:
        return math.exp(-0.664 - 1.430 * math.log(pressure) - 0.395 * math.log(pb) + 0.390 * math.log(temperature_f) + 0.455 * math.log(rsb) + 0.262 * math.log(api))

    @staticmethod
    def _vb_co_undersaturated(rsb: float, temperature_f: float, sg_g: float, api: float, pressure: float) -> float:
        return (-1433.0 + 5.0 * rsb + 17.2 * temperature_f - 1180.0 * sg_g + 12.61 * api) / (1.0e5 * pressure)

    @staticmethod
    def _beggs_robinson_dead(api: float, temperature_f: float) -> float:
        sgo = 141.5 / (api + 131.5)
        x = temperature_f**-1.163 * math.exp(13.108 - 6.591 / sgo)
        return 10.0**x - 1.0

    @classmethod
    def _beggs_robinson_saturated(cls, api: float, temperature_f: float, rs: float) -> float:
        muod = cls._beggs_robinson_dead(api, temperature_f)
        a = 10.715 * (rs + 100.0) ** -0.515
        b = 5.44 * (rs + 150.0) ** -0.338
        return a * muod**b

    @staticmethod
    def _vb_oil_viscosity_undersaturated(mu_os: float, pressure: float, pb: float) -> float:
        m = 2.6 * pressure**1.187 * math.exp(-11.513 - 8.98e-5 * pressure)
        return mu_os * (pressure / pb) ** m

    @staticmethod
    def _sutton_pseudo_critical(sg_g: float) -> tuple[float, float]:
        tpc = 169.2 + 349.5 * sg_g - 74.0 * sg_g**2
        ppc = 756.8 - 131.0 * sg_g - 3.6 * sg_g**2
        return ppc, tpc

    def _dak_z(self, pressure: float, temperature_f: float, sg_g: float) -> tuple[float, int, float]:
        a1, a2, a3, a4, a5 = 0.3265, -1.0700, -0.5339, 0.01569, -0.05165
        a6, a7, a8, a9, a10, a11 = 0.5475, -0.7361, 0.1844, 0.1056, 0.6134, 0.7210
        ppc, tpc = self._sutton_pseudo_critical(sg_g)
        ppr = pressure / ppc
        tpr = (temperature_f + 459.67) / tpc
        rho = max(0.01, 0.27 * ppr / tpr)

        def residual(r: float) -> float:
            z = 1.0 + (a1 + a2 / tpr + a3 / tpr**3 + a4 / tpr**4 + a5 / tpr**5) * r
            z += (a6 + a7 / tpr + a8 / tpr**2) * r**2
            z -= a9 * (a7 / tpr + a8 / tpr**2) * r**5
            z += a10 * (1.0 + a11 * r**2) * (r**2 / tpr**3) * math.exp(-a11 * r**2)
            return 0.27 * ppr / (r * tpr) - z

        for iteration in range(1, self.DAK_MAX_ITERATIONS + 1):
            f = residual(rho)
            if abs(f) < self.DAK_RESIDUAL_TOLERANCE:
                return 0.27 * ppr / (rho * tpr) / max(1.0, 1.0), iteration, f
            h = max(1.0e-6, abs(rho) * 1.0e-5)
            derivative = (residual(rho + h) - residual(max(1.0e-8, rho - h))) / (h + h)
            if not math.isfinite(derivative) or derivative == 0.0:
                raise _NonConvergence
            delta = max(-0.5 * rho, min(0.5 * rho, f / derivative))
            new_rho = max(1.0e-8, rho - delta)
            if abs(new_rho - rho) < self.DAK_STEP_TOLERANCE and abs(f) < self.DAK_RESIDUAL_TOLERANCE:
                rho = new_rho
                return 0.27 * ppr / (rho * tpr), iteration, residual(rho)
            rho = new_rho
        raise _NonConvergence

    @staticmethod
    def _lee_gonzalez_eakin(z: float, pressure: float, temperature_f: float, sg_g: float) -> float:
        tr = temperature_f + 459.67
        mw = 28.967 * sg_g
        k = (9.4 + 0.02 * mw) * tr**1.5 / (209.0 + 19.0 * mw + tr)
        x = 3.5 + 986.0 / tr + 0.001 * mw
        y = 2.4 - 0.2 * x
        rho_g = (28.967 * sg_g * pressure) / (10.732 * z * tr * 62.428)
        return k * math.exp(x * rho_g**y) / 10000.0

    @staticmethod
    def _validity_warnings(state: PvtState, z: float, warnings: list[str], limitations: list[str]) -> None:
        if not 16.0 <= state.oil_api <= 58.0 or not 70.0 <= state.temperature_f <= 295.0:
            limitations.append("Oil-viscosity state is outside the published Beggs-Robinson development range.")
        if not 100.0 <= state.pressure_psia <= 8000.0 or not 100.0 <= state.temperature_f <= 340.0:
            limitations.append("Gas-property state is outside the practical published LGE applicability range.")
        if state.gas_specific_gravity > 1.0:
            limitations.append("Lee-Gonzalez-Eakin accuracy is reduced for gas specific gravity above 1.0.")


class _NonConvergence(Exception):
    pass
