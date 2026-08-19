"""Deterministic integrated well + surface choke operating-point engine.

This module is deliberately an orchestration layer.  It reuses the released
IPR engine, segmented VLP engine, and Gilbert ChokeEngine V1; it does not
contain a second petroleum correlation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple

from services.production_engine import IPREngine
from services import vlp_engine
from services.choke_engine import ChokeEngine, ChokeError, ChokeInput, ChokeResult


class SystemError(ValueError):
    """Typed, user-safe failure from the integrated system solver."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")


@dataclass(frozen=True)
class SystemInput:
    """Validated field-unit contract for the integrated calculation."""

    pr: float
    # Compatibility/initial-guess field; the coupled solver determines THP.
    thp: float
    tvd: float
    tubing_id_in: float
    gor_scf_stb: float
    rs_scf_stb: float
    api: float
    gamma_g: float
    mu_l_cp: float
    bo_rb_stb: float
    t_wh_f: float
    geothermal_f_100ft: float
    choke_size_64th_in: float
    downstream_pressure_psia: float
    choke_model: str = "gilbert_1954"
    ipr_model: str = "auto"
    vlp_model: str = "beggs_brill"
    pb: Optional[float] = None
    j: Optional[float] = None
    j_star: Optional[float] = None
    qmax: Optional[float] = None
    q_test: Optional[float] = None
    pwf_test: Optional[float] = None
    wc: float = 0.0
    gamma_w: float = 1.07
    bw: float = 1.01
    z_factor: float = 0.9
    sigma: float = 30.0
    n_segments: int = 80
    q_min: float = 1.0
    q_max: Optional[float] = None
    n_points: int = 41
    pressure_tol: float = 0.1
    max_refine_iter: int = 60


@dataclass
class SystemResult:
    """Integrated well/choke result with explicit solver traceability."""

    status: str
    operating_rate_bpd: Optional[float] = None
    pwf_psia: Optional[float] = None
    upstream_pressure_psia: Optional[float] = None
    downstream_pressure_psia: float = 0.0
    choke_size_64th_in: float = 0.0
    choke_model: str = "gilbert_1954"
    choke_flow_regime: str = "UNAVAILABLE"
    ipr_model: str = "unknown"
    vlp_model: str = "beggs_brill"
    solver_residual_psi: Optional[float] = None
    solver_iterations: int = 0
    solver_method: str = "rate_scan + bracketed_bisection"
    convergence: str = "not_converged"
    reason: str = ""
    wellhead_pressure_psia: Optional[float] = None
    choke_result: Optional[ChokeResult] = None
    vlp_result: Any = None
    pvt_metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)


class IntegratedSystemEngine:
    """Couple the existing reservoir/well and Gilbert choke calculations."""

    DEFAULT_PRESSURE_TOL = 0.1
    DEFAULT_GRID_TOL = 2.0

    def __init__(self, *, ipr_engine: Optional[IPREngine] = None,
                 choke_engine: Optional[ChokeEngine] = None):
        self.ipr = ipr_engine or IPREngine()
        self.choke = choke_engine or ChokeEngine()

    @staticmethod
    def _finite(name: str, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SystemError("INVALID_INPUT", f"{name} must be finite numeric.")
        value = float(value)
        if not math.isfinite(value):
            raise SystemError("INVALID_INPUT", f"{name} must be finite numeric.")
        return value

    def _validate(self, inputs: SystemInput) -> None:
        for name in (
            "pr", "thp", "tvd", "tubing_id_in", "gor_scf_stb",
            "rs_scf_stb", "api", "gamma_g", "mu_l_cp", "bo_rb_stb",
            "t_wh_f", "geothermal_f_100ft", "choke_size_64th_in",
            "downstream_pressure_psia", "wc", "gamma_w", "bw",
            "z_factor", "sigma", "q_min", "pressure_tol",
        ):
            self._finite(name, getattr(inputs, name))
        if inputs.pr <= 0 or inputs.thp <= 0:
            raise SystemError("PHYSICALLY_INVALID_STATE", "pr and thp must be positive.")
        if inputs.tvd <= 0 or inputs.tubing_id_in <= 0:
            raise SystemError("PHYSICALLY_INVALID_STATE", "tvd and tubing_id_in must be positive.")
        if inputs.downstream_pressure_psia < 0:
            raise SystemError("PHYSICALLY_INVALID_STATE", "downstream pressure must be non-negative.")
        if not 0.0 <= inputs.wc <= 1.0:
            raise SystemError("PHYSICALLY_INVALID_STATE", "wc must be between 0 and 1.")
        if inputs.n_segments < 4 or inputs.n_points < 3:
            raise SystemError("PHYSICALLY_INVALID_STATE", "segments must be >= 4 and n_points >= 3.")
        if inputs.q_min <= 0:
            raise SystemError("PHYSICALLY_INVALID_STATE", "q_min must be positive for choke coupling.")
        if inputs.pressure_tol <= 0 or inputs.max_refine_iter < 1:
            raise SystemError("PHYSICALLY_INVALID_STATE", "solver tolerances are invalid.")
        if inputs.q_max is not None and inputs.q_max <= inputs.q_min:
            raise SystemError("PHYSICALLY_INVALID_STATE", "q_max must exceed q_min.")

    def _resolve_ipr(self, inputs: SystemInput) -> Tuple[str, Dict[str, float], float, str]:
        """Resolve the existing IPR API into a rate/pressure callable contract."""
        model = str(inputs.ipr_model or "auto").strip().lower()
        if model not in ("auto", "linear", "vogel", "composite"):
            raise SystemError("INVALID_INPUT", "ipr_model must be auto, linear, vogel, or composite.")
        pr = inputs.pr
        test_pair = inputs.q_test is not None and inputs.pwf_test is not None
        if (inputs.q_test is None) != (inputs.pwf_test is None):
            raise SystemError("INSUFFICIENT_DATA", "q_test and pwf_test must be supplied together.")

        if model == "auto":
            if inputs.pb is not None and pr > inputs.pb and (inputs.j is not None or test_pair):
                model = "composite"
            elif inputs.qmax is not None or test_pair:
                model = "vogel"
            elif inputs.j is not None:
                model = "linear"
            else:
                raise SystemError("INSUFFICIENT_DATA", "provide j, qmax, or q_test plus pwf_test for IPR.")

        if model == "linear":
            j = inputs.j
            if j is None:
                if not test_pair:
                    raise SystemError("INSUFFICIENT_DATA", "linear IPR requires j or q_test plus pwf_test.")
                j = self.ipr.linear_j(inputs.q_test, pr, inputs.pwf_test)
            if j <= 0:
                raise SystemError("PHYSICALLY_INVALID_STATE", "j must be positive.")
            q_at_zero = self.ipr.linear_q(pr, j, 0.0)
            return model, {"j": float(j)}, float(q_at_zero), "Linear IPR"

        if model == "vogel":
            qmax = inputs.qmax
            if qmax is None:
                if not test_pair:
                    raise SystemError("INSUFFICIENT_DATA", "vogel IPR requires qmax or q_test plus pwf_test.")
                qmax = self.ipr.vogel_qmax_from_test(pr, inputs.pwf_test, inputs.q_test)
            if qmax <= 0:
                raise SystemError("PHYSICALLY_INVALID_STATE", "qmax must be positive.")
            return model, {"qmax": float(qmax)}, float(qmax), "Vogel IPR"

        if inputs.pb is None:
            raise SystemError("INSUFFICIENT_DATA", "composite IPR requires pb.")
        j_star = inputs.j_star if inputs.j_star is not None else inputs.j
        if j_star is None:
            if not test_pair:
                raise SystemError("INSUFFICIENT_DATA", "composite IPR requires j or q_test plus pwf_test.")
            j_star = self.ipr.linear_j(inputs.q_test, pr, inputs.pwf_test)
        qb, qmax = self.ipr.composite_segments(pr, inputs.pb, j_star)
        return "composite", {"pb": float(inputs.pb), "j_star": float(j_star)}, float(qmax), "Composite IPR"

    def _ipr_rate(self, model: str, params: Dict[str, float], inputs: SystemInput, pwf: float) -> float:
        if model == "linear":
            return self.ipr.linear_q(inputs.pr, params["j"], pwf)
        if model == "vogel":
            return self.ipr.vogel_q(inputs.pr, params["qmax"], pwf)
        return self.ipr.composite_q(inputs.pr, params["pb"], params["j_star"], pwf)

    def _ipr_pwf(self, model: str, params: Dict[str, float], inputs: SystemInput, q: float) -> float:
        """Invert the existing IPR public rate function deterministically."""
        q = float(q)
        qmax = params.get("qmax")
        if qmax is None:
            if model == "linear":
                qmax = self.ipr.linear_q(inputs.pr, params["j"], 0.0)
            else:
                _, qmax = self.ipr.composite_segments(inputs.pr, params["pb"], params["j_star"])
        if q < 0 or q > qmax + 1e-6:
            raise SystemError("NO_OPERATING_POINT", "rate is outside the selected IPR domain.")
        lo, hi = 0.0, inputs.pr
        for _ in range(70):
            mid = (lo + hi) / 2.0
            q_mid = self._ipr_rate(model, params, inputs, mid)
            if abs(q_mid - q) <= 1e-6:
                return mid
            # IPR rate decreases as Pwf increases.
            if q_mid > q:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    @staticmethod
    def _merge_pvt_metadata(target: Dict[str, Any], metadata: Dict[str, Any]) -> None:
        if not metadata:
            return
        target["enabled"] = True
        target["mode"] = metadata.get("mode", "pressure_dependent")
        target["provider"] = metadata.get("provider", target.get("provider", "BlackOilPvtProvider"))
        target.setdefault("statuses", set()).update(metadata.get("statuses", []))
        target.setdefault("phase_regions", set()).update(metadata.get("phase_regions", []))
        target.setdefault("warnings", [])
        target.setdefault("limitations", [])
        for key in ("warnings", "limitations"):
            for item in metadata.get(key, []) or []:
                if item not in target[key]:
                    target[key].append(item)
        ranges = metadata.get("pressure_range_psia")
        if ranges and len(ranges) == 2:
            target.setdefault("pressure_ranges", []).append([float(ranges[0]), float(ranges[1])])
        target["pvt_evaluations"] = target.get("pvt_evaluations", 0) + int(metadata.get("pvt_evaluations", 0) or 0)
        if metadata.get("provenance"):
            target["provenance"] = metadata["provenance"]

    @staticmethod
    def _finalize_pvt_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        if not metadata.get("enabled"):
            return {}
        ranges = [r for r in metadata.get("pressure_ranges", []) if len(r) == 2]
        flat = [x for r in ranges for x in r]
        return {
            "enabled": True,
            "mode": metadata.get("mode", "pressure_dependent"),
            "provider": metadata.get("provider", "BlackOilPvtProvider"),
            "pressure_range_psia": [min(flat), max(flat)] if flat else [],
            "statuses": sorted(metadata.get("statuses", set())),
            "phase_regions": sorted(metadata.get("phase_regions", set())),
            "pvt_evaluations": metadata.get("pvt_evaluations", 0),
            "provenance": metadata.get("provenance", {}),
            "warnings": list(metadata.get("warnings", [])),
            "limitations": list(metadata.get("limitations", [])),
            "evaluation_strategy": "dynamic_well_pressure_and_upstream_choke_pressure",
        }

    def _vlp(self, inputs: SystemInput, *, thp: float, q: float,
             pvt_provider: Any, pvt_context: Optional[Dict[str, Any]]) -> Any:
        q_o = q * (1.0 - inputs.wc)
        q_w = q * inputs.wc
        try:
            return vlp_engine.traverse(
                thp=thp, tvd=inputs.tvd, q_o=q_o, q_w=q_w,
                gor=inputs.gor_scf_stb, bo=inputs.bo_rb_stb, bw=inputs.bw,
                z_factor=inputs.z_factor, gamma_g=inputs.gamma_g,
                gamma_w=inputs.gamma_w, mu_l=inputs.mu_l_cp,
                api=inputs.api, wc=inputs.wc, tubing_id_in=inputs.tubing_id_in,
                rs=inputs.rs_scf_stb, t_wh=inputs.t_wh_f,
                geothermal=inputs.geothermal_f_100ft, sigma=inputs.sigma,
                n_segments=inputs.n_segments, vlp_model=inputs.vlp_model,
                pvt_provider=pvt_provider, pvt_context=pvt_context,
            )
        except (ValueError, ZeroDivisionError) as exc:
            text = str(exc)
            code = text.split(":", 1)[0] if ":" in text else "NUMERICAL_NON_CONVERGENCE"
            if code == "PHYSICALLY_INVALID":
                code = "PHYSICALLY_INVALID_STATE"
            if code not in ("INSUFFICIENT_DATA", "CORRELATION_LIMITATION", "NUMERICAL_NON_CONVERGENCE", "PHYSICALLY_INVALID_STATE"):
                code = "NUMERICAL_NON_CONVERGENCE"
            raise SystemError(code, text.split(":", 1)[1].strip() if ":" in text else text) from exc

    def _well_required_thp(self, inputs: SystemInput, model: str,
                           params: Dict[str, float], q: float,
                           pvt_provider: Any,
                           pvt_context: Optional[Dict[str, Any]],
                           pvt_tracker: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Any, int]:
        target_pwf = self._ipr_pwf(model, params, inputs, q)
        lo = max(inputs.downstream_pressure_psia + 1e-5, 0.1)
        hi = max(inputs.pr, inputs.downstream_pressure_psia * 1.5 + 100.0)
        r_lo = self._vlp(inputs, thp=lo, q=q, pvt_provider=pvt_provider, pvt_context=pvt_context)
        r_hi = self._vlp(inputs, thp=hi, q=q, pvt_provider=pvt_provider, pvt_context=pvt_context)
        self._merge_pvt_metadata(pvt_tracker, getattr(r_lo, "pvt_metadata", {}))
        self._merge_pvt_metadata(pvt_tracker, getattr(r_hi, "pvt_metadata", {}))
        f_lo = float(r_lo.pwf) - target_pwf
        f_hi = float(r_hi.pwf) - target_pwf
        if f_lo > inputs.pressure_tol or f_hi < -inputs.pressure_tol:
            return None, target_pwf, None, 0
        best = r_hi
        iterations = 0
        for iterations in range(1, inputs.max_refine_iter + 1):
            mid = (lo + hi) / 2.0
            r_mid = self._vlp(inputs, thp=mid, q=q, pvt_provider=pvt_provider, pvt_context=pvt_context)
            self._merge_pvt_metadata(pvt_tracker, getattr(r_mid, "pvt_metadata", {}))
            best = r_mid
            f_mid = float(r_mid.pwf) - target_pwf
            if abs(f_mid) <= inputs.pressure_tol:
                return mid, target_pwf, r_mid, iterations
            if f_mid < 0.0:
                lo = mid
            else:
                hi = mid
        return None, target_pwf, best, iterations

    def _choke_required_pressure(self, inputs: SystemInput, q: float,
                                 pvt_provider: Any,
                                 pvt_context: Optional[Dict[str, Any]]) -> Tuple[float, ChokeResult]:
        # First use the frozen engine to obtain Gilbert's required pressure.
        probe_upstream = max(
            inputs.downstream_pressure_psia / 0.5,
            inputs.downstream_pressure_psia + 100.0,
            100.0,
        )
        try:
            probe = self.choke.calculate(ChokeInput(
                upstream_pressure_psia=probe_upstream,
                downstream_pressure_psia=inputs.downstream_pressure_psia,
                choke_size_64th_in=inputs.choke_size_64th_in,
                gor_scf_stb=inputs.gor_scf_stb,
                liquid_rate_bpd=q,
                choke_model=inputs.choke_model,
            ))
        except ChokeError as exc:
            code = "PHYSICALLY_INVALID_STATE" if exc.code == "PHYSICALLY_INVALID" else exc.code
            raise SystemError(code, exc.message) from exc
        if probe.correlation_pressure_psia is None:
            raise SystemError("NO_OPERATING_POINT", "Gilbert choke correlation cannot define an upstream pressure for this rate.")
        required = float(probe.correlation_pressure_psia)
        if required <= inputs.downstream_pressure_psia:
            raise SystemError("NO_OPERATING_POINT", "required choke upstream pressure is not greater than downstream pressure.")
        try:
            final = self.choke.calculate(ChokeInput(
                upstream_pressure_psia=required,
                downstream_pressure_psia=inputs.downstream_pressure_psia,
                choke_size_64th_in=inputs.choke_size_64th_in,
                gor_scf_stb=inputs.gor_scf_stb,
                liquid_rate_bpd=q,
                choke_model=inputs.choke_model,
            ), pvt_provider=pvt_provider, pvt_context=pvt_context)
        except ChokeError as exc:
            code = "PHYSICALLY_INVALID_STATE" if exc.code == "PHYSICALLY_INVALID" else exc.code
            raise SystemError(code, exc.message) from exc
        if str(final.flow_regime).upper() != "CRITICAL":
            raise SystemError(
                "NO_OPERATING_POINT",
                "Gilbert critical-flow coupling is unavailable outside the critical-flow domain.",
            )
        return required, final

    def calculate(self, inputs: SystemInput, *, pvt_provider: Any = None,
                  pvt_context: Optional[Dict[str, Any]] = None) -> SystemResult:
        self._validate(inputs)
        model, ipr_params, ipr_qmax, ipr_display = self._resolve_ipr(inputs)
        q_hi = inputs.q_max if inputs.q_max is not None else ipr_qmax
        if q_hi <= inputs.q_min:
            raise SystemError("PHYSICALLY_INVALID_STATE", "integrated rate domain is empty.")
        pvt_tracker: Dict[str, Any] = {}
        n_grid = int(inputs.n_points)
        q_grid = [inputs.q_min + (q_hi - inputs.q_min) * i / (n_grid - 1) for i in range(n_grid)]
        samples: List[Tuple[float, float, float, float, Any, ChokeResult]] = []
        evaluations = 0
        choke_domain_rejections = 0
        for q in q_grid:
            try:
                thp_well, pwf, vlp_result, n_inner = self._well_required_thp(
                    inputs, model, ipr_params, q, pvt_provider, pvt_context, pvt_tracker)
                evaluations += n_inner
                if thp_well is None:
                    continue
                choke_pressure, choke_result = self._choke_required_pressure(
                    inputs, q, pvt_provider, pvt_context)
                self._merge_pvt_metadata(pvt_tracker, choke_result.pvt_metadata)
                residual = thp_well - choke_pressure
                samples.append((q, residual, thp_well, pwf, vlp_result, choke_result))
            except SystemError as exc:
                # A low-rate sample can require choke upstream pressure below
                # downstream pressure; it is outside the coupled domain, not a
                # solver crash. Continue scanning for a valid bracket.
                if exc.code == "NO_OPERATING_POINT":
                    choke_domain_rejections += 1
                    continue
                raise
            except Exception as exc:
                raise SystemError("NUMERICAL_NON_CONVERGENCE", str(exc)) from exc

        brackets: List[Tuple[Tuple[float, float, float, float, Any, ChokeResult], Tuple[float, float, float, float, Any, ChokeResult]]] = []
        for a, b in zip(samples, samples[1:]):
            if a[1] == 0.0:
                brackets.append((a, a))
            elif a[1] * b[1] < 0.0:
                brackets.append((a, b))
        if samples and abs(samples[-1][1]) <= inputs.pressure_tol:
            brackets.append((samples[-1], samples[-1]))
        if not brackets:
            code = "NO_OPERATING_POINT"
            reason = "No rate in the supplied domain satisfies both well and choke pressure relationships."
            if not samples:
                if choke_domain_rejections == len(q_grid):
                    reason = "The choke critical-flow domain does not overlap the supplied well-side rate domain."
                else:
                    reason = "The well-side pressure domain and choke pressure relationship do not overlap."
            return SystemResult(
                status=code, downstream_pressure_psia=inputs.downstream_pressure_psia,
                choke_size_64th_in=inputs.choke_size_64th_in, choke_model=inputs.choke_model,
                ipr_model=ipr_display, vlp_model=inputs.vlp_model,
                solver_iterations=evaluations, reason=reason,
                pvt_metadata=self._finalize_pvt_metadata(pvt_tracker),
            )
        if len(brackets) > 1:
            return SystemResult(
                status="MULTIPLE_OPERATING_POINTS",
                downstream_pressure_psia=inputs.downstream_pressure_psia,
                choke_size_64th_in=inputs.choke_size_64th_in, choke_model=inputs.choke_model,
                ipr_model=ipr_display, vlp_model=inputs.vlp_model,
                solver_iterations=evaluations, reason="Multiple pressure-consistent operating brackets were found.",
                pvt_metadata=self._finalize_pvt_metadata(pvt_tracker),
            )

        left, right = brackets[0]
        if left[0] == right[0]:
            best = left
            iterations = 0
        else:
            lo, hi = left, right
            best = left if abs(left[1]) < abs(right[1]) else right
            iterations = 0
            for iterations in range(1, inputs.max_refine_iter + 1):
                q_mid = (lo[0] + hi[0]) / 2.0
                thp_mid, pwf_mid, vlp_mid, n_inner = self._well_required_thp(
                    inputs, model, ipr_params, q_mid, pvt_provider, pvt_context, pvt_tracker)
                evaluations += n_inner
                if thp_mid is None:
                    raise SystemError("NUMERICAL_NON_CONVERGENCE", "well-side pressure inversion lost its bracket.")
                choke_mid, choke_res_mid = self._choke_required_pressure(
                    inputs, q_mid, pvt_provider, pvt_context)
                self._merge_pvt_metadata(pvt_tracker, choke_res_mid.pvt_metadata)
                f_mid = thp_mid - choke_mid
                candidate = (q_mid, f_mid, thp_mid, pwf_mid, vlp_mid, choke_res_mid)
                if abs(f_mid) < abs(best[1]):
                    best = candidate
                if abs(f_mid) <= inputs.pressure_tol:
                    break
                if lo[1] * f_mid <= 0.0:
                    hi = candidate
                else:
                    lo = candidate
            else:
                raise SystemError("NUMERICAL_NON_CONVERGENCE", "integrated rate root did not converge within the iteration limit.")

        residual = abs(float(best[1]))
        if residual > inputs.pressure_tol:
            raise SystemError("NUMERICAL_NON_CONVERGENCE", "integrated operating-point residual exceeds tolerance.")
        return SystemResult(
            status="OK", operating_rate_bpd=float(best[0]), pwf_psia=float(best[3]),
            upstream_pressure_psia=float(best[2]), wellhead_pressure_psia=float(best[2]),
            downstream_pressure_psia=inputs.downstream_pressure_psia,
            choke_size_64th_in=inputs.choke_size_64th_in, choke_model=inputs.choke_model,
            choke_flow_regime=best[5].flow_regime, ipr_model=ipr_display,
            vlp_model=inputs.vlp_model, solver_residual_psi=residual,
            solver_iterations=evaluations + iterations,
            convergence="converged", reason="Well-side and choke-side pressure relationships agree within tolerance.",
            choke_result=best[5], vlp_result=best[4],
            pvt_metadata=self._finalize_pvt_metadata(pvt_tracker),
            warnings=list(getattr(best[4], "warnings", [])),
            limitations=list(getattr(best[4], "limitations", [])),
        )
