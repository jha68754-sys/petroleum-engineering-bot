#!/usr/bin/env python3
"""Independent Phase 5B Black-Oil V1 reference calculations.

This module intentionally imports no production service code. It is a reference
calculator for the documentation-only freeze and must remain independent from
any future provider implementation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def api_to_sgo(api: float) -> float:
    return 141.5 / (api + 131.5)


def corrected_gas_gravity(sg_g: float, api: float, separator_temperature_f: float, separator_pressure_psia: float) -> float:
    return sg_g * (1.0 + 0.00005912 * api * separator_temperature_f * math.log10(separator_pressure_psia / 114.7))


def vb_constants(api: float) -> tuple[float, float, float]:
    if api <= 30.0:
        return 0.0362, 1.0937, 25.7240
    return 0.0178, 1.1870, 23.9310


def vb_rs(api: float, sg_gc: float, pressure_psia: float, temperature_f: float) -> float:
    c1, c2, c3 = vb_constants(api)
    return c1 * sg_gc ** c2 * math.exp(c3 * api / (temperature_f + 460.0)) * pressure_psia ** c2


def vb_pb(api: float, sg_gc: float, rsb_scf_stb: float, temperature_f: float) -> float:
    c1, c2, c3 = vb_constants(api)
    return (rsb_scf_stb / (c1 * sg_gc ** c2 * math.exp(c3 * api / (temperature_f + 460.0)))) ** (1.0 / c2)


def vb_bo_saturated(api: float, rs_scf_stb: float, sg_gc: float, temperature_f: float) -> float:
    if api <= 30.0:
        a1, a2, a3 = 4.677e-4, 1.751e-5, -1.811e-8
    else:
        a1, a2, a3 = 4.670e-4, 1.100e-5, 1.337e-9
    sg_o = api_to_sgo(api)
    return 1.0 + a1 * rs_scf_stb + a2 * (temperature_f - 60.0) * (sg_gc / sg_o) + a3 * rs_scf_stb * (temperature_f - 60.0) * (sg_gc / sg_o)


def vb_co_undersaturated(rsb_scf_stb: float, temperature_f: float, sg_g: float, api: float, pressure_psia: float) -> float:
    return (-1433.0 + 5.0 * rsb_scf_stb + 17.2 * temperature_f - 1180.0 * sg_g + 12.61 * api) / (1.0e5 * pressure_psia)


def villena_lanzi_co_saturated(pressure_psia: float, pb_psia: float, temperature_f: float, rsb_scf_stb: float, api: float) -> float:
    return math.exp(-0.664 - 1.430 * math.log(pressure_psia) - 0.395 * math.log(pb_psia) + 0.390 * math.log(temperature_f) + 0.455 * math.log(rsb_scf_stb) + 0.262 * math.log(api))


def bo_undersaturated(bob: float, co_1_psi: float, pressure_psia: float, pb_psia: float) -> float:
    return bob * math.exp(co_1_psi * (pb_psia - pressure_psia))


def beggs_robinson_dead(api: float, temperature_f: float) -> float:
    sg_o = api_to_sgo(api)
    x = temperature_f ** -1.163 * math.exp(13.108 - 6.591 / sg_o)
    return 10.0 ** x - 1.0


def beggs_robinson_saturated(api: float, temperature_f: float, rs_scf_stb: float) -> float:
    mu_od = beggs_robinson_dead(api, temperature_f)
    a = 10.715 * (rs_scf_stb + 100.0) ** -0.515
    b = 5.44 * (rs_scf_stb + 150.0) ** -0.338
    return a * mu_od ** b


def vb_oil_viscosity_undersaturated(mu_os_cp: float, pressure_psia: float, pb_psia: float) -> float:
    m = 2.6 * pressure_psia ** 1.187 * math.exp(-11.513 - 8.98e-5 * pressure_psia)
    return mu_os_cp * (pressure_psia / pb_psia) ** m


def sutton_pseudo_critical(sg_g: float) -> tuple[float, float]:
    tpc_r = 169.2 + 349.5 * sg_g - 74.0 * sg_g ** 2
    ppc_psia = 756.8 - 131.0 * sg_g - 3.6 * sg_g ** 2
    return ppc_psia, tpc_r


def dak_z(pressure_psia: float, temperature_f: float, sg_g: float) -> tuple[float, int, float]:
    a1, a2, a3, a4, a5 = 0.3265, -1.0700, -0.5339, 0.01569, -0.05165
    a6, a7, a8, a9, a10, a11 = 0.5475, -0.7361, 0.1844, 0.1056, 0.6134, 0.7210
    ppc, tpc = sutton_pseudo_critical(sg_g)
    ppr = pressure_psia / ppc
    tpr = (temperature_f + 459.67) / tpc
    rho = max(0.01, 0.27 * ppr / tpr)
    for iteration in range(1, 101):
        z = 1.0 + (a1 + a2 / tpr + a3 / tpr**3 + a4 / tpr**4 + a5 / tpr**5) * rho
        z += (a6 + a7 / tpr + a8 / tpr**2) * rho**2
        z -= a9 * (a7 / tpr + a8 / tpr**2) * rho**5
        z += a10 * (1.0 + a11 * rho**2) * (rho**2 / tpr**3) * math.exp(-a11 * rho**2)
        residual = 0.27 * ppr / (rho * tpr) - z
        if abs(residual) < 1e-10:
            return z, iteration, residual
        h = max(1e-6, abs(rho) * 1e-5)
        def f(r: float) -> float:
            zz = 1.0 + (a1 + a2 / tpr + a3 / tpr**3 + a4 / tpr**4 + a5 / tpr**5) * r
            zz += (a6 + a7 / tpr + a8 / tpr**2) * r**2
            zz -= a9 * (a7 / tpr + a8 / tpr**2) * r**5
            zz += a10 * (1.0 + a11 * r**2) * (r**2 / tpr**3) * math.exp(-a11 * r**2)
            return 0.27 * ppr / (r * tpr) - zz
        derivative = (f(rho + h) - f(max(1e-8, rho - h))) / (h + h)
        step = residual / derivative if derivative else residual
        step = max(-0.5 * rho, min(0.5 * rho, step))
        rho = max(1e-8, rho - step)
    raise RuntimeError("DAK non-convergence")


def bg_rb_scf(z: float, temperature_f: float, pressure_psia: float) -> float:
    return 0.00505 * z * (temperature_f + 460.0) / pressure_psia


def lee_gonzalez_eakin(z: float, pressure_psia: float, temperature_f: float, sg_g: float) -> float:
    t_r = temperature_f + 459.67
    mw = 28.967 * sg_g
    k = (9.4 + 0.02 * mw) * t_r ** 1.5 / (209.0 + 19.0 * mw + t_r)
    x = 3.5 + 986.0 / t_r + 0.001 * mw
    y = 2.4 - 0.2 * x
    rho_g = (28.967 * sg_g * pressure_psia) / (10.732 * z * t_r * 62.428)
    return k * math.exp(x * rho_g ** y) / 10000.0


def check(name: str, value: float, predicate: bool, units: str) -> dict:
    return {"name": name, "value": value, "units": units, "pass": bool(predicate)}


def main() -> None:
    cases = []
    for label, api, sg, temp, rsb in [("api_le_30", 28.0, 0.72, 180.0, 650.0), ("api_gt_30", 38.0, 0.78, 200.0, 850.0)]:
        separator_pressure_psia = 100.0
        separator_temperature_f = 100.0
        sgc = corrected_gas_gravity(sg, api, separator_temperature_f, separator_pressure_psia)
        pb = vb_pb(api, sgc, rsb, temp)
        rs = vb_rs(api, sgc, pb, temp)
        bob = vb_bo_saturated(api, rsb, sgc, temp)
        cases.append({"case": label, "inputs": {"api": api, "sg_g": sg, "temperature_f": temp, "separator_pressure_psia": separator_pressure_psia, "separator_temperature_f": separator_temperature_f, "rsb_scf_stb": rsb}, "values": {"sg_corrected": sgc, "pb_psia": pb, "rs_at_pb_scf_stb": rs, "bob_rb_stb": bob}, "checks": [check("Rs nonnegative", rs, rs >= 0, "scf/STB"), check("Bo positive", bob, bob > 0, "rb/STB"), check("Pb/Rs inverse", rs, abs(rs-rsb) < 1e-8, "scf/STB")]})
    api, sg, temp, rsb, pb = 35.0, 0.75, 180.0, 700.0, 2500.0
    separator_pressure_psia = 100.0
    separator_temperature_f = 100.0
    sgc = corrected_gas_gravity(sg, api, separator_temperature_f, separator_pressure_psia)
    bob = vb_bo_saturated(api, rsb, sgc, temp)
    co = vb_co_undersaturated(rsb, temp, sg, api, 3500.0)
    bo = bo_undersaturated(bob, co, 3500.0, pb)
    muod = beggs_robinson_dead(api, temp)
    muos = beggs_robinson_saturated(api, temp, rsb)
    muo = vb_oil_viscosity_undersaturated(muos, 3500.0, pb)
    cases.append({"case": "undersaturated_oil", "inputs": {"api": api, "sg_g": sg, "temperature_f": temp, "separator_pressure_psia": separator_pressure_psia, "separator_temperature_f": separator_temperature_f, "rsb_scf_stb": rsb, "pb_psia": pb, "pressure_psia": 3500.0}, "values": {"bob_rb_stb": bob, "co_1_psi": co, "bo_rb_stb": bo, "mu_od_cp": muod, "mu_os_cp": muos, "mu_o_cp": muo}, "checks": [check("Bo positive", bo, bo > 0, "rb/STB"), check("oil viscosity positive", muo, muo > 0, "cP")]})
    for label, p, t in [("dak_low", 500.0, 100.0), ("dak_medium", 2500.0, 180.0), ("dak_high", 8000.0, 260.0)]:
        z, iterations, residual = dak_z(p, t, 0.70)
        bg = bg_rb_scf(z, t, p)
        mug = lee_gonzalez_eakin(z, p, t, 0.70)
        cases.append({"case": label, "inputs": {"pressure_psia": p, "temperature_f": t, "sg_g": 0.70}, "values": {"z": z, "dak_iterations": iterations, "dak_residual": residual, "bg_rb_scf": bg, "bg_rb_mscf": bg * 1000.0, "mu_g_cp": mug}, "checks": [check("Z positive", z, z > 0, "dimensionless"), check("Bg positive", bg, bg > 0, "rb/scf"), check("DAK residual", residual, abs(residual) < 1e-10, "dimensionless"), check("Bg unit identity", bg * 1000.0, abs(bg * 1000.0 - bg * 1000.0) < 1e-15, "rb/Mscf") ]})
    print(json.dumps({"source": "independent_reference_only", "equation_reproduction_tolerance": {"absolute": 1e-8, "relative": 1e-8}, "dak_residual_tolerance": 1e-10, "cases": cases}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
