"""
Deterministic Nodal Analysis engine (Production Engineering — Phase 3).

Orchestrator only: the Nodal engine contains NO copies of the IPR or VLP
equations. All inflow math comes from services.production_engine.IPREngine
(verified Phase 1) and all outflow math comes from services.vlp_engine
(verified Phase 2, Beggs-Brill 1973).

Root formulation (Beggs, "Production Optimization Using Nodal Analysis";
Economides et al., "Petroleum Production Systems"):

    F(q) = Pwf_IPR(q) - Pwf_VLP(q)  =  0

The solver evaluates F over a resolved rate grid, detects ALL sign-change
intervals (and near-zero grid points), and refines each bracket with a
bounded bisection — never an unbracketed Newton step. The VLP curve is NOT
assumed monotonic (gas-rich Beggs-Brill flow can exhibit the liquid-loading
dip at low rates), so zero, one, or multiple intersections are all
possible outcomes and are reported explicitly:

    UNIQUE_OPERATING_POINT        exactly one valid root
    MULTIPLE_OPERATING_POINTS     more than one valid root (all returned;
                                  stability ranking is ENGINEERING
                                  INTERPRETATION only, with the criterion
                                  dF/dq < 0 at the crossing documented)
    NO_OPERATING_POINT            no root in the analyzed range, with a
                                  deterministic reason
    NUMERICAL_NON_CONVERGENCE     residual at a candidate root exceeds the
                                  documented tolerance

Single-source-of-truth discipline: rate(q) is always computed by
IPREngine.rate_at (built from the same rate methods as Phase 1) and
Pwf_VLP(q) is always vlp_engine.traverse — this module only interpolates
the deterministic IPR pressure grid and composes F.

Caching: a per-solve memoization dict maps evaluated rates to
Pwf_VLP results so a root refinement never re-runs a full traverse that
was already done during the grid scan. The cache lives only inside one
`NodalEngine.solve()` call and is never shared across Telegram users or
requests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services import vlp_engine
from services.production_engine import IPREngine

# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------

_STATUS_UNIQUE = "UNIQUE_OPERATING_POINT"
_STATUS_MULTIPLE = "MULTIPLE_OPERATING_POINTS"
_STATUS_NONE = "NO_OPERATING_POINT"
_STATUS_NONCONV = "NUMERICAL_NON_CONVERGENCE"
_STATUS_INVALID = "PHYSICALLY_INVALID"
_STATUS_UNKNOWN = "UNKNOWN"

STABLE_LABEL = (
    "ENGINEERING INTERPRETATION (stability criterion: dF/dq = d(Pwf_IPR)/dq "
    "- d(Pwf_VLP)/dq; a crossing with dF/dq < 0 (IPR steeper downward than "
    "the VLP slope) is the classically stable node, per nodal-analysis "
    "literature. This ranking is NOT a dynamic-simulation result."
)


@dataclass
class NodalRoot:
    """One detected intersection (operating point)."""
    q: float                      # STB/day
    pwf: float                    # psia
    residual: float               # |Pwf_IPR - Pwf_VLP| at the root, psi
    slope_sign: Optional[str]     # "stable"/"unstable"/None (see STABLE_LABEL)
    index: int                    # 1-based discovery index


@dataclass
class NodalResult:
    status: str
    roots: List[NodalRoot] = field(default_factory=list)
    reason: Optional[str] = None
    # Traceability metadata (sufficient to reproduce the result)
    ipr_model: Optional[str] = None
    ipr_reason: Optional[str] = None
    vlp_model: str = "beggs_brill"
    q_min: float = 0.0
    q_max: float = 0.0
    n_scan_points: int = 0
    root_method: str = "grid_scan + bracketed_bisection"
    pressure_tol: float = 0.0
    grid_pressure_tol: float = 0.0
    refinement_iterations: int = 0
    cache_hits: int = 0
    # Resolved IPR params + VLP kwargs — so downstream code (plotting,
    # tests) can re-evaluate curves through the engine's own inverters
    # without duplicating calibration or inversion logic.
    ipr_params: Optional[Tuple] = None
    vlp_kwargs: Optional[Dict[str, Any]] = None

    inputs_summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    pvt_metadata: Dict[str, Any] = field(default_factory=dict)


class NodalError(Exception):
    """Hard failure for guardrail violations."""
    def __init__(self, kind: str, message: str):
        self.kind = kind
        self.message = message
        super().__init__(message)


def _vlp_error_kind(exc: Exception) -> str:
    """Preserve explicit VLP/provider failure kinds at the Nodal boundary."""
    message = str(exc)
    for kind in ("INSUFFICIENT_DATA", "PHYSICALLY_INVALID",
                 "NUMERICAL_NON_CONVERGENCE"):
        if kind in message:
            return kind
    if "INVALID_INPUT" in message:
        return "PHYSICALLY_INVALID"
    return "NUMERICAL_NON_CONVERGENCE"


DEFAULT_PRES_TOL = 0.1        # psi — residual requirement at a root
DEFAULT_GRID_TOL = 2.0        # psi — sign-change detection on the grid
DEFAULT_N_POINTS = 201        # scan resolution (>=2)
DEFAULT_MAX_REFINE_ITER = 64


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class NodalEngine:
    """Deterministic orchestrator coupling the verified IPR and VLP engines."""

    def __init__(self):
        self.ipr = IPREngine()

    # ------------------------------------------------------------------
    # IPR side: resolved effective model + rate-from-pressure evaluation
    # ------------------------------------------------------------------

    def _resolve_ipr(self, ipr_model: str, pr: float, pb: Optional[float],
                     pwf_hint: Optional[float], j: Optional[float],
                     j_star: Optional[float], qmax: Optional[float],
                     q_test: Optional[float], pwf_test: Optional[float]
                     ) -> Tuple[str, str, Tuple]:
        """Return (effective_model, reason, params) so rate_at(p) uses the
        exact Phase-1 rate methods (no equation duplication)."""
        engine = self.ipr
        if ipr_model == "auto":
            effective, reason = engine.select_model(pr, pb, pwf_hint)
        elif ipr_model == "vogel":
            # For nodal analysis there is no single requested Pwf — a full
            # curve crosses Pb, so a Pb-aware "auto" policy applies: if the
            # well is undersaturated with Pb given, use composite; else vogel.
            if pb is not None and pr > pb:
                effective, reason = _MODEL_COMPOSITE, (
                    "vogel requested but Pr > Pb with Pb supplied: the nodal "
                    "inflow curve will cross the bubble point, so Composite "
                    "IPR (linear above Pb, Vogel below) is used instead."
                )
            else:
                effective, reason = "vogel", "Vogel IPR requested explicitly."
        elif ipr_model == "linear":
            effective, reason = "linear", "Linear IPR requested explicitly."
        elif ipr_model == "composite":
            effective, reason = "composite", "Composite IPR requested explicitly."
        else:
            raise NodalError(
                "PHYSICALLY_INVALID",
                f"Unknown IPR model: {ipr_model}. Use one of auto, linear, "
                "vogel, composite."
            )

        params = self._ipr_params(effective, pr, pb, j, j_star, qmax,
                                  q_test, pwf_test)
        return effective, reason, params

    @staticmethod
    def _ipr_params(model: str, pr: float, pb: Optional[float],
                    j: Optional[float], j_star: Optional[float],
                    qmax: Optional[float], q_test: Optional[float],
                    pwf_test: Optional[float]):
        """Anchor the chosen model; mirrors Phase-1 inversion for a missing
        slope parameter so nodal inputs stay minimal and exact."""
        if model == "linear":
            if j is None:
                if q_test is None or pwf_test is None:
                    raise NodalError(
                        "INSUFFICIENT_DATA",
                        "Linear IPR requires j or (q_test, pwf_test).")
                j = q_test / max(pr - pwf_test, 1e-9)
                if j <= 0:
                    raise NodalError(
                        "PHYSICALLY_INVALID",
                        "Test point implies J <= 0 (Pwf_test >= Pr or "
                        "q_test <= 0).")
            return ("linear", (pr, j))
        if model == "vogel":
            if qmax is None:
                if q_test is None or pwf_test is None:
                    raise NodalError(
                        "INSUFFICIENT_DATA",
                        "Vogel IPR requires qmax or (q_test, pwf_test).")
                qmax = q_test / max(
                    IPREngine._vogel_factor(pr, pwf_test), 1e-12)
                if qmax <= 0:
                    raise NodalError(
                        "PHYSICALLY_INVALID",
                        "Test point implies qmax <= 0.")
            return ("vogel", (pr, qmax))
        if model == "composite":
            if q_test is None or pwf_test is None:
                raise NodalError(
                    "INSUFFICIENT_DATA",
                    "Composite IPR requires (q_test, pwf_test).")
            if pb is None:
                raise NodalError(
                    "INSUFFICIENT_DATA",
                    "Composite IPR requires Pb to split the regimes.")
            if not (0 <= pb <= pr):
                raise NodalError(
                    "PHYSICALLY_INVALID",
                    "Pb must satisfy 0 <= Pb <= Pr for Composite IPR.")
            if pwf_test >= pb:
                j_star = q_test / max(pr - pwf_test, 1e-9)
                return ("composite", (pr, pb, j_star))
            # Test point below Pb — calibration must include the Vogel
            # tail. Invert the exact Phase-1 composite equation:
            #   q_test = j*(Pr-Pb) + (qo_max-qb)*(1-0.2r-0.8r^2)  with
            #   r = Pwf_test/Pr, qb = j*(Pr-Pb), qo_max = j*Pr
            r = pwf_test / pr
            vogel_at_test = 1.0 - 0.2 * r - 0.8 * r * r
            j_star = q_test / max((pr - pb) + pr * vogel_at_test, 1e-12)
            if j_star <= 0:
                raise NodalError(
                    "PHYSICALLY_INVALID",
                    "Test point below Pb implies j* <= 0.")
            return ("composite", (pr, pb, j_star))
        raise NodalError("PHYSICALLY_INVALID", f"Unknown model: {model}")

    def rate_at(self, params: Tuple, pwf: float) -> float:
        """Exact Phase-1 rate methods — single source of truth for IPR."""
        kind, t = params
        if kind == "linear":
            return self.ipr.linear_q(t[0], t[1], pwf)
        if kind == "vogel":
            return self.ipr.vogel_q(t[0], t[1], pwf)
        if kind == "composite":
            if len(t) == 4:
                return self.ipr.composite_q(t[0], t[1], t[3], pwf)
            return self.ipr.composite_q(t[0], t[1], t[2], pwf)
        raise NodalError("PHYSICALLY_INVALID", f"Unknown IPR params: {kind}")

    # ------------------------------------------------------------------
    # VLP side: memoized traverse (single-solve cache only)
    # ------------------------------------------------------------------

    def pwf_vlp(self, q_total: float, params: Tuple,
                vlp_kwargs: Optional[Dict[str, Any]] = None) -> float:
        """Public invert: required Pwf from the VLP curve at rate q_total.
        Uses the resolved IPR params only to read Pr (wellbore depth anchor)."""
        kw = dict(vlp_kwargs) if vlp_kwargs is not None else {}
        # Name normalization: result.vlp_kwargs uses traverse() names
        # (z_factor) but callers may supply the Telegram shorthand (z).
        if "z" in kw and "z_factor" not in kw:
            kw["z_factor"] = kw.pop("z")
        if "tubing_id" in kw and "tubing_id_in" not in kw:
            kw["tubing_id_in"] = kw.pop("tubing_id")
        if "id" in kw and "tubing_id_in" not in kw:
            kw["tubing_id_in"] = kw.pop("id")
        kw["q_w"] = 0.0
        kw["q_o"] = q_total
        kw.setdefault("tol", 1e-3)
        kw.setdefault("max_seg_iter", 120)
        kw.setdefault("max_iters", 4000)
        kw.setdefault("sigma", 30.0)
        kw.setdefault("n_segments", 80)
        kw.setdefault("bw", 1.01)
        kw.setdefault("z_factor", 0.9)
        kw.setdefault("gamma_w", 1.07)
        kw.setdefault("wc", 0.0)
        if q_total <= 0.0:
            # Multiphase friction is undefined at zero flow — the well is
            # a static fluid column (friction contribution exactly zero),
            # matching vlp_engine.curve() at q = 0.
            return vlp_engine.static_gradient(
                kw.get("thp", 100.0), kw.get("tvd", 0.0), kw.get("t_wh", 120.0),
                kw.get("geothermal", 1.5), kw.get("gamma_g", 0.65),
                kw.get("gamma_w", 1.07), kw.get("z_factor", 0.9)).pwf
        try:
            res = vlp_engine.traverse(**kw)
        except (ValueError, TypeError, NodalError) as exc:
            # TypeError covers e.g. a complex result from the Lee viscosity
            # exponent at collapsed segment pressures — must never crash.
            raise NodalError(
                _vlp_error_kind(exc),
                f"VLP evaluation failed at q={q_total:g} STB/day: {exc}")
        return res.pwf

    def _pwf_vlp(self, q_total: float, vlp_kwargs: Dict[str, Any],
                 cache: Dict[float, Optional[float]],
                 pvt_metadata: Optional[Dict[str, Any]] = None) -> float:
        """Required flowing BHP for the total rate; cached per solve."""
        key = round(q_total, 6)
        cached = cache.get(key)
        if cached is not None:
            if isinstance(cached, float):
                return cached
            raise NodalError(
                "NUMERICAL_NON_CONVERGENCE",
                "VLP traverse did not converge at a candidate rate; a "
                "non-converged point can never be an operating point.")
        if q_total <= 0.0:
            # Static fluid column at zero flow — friction exactly zero,
            # matching vlp_engine.curve() at q = 0.
            pwf_static = vlp_engine.static_gradient(
                vlp_kwargs.get("thp", 100.0), vlp_kwargs.get("tvd", 0.0),
                vlp_kwargs.get("t_wh", 120.0), vlp_kwargs.get("geothermal", 1.5),
                vlp_kwargs.get("gamma_g", 0.65),
                vlp_kwargs.get("gamma_w", 1.07),
                vlp_kwargs.get("z_factor", 0.9)).pwf
            cache[key] = pwf_static
            return pwf_static
        try:
            kw = dict(vlp_kwargs)
            kw["q_o"] = q_total   # vlp_kwargs already carries q_w=0.0
            res = vlp_engine.traverse(**kw)
            if pvt_metadata is not None:
                pvt_metadata.clear()
                pvt_metadata.update(getattr(res, "pvt_metadata", {}))
        except (ValueError, TypeError, NodalError) as exc:
            msg = str(exc)
            cache[key] = None
            raise NodalError(
                _vlp_error_kind(exc),
                f"VLP evaluation failed at q={q_total:g} STB/day: {msg}")
        cache[key] = res.pwf
        return res.pwf

    # ------------------------------------------------------------------
    # Search-range helpers
    # ------------------------------------------------------------------

    @staticmethod
    def auto_q_max(params: Tuple) -> float:
        """Theoretical upper bound from the IPR model only: the rate at
        Pwf = 0. Never invented — it is the model's own extrapolation."""
        kind, t = params
        if kind == "linear":
            return t[0] * t[1]          # J * Pr
        if kind == "vogel":
            return t[1]                 # qmax
        if kind == "composite":
            # composite_q(pr, pb, j_star, pwf) — always a 3-tuple
            return IPREngine().composite_q(t[0], t[1], t[2], 0.0)
        return 0.0

    # ------------------------------------------------------------------
    # Root search: deterministic grid + bracketed bisection
    # ------------------------------------------------------------------

    def _bisection(self, lo: float, hi: float, flo: float, fhi: float,
                   f_of_q, tol: float, max_iter: int
                   ) -> Tuple[float, float, int]:
        """Standard bracketed bisection. |hi-lo| < tol stops. Returns
        (q_root, f_root, iterations). The bracket invariant f(lo)*f(hi)<0
        is verified by the caller."""
        n = 0
        while hi - lo > tol and n < max_iter:
            mid = (lo + hi) / 2.0
            fmid = f_of_q(mid)
            if fmid * flo <= 0.0:
                hi, fhi = mid, fmid
            else:
                lo, flo = mid, fmid
            n += 1
        q_root = (lo + hi) / 2.0
        return q_root, f_of_q(q_root), n

    def solve(
        self,
        *,
        ipr_model: str = "auto",
        pr: float,
        pb: Optional[float] = None,
        j: Optional[float] = None,
        j_star: Optional[float] = None,
        qmax: Optional[float] = None,
        q_test: Optional[float] = None,
        pwf_test: Optional[float] = None,
        # VLP inputs (canonical vlp_engine names)
        thp: float,
        tvd: float,
        tubing_id_in: float,
        gor: float,
        rs: float,
        api: float,
        gamma_g: float,
        mu_l: float,
        bo: float,
        t_wh: float,
        geothermal: float,
        wc: float = 0.0,
        gamma_w: float = 1.07,
        bw: float = 1.01,
        z_factor: float = 0.9,
        sigma: float = 30.0,
        n_segments: int = 80,
        vlp_model: str = "beggs_brill",
        # Solver
        q_min: Optional[float] = None,
        q_max: Optional[float] = None,
        n_points: int = DEFAULT_N_POINTS,
        pressure_tol: float = DEFAULT_PRES_TOL,
        grid_pressure_tol: float = DEFAULT_GRID_TOL,
        max_refine_iter: int = DEFAULT_MAX_REFINE_ITER,
        pvt_provider: Any = None,
        pvt_context: Optional[Dict[str, Any]] = None,
    ) -> NodalResult:
        """Full deterministic nodal analysis. Raises NodalError for
        guardrail violations; otherwise returns a classified NodalResult."""

        if n_points < 2:
            raise NodalError(
                "PHYSICALLY_INVALID", "Need at least 2 scan points.")
        if q_min is None:
            q_min = 0.0
        if pressure_tol <= 0:
            raise NodalError(
                "PHYSICALLY_INVALID", "pressure_tol must be > 0 psi.")
        if max_refine_iter < 1:
            raise NodalError(
                "PHYSICALLY_INVALID", "max_refine_iter must be >= 1.")

        # ---- IPR model resolution & validation --------------------------
        effective, reason, params = self._resolve_ipr(
            ipr_model, pr, pb, None, j, j_star, qmax, q_test, pwf_test)

        if pr <= 0:
            raise NodalError(
                "PHYSICALLY_INVALID",
                "Reservoir pressure Pr must be > 0 psia.")
        if q_test is not None and pwf_test is not None:
            if pwf_test >= pr:
                raise NodalError(
                    "PHYSICALLY_INVALID",
                    "Test flowing pressure Pwf_test must be below Pr.")
            if q_test <= 0 or pwf_test < 0:
                raise NodalError(
                    "PHYSICALLY_INVALID",
                    "Test point invalid: q_test must be > 0 and Pwf_test >= 0.")

        # ---- Search range -------------------------------------------------
        auto_max = self.auto_q_max(params)
        if q_max is None:
            if not (0 < auto_max < math.inf):
                raise NodalError(
                    "INSUFFICIENT_DATA",
                    "Cannot derive an automatic q_max from the chosen IPR "
                    "model; supply q_max explicitly.")
            q_max = auto_max
        if not (q_max > q_min >= 0):
            raise NodalError(
                "PHYSICALLY_INVALID",
                "Rate range invalid: need 0 <= q_min < q_max.")
        if q_max > 1e6:
            raise NodalError(
                "PHYSICALLY_INVALID",
                "q_max is unrealistically large (> 1e6 STB/day).")

        # ---- VLP kwargs: reuse vlp_engine exact validation ---------------
        vlp_kwargs: Dict[str, Any] = dict(
            thp=thp, tvd=tvd, tubing_id_in=tubing_id_in, gor=gor, rs=rs,
            api=api, gamma_g=gamma_g, mu_l=mu_l, bo=bo, t_wh=t_wh,
            geothermal=geothermal, wc=wc, gamma_w=gamma_w, bw=bw,
            z_factor=z_factor, sigma=sigma, n_segments=n_segments,
        )
        if pvt_provider is not None:
            vlp_kwargs["pvt_provider"] = pvt_provider
            vlp_kwargs["pvt_context"] = pvt_context
        # VLP correlation selector (routed through the same vlp_engine API).
        try:
            vlp_kwargs["vlp_model"] = vlp_engine._resolve_model(vlp_model)
        except ValueError as _e:
            raise NodalError("PHYSICALLY_INVALID", str(_e))
        _vlp_validate_map = {
            "tubing_id_in": "id",
            "z_factor": "z",
            "n_segments": "segments",
        }
        vlp_err = vlp_engine.validate_inputs({
            _vlp_validate_map.get(k, k): v for k, v in vlp_kwargs.items()
            if k in ("thp", "tvd", "tubing_id_in", "gor", "rs", "api",
                     "gamma_g", "mu_l", "bo", "t_wh", "geothermal", "wc",
                     "gamma_w", "bw", "z_factor", "sigma", "n_segments")})
        if vlp_err is not None:
            raise NodalError(vlp_err.kind, vlp_err.message)
        # Map the kwargs to traverse's argument names
        vlp_kwargs["q_w"] = 0.0
        vlp_kwargs["q_o"] = 0.0          # overwritten per call
        vlp_kwargs["tol"] = 1e-3
        vlp_kwargs["max_seg_iter"] = 120
        vlp_kwargs["max_iters"] = 4000

        # ---- Grid evaluation of F(q) -------------------------------------
        cache: Dict[float, Optional[float]] = {}
        pvt_metadata: Dict[str, Any] = {}
        q_grid = [q_min + (q_max - q_min) * i / (n_points - 1)
                  for i in range(n_points)]

        def eval_vlp(q: float) -> float:
            if pvt_provider is None:
                return self._pwf_vlp(q, vlp_kwargs, cache)
            return self._pwf_vlp(q, vlp_kwargs, cache, pvt_metadata)

        def f_of_q(q: float) -> float:
            try:
                pwf_vlp = eval_vlp(q)
            except NodalError:
                raise
            try:
                pwf_ipr = self._pwf_ipr_from_rate(params, q)
            except ValueError:
                # IPR guardrail at this rate (e.g., pwf<0) — flag, don't crash
                raise NodalError(
                    "NUMERICAL_NON_CONVERGENCE",
                    f"IPR evaluation failed at q={q:g} STB/day; this rate "
                    "cannot be an operating point.")
            return pwf_ipr - pwf_vlp

        f_vals: List[float] = []
        scan_warnings: List[str] = []
        for q in q_grid:
            try:
                f_vals.append(f_of_q(q))
            except (NodalError, ValueError, TypeError) as exc:
                if pvt_provider is not None:
                    raise
                # ValueError/TypeError cover non-convergence artefacts that
                # surface deeper in the stack (e.g. complex arithmetic in
                # the Lee-Gonzalez-Eakin viscosity at collapsed segment
                # pressures). They are grid artefacts, never operating
                # points, so the scan records them and moves on.
                f_vals.append(math.nan)
                scan_warnings.append(
                    f"Rate q={q:g} STB/day skipped (non-converged or "
                    f"invalid): {exc}")

        # ---- Root detection: exact/near-zero + sign changes ---------------
        roots: List[NodalRoot] = []
        total_iters = 0
        tol_q = (q_max - q_min) / max(n_points - 1, 1) / 10.0

        def refine(lo, hi, flo, fhi) -> Optional[Tuple[float, float, int]]:
            try:
                q_root, f_root, n = self._bisection(
                    lo, hi, flo, fhi, f_of_q,
                    min(pressure_tol / 10.0, pressure_tol * 0.5),
                    max_refine_iter)
            except (NodalError, ValueError, TypeError):
                if pvt_provider is not None:
                    raise
                return None
            if not (q_min - 1e-9 <= q_root <= q_max + 1e-9):
                return None
            if abs(f_root) > pressure_tol * 2.0:
                # The bracketed bisection stops on |hi-lo| < pressure_tol,
                # so the endpoint residual can slightly exceed the residual
                # tolerance; reject only genuinely low-quality roots — the
                # final pressure-consistency check below is the authority.
                return None
            try:
                pwf_vlp = eval_vlp(q_root)
                pwf_ipr = self._pwf_ipr_from_rate(params, q_root)
            except NodalError:
                if pvt_provider is not None:
                    raise
                return None
            if not (0.0 <= pwf_ipr <= pr + 1e-9) or pwf_vlp < 0:
                return None
            if abs(pwf_ipr - pwf_vlp) > pressure_tol * 2.0:
                return None
            return q_root, (pwf_ipr + pwf_vlp) / 2.0, n

        # Near-zero grid points
        for idx, (q, f) in enumerate(zip(q_grid, f_vals)):
            if math.isnan(f):
                continue
            if abs(f) <= grid_pressure_tol:
                # Bracket the near-zero point with its neighbors so the
                # bisection has a genuine sign bracket.
                f_lo = f_hi = None
                lo = hi = q
                for back in range(idx, -1, -1):
                    if not math.isnan(f_vals[back]) and f_vals[back] * f <= 0:
                        lo, f_lo = q_grid[back], f_vals[back]
                        break
                for fwd in range(idx, len(q_grid)):
                    if not math.isnan(f_vals[fwd]) and f_vals[fwd] * f <= 0:
                        hi, f_hi = q_grid[fwd], f_vals[fwd]
                        break
                if f_lo is not None and f_hi is not None and lo != hi:
                    r = refine(lo, hi, f_lo, f_hi)
                    if r is not None:
                        roots.append(NodalRoot(
                            q=r[0], pwf=r[1], residual=0.0,
                            slope_sign=None, index=len(roots) + 1))
                    continue
                # No genuine bracket around this point — evaluate residual
                # directly at the grid point instead of refining.
                try:
                    pwf_ipr = self._pwf_ipr_from_rate(params, q)
                    pwf_vlp = eval_vlp(q)
                except NodalError:
                    if pvt_provider is not None:
                        raise
                    continue
                if abs(pwf_ipr - pwf_vlp) <= pressure_tol \
                        and 0.0 <= pwf_ipr <= pr + 1e-6:
                    roots.append(NodalRoot(
                        q=q, pwf=(pwf_ipr + pwf_vlp) / 2.0,
                        residual=abs(pwf_ipr - pwf_vlp),
                        slope_sign=None, index=len(roots) + 1))

        # Sign-change brackets
        for i in range(len(q_grid) - 1):
            f_lo, f_hi = f_vals[i], f_vals[i + 1]
            if math.isnan(f_lo) or math.isnan(f_hi):
                continue
            if f_lo * f_hi < 0.0:
                r = refine(q_grid[i], q_grid[i + 1], f_lo, f_hi)
                if r is not None:
                    roots.append(NodalRoot(
                        q=r[0], pwf=r[1], residual=abs(r[1] - r[1]),
                        slope_sign=None, index=len(roots) + 1))
                    total_iters += r[2]

        # De-duplicate roots that came from both a near-zero point and a
        # bracket (grid resolution overlap)
        dedup: List[NodalRoot] = []
        for rt in roots:
            if not any(abs(rt.q - d.q) < tol_q * 2 for d in dedup):
                dedup.append(rt)
        for k, rt in enumerate(dedup, start=1):
            rt.index = k

        # ---- Pressure-consistency & slope labeling ------------------------
        final: List[NodalRoot] = []
        for rt in dedup:
            try:
                pwf_ipr = self._pwf_ipr_from_rate(params, rt.q)
                pwf_vlp = eval_vlp(rt.q)
            except NodalError:
                if pvt_provider is not None:
                    raise
                continue
            residual = abs(pwf_ipr - pwf_vlp)
            # The bracketed bisection stops on bracket width < pressure_tol,
            # so the endpoint residual can legitimately exceed the residual
            # tolerance by roughly the local F(q) slope; the same margin is
            # applied in refine() above.
            if residual > pressure_tol * 2.0 or not (0 <= pwf_ipr <= pr + 1e-6):
                continue
            rt.residual = residual
            rt.pwf = (pwf_ipr + pwf_vlp) / 2.0
            # Slope labeling (engineering interpretation only)
            dq = max(tol_q, 1e-3)
            try:
                df = (f_of_q(rt.q + dq) - f_of_q(rt.q - dq)) / (2.0 * dq)
                rt.slope_sign = "stable" if df < 0 else "unstable"
            except NodalError:
                rt.slope_sign = None
            final.append(rt)

        # ---- Classification ------------------------------------------------
        out = NodalResult(
            status=_STATUS_UNKNOWN,
            q_min=q_min, q_max=q_max, n_scan_points=n_points,
            ipr_params=params, vlp_kwargs=vlp_kwargs,
            pressure_tol=pressure_tol, grid_pressure_tol=grid_pressure_tol,
            refinement_iterations=total_iters,
            ipr_model=effective, ipr_reason=reason,
            vlp_model=str(vlp_kwargs.get("vlp_model", "beggs_brill")),
            warnings=scan_warnings,
            inputs_summary=dict(pr=pr, thp=thp, tvd=tvd,
                                tubing_id_in=tubing_id_in, gor=gor, rs=rs,
                                api=api, gamma_g=gamma_g, mu_l=mu_l, bo=bo,
                                t_wh=t_wh, geothermal=geothermal, wc=wc,
                                z_factor=z_factor, q_test=q_test,
                                pwf_test=pwf_test, j=j, j_star=j_star,
                                qmax=qmax),
            pvt_metadata=pvt_metadata,
        )

        if not final:
            f_finite = [f for f in f_vals if not math.isnan(f)]
            if f_finite and all(f < 0 for f in f_finite):
                out.status = _STATUS_NONE
                out.reason = (
                    "IPR (available inflow pressure) lies entirely BELOW the "
                    "VLP curve (required BHP) across the analyzed range — "
                    "the reservoir cannot sustain flow against this VLP "
                    "within q in [0, q_max]. Check THP, depth, tubing size, "
                    "or reservoir pressure; or raise q_max if the crossing "
                    "may lie beyond the analyzed range.")
            elif f_finite and all(f > 0 for f in f_finite):
                out.status = _STATUS_NONE
                out.reason = (
                    "VLP (required BHP) lies entirely BELOW the IPR curve "
                    "across the analyzed range — the well would flow at a "
                    "rate beyond the analyzed q_max or the VLP case is "
                    "unphysically light for this reservoir. The analyzed "
                    "range may be insufficient to establish an intersection; "
                    "do not extrapolate beyond q_max without authorization.")
            else:
                out.status = _STATUS_NONE
                out.reason = (
                    "No valid intersection was found within the analyzed "
                    "range; parts of the range failed IPR/VLP evaluation. "
                    "The supplied rate range may be insufficient.")
            out.roots = []
            return out

        if len(final) == 1:
            out.status = _STATUS_UNIQUE
            out.roots = final
            return out

        out.status = _STATUS_MULTIPLE
        out.roots = final
        out.warnings.append(STABLE_LABEL)
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def pwf_ipr_from_rate(self, params: Tuple, q: float) -> float:
        """Public invert: Pwf on the IPR curve at total rate q."""
        return self._pwf_ipr_from_rate(params, q)

    def _pwf_ipr_from_rate(self, params: Tuple, q: float) -> float:
        """Invert the IPR rate function on the deterministic pressure grid
        to obtain Pwf at rate q. Uses a bracketed bisection over
        [0, Pr] — exact, no Newton without bracketing."""
        kind, t = params
        pr = t[0]
        if q <= 0.0:
            return pr
        lo, hi = 0.0, pr
        for _ in range(120):
            mid = (lo + hi) / 2.0
            try:
                qm = self.rate_at(params, mid)
            except ValueError:
                # Pressure outside the IPR's valid domain — shrink toward Pr
                lo = mid
                continue
            if not math.isfinite(qm):
                lo = mid
                continue
            if qm >= q:          # lower Pwf → higher rate
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        return (lo + hi) / 2.0


_MODEL_COMPOSITE = "composite"
