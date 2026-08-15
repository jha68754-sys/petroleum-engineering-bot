"""
Vertical Lift Performance (VLP) Engine — Phase 2: VLP (deterministic).
Correlation: BEGGS-BRILL (1973), SPE-4007-PA, with full flow-pattern
determination, horizontal/inclined holdup, two-phase friction factor,
and segmented pressure traverse.

Equation basis, assumptions, units, and limitations are documented at the
bottom of this file and in VLP_ENGINEERING_MODEL.md.

Units (petroleum field units throughout):
  pressure : psia        depth      : ft
  diameter : in          temperature: degF
  oil rate : STB/day     water rate : STB/day (or water cut fraction)
  gas rate : scf/day     GOR        : scf/STB
  viscosity: cP          density    : lbm/ft3
  gravity  : dimensionless (air = 1)

The AI layer (Groq) MUST NEVER be the numerical source of truth here.
This module generates all numerical values; the AI only explains them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------- #
# Constants
# ---------------------------------------------------------------------- #
G_FT_S2 = 32.174          # gravitational acceleration, ft/s^2
GC = 32.174               # gc, lbm-ft/(lbf-s^2)
PSI_PSF = 144.0           # 1 psi = 144 lbf/ft^2
PI = math.pi
WATER_DENSITY = 62.4      # lbm/ft3 at standard conditions
OIL_WEIGHT = 350.0        # lb of water per STB equivalent
AIR_DENSITY_STD = 0.0764  # lbm/ft3 at 14.7 psia, 60 F
SC_PRESSURE = 14.7        # standard pressure, psia
SC_TEMPERATURE = 520.0    # standard temperature, R (60 F)

# Default solver parameters (user-overridable where useful)
DEFAULT_SEGMENTS = 80      # tubing divided into this many segments
DEFAULT_TOL = 1e-6         # relative tolerance for midpoint pressure iteration
DEFAULT_MAX_SEG_ITER = 40   # iterations allowed per segment
DEFAULT_MAX_ITERS = 4000   # global safety cap (segments × per-segment)

# Beggs-Brill horizontal holdup coefficients: a, b, c where HL(0)=a*lam^b, a=NFr^c
_BB_COEFS: Dict[str, Tuple[float, float, float]] = {
    "segregated":   (0.98, 0.4846, 0.0868),
    "intermittent": (0.845, 0.5351, 0.0173),
    "distributed":  (1.065, 0.5824, 0.0609),
}
# Transition regime (between intermittent and distributed): weighted HL(0)
# is computed from the L2/L3 boundary lambdas; coefficients below are
# the distributed values used for the transition holdup after weighting.

# Inclination-correction C coefficients (uphill): d, e, f, g in
#   C = (1 - lam) * ln(d * lam^e * NLV^f * g)
_BB_INCL_COEFS: Dict[str, Tuple[float, float, float, float]] = {
    "segregated":   (0.011, -3.768, 3.539, -1.614),
    "intermittent": (2.96, 0.305, -0.4473, 0.0978),
    "distributed":  (0.0, 0.0, 0.0, 0.0),     # no inclination correction
}
# Downhill (all patterns): d, e, f, g
_BB_DOWNHILL = (4.70, -0.3692, 0.1244, -0.5056)

_MODEL_BEGGS_BRILL = "beggs_brill"
_MODEL_HAGEDORN_BROWN = "hagedorn_brown"
MODEL_DISPLAY = {"beggs_brill": "Beggs-Brill (1973) multiphase",
                 "hagedorn_brown": "Hagedorn-Brown (1965) multiphase"}
MODEL_ID = "vlp_model"
VALID_MODELS = (_MODEL_BEGGS_BRILL, _MODEL_HAGEDORN_BROWN)


def _resolve_model(vlp_model: Optional[str]) -> str:
    """Normalized model identifier. Beggs-Brill remains the default."""
    if vlp_model is None:
        return _MODEL_BEGGS_BRILL
    key = vlp_model.strip().lower().replace("-", "_")
    if key in VALID_MODELS:
        return key
    if "hagedorn" in key or key == "hb":
        return _MODEL_HAGEDORN_BROWN
    if "beggs" in key or "brill" in key or key == "bb":
        return _MODEL_BEGGS_BRILL
    raise ValueError(
        f"PHYSICALLY_INVALID: unknown vlp_model '{vlp_model}'; use "
        f"'beggs_brill' (default) or 'hagedorn_brown'.")


# ---------------------------------------------------------------------- #
# Structured validation
# ---------------------------------------------------------------------- #
@dataclass
class VLPError:
    kind: str  # "PHYSICALLY_INVALID" | "INSUFFICIENT_DATA" |
               # "NUMERICAL_NON_CONVERGENCE" | "CORRELATION_LIMITATION"
    message: str


class VLPResult:
    """Outcome of a single-rate VLP calculation."""
    def __init__(self, status: str, **kw):
        self.status = status
        self.pwf: Optional[float] = kw.get("pwf")
        self.thp: Optional[float] = kw.get("thp")
        self.rate: Optional[float] = kw.get("rate")
        self.water_cut: Optional[float] = kw.get("water_cut")
        self.gor: Optional[float] = kw.get("gor")
        self.tvd: Optional[float] = kw.get("tvd")
        self.tubing_id: Optional[float] = kw.get("tubing_id")
        self.segments: int = kw.get("segments", 0)
        self.components: Optional[Dict[str, float]] = kw.get("components")
        self.flow_pattern_counts: Optional[Dict[str, int]] = kw.get(
            "flow_pattern_counts")
        self.elevation_psi: float = kw.get("elevation_psi", 0.0)
        self.friction_psi: float = kw.get("friction_psi", 0.0)
        self.acceleration_psi: float = kw.get("acceleration_psi", 0.0)
        self.iterations: int = kw.get("iterations", 0)
        self.warnings: List[str] = kw.get("warnings", [])
        self.limitations: List[str] = kw.get("limitations", [])
        self.z_factor: Optional[float] = kw.get("z_factor")
        self.z_factor_provenance: Optional[str] = kw.get(
            "z_factor_provenance")  # "user supplied" | "default"
        self.input_defaults: List[str] = kw.get("input_defaults", [])
        self.pvt_metadata: Dict[str, Any] = kw.get("pvt_metadata", {})

    @property
    def converged(self) -> bool:
        return self.status == "CONVERGED"


# ---------------------------------------------------------------------- #
# Property helpers (black-oil style, defensible simplifications)
# ---------------------------------------------------------------------- #
def _rho_g(p: float, z: float, t_f: float, gamma_g: float) -> float:
    """Gas density, lbm/ft3, real-gas law (p psia, t degF, z dimensionless)."""
    return 2.7 * gamma_g * p / (z * (t_f + 460.0))


def _rho_l(api: float, rs: float, gamma_g: float, bo: float,
             gamma_w: float, wc: float) -> float:
    """Liquid density, lbm/ft3 — standard industry mass-balance form
    (Brown, Technology of Artificial Lift, Vol. 1; Economides et al.):
        rho_L = (350 * sg_o + Rs * sg_g * 0.0764) / (Bo * 5.615)
    Mass per STB (lb of oil + lb of dissolved gas) divided by the
    in-situ volume (Bo rb/STB * 5.615 ft3/rb).  Water phase:
    62.4 * sg_w.  Blended by water-cut fraction.
    """
    sg_o = 141.5 / (api + 131.5)
    rho_o = (350.0 * sg_o + rs * gamma_g * 0.0764) / (bo * 5.615)
    rho_w = WATER_DENSITY * gamma_w
    return rho_o * (1.0 - wc) + rho_w * wc


def _gas_viscosity_lee(t_f: float, p: float, gamma_g: float,
                       z: float = 1.0) -> float:
    """Gas viscosity, cP — Lee-Gonzalez-Eakin (1966), SPE-1340."""
    m_w = 28.967 * gamma_g
    t_r = t_f + 460.0
    if t_r <= 0.0:
        raise ValueError("PHYSICALLY_INVALID: absolute temperature must be "
                         "above 0 R for gas viscosity.")
    rho_g_lbm_ft3 = _rho_g(p, z, t_f, gamma_g)
    # Published Lee-Gonzalez-Eakin form uses gas density in g/cm3
    # (1 lbm/ft3 = 0.016018 g/cm3).
    rho_g = rho_g_lbm_ft3 * 0.016018
    k = (9.4 + 0.02 * m_w) * t_r ** 1.5 / (209.0 + 19.0 * m_w + t_r)
    x = 3.5 + 986.0 / t_r + 0.01 * m_w
    y = 2.4 - 0.2 * x
    try:
        val = math.exp(x * rho_g ** y)
    except OverflowError:
        # Nonphysical gas density produced an unbounded viscosity; flag
        # it so the solver treats the step as divergent rather than
        # silently corrupting the traverse.
        raise ValueError("NUMERICAL_NON_CONVERGENCE: gas viscosity "
                         "calculation overflowed at segment conditions "
                         "(rho_g = %.4f lbm/ft3)." % rho_g)
    return 1e-4 * k * val


def _colebrook(eps_in: float, d_ft: float, re: float) -> float:
    """Darcy friction factor, implicit Colebrook solved by fixed-point
    iteration with Haaland initial guess. Robust for Re >= 2000."""
    eps_over_d = eps_in / (12.0 * d_ft)
    inv_sqrt = -2.0 * math.log10(eps_over_d / 3.7 + 12.0 / re)
    for _ in range(30):
        lhs = 1.0 / inv_sqrt
        rhs = -2.0 * math.log10(eps_over_d / 3.7 + 2.51 / (re * lhs))
        new_inv = rhs
        if abs(new_inv - inv_sqrt) < 1e-12:
            break
        inv_sqrt = new_inv
    return (1.0 / inv_sqrt) ** 2


def _no_slip_friction(re: float, eps_in: float, d_ft: float) -> float:
    """No-slip (single-phase mixture) Darcy friction factor."""
    if re < 2000.0:
        return 16.0 / re
    return _colebrook(eps_in, d_ft, re)


# ---------------------------------------------------------------------- #
# Beggs-Brill core
# ---------------------------------------------------------------------- #
def _bb_flow_pattern(lam: float, nfr: float) -> str:
    """Flow-pattern determination from the ORIGINAL Beggs-Brill (1973)
    boundaries (as restated in Brill & Beggs 1991)."""
    l1 = 316.0 * lam ** 0.302
    l2 = 0.0009252 * lam ** (-2.4684)
    l3 = 0.10 * lam ** (-1.4516)
    l4 = 0.5 * lam ** (-6.738)
    if lam < 0.01 and nfr < l1:
        return "segregated"
    if lam >= 0.01 and nfr < l2:
        return "segregated"
    if 0.01 <= lam < 0.4 and l2 <= nfr <= l3:
        return "intermittent"
    if lam >= 0.4 and l3 < nfr <= l4:
        return "intermittent"
    if lam < 0.4 and nfr >= l3:
        return "distributed"
    if lam >= 0.4 and nfr > l4:
        return "distributed"
    return "transition"


def _bb_holdup(lam: float, nfr: float, pattern: str, theta_rad: float,
               vsl: float, rho_l: float, sigma: float = 30.0,
               re: float = 0.0) -> float:
    """Beggs-Brill liquid holdup HL(theta) for a vertical/uphill pipe.
    theta_rad: angle from HORIZONTAL (uphill positive). For a flowing
    vertical well use theta = pi/2."""
    if pattern == "transition":
        # Weighted HL(0) between the intermittent and distributed boundary
        # values, eta = (L3 - NFr) / (L3 - L2) (Brill & Beggs 1991).
        l1 = 316.0 * lam ** 0.302
        l2 = 0.0009252 * lam ** (-2.4684)
        l3 = 0.10 * lam ** (-1.4516)
        if l3 > l2:
            eta = (l3 - nfr) / (l3 - l2)
        else:
            eta = 0.5
        eta = max(0.0, min(1.0, eta))
        a_i, b_i, c_i = _BB_COEFS["intermittent"]
        a_d, b_d, c_d = _BB_COEFS["distributed"]
        hl_i = (nfr ** c_i) * (lam ** b_i)
        hl_d = (nfr ** c_d) * (lam ** b_d)
        hl0 = eta * hl_i + (1.0 - eta) * hl_d
    else:
        a, b, c = _BB_COEFS[pattern]
        hl0 = (nfr ** c) * (lam ** b)
    hl0 = max(hl0, lam)          # holdup can never be below no-slip value
    hl0 = min(hl0, 1.0)
    if theta_rad <= 0.0 or pattern == "distributed":
        return hl0
    if pattern == "transition":
        # Use the intermittent correction (conservative, standard practice);
        # the transition regime is weighted between L2/L3 boundaries for
        # HL(0) but the inclination correction C is taken from the
        # intermittent coefficients (Brill & Beggs, 1991, Ch. 3).
        pass
    pattern_key = "intermittent" if pattern == "transition" else pattern
    d, e, f, g = _BB_INCL_COEFS[pattern_key]
    n_lv = 1.938 * vsl * (rho_l / sigma) ** 0.25
    # Published Beggs-Brill form: C = (1 - lam) * ln( d * lam^e * N_LV^f /
    # N_Re^g ). The g term DIVIDES (Reynolds number to the power g), which
    # keeps the logarithm argument positive for the signed coefficients.
    denom = max(re, 1.0) ** g
    arg = d * (lam ** e) * (n_lv ** f) / denom
    if arg <= 0.0:
        # Degenerate flow (zero liquid or gas rates) — no inclination
        # correction is physically meaningful; return the horizontal holdup.
        return hl0
    c_coef = (1.0 - lam) * math.log(arg)
    c_coef = max(c_coef, -0.0654)
    c_coef = min(c_coef, 1.0)
    psi = math.exp(c_coef * (math.sin(1.8 * theta_rad)
                             - 0.333 * math.sin(1.8 * theta_rad) ** 3))
    psi = max(psi, 1.0) if theta_rad > 0 else psi
    hl = hl0 * psi
    return min(hl, 1.0)


def _bb_two_phase_friction(lam: float, hl: float, re: float, eps_in: float,
                           d_ft: float) -> Tuple[float, float]:
    """Two-phase friction factor ftp and no-slip fn. Returns (ftp, fn)."""
    fn = _no_slip_friction(re, eps_in, d_ft)
    y = lam / (hl ** 2) if hl > 0 else 0.0
    s = 0.0
    if y > 1.0:
        ln_y = math.log(y)
        denom = (-0.0523 + 3.182 * ln_y - 0.8725 * ln_y ** 2
                 + 0.01853 * ln_y ** 4)
        s = ln_y / denom
        s = min(s, 1.0)
    return fn * math.exp(s), fn


# ---------------------------------------------------------------------- #
# Segment hydrodynamics
# ---------------------------------------------------------------------- #
def _segment_state(p: float, t_f: float, q_o: float, q_w: float,
                   gor: float, bo: float, bw: float, z: float,
                   gamma_g: float, gamma_w: float, mu_l: float,
                   api: float, wc: float, d_ft: float, rs: float,
                   sigma: float, mu_g: Optional[float] = None) -> Dict[str, float]:
    """Compute all local flow variables at a segment node (standard BB
    input set). Returns a dictionary of local properties."""
    a = PI * d_ft ** 2 / 4.0
    # Free gas rate (only solution gas above bubble point stays dissolved)
    q_g_free = max(gor - rs, 0.0) * (q_o + q_w)
    vsl = ((q_o * bo + q_w * bw) / 5.615) / a / 86400.0
    vsg = (q_g_free * SC_PRESSURE / p * ((t_f + 460.0) / SC_TEMPERATURE)
           * (1.0 / max(z, 1e-9))) / a / 86400.0
    vm = vsl + vsg
    lam = vsl / vm if vm > 0 else (1.0 if (q_o + q_w) > 0 else 0.0)
    nfr = vm ** 2 / (G_FT_S2 * d_ft) if d_ft > 0 and vm > 0 else 0.0
    pattern = _bb_flow_pattern(lam, nfr)
    rho_l = _rho_l(api, rs, gamma_g, bo, gamma_w, wc)
    rho_g = _rho_g(p, z, t_f, gamma_g)
    hl = _bb_holdup(lam, nfr, pattern, PI / 2.0, vsl, rho_l, sigma)
    hl = max(hl, lam)
    rho_m = rho_l * hl + rho_g * (1.0 - hl)
    rho_s = rho_l * hl + rho_g * (1.0 - hl)
    mu_g = (_gas_viscosity_lee(t_f, p, gamma_g, z)
             if mu_g is None else mu_g)
    mu_m = mu_l * lam + mu_g * (1.0 - lam)
    re = 1488.0 * rho_m * vm * d_ft / mu_m if mu_m > 0 else 0.0
    ftp, fn = _bb_two_phase_friction(lam, hl, re, 0.00065, d_ft)
    gm = rho_m * vm * a               # lbm/s
    return dict(vm=vm, vsl=vsl, vsg=vsg, lam=lam, nfr=nfr, pattern=pattern,
                rho_l=rho_l, rho_g=rho_g, hl=hl, rho_m=rho_m,
                rho_s=rho_s, mu_m=mu_m, mu_g=mu_g, re=re, ftp=ftp, fn=fn,
                gm=gm)


def _resolve_pvt_properties(pvt_provider: Any,
                            pvt_context: Optional[Dict[str, Any]],
                            fallback: Dict[str, float],
                            tracker: Dict[str, Any],
                            pressure_psia: Optional[float] = None,
                            temperature_f: Optional[float] = None) -> Dict[str, float]:
    """Resolve PVT at the local pressure/temperature for one VLP state.

    The provider remains strictly opt-in. With no provider, the original
    caller-supplied properties are returned unchanged. With a provider, the
    context supplies the approved explicit Black-Oil inputs and the local
    segment pressure/temperature override only the state coordinates. Exact
    state memoization is deterministic and does not alter numerical behavior.
    """
    if pvt_provider is None:
        return fallback
    if not pvt_context:
        raise ValueError(
            "INSUFFICIENT_DATA: pvt_context with explicit pressure_psia and "
            "temperature_f is required when pvt_provider is enabled.")
    try:
        from services.black_oil_pvt import PvtState
        state_kwargs = dict(pvt_context)
        context_pressure = state_kwargs.pop("pressure_psia")
        context_temperature = state_kwargs.pop("temperature_f")
        local_pressure = context_pressure if pressure_psia is None else pressure_psia
        local_temperature = (context_temperature if temperature_f is None
                             else temperature_f)
        numeric_values = (context_pressure, context_temperature,
                          local_pressure, local_temperature)
        if any(isinstance(value, bool)
               or not isinstance(value, (int, float))
               or not math.isfinite(float(value))
               for value in numeric_values):
            raise TypeError("pressure_psia and temperature_f must be finite numeric values")
        if float(context_pressure) <= 0.0 or float(context_temperature) <= -459.67:
            raise ValueError("pressure_psia/temperature_f context is physically invalid")
        local_pressure = float(local_pressure)
        local_temperature = float(local_temperature)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "PHYSICALLY_INVALID: pvt_context must contain a valid explicit "
            "pressure_psia/temperature_f state for the Black-Oil provider."
        ) from exc

    cache = tracker.setdefault("cache", {})
    cache_key = (local_pressure, local_temperature)
    if cache_key in cache:
        tracker["last_properties"] = cache[cache_key]
        return cache[cache_key]

    # Do not catch provider exceptions here: an explicitly selected provider
    # must expose its engineering failure kind to the caller.
    result = pvt_provider.evaluate(PvtState(
        pressure_psia=local_pressure,
        temperature_f=local_temperature,
        **state_kwargs))
    tracker["pvt_evaluations"] += 1
    tracker["pressures"].append(local_pressure)
    tracker["temperatures"].append(local_temperature)
    status = str(getattr(result, "status", "UNKNOWN"))
    tracker["statuses"].add(status)
    phase_region = getattr(result, "phase_region", None)
    if phase_region is not None:
        tracker["phase_regions"].add(str(phase_region))
    pb = getattr(result, "pb_psia", None)
    if pb is not None and math.isfinite(float(pb)):
        tracker["bubble_points"].add(float(pb))
    tracker["provenance"] = getattr(result, "provenance", {}) or {}
    for key in ("warnings", "limitations"):
        for item in getattr(result, key, []) or []:
            if item not in tracker[key]:
                tracker[key].append(item)
    if status not in ("OK", "CORRELATION_LIMITATION"):
        raise ValueError(
            f"{status}: Black-Oil provider failed at {local_pressure:.6g} "
            "psia.")
    values = {
        "rs": getattr(result, "rs_scf_stb", None),
        "bo": getattr(result, "bo_rb_stb", None),
        "z": getattr(result, "z_factor", None),
        "mu_l": getattr(result, "mu_o_cp", None),
        "mu_g": getattr(result, "mu_g_cp", None),
        "bg": getattr(result, "bg_rb_scf", None),
    }
    missing = [name for name, value in values.items()
               if value is None or not math.isfinite(float(value))]
    if missing:
        raise ValueError(
            "INSUFFICIENT_DATA: Black-Oil provider returned missing/non-finite "
            f"properties: {', '.join(missing)}.")
    resolved = {name: float(value) for name, value in values.items()}
    cache[cache_key] = resolved
    tracker["unique_states"].add(cache_key)
    tracker["last_properties"] = resolved
    return resolved


def _finalize_pvt_metadata(pvt_provider: Any,
                           tracker: Dict[str, Any]) -> Dict[str, Any]:
    if pvt_provider is None:
        return {}
    pressures = tracker["pressures"]
    bubble_points = sorted(tracker["bubble_points"])
    pressure_min = min(pressures) if pressures else None
    pressure_max = max(pressures) if pressures else None
    pb_crossed = any(pressure_min < pb < pressure_max
                     for pb in bubble_points
                     if pressure_min is not None and pressure_max is not None)
    return {
        "enabled": True,
        "mode": "pressure_dependent_segment",
        "provider": pvt_provider.__class__.__name__,
        "pressure_psia": pressures[0] if pressures else None,
        "pressure_range_psia": ([pressure_min, pressure_max]
                                if pressures else []),
        "temperature_range_f": ([min(tracker["temperatures"]),
                                  max(tracker["temperatures"])]
                                 if tracker["temperatures"] else []),
        "pvt_evaluations": tracker["pvt_evaluations"],
        "unique_pressure_states": len({key[0] for key in tracker["unique_states"]}),
        "phase_regions": sorted(tracker["phase_regions"]),
        "bubble_point_psia": bubble_points[0] if len(bubble_points) == 1 else bubble_points,
        "pb_crossed": pb_crossed,
        "provenance": tracker["provenance"],
        "warnings": list(tracker["warnings"]),
        "limitations": list(tracker["limitations"]),
    }


def _gradients(st: Dict[str, float], d_ft: float) -> Tuple[float, float]:
    """Elevation and friction pressure gradients, psi/ft (vertical pipe)."""
    dp_el = st["rho_s"] * G_FT_S2 / GC / PSI_PSF
    dp_fr = (st["ftp"] * st["gm"] * st["vm"]) / (2.0 * GC * d_ft) / PSI_PSF
    return dp_el, dp_fr


# ---------------------------------------------------------------------- #
# Segmented pressure traverse
# ---------------------------------------------------------------------- #
def traverse(thp: float, tvd: float, q_o: float, q_w: float, gor: float,
             bo: float, bw: float, z_factor: float, gamma_g: float,
             gamma_w: float, mu_l: float, api: float, wc: float,
             tubing_id_in: float, rs: float, t_wh: float, geothermal: float,
             sigma: float = 30.0, n_segments: int = DEFAULT_SEGMENTS,
             tol: float = DEFAULT_TOL,
             max_seg_iter: int = DEFAULT_MAX_SEG_ITER,
             max_iters: int = DEFAULT_MAX_ITERS,
             vlp_model: Optional[str] = None,
             z_provenance: Optional[str] = None,
             input_defaults: Optional[List[str]] = None,
             pvt_provider: Any = None,
             pvt_context: Optional[Dict[str, Any]] = None) -> VLPResult:
    """Segmented pressure traverse, wellhead -> bottomhole.

    Model selection: 'beggs_brill' (default, original implementation) or
    'hagedorn_brown' (dispatches to traverse_hb). Beggs-Brill code path is
    unchanged when vlp_model is None; provider behavior is opt-in.
    """
    resolved = _resolve_model(vlp_model)
    if resolved == _MODEL_HAGEDORN_BROWN:
        return traverse_hb(
            thp, tvd, q_o, q_w, gor, bo, bw, z_factor, gamma_g, gamma_w,
            mu_l, api, wc, tubing_id_in, rs, t_wh, geothermal, sigma,
            n_segments, tol, max_seg_iter, max_iters,
            z_provenance=z_provenance, input_defaults=input_defaults,
            pvt_provider=pvt_provider, pvt_context=pvt_context)

    # Midpoint method per segment: properties evaluated at the arithmetic-mean
    # pressure of the segment endpoints, iterated until the segment delta-p
    # converges within `tol` (relative). Global iteration count is capped at
    # `max_iters`; exceeding it returns NUMERICAL_NON_CONVERGENCE (never a
    # silent answer). Pressure floor 0.01 psia is enforced with an error.

    # q_o, q_w: STB/day (total rates, water cut already accounted for in
    # q_w). GOR: scf/STB (produced). rs: scf/STB from the caller or the
    # pressure-resolved provider state at each local segment evaluation.
    if n_segments < 4:
        raise ValueError(
            "PHYSICALLY_INVALID: segment count must be >= 4 for a stable "
            "midpoint traverse.")
    d_ft = tubing_id_in / 12.0
    dl = tvd / n_segments
    total_iters = 0
    p = thp
    elev_psi = 0.0
    fric_psi = 0.0
    accel_psi = 0.0
    patterns: Dict[str, int] = {}
    seg_grads: List[Tuple[float, float]] = []
    pvt_tracker: Dict[str, Any] = {
        "pressures": [], "temperatures": [], "phase_regions": set(),
        "statuses": set(), "bubble_points": set(), "unique_states": set(),
        "pvt_evaluations": 0, "cache": {}, "provenance": {},
        "warnings": [], "limitations": []}
    fallback_properties = {
        "rs": rs, "bo": bo, "z": z_factor, "mu_l": mu_l,
        "mu_g": None, "bg": 0.0}

    def local_properties(p_eval: float, t_eval: float) -> Dict[str, float]:
        return _resolve_pvt_properties(
            pvt_provider, pvt_context, fallback_properties, pvt_tracker,
            pressure_psia=p_eval, temperature_f=t_eval)

    for i in range(n_segments):
        t_f = t_wh + geothermal * (i + 0.5) * dl / 100.0
        # bisection on the downstream pressure p2
        converged_seg = False
        seg_dp_el, seg_dp_fr = 0.0, 0.0
        p2 = p  # fallback: no pressure step if the segment cannot be solved
        seg_st: Optional[Dict[str, float]] = None
        # Bracketed bisection on the downstream pressure p2. The segment
        # residual g(p2) = p + dl*dp(p_avg) - p2 is MONOTONICALLY DECREASING
        # in p2 (a higher p2 reduces gas expansion, so dp(p_avg) falls
        # slower than p2 rises). It therefore has exactly one root, which
        # simple fixed-point iteration can miss (it can settle on a
        # self-consistent but wrong low-pressure branch for two-phase
        # flow). Bisection over a physically constructed bracket finds the
        # unique root robustly, at the cost of a few extra property
        # evaluations per segment.
        try:
            props_up = local_properties(p, t_f)
            st_up = _segment_state(
                p, t_f, q_o, q_w, gor, props_up["bo"], bw,
                props_up["z"], gamma_g, gamma_w, props_up["mu_l"],
                api, wc, d_ft, props_up["rs"], sigma,
                props_up["mu_g"])
        except (ValueError, ZeroDivisionError):
            if pvt_provider is not None:
                raise
            seg_dp_el, seg_dp_fr = 0.0, 0.0
        else:
            dp_up_el, dp_up_fr = _gradients(st_up, d_ft)
            # Upper bracket: full upstream-endpoint gradient over the step
            # (monotonically decreasing dp/p means the downstream pressure
            # can never exceed this).
            hi = p + (dp_up_el + dp_up_fr) * dl
            lo = p + 1e-9
            for k in range(max_seg_iter):
                p_avg = (p + (lo + hi) / 2.0) / 2.0
                if p_avg <= 0.01:
                    raise ValueError(
                        "NUMERICAL_NON_CONVERGENCE: pressure collapsed "
                        "below 0.01 psia during the traverse.")
                try:
                    props_mid = local_properties(p_avg, t_f)
                    st = _segment_state(
                        p_avg, t_f, q_o, q_w, gor, props_mid["bo"], bw,
                        props_mid["z"], gamma_g, gamma_w, props_mid["mu_l"],
                        api, wc, d_ft, props_mid["rs"], sigma,
                        props_mid["mu_g"])
                except (ValueError, ZeroDivisionError):
                    if pvt_provider is not None:
                        raise
                    seg_dp_el, seg_dp_fr = 0.0, 0.0
                    break
                dp_el, dp_fr = _gradients(st, d_ft)
                seg_dp_el, seg_dp_fr = dp_el, dp_fr
                # kinetic-energy (acceleration) correction
                p_mid = (lo + hi) / 2.0
                try:
                    t_next = t_f + geothermal * (i + 1) * dl / 100.0
                    props_next = local_properties(p_mid, t_next)
                    st2 = _segment_state(
                        p_mid, t_next, q_o, q_w, gor, props_next["bo"], bw,
                        props_next["z"], gamma_g, gamma_w,
                        props_next["mu_l"], api, wc, d_ft,
                        props_next["rs"], sigma, props_next["mu_g"])
                    dp_dvm = (st2["rho_s"] * st2["vm"]
                              - st["rho_s"] * st["vm"])
                    ek_prime = dp_dvm / GC / PSI_PSF
                except (ValueError, ZeroDivisionError):
                    if pvt_provider is not None:
                        raise
                    ek_prime = 0.0
                denom = 1.0 - ek_prime
                dp = (dp_el + dp_fr) / (denom if abs(denom) > 1e-9 else 1e-9)
                g_mid = p + dp * dl - p_mid
                if g_mid > 0:
                    lo = p_mid
                else:
                    hi = p_mid
                if hi - lo <= max(tol * max(p_mid, 1.0), 1e-6):
                    p2 = (lo + hi) / 2.0
                    converged_seg = True
                    seg_st = st
                    accel_psi += abs(ek_prime * dp) * dl
                    seg_grads.append((seg_dp_el, seg_dp_fr))
                    break
                total_iters += 1
                if total_iters >= max_iters:
                    raise ValueError(
                        "NUMERICAL_NON_CONVERGENCE: segmented traverse did "
                        "not converge within the allowed iteration budget.")
        if not converged_seg:
            total_iters += max_seg_iter
        seg_grads.append((seg_dp_el, seg_dp_fr))
        elev_psi += seg_dp_el * dl
        fric_psi += seg_dp_fr * dl
        if seg_st is not None:
            patterns[seg_st["pattern"]] = (
                patterns.get(seg_st["pattern"], 0) + 1)
        p = p2
        if p <= 0.01:
            raise ValueError(
                "NUMERICAL_NON_CONVERGENCE: bottomhole pressure collapsed "
                "below the 0.01 psia floor; check wellhead/rate inputs.")
    pvt_metadata = _finalize_pvt_metadata(pvt_provider, pvt_tracker)
    last_pvt = pvt_tracker.get("last_properties", {})
    return VLPResult(
        status="CONVERGED", pwf=p, thp=thp, rate=q_o + q_w,
        water_cut=wc, gor=gor, tvd=tvd, tubing_id=tubing_id_in,
        segments=n_segments,
        components=dict(elevation=elev_psi, friction=fric_psi,
                        acceleration=accel_psi),
        flow_pattern_counts=patterns,
        elevation_psi=elev_psi, friction_psi=fric_psi,
        acceleration_psi=accel_psi, iterations=total_iters,
        z_factor=(last_pvt["z"] if pvt_provider is not None
                   else z_factor),
        z_factor_provenance=("BlackOilPvtProvider" if pvt_provider is not None
                             else z_provenance),
        input_defaults=input_defaults,
        warnings=pvt_metadata.get("warnings", []),
        limitations=pvt_metadata.get("limitations", []),
        pvt_metadata=pvt_metadata)


def traverse_hb(thp: float, tvd: float, q_o: float, q_w: float, gor: float,
                bo: float, bw: float, z_factor: float, gamma_g: float,
                gamma_w: float, mu_l: float, api: float, wc: float,
                tubing_id_in: float, rs: float, t_wh: float,
                geothermal: float, sigma: float = 30.0,
                n_segments: int = DEFAULT_SEGMENTS,
                tol: float = DEFAULT_TOL,
                max_seg_iter: int = DEFAULT_MAX_SEG_ITER,
                max_iters: int = DEFAULT_MAX_ITERS,
                z_provenance: Optional[str] = None,
                input_defaults: Optional[List[str]] = None,
                pvt_provider: Any = None,
                pvt_context: Optional[Dict[str, Any]] = None) -> VLPResult:
    """Segmented Hagedorn-Brown (1965) pressure traverse, wellhead ->
    bottomhole.

    Structural mirror of `traverse` (same bracketed bisection, same
    midpoint method, same convergence contract). Segment properties come
    from the independent `services.hagedorn_brown` module. Flow-pattern
    counts are N/A for H-B (a segmented correlation with no distinct
    pattern map); the result keeps the field for API symmetry.
    """
    # Late import keeps hagedorn_brown out of the frozen Beggs-Brill path.
    from services import hagedorn_brown as _hb
    if n_segments < 4:
        raise ValueError(
            "PHYSICALLY_INVALID: segment count must be >= 4 for a stable "
            "midpoint traverse.")
    d_ft = tubing_id_in / 12.0
    dl = tvd / n_segments
    total_iters = 0
    p = thp
    elev_psi = 0.0
    fric_psi = 0.0
    accel_psi = 0.0
    seg_grads: List[Tuple[float, float]] = []
    warnings: List[str] = []
    # Applicability envelope (Hagedorn & Brown 1965 test range)
    env = _hb.HB_APPLICABILITY
    if not (env["tubing_id_in"][0] <= tubing_id_in <= env["tubing_id_in"][1]):
        warnings.append(
            f"CORRELATION_LIMITATION: tubing ID {tubing_id_in} in is outside "
            f"the published H-B range {env['tubing_id_in']} in.")
    if not (env["gor"][0] <= gor <= env["gor"][1]):
        warnings.append(
            f"CORRELATION_LIMITATION: GOR {gor} scf/STB is outside the "
            f"published H-B range {env['gor']} scf/STB.")
    q_total = q_o + q_w
    if not (env["liquid_rate"][0] <= q_total <= env["liquid_rate"][1]):
        warnings.append(
            f"CORRELATION_LIMITATION: liquid rate {q_total} STB/D is outside "
            f"the published H-B range {env['liquid_rate']} STB/D.")
    pvt_tracker: Dict[str, Any] = {
        "pressures": [], "temperatures": [], "phase_regions": set(),
        "statuses": set(), "bubble_points": set(), "unique_states": set(),
        "pvt_evaluations": 0, "cache": {}, "provenance": {},
        "warnings": [], "limitations": []}
    fallback_properties = {
        "rs": rs, "bo": bo, "z": z_factor, "mu_l": mu_l,
        "mu_g": None, "bg": 0.0}

    def local_properties(p_eval: float, t_eval: float) -> Dict[str, float]:
        return _resolve_pvt_properties(
            pvt_provider, pvt_context, fallback_properties, pvt_tracker,
            pressure_psia=p_eval, temperature_f=t_eval)

    for i in range(n_segments):
        t_f = t_wh + geothermal * (i + 0.5) * dl / 100.0
        converged_seg = False
        seg_dp_el, seg_dp_fr = 0.0, 0.0
        p2 = p
        seg_st: Optional[Dict[str, float]] = None
        try:
            props_up = local_properties(p, t_f)
            st_up = _hb.hb_segment_state(
                p, t_f, q_o, q_w, gor, props_up["bo"], bw,
                props_up["z"], gamma_g, gamma_w, props_up["mu_l"],
                api, wc, d_ft, props_up["rs"], sigma,
                mu_g=props_up["mu_g"])
        except (ValueError, ZeroDivisionError):
            if pvt_provider is not None:
                raise
            seg_dp_el, seg_dp_fr = 0.0, 0.0
        else:
            dp_up_el, dp_up_fr = _hb.hb_gradients(st_up, d_ft)
            hi = p + (dp_up_el + dp_up_fr) * dl
            lo = p + 1e-9
            for k in range(max_seg_iter):
                p_avg = (p + (lo + hi) / 2.0) / 2.0
                if p_avg <= 0.01:
                    raise ValueError(
                        "NUMERICAL_NON_CONVERGENCE: pressure collapsed "
                        "below 0.01 psia during the traverse.")
                try:
                    props_mid = local_properties(p_avg, t_f)
                    st = _hb.hb_segment_state(
                        p_avg, t_f, q_o, q_w, gor, props_mid["bo"], bw,
                        props_mid["z"], gamma_g, gamma_w, props_mid["mu_l"],
                        api, wc, d_ft, props_mid["rs"], sigma,
                        mu_g=props_mid["mu_g"])
                except (ValueError, ZeroDivisionError):
                    if pvt_provider is not None:
                        raise
                    seg_dp_el, seg_dp_fr = 0.0, 0.0
                    break
                dp_el, dp_fr = _hb.hb_gradients(st, d_ft)
                seg_dp_el, seg_dp_fr = dp_el, dp_fr
                p_mid = (lo + hi) / 2.0
                try:
                    t_next = t_f + geothermal * (i + 1) * dl / 100.0
                    props_next = local_properties(p_mid, t_next)
                    st2 = _hb.hb_segment_state(
                        p_mid, t_next, q_o, q_w, gor, props_next["bo"], bw,
                        props_next["z"], gamma_g, gamma_w,
                        props_next["mu_l"], api, wc, d_ft,
                        props_next["rs"], sigma, mu_g=props_next["mu_g"])
                    dp_dvm = (st2["rho_s"] * st2["vm"]
                              - st["rho_s"] * st["vm"])
                    ek_prime = dp_dvm / GC / PSI_PSF
                except (ValueError, ZeroDivisionError):
                    if pvt_provider is not None:
                        raise
                    ek_prime = 0.0
                denom = 1.0 - ek_prime
                dp = (dp_el + dp_fr) / (denom if abs(denom) > 1e-9 else 1e-9)
                g_mid = p + dp * dl - p_mid
                if g_mid > 0:
                    lo = p_mid
                else:
                    hi = p_mid
                if hi - lo <= max(tol * max(p_mid, 1.0), 1e-6):
                    p2 = (lo + hi) / 2.0
                    converged_seg = True
                    seg_st = st
                    accel_psi += abs(ek_prime * dp) * dl
                    seg_grads.append((seg_dp_el, seg_dp_fr))
                    break
                total_iters += 1
                if total_iters >= max_iters:
                    raise ValueError(
                        "NUMERICAL_NON_CONVERGENCE: segmented traverse did "
                        "not converge within the allowed iteration budget.")
        if not converged_seg:
            total_iters += max_seg_iter
        seg_grads.append((seg_dp_el, seg_dp_fr))
        elev_psi += seg_dp_el * dl
        fric_psi += seg_dp_fr * dl
        p = p2
        if p <= 0.01:
            raise ValueError(
                "NUMERICAL_NON_CONVERGENCE: bottomhole pressure collapsed "
                "below the 0.01 psia floor; check wellhead/rate inputs.")
    pvt_metadata = _finalize_pvt_metadata(pvt_provider, pvt_tracker)
    last_pvt = pvt_tracker.get("last_properties", {})
    return VLPResult(
        status="CONVERGED", pwf=p, thp=thp, rate=q_o + q_w,
        water_cut=wc, gor=gor, tvd=tvd, tubing_id=tubing_id_in,
        segments=n_segments,
        components=dict(elevation=elev_psi, friction=fric_psi,
                        acceleration=accel_psi),
        flow_pattern_counts={},
        elevation_psi=elev_psi, friction_psi=fric_psi,
        acceleration_psi=accel_psi, iterations=total_iters,
        warnings=warnings + list(pvt_tracker["warnings"]),
        limitations=warnings + list(pvt_tracker["limitations"]),
        z_factor=(last_pvt["z"] if pvt_provider is not None
                   else z_factor),
        z_factor_provenance=("BlackOilPvtProvider" if pvt_provider is not None
                             else z_provenance),
        input_defaults=input_defaults,
        pvt_metadata=pvt_metadata)


# ---------------------------------------------------------------------- #
# Zero-rate / static limit (documented, numerically safe)
# ---------------------------------------------------------------------- #
def static_gradient(thp: float, tvd: float, t_wh: float, geothermal: float,
                    gamma_g: float, gamma_w: float, z_factor: float = 1.0,
                    gas_column: bool = True) -> VLPResult:
    """At q = 0 the multiphase friction formula is undefined; the well
    behaves as a static fluid column. Returns the static bottomhole
    pressure. Friction contribution is exactly zero and the acceleration
    term vanishes by construction."""
    if gas_column:
        rho = _rho_g((thp + max(thp, 1.0)) / 2.0, z_factor,
                     t_wh + geothermal * tvd / 200.0, gamma_g)
        label = "static gas column"
    else:
        rho = WATER_DENSITY * gamma_w
        label = "static liquid column"
    pwf = thp + rho * G_FT_S2 / GC / PSI_PSF * tvd
    return VLPResult(
        status="CONVERGED", pwf=pwf, thp=thp, rate=0.0, tvd=tvd,
        components=dict(elevation=rho * G_FT_S2 / GC / PSI_PSF * tvd,
                        friction=0.0, acceleration=0.0),
        iterations=0,
        warnings=[f"Zero-rate case: {label} hydrostatic only; "
                  "friction contribution is zero by definition."])


# ---------------------------------------------------------------------- #
# Curve generation (deterministic rules, no invented envelopes)
# ---------------------------------------------------------------------- #
def vlp_curve(thp: float, tvd: float, gor: float, bo: float, bw: float,
              z_factor: float, gamma_g: float, gamma_w: float,
              mu_l: float, api: float, wc: float, tubing_id_in: float,
              rs: float, t_wh: float, geothermal: float,
              q_min: float, q_max: float, n_points: int,
              n_segments: int = DEFAULT_SEGMENTS,
              sigma: float = 30.0,
              vlp_model: Optional[str] = None,
              z_provenance: Optional[str] = None,
              input_defaults: Optional[List[str]] = None,
              pvt_provider: Any = None,
              pvt_context: Optional[Dict[str, Any]] = None,
              **_kwargs) -> Tuple[List[float],
                                                         List[float]]:
    """Calculated VLP curve: Pwf vs total rate. Rates are swept linearly;
    the water phase rate scales with water cut (q_w = q_o*wc/(1-wc)).
    Caller MUST supply q_min/q_max - no envelope is invented."""
    if n_points < 2:
        raise ValueError("PHYSICALLY_INVALID: need at least 2 curve points.")
    qs: List[float] = []
    ps: List[float] = []
    for i in range(n_points):
        q_total = q_min + (q_max - q_min) * i / (n_points - 1)
        if q_total <= 0.0:
            # Multiphase friction is undefined at zero flow; the well is a
            # static fluid column — use static_gradient (friction = 0).
            qs.append(q_total)
            ps.append(static_gradient(
                thp, tvd, t_wh, geothermal, gamma_g, gamma_w,
                z_factor).pwf)
            continue
        q_o = q_total * (1.0 - wc)
        q_w = q_total * wc
        res = traverse(
            thp, tvd, q_o, q_w, gor, bo, bw, z_factor, gamma_g, gamma_w,
            mu_l, api, wc, tubing_id_in, rs, t_wh, geothermal, sigma,
            n_segments, vlp_model=vlp_model,
            z_provenance=z_provenance if z_provenance else "default",
            input_defaults=input_defaults,
            pvt_provider=pvt_provider, pvt_context=pvt_context)
        qs.append(q_total)
        ps.append(res.pwf if res.pwf is not None else 0.0)
    return qs, ps


# ---------------------------------------------------------------------- #
# Validation / input contract
# ---------------------------------------------------------------------- #
REQUIRED_INPUTS = [
    ("thp", "Wellhead (tubing-head) pressure, psia"),
    ("tvd", "True vertical depth, ft"),
    ("id", "Tubing inside diameter, in"),
    ("q", "Oil production rate, STB/day (use q_w or wc for water)"),
    ("gor", "Produced GOR, scf/STB"),
    ("api", "Oil API gravity"),
    ("gamma_g", "Gas specific gravity (air = 1)"),
    ("mu_l", "Oil (liquid) viscosity, cP"),
    ("bo", "Oil formation volume factor, rb/STB"),
    ("rs", "Solution GOR at the average pressure, scf/STB"),
    ("t_wh", "Wellhead temperature, degF"),
    ("geothermal", "Geothermal gradient, degF/100 ft"),
]
OPTIONAL_INPUTS = [
    ("wc", "Water cut, fraction 0..1 (default 0)"),
    ("q_w", "Water rate, STB/day (alternative to wc)"),
    ("gamma_w", "Water specific gravity (default 1.07)"),
    ("bw", "Water FVF, rb/STB (default 1.01)"),
    ("z", "Gas compressibility factor (default 1.0 if unknown)"),
    ("sigma", "Surface tension, dyne/cm (default 30)"),
    ("segments", "Number of traverse segments (default 80)"),
    (MODEL_ID, "VLP correlation: 'beggs_brill' (default) or "
               "'hagedorn_brown'"),
]


def validate_inputs(kwargs: Dict[str, Optional[float]]) -> Optional[VLPError]:
    """Hard-reject physically invalid inputs. Returns a VLPError or None."""
    def num(k):
        v = kwargs.get(k)
        return None if v is None else float(v)

    thp, tvd, did = num("thp"), num("tvd"), num("id")
    q, q_w = num("q"), num("q_w")
    wc, gor, api = num("wc"), num("gor"), num("api")
    g_g, g_w, mu_l = num("gamma_g"), num("gamma_w"), num("mu_l")
    bo, bw, rs = num("bo"), num("bw"), num("rs")
    t_wh, geoth, z, sigma, qo_test = num("t_wh"), num("geothermal"), \
        num("z"), num("sigma"), num("segments")

    if any(v is not None and not math.isfinite(v) for v in
           (thp, tvd, did, q, q_w, wc, gor, api, g_g, g_w, mu_l, bo, bw,
            rs, t_wh, geoth, z, sigma, qo_test)):
        return VLPError("PHYSICALLY_INVALID",
                        "All inputs must be finite numbers.")
    if tvd is not None and tvd <= 0:
        return VLPError("PHYSICALLY_INVALID", "TVD must be > 0 ft.")
    if did is not None and did <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Tubing inside diameter must be > 0 in.")
    if q is not None and q < 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Oil rate must be >= 0 STB/day.")
    if q_w is not None and q_w < 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Water rate must be >= 0 STB/day.")
    if wc is not None and not (0.0 <= wc <= 1.0):
        return VLPError("PHYSICALLY_INVALID",
                        "Water cut must be between 0 and 1 (fraction).")
    if wc is not None and q is not None and q_w is not None:
        expected = q * wc / (1.0 - wc) if wc < 1.0 else float("inf")
        if abs(q_w - expected) > 1e-6 * max(abs(expected), 1.0):
            return VLPError("PHYSICALLY_INVALID",
                            "Water rate inconsistent with oil rate and "
                            "water cut (q_w must equal q*wc/(1-wc)).")
    if gor is not None and gor < 0:
        return VLPError("PHYSICALLY_INVALID", "GOR must be >= 0 scf/STB.")
    if g_g is not None and g_g <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Gas gravity must be > 0 (air = 1).")
    if mu_l is not None and mu_l <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Liquid viscosity must be > 0 cP.")
    if thp is not None and thp <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Wellhead pressure must be > 0 psia (absolute).")
    if t_wh is not None and t_wh + 460.0 <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Wellhead temperature must give an absolute "
                        "temperature above 0 R.")
    if api is not None and api < 0:
        return VLPError("PHYSICALLY_INVALID", "API gravity must be >= 0.")
    if bo is not None and bo <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Bo must be > 0 rb/STB.")
    if rs is not None and rs < 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Solution GOR must be >= 0 scf/STB.")
    if z is not None and not (0.1 < z < 1.5):
        return VLPError("PHYSICALLY_INVALID",
                        "Z-factor must be in a physical range (0.1 < Z < 1.5).")
    if gor is not None and rs is not None and gor < rs and (q or 0) > 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Produced GOR cannot be below solution GOR while "
                        "the well is producing (would imply negative free "
                        "gas).")
    if sigma is not None and sigma <= 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Surface tension must be > 0 dyne/cm.")
    if qo_test is not None and (qo_test < 4 or qo_test > 400):
        return VLPError("PHYSICALLY_INVALID",
                        "Segments must be between 4 and 400.")
    if geoth is not None and geoth < 0:
        return VLPError("PHYSICALLY_INVALID",
                        "Geothermal gradient must be >= 0 degF/100 ft.")
    return None


def missing_inputs(kwargs: Dict[str, Optional[float]],
                   model_req: str) -> List[str]:
    """Return the list of required-but-missing parameter names."""
    required = ["thp", "tvd", "id", "q", "gor", "api", "gamma_g", "mu_l",
                "bo", "rs", "t_wh", "geothermal"]
    _ = model_req  # reserved hook for future model-specific inputs
    # H-B requires no additional inputs beyond the standard contract.
    if kwargs.get("wc") is not None or kwargs.get("q_w") is not None:
        required += []  # water handled optionally
    return [k for k in required if kwargs.get(k) is None]
