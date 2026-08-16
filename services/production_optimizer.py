"""
Production Optimization & Nodal Sensitivity Engine (Phase 4).

A deterministic layer ABOVE the verified Nodal engine. It owns NO
equations: IPR math is IPREngine (Phase 1), VLP math is vlp_engine
(Phase 2), and the operating point comes from NodalEngine (Phase 3).

Responsibilities of this module ONLY:
- Sensitivity: sweep ONE supplied parameter, rerun the Nodal solver,
  capture operating points, and report deltas versus a BASE CASE.
- Optimization: candidate comparison under an explicit deterministic
  objective with optional explicit constraints (constraint engine).

Numerical engineering results are deterministic and reproducible.

Units (oilfield): pr/Pwf/THP/pressures psia; rates STB/day (liquid),
GOR/Rs scf/STB; dimensions ft/in; WC fraction in [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from logging_config import get_logger
from services.nodal_engine import (
    NodalEngine, NodalError, NodalResult,
    _STATUS_UNIQUE, _STATUS_NONE, _STATUS_MULTIPLE,
    _STATUS_INVALID, _STATUS_UNKNOWN,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Sensitivity variables (canonical Telegram names)
# ---------------------------------------------------------------------------
SENSITIVITY_TYPES = ("thp", "tubing_id", "water_cut", "gor")

# Telegram name -> (solve kwarg name, physical minimum, physical maximum)
_SENSVAR_MAP = {
    "thp": ("thp", 0.0, None),                    # psia; > 0 required
    "tubing_id": ("tubing_id_in", 0.0, None),     # in; > 0 required
    "water_cut": ("wc", 0.0, 1.0),
    "gor": ("gor", 0.0, None),                    # scf/STB; >= 0
}

# ---------------------------------------------------------------------------
# Candidate / scenario classification
# ---------------------------------------------------------------------------
FEASIBLE = "FEASIBLE"
INFEASIBLE = "INFEASIBLE"              # candidate violates a constraint
NO_OPERATING_POINT = "NO_OPERATING_POINT"
MULTIPLE_OPERATING_POINTS = "MULTIPLE_OPERATING_POINTS"
NUMERICAL_NON_CONVERGENCE = "NUMERICAL_NON_CONVERGENCE"
PHYSICALLY_INVALID = "PHYSICALLY_INVALID"

# Objectives
OBJECTIVES = ("max_oil_rate",)

# Constraints the engine can evaluate
SUPPORTED_CONSTRAINTS = (
    "min_pwf",            # minimum flowing BHP (psia)
    "max_drawdown",       # maximum Pr - Pwf (psi)
    "max_liquid_rate",    # maximum liquid rate (STB/day)
    "max_water_cut",      # maximum water-cut fraction
    "min_thp",            # minimum THP (psia)
    "max_thp",            # maximum THP (psia)
    "allowed_tubing_ids", # explicit set of allowed tubing IDs (in)
    "max_gor",            # maximum produced GOR (scf/STB)
)

# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class SensitivityPoint:
    """One point in a sensitivity sweep."""
    parameter_value: float
    nodal: Optional[NodalResult]      # None only on solve() validation errors
    classification: str               # one of the *_POINT / *_INVALID labels
    q_op: Optional[float]             # STB/day (unique root only)
    pwf_op: Optional[float]           # psia
    n_roots: int
    residual: Optional[float]
    solve_error: Optional[str]        # PHYSICALLY_INVALID / unexpected error text

    @classmethod
    def from_nodal(cls, parameter_value: float,
                   nodal: Optional[NodalResult],
                   solve_error: Optional[str] = None) -> "SensitivityPoint":
        if nodal is None:
            return cls(parameter_value=parameter_value, nodal=None,
                       classification=PHYSICALLY_INVALID, q_op=None,
                       pwf_op=None, n_roots=0, residual=None,
                       solve_error=solve_error or "solve raised NodalError")
        n = len(nodal.roots)
        if n == 0:
            return cls(parameter_value=parameter_value, nodal=nodal,
                       classification=NO_OPERATING_POINT, q_op=None,
                       pwf_op=None, n_roots=0, residual=None,
                       solve_error=None)
        if n > 1:
            return cls(parameter_value=parameter_value, nodal=nodal,
                       classification=MULTIPLE_OPERATING_POINTS,
                       q_op=None, pwf_op=None, n_roots=n, residual=None,
                       solve_error=None)
        rt = nodal.roots[0]
        return cls(parameter_value=parameter_value, nodal=nodal,
                   classification=FEASIBLE, q_op=rt.q, pwf_op=rt.pwf,
                   n_roots=1, residual=rt.residual, solve_error=None)


@dataclass
class SensitivityDelta:
    """Delta of one sweep point versus the base case."""
    parameter_value: float
    dq: Optional[float]
    dq_pct: Optional[float]
    dpwf: Optional[float]


@dataclass
class SensitivityResult:
    """Full sensitivity analysis output."""
    variable: str                     # "thp" / "tubing_id" / "water_cut" / "gor"
    base_value: float
    base_point: Optional[SensitivityPoint]
    points: List[SensitivityPoint]
    deltas: List[SensitivityDelta]
    sweep: List[float]                # the evaluated parameter values
    warnings: List[str] = field(default_factory=list)


@dataclass
class ConstraintViolation:
    parameter_value: float
    constraint: str
    limit: float
    actual: float
    satisfied: bool


@dataclass
class OptimizationCandidate:
    """One evaluated candidate in a constrained comparison."""
    parameter_value: float
    point: SensitivityPoint
    constraint_violations: List[ConstraintViolation] = field(
        default_factory=list)
    classification: str = FEASIBLE    # recomputed by constraint engine
    objective_value: Optional[float] = None  # e.g. q_op for max_oil_rate
    review_required: bool = False     # MULTIPLE / non-convergence


@dataclass
class OptimizationResult:
    objective: str
    variable: str
    base_candidate: Optional[OptimizationCandidate]
    candidates: List[OptimizationCandidate]
    best: Optional[OptimizationCandidate]
    all_infeasible: bool
    warnings: List[str] = field(default_factory=list)


class OptimizationError(Exception):
    """Hard failure for invalid optimization requests."""
    def __init__(self, kind: str, message: str):
        self.kind = kind
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Constraint evaluation
# ---------------------------------------------------------------------------

def evaluate_constraint(name: str, limit: Any,
                        candidate: OptimizationCandidate) -> Optional[ConstraintViolation]:
    """Evaluate one explicitly-supplied constraint. Returns a violation
    record (satisfied=True means the constraint passed). Returns None only
    for constraints this engine cannot evaluate.

    NOTE: the caller must translate Telegram names
    (min_pwf, max_drawdown, ...) into these same names before calling.
    """
    point = candidate.point
    if point.q_op is None or point.pwf_op is None:
        return None  # no operating point — handled by classification instead

    if name == "min_pwf":
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), point.pwf_op,
            point.pwf_op >= float(limit))
    if name == "max_drawdown":
        pr = _solve_kwarg(candidate.point.nodal, "pr")
        if pr is None:
            return None
        dd = pr - point.pwf_op
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), dd,
            dd <= float(limit))
    if name == "max_liquid_rate":
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), point.q_op,
            point.q_op <= float(limit))
    if name == "max_water_cut":
        wc = _solve_kwarg(point.nodal, "wc")
        if wc is None:
            return None
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), wc,
            wc <= float(limit))
    if name == "min_thp":
        thp = _solve_kwarg(point.nodal, "thp")
        if thp is None:
            return None
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), thp,
            thp >= float(limit))
    if name == "max_thp":
        thp = _solve_kwarg(point.nodal, "thp")
        if thp is None:
            return None
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), thp,
            thp <= float(limit))
    if name == "allowed_tubing_ids":
        did = _solve_kwarg(point.nodal, "tubing_id_in")
        if did is None:
            return None
        allowed = [float(x) for x in limit]
        return ConstraintViolation(
            candidate.parameter_value, name, 0.0, did,
            any(abs(did - a) < 1e-6 for a in allowed))
    if name == "max_gor":
        gor = _solve_kwarg(point.nodal, "gor")
        if gor is None:
            return None
        return ConstraintViolation(
            candidate.parameter_value, name, float(limit), gor,
            gor <= float(limit))
    return None  # UNSUPPORTED_CONSTRAINT


def _solve_kwarg(nodal: Optional[NodalResult], key: str) -> Optional[float]:
    """Read an original solve input from the NodalResult inputs summary.

    The solver stores a superset of names; Telegram names and internal
    names are both tolerated (tubing_id_in covers the internal name used
    in result.vlp_kwargs)."""
    if nodal is None:
        return None
    summary = nodal.inputs_summary or {}
    v = summary.get(key)
    if v is None and key == "tubing_id_in":
        v = summary.get("id")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# The optimizer
# ---------------------------------------------------------------------------

class ProductionOptimizer:
    """Deterministic sensitivity + candidate-optimization layer.

    All IPR/VLP/Nodal math is delegated to the verified Phase 1-3 engines.
    """

    def __init__(self):
        self.nodal = NodalEngine()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _solve(self, variable: str, value: float,
               base_kwargs: Dict[str, float],
               ipr_kwargs: Dict[str, Optional[float]],
               pvt_provider: Any = None,
               pvt_context: Optional[Dict[str, Any]] = None
               ) -> Optional[NodalResult]:
        kw = dict(base_kwargs)
        kw[_SENSVAR_MAP[variable][0]] = value
        ipr = dict(ipr_kwargs)
        try:
            return self.nodal.solve(
                ipr_model=ipr.pop("ipr_model", "auto"),
                pr=ipr["pr"], pb=ipr.get("pb"),
                j=ipr.get("j"), j_star=ipr.get("j_star"),
                qmax=ipr.get("qmax"),
                q_test=ipr.get("q_test"),
                pwf_test=ipr.get("pwf_test"),
                pvt_provider=pvt_provider,
                pvt_context=pvt_context,
                **kw)
        except (NodalError, ValueError, TypeError) as exc:
            raise exc

    @staticmethod
    def _validate_range(variable: str, values: List[float],
                        n_points: Optional[int],
                        lo: Optional[float], hi: Optional[float]
                        ) -> List[float]:
        """Validate a sweep specification. Explicit list wins; otherwise
        a bounded range is expanded to n_points uniform values."""
        if values:
            for v in values:
                if not math.isfinite(v):
                    raise OptimizationError(
                        "PHYSICALLY_INVALID",
                        f"Sweep values must be finite numbers "
                        f"(got {v:g} for {variable}).")
            phys_min, phys_max = _SENSVAR_MAP[variable][1], \
                _SENSVAR_MAP[variable][2]
            phys_hi = phys_max if phys_max is not None else float("inf")
            for v in values:
                if v < phys_min or v > phys_hi:
                    hi_txt = (f", {phys_max:g}" if phys_max is not None
                              else "")
                    raise OptimizationError(
                        "PHYSICALLY_INVALID",
                        f"{variable}={v:g} is outside the physical range "
                        f"[{phys_min:g}{hi_txt}].")
            return list(dict.fromkeys(values))  # keep order, dedupe
        if lo is None or hi is None:
            raise OptimizationError(
                "MISSING_DATA",
                f"Provide an explicit candidate list for {variable} or a "
                f"bounded range with {variable}_min and {variable}_max.")
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise OptimizationError(
                "PHYSICALLY_INVALID",
                f"{variable}_min and {variable}_max must be finite numbers.")
        n = int(n_points) if n_points is not None else 5
        if n < 2:
            raise OptimizationError(
                "PHYSICALLY_INVALID", f"n_points must be >= 2 (got {n}).")
        if lo >= hi:
            raise OptimizationError(
                "PHYSICALLY_INVALID",
                f"{variable}_min must be < {variable}_max.")
        phys_min, phys_max = _SENSVAR_MAP[variable][1], \
            _SENSVAR_MAP[variable][2]
        phys_hi = phys_max if phys_max is not None else float("inf")
        if lo < phys_min or hi > phys_hi:
            hi_txt = (f", {phys_max:g}" if phys_max is not None else "")
            raise OptimizationError(
                "PHYSICALLY_INVALID",
                f"Range [{lo:g}, {hi:g}] exceeds the physical range "
                f"[{phys_min:g}{hi_txt}] for {variable}.")
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    # ------------------------------------------------------------------
    # Sensitivity analysis
    # ------------------------------------------------------------------
    def sensitivity(self, variable: str, *,
                    explicit_values: Optional[List[float]] = None,
                    lo: Optional[float] = None,
                    hi: Optional[float] = None,
                    n_points: Optional[int] = None,
                    base_value: Optional[float] = None,
                    base_kwargs: Optional[Dict[str, float]] = None,
                    ipr_kwargs: Optional[Dict[str, Optional[float]]] = None,
                    pvt_provider: Any = None,
                    pvt_context: Optional[Dict[str, Any]] = None
                    ) -> SensitivityResult:
        """One-variable deterministic sensitivity over the verified Nodal
        solver. base_kwargs holds the VLP inputs EXCLUDING the swept
        variable; ipr_kwargs holds the IPR inputs (incl. ipr_model and pr).
        """
        if variable not in _SENSVAR_MAP:
            raise OptimizationError(
                "UNSUPPORTED_VARIABLE",
                f"Sensitivity type must be one of "
                f"{', '.join(sorted(SENSITIVITY_TYPES))} "
                f"(got '{variable}').")
        sweep = self._validate_range(variable, explicit_values or [],
                                     n_points, lo, hi)
        if not sweep:
            raise OptimizationError(
                "MISSING_DATA", f"No sweep points generated for {variable}.")

        # Base case: use the first supplied explicit value if no base_value
        # was given and the sweep is a candidate list; otherwise use lo.
        if base_value is None:
            if explicit_values:
                base_value = explicit_values[0]
            else:
                base_value = lo
        ipr_kwargs = ipr_kwargs or {}
        base_kwargs = base_kwargs or {}

        warnings: List[str] = []
        base_point = None
        try:
            nodal = self._solve(
                variable, base_value, base_kwargs, ipr_kwargs,
                pvt_provider=pvt_provider, pvt_context=pvt_context)
        except (NodalError, ValueError, TypeError) as exc:
            nodal = None
            warnings.append(f"Base case ({variable}={base_value:g}) could "
                            f"not be solved: {exc}")
        if nodal is not None and nodal.status != _STATUS_UNIQUE:
            warnings.append(
                f"Base case ({variable}={base_value:g}) resolved to status "
                f"{nodal.status} rather than a unique operating point — "
                f"deltas are still computed where possible.")
        base_point = SensitivityPoint.from_nodal(base_value, nodal)

        points: List[SensitivityPoint] = []
        for v in sweep:
            try:
                nodal = self._solve(
                    variable, v, base_kwargs, ipr_kwargs,
                    pvt_provider=pvt_provider, pvt_context=pvt_context)
                points.append(SensitivityPoint.from_nodal(v, nodal))
            except (NodalError, ValueError, TypeError) as exc:
                points.append(SensitivityPoint.from_nodal(
                    v, None, solve_error=f"{type(exc).__name__}: {exc}"))
                warnings.append(f"{variable}={v:g} could not be solved: "
                                f"{exc}")

        # Deltas versus base case (operating points only)
        bq, bpwf = base_point.q_op, base_point.pwf_op
        deltas: List[SensitivityDelta] = []
        for p in points:
            dq = (p.q_op - bq) if (p.q_op is not None and bq is not None) else None
            dq_pct = (100.0 * dq / bq) if (dq is not None and bq) else None
            dpwf = (p.pwf_op - bpwf) if (p.pwf_op is not None
                                         and bpwf is not None) else None
            deltas.append(SensitivityDelta(p.parameter_value, dq, dq_pct,
                                           dpwf))
        return SensitivityResult(variable=variable, base_value=base_value,
                                 base_point=base_point, points=points,
                                 deltas=deltas, sweep=sweep,
                                 warnings=warnings)

    # ------------------------------------------------------------------
    # Constrained candidate optimization
    # ------------------------------------------------------------------
    @staticmethod
    def validate_objective(objective: str) -> str:
        obj = (objective or "").lower()
        if obj not in OBJECTIVES:
            raise OptimizationError(
                "UNSUPPORTED_OBJECTIVE",
                f"Objective must be one of {', '.join(OBJECTIVES)} "
                f"(got '{objective}').")
        return obj

    def optimize(self, variable: str, *,
                 values: List[float],
                 objective: str,
                 constraints: Optional[Dict[str, Any]] = None,
                 base_kwargs: Optional[Dict[str, float]] = None,
                 ipr_kwargs: Optional[Dict[str, Optional[float]]] = None
                 ) -> OptimizationResult:
        """Constrained candidate comparison. `values` is the explicit
        candidate list supplied by the user; `constraints` maps supported
        constraint names to limits (evaluated only for constraints this
        engine implements; unsupported ones raise UNSUPPORTED_CONSTRAINT).
        """
        if variable not in _SENSVAR_MAP:
            raise OptimizationError(
                "UNSUPPORTED_VARIABLE",
                f"Sensitivity type must be one of "
                f"{', '.join(sorted(SENSITIVITY_TYPES))}.")
        if len(values) < 2:
            raise OptimizationError(
                "MISSING_DATA",
                "Candidate optimization requires at least two candidates.")
        obj = self.validate_objective(objective)
        constraints = constraints or {}
        for cname in constraints:
            if cname not in SUPPORTED_CONSTRAINTS:
                raise OptimizationError(
                    "UNSUPPORTED_CONSTRAINT",
                    f"Constraint '{cname}' is not implemented. Supported: "
                    f"{', '.join(sorted(SUPPORTED_CONSTRAINTS))}.")

        ipr_kwargs = ipr_kwargs or {}
        base_kwargs = base_kwargs or {}
        candidates: List[OptimizationCandidate] = []
        warnings: List[str] = []

        for v in values:
            try:
                nodal = self._solve(variable, v, base_kwargs, ipr_kwargs)
            except (NodalError, ValueError, TypeError) as exc:
                point = SensitivityPoint.from_nodal(
                    v, None, solve_error=f"{type(exc).__name__}: {exc}")
                violations, classification = self._classify_point(point)
                candidates.append(OptimizationCandidate(
                    parameter_value=v, point=point,
                    constraint_violations=violations,
                    classification=classification,
                    objective_value=None, review_required=True))
                warnings.append(f"Candidate {variable}={v:g} could not be "
                                f"solved: {exc}")
                continue

            point = SensitivityPoint.from_nodal(v, nodal)
            violations, classification = self._classify_point(point)

            # Constraint evaluation (feasible points only)
            extra_violations = []
            if classification == FEASIBLE:
                cand_temp = OptimizationCandidate(
                    parameter_value=v, point=point)
                for cname, limit in constraints.items():
                    cv = evaluate_constraint(cname, limit, cand_temp)
                    if cv is not None and not cv.satisfied:
                        extra_violations.append(cv)
                if extra_violations:
                    classification = INFEASIBLE

            obj_value = None
            review = (classification == MULTIPLE_OPERATING_POINTS
                      or classification == NUMERICAL_NON_CONVERGENCE)
            if classification == FEASIBLE and obj == "max_oil_rate":
                obj_value = point.q_op

            candidates.append(OptimizationCandidate(
                parameter_value=v, point=point,
                constraint_violations=violations + extra_violations,
                classification=classification,
                objective_value=obj_value, review_required=review))

        # Base candidate = first candidate in the supplied list
        base = candidates[0] if candidates else None

        feasible = [c for c in candidates
                    if c.classification == FEASIBLE
                    and c.objective_value is not None]
        best = None
        all_infeasible = len(candidates) > 0 and not feasible
        if feasible:
            if obj == "max_oil_rate":
                best = max(feasible, key=lambda c: c.objective_value)
        return OptimizationResult(
            objective=obj, variable=variable,
            base_candidate=base, candidates=candidates, best=best,
            all_infeasible=all_infeasible, warnings=warnings)

    @staticmethod
    def _classify_point(point: SensitivityPoint
                        ) -> Tuple[List[ConstraintViolation], str]:
        if point.classification == PHYSICALLY_INVALID:
            return [], PHYSICALLY_INVALID
        if point.classification == NO_OPERATING_POINT:
            return [], NO_OPERATING_POINT
        if point.classification == MULTIPLE_OPERATING_POINTS:
            return [], MULTIPLE_OPERATING_POINTS
        if point.q_op is None:
            return [], NUMERICAL_NON_CONVERGENCE
        return [], FEASIBLE
