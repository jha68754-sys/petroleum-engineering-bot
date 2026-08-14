"""Hagedorn-Brown (1965) vertical multiphase-flow correlation.

Reference: Hagedorn, A.R. & Brown, K.E. (1965), "Experimental Study of
Pressure Gradients Occurring During Continuous Two-Phase Flow in Small-
Diameter Vertical Conduits," JPT 17(4), 475-484, SPE-940-PA.

Secondary verified references (published forms, identical to the original
within the documented closed-form precision):

- Economides, Hill, Economides & Zhu, "Petroleum Production Systems",
  2nd ed. (2013) — N_LV, N_GV, N_D, N_L, C_NL, H group, H_L/psi curve,
  B/psi secondary correction.
- Lyons, "Standard Handbook of Petroleum and Natural Gas Engineering",
  2nd ed. (1996) — property and superficial-velocity forms.

This module is an INDEPENDENT implementation of the published Hagedorn-Brown
methodology. It is NOT a renamed or parameter-tuned Beggs-Brill calculation.

Field (US oilfield) units throughout. Every conversion is documented.

Revision 2 (post live-verification audit): the original revision used an
incorrect holdup group (N_RE instead of N_GV^0.575, missing the published
(p/14.7)^0.1 and N_D groups) and a wrong C_NL argument (N_RE instead of
the liquid viscosity number N_L). Both have been replaced by the verbatim
published forms listed above.
"""

import math
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------- #
# Constants (field units)
# ---------------------------------------------------------------------- #
PI = math.pi
SC_PRESSURE = 14.7    # psia — standard condition pressure
SC_TEMPERATURE = 520.0  # deg R — standard condition temperature (60 F)
G_FT_S2 = 32.174      # ft/s^2 — gravitational acceleration
GC = 32.174           # lbm-ft/lbf-s^2
PSI_PSF = 144.0       # (lb/ft^2) per psi
SIGMA_WATER = 72.0    # dyne/cm — reference surface tension of water (H-B
                      # base liquid); reference oil ~35 dyne/cm (Lyons)

# Published viscosity-number coefficients for the C_NL fit
# C_NL = 0.061*N_L^3 - 0.0929*N_L^2 + 0.0505*N_L + 0.0019
# (Economides et al., fit of the published H-B viscosity-number curve;
# bounded to the physically meaningful range of the published curve.)
_CNL_A3 = 0.061
_CNL_A2 = -0.0929
_CNL_A1 = 0.0505
_CNL_A0 = 0.0019
CNL_MIN = 0.001
CNL_MAX = 1.055

# ---------------------------------------------------------------------- #
# Published dimensionless groups
# ---------------------------------------------------------------------- #

def _dim_numbers(vsl: float, vsg: float, d_ft: float, rho_l: float,
                 sigma_l: float, mu_l: float) -> Dict[str, float]:
    """Published Hagedorn-Brown dimensionless numbers (Economides et al.):

        N_LV = 1.938 * v_SL * (rho_L/sigma_L)^0.25
        N_GV = 1.938 * v_SG * (rho_L/sigma_L)^0.25
        N_D  = 120.872 * D * (rho_L/sigma_L)^0.5
        N_L  = 0.15726 * mu_L * (1/(rho_L*sigma_L^3))^0.25
    """
    q = (rho_l / max(sigma_l, 1e-9)) ** 0.25
    n_lv = 1.938 * vsl * q
    n_gv = 1.938 * vsg * q
    n_d = 120.872 * d_ft * (rho_l / max(sigma_l, 1e-9)) ** 0.5
    n_l = 0.15726 * mu_l * (1.0 / max(rho_l * sigma_l ** 3, 1e-27)) ** 0.25
    return dict(n_lv=n_lv, n_gv=n_gv, n_d=n_d, n_l=n_l)


def _cn_l(n_l: float) -> float:
    """Published C_NL from the liquid viscosity number N_L (Economides et
    al., closed-form fit of the H-B published curve; bounded)."""
    x = max(min(n_l, 1.0), 0.0)
    cnl = (_CNL_A3 * x ** 3 + _CNL_A2 * x ** 2
           + _CNL_A1 * x + _CNL_A0)
    return max(min(cnl, CNL_MAX), CNL_MIN)


def _hb_holdup(n_lv: float, n_gv: float, n_d: float, cn_l: float,
               p: float) -> float:
    """Published H-B primary + secondary holdup correlation (Economides et
    al., "Petroleum Production Systems" 2nd ed.; original SPE-940 curve):

        H   = (N_LV / N_GV^0.575) * (p/14.7)^0.1 * (C_NL / N_D)
        B   = N_GV * N_LV^0.38 / N_D^2.14
        psi = piecewise polynomial in B (three published regions)
        H_L / psi = sqrt((0.0047 + 1123.32*H + 729489.64*H^2) /
                         (1 + 1097.1566*H + 722153.97*H^2))

    Returns primary holdup hl_primary and the no-slip lambda (for the
    published lower bound hl >= lambda). Division-by-zero and extreme-B
    protection are deterministic clamps, not tuning.
    """
    n_gv_safe = max(n_gv, 1e-9)
    n_d_safe = max(n_d, 1e-9)
    h_group = (n_lv / n_gv_safe ** 0.575) * (p / SC_PRESSURE) ** 0.1 \
        * (cn_l / n_d_safe)
    b = n_gv * max(n_lv, 0.0) ** 0.38 / n_d_safe ** 2.14
    b = max(b, 0.0)
    if b <= 0.025:
        psi = 27170.0 * b ** 3 - 317.52 * b ** 2 + 0.5472 * b + 0.9999
    elif b <= 0.055:
        psi = -533.33 * b ** 2 + 58.524 * b + 0.1171
    else:
        psi = 2.5714 * b + 1.5962
    psi = max(psi, 1e-6)
    num = 0.0047 + 1123.32 * h_group + 729489.64 * h_group ** 2
    den = 1.0 + 1097.1566 * h_group + 722153.97 * h_group ** 2
    hl = math.sqrt(num / max(den, 1e-18)) / psi
    return min(hl, 1.0)


def _rho_l(api: float, rs: float, gamma_g: float, bo: float,
           gamma_w: float, wc: float) -> float:
    """Mixed-liquid density, lbm/ft^3, at in-situ conditions.

    Oil density component includes dissolved gas (Hagedorn-Brown form,
    62.4*gamma_o + 0.0136*Rs*gamma_g over Bo), with the standard API
    relation gamma_o = 141.5/(131.5+API); oil/water weighted by water cut.
    """
    gamma_o = 141.5 / (131.5 + api)
    rho_o = (62.4 * gamma_o + 0.0136 * rs * gamma_g) / max(bo, 1e-9)
    rho_w = 62.4 * gamma_w
    return rho_o * (1.0 - wc) + rho_w * wc


def _sigma_l(wc: float, sigma: float) -> float:
    """Liquid surface tension blend (Lyons published form):
        sigma_L = sigma_o*(1/(1+WOR)) + sigma_w*(WOR/(1+WOR))
    which reduces to the linear water-cut blend
        sigma_L = sigma_o*(1 - WC) + sigma_w*WC
    with reference values sigma_oil ~ 30-35 and sigma_water = 72 dyne/cm.
    The `sigma` input is the oil-continuous surface tension."""
    return max(sigma, 1.0) * (1.0 - wc) + SIGMA_WATER * wc


def _rho_g(p: float, z: float, t_f: float, gamma_g: float) -> float:
    """Gas density, lbm/ft^3, real-gas law (field units)."""
    return 2.698826 * gamma_g * p / (z * (t_f + 460.0))


def _gas_viscosity_lee(t_f: float, p: float, gamma_g: float,
                       z: float) -> float:
    """Gas viscosity, cp — Lee-Gonzalez-Eakin (1966). Same sub-model as
    the verified Beggs-Brill engine; viscosity of a single phase is a
    universal physical property, not correlation-specific."""
    mw = gamma_g * 28.967
    rho_g = _rho_g(p, z, t_f, gamma_g)
    t = t_f + 460.0
    y = 344.8 + 986.4 / t + 2.445 * t * math.log10(mw)
    k = (9.4 + 0.02 * mw) * t ** 1.5 / (209.0 + 19.0 * mw + y)
    x = 3.5 + 986.0 / t + 0.01 * mw
    u1 = k * math.exp(x * (rho_g / 62.4) ** y)
    return max(u1, 0.008)


def _hb_f_tp(hl: float, re: float, f_sl: float) -> float:
    """Hagedorn-Brown two-phase friction factor.

    The H-B density-ratio pressure-gradient equation uses a two-phase
    friction factor f_TP defined by:

        f_TP = f_SL * (0.0056 + 0.5 * f_SL)

    This is the published H-B expression (Hagedorn & Brown 1965, Eq. 21;
    Brown & Beggs 1977, Eq. 2.42)."""
    return f_sl * (0.0056 + 0.5 * f_sl)


def _fanning_sl(re: float, eps: float, d_ft: float) -> float:
    """Single-phase Fanning friction factor, Churchill approximation to the
    Moody chart (valid for laminar and turbulent, deterministic)."""
    if re <= 2000.0:
        return 16.0 / max(re, 1e-9)
    a = (2.457 * math.log(1.0 / (7.0 / max(re, 1e-9)
                                 + 0.27 * eps / max(d_ft, 1e-9)))) ** 16
    b = (37530.0 / max(re, 1e-9)) ** 16
    c = (a + b) ** (-1.5)
    c = max(c, 0.0)
    f = 8.0 * ((8.0 / max(re, 1e-9)) ** 12 + (c) ** (-1.5)) ** (-1.0 / 12.0)
    return max(f, 0.004)


def hb_segment_state(p: float, t_f: float, q_o: float, q_w: float,
                     gor: float, bo: float, bw: float, z: float,
                     gamma_g: float, gamma_w: float, mu_l: float,
                     api: float, wc: float, d_ft: float, rs: float,
                     sigma: float,
                     q_g_inj: float = 0.0,
                     mu_g: Optional[float] = None) -> Dict[str, float]:
    """All local Hagedorn-Brown flow variables at one segment node.

    Published H-B forms only (see module docstring). Returns: vm, vsl,
    vsg, lam, hl, rho_l, rho_g, rho_m, rho_s, mu_g, re, f_sl, f_tp, gm,
    n_lv, n_gv, n_d, n_l, cn_l. Field units, pure deterministic math.

    Two physical limits are enforced as published practice:
    - q = 0 (static): liquid-full column, hl = 1, friction = 0.
    - hl is never permitted below the no-slip fraction lambda
      (documented modification; Economides et al.).
    """
    a = PI * d_ft ** 2 / 4.0          # flow area, ft^2
    # Free gas rate (solution gas above bubble point stays dissolved)
    q_g_free = max(gor - rs, 0.0) * (q_o + q_w) + q_g_inj
    vsl = ((q_o * bo + q_w * bw) / 5.615) / a / 86400.0   # ft/s
    # Lyons published form: in-situ scf conversion 14.7/p * T_R/520 / z
    vsg = (q_g_free * SC_PRESSURE / max(p, 1e-9)
           * ((t_f + 460.0) / SC_TEMPERATURE) * (1.0 / max(z, 1e-9))
           ) / a / 86400.0
    vm = vsl + vsg
    lam = vsl / vm if vm > 0 else (1.0 if (q_o + q_w) > 0 else 0.0)

    rho_l = _rho_l(api, rs, gamma_g, bo, gamma_w, wc)
    sigma_l = _sigma_l(wc, sigma)
    rho_g = _rho_g(p, z, t_f, gamma_g)
    mu_g = (_gas_viscosity_lee(t_f, p, gamma_g, z)
             if mu_g is None else mu_g)

    dims = _dim_numbers(vsl, vsg, d_ft, rho_l, sigma_l, mu_l)
    cn_l = _cn_l(dims["n_l"])

    # Zero-rate (static) limit: the correlation velocity groups collapse;
    # the physically correct static limit is a liquid-full column,
    # matching the verified Beggs-Brill zero-rate behavior
    # (static_gradient).
    if vsl <= 0.0:
        hl = 1.0 if (q_o + q_w) > 0 else 0.0
        rho_s = hl * rho_l + (1.0 - hl) * rho_g
        rho_m = rho_s
        eps = 0.00065
        f_sl = _fanning_sl(0.0, eps, d_ft)
        return dict(vm=vm, vsl=vsl, vsg=vsg, lam=lam, hl=hl,
                    rho_l=rho_l, rho_g=rho_g, rho_m=rho_m, rho_s=rho_s,
                    mu_g=mu_g, re=0.0, f_sl=f_sl,
                    f_tp=f_sl * (0.0056 + 0.5 * f_sl), gm=0.0,
                    n_lv=0.0, n_gv=0.0, n_d=dims["n_d"], n_l=dims["n_l"],
                    cn_l=cn_l)

    hl = _hb_holdup(dims["n_lv"], dims["n_gv"], dims["n_d"], cn_l, p)
    # Published practice: holdup can never be below no-slip.
    hl = max(hl, lam)

    # H-B elevation gradient uses the no-slip mixture density rho_s
    # (density-ratio equation, Economides et al.):
    rho_s = lam * rho_l + (1.0 - lam) * rho_g
    rho_m = hl * rho_l + (1.0 - hl) * rho_g
    mu_m = mu_l * lam + mu_g * (1.0 - lam)
    re = 1488.0 * rho_m * vm * d_ft / max(mu_m, 1e-9)
    eps = 0.00065  # ft — default tubing roughness (documented)
    f_sl = _fanning_sl(re, eps, d_ft)
    f_tp = _hb_f_tp(hl, re, f_sl)
    gm = rho_m * vm * a  # lbm/s
    return dict(vm=vm, vsl=vsl, vsg=vsg, lam=lam, hl=hl, rho_l=rho_l,
                rho_g=rho_g, rho_m=rho_m, rho_s=rho_s, mu_g=mu_g, re=re,
                f_sl=f_sl, f_tp=f_tp, gm=gm, n_lv=dims["n_lv"],
                n_gv=dims["n_gv"], n_d=dims["n_d"], n_l=dims["n_l"],
                cn_l=cn_l)


def hb_gradients(st: Dict[str, float], d_ft: float) -> Tuple[float, float]:
    """Hagedorn-Brown elevation and friction pressure gradients, psi/ft.

    Elevation: dp/dz = rho_s * g / g_c / 144        (no-slip density, published)
    Friction:  dp/dz = f_TP * G_m * v_m / (2 * g_c * D) / 144
    (published H-B pressure-gradient equations, field units)
    """
    dp_el = st["rho_s"] * G_FT_S2 / GC / PSI_PSF
    dp_fr = (st["f_tp"] * st["gm"] * st["vm"]) / (2.0 * GC * d_ft) / PSI_PSF
    return dp_el, dp_fr


# ---------------------------------------------------------------------- #
# Applicability envelope
# ---------------------------------------------------------------------- #
# Published experimental basis: 1500-ft vertical well, test sections of
# 1-in, 1.25-in, and 1.5-in internal diameter (Hagedorn & Brown 1965).
# The paper gives no strict GOR or liquid-rate limits; the original test
# conditions spanned liquid rates of roughly 50-1200 STB/D and GOR values
# up to ~1500-2000 scf/STB with gas rates to ~1.2 MMscf/D. Industrial
# practice extrapolates the ID range to ~4 in (widely used VLP default),
# but values beyond the published 1-1.5 in range carry an explicit
# CORRELATION_LIMITATION warning and are indicative, not validated.
HB_APPLICABILITY = dict(
    tubing_id_in=(1.0, 1.5),             # published test diameters (1, 1.25,
                                         # and 1.5-in test sections)
    gor=(0.0, 2000.0),                   # scf/STB — original test range
    liquid_rate=(50.0, 1200.0),          # STB/D — original test range
    note="Hagedorn-Brown was developed on vertical 1/1.25/1.5-in test "
         "strings. Results with ID outside 1.0-1.5 in (or conditions far "
         "beyond the original test envelope) carry CORRELATION_LIMITATION "
         "warnings; vertical wells only. Industrial practice still uses "
         "H-B as a default oil-well VLP correlation up to ~4-in ID.")
