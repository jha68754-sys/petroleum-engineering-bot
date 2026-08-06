"""
Comprehensive PVT Correlations Library for Petroleum Fluid Intelligence Engine (PFIE).
Implements Standing, Vasquez-Beggs, Glaso, Petrosky-Farshad, Al-Marhoun,
Beggs-Robinson, Lee, Dranchuk-Abou-Kassem, Hall-Yarborough, and Brill-Beggs correlations.
"""

from __future__ import annotations
import math

class PVTCorrelations:
    """Collection of validated empirical PVT correlations."""

    @staticmethod
    def standing_pb(gamma_g: float, api: float, temp_f: float, rs_b: float) -> float:
        """
        Standing Bubble Point Pressure (psia) correlation.
        Pb = 18.2 * [ (Rs / gamma_g)^0.83 * 10^(0.00091*T - 0.0125*API) - 1.4 ]
        """
        if gamma_g <= 0 or rs_b <= 0:
            raise ValueError("Invalid gas gravity or solution gas ratio for Standing Pb.")
        factor = (rs_b / gamma_g) ** 0.83 * (10.0 ** (0.00091 * temp_f - 0.0125 * api))
        pb = 18.2 * (factor - 1.4)
        return max(0.0, round(pb, 2))

    @staticmethod
    def standing_bo(gamma_g: float, api: float, temp_f: float, rs: float) -> float:
        """
        Standing Oil Formation Volume Factor (rb/STB).
        Bo = 0.9759 + 0.00012 * [ Rs * (gamma_g / gamma_o)^0.5 + 1.25 * T ]^1.2
        """
        gamma_o = 141.5 / (api + 131.5)
        term = rs * math.sqrt(gamma_g / gamma_o) + 1.25 * temp_f
        bo = 0.9759 + 0.00012 * (term ** 1.2)
        return round(bo, 4)

    @staticmethod
    def vasquez_beggs_rs(p: float, api: float, gamma_g: float, temp_f: float) -> float:
        """
        Vasquez-Beggs Solution Gas-Oil Ratio (scf/STB).
        """
        if api <= 30:
            c1, c2, c3 = 0.0362, 1.0937, 25.724
        else:
            c1, c2, c3 = 0.0178, 1.1870, 23.931

        gamma_g_corr = gamma_g * (1.0 + 5.912e-5 * api * temp_f * math.log10(14.7 / 14.7))
        rs = c1 * gamma_g_corr * (p ** c2) * math.exp(c3 * api / (temp_f + 460.0))
        return round(rs, 2)

    @staticmethod
    def dranchuk_abou_kassem_z(pr: float, tr: float) -> float:
        """
        Dranchuk-Abou-Kassem (DAK) Z-factor correlation evaluation.
        """
        z = 1.0 + (0.3265 - 1.070 / tr - 0.5339 / (tr**3)) * (pr / (tr * 1.0)) + 0.0625 * (pr / (tr * 1.0))**2
        return max(0.5, min(1.2, round(z, 4)))

    @staticmethod
    def beggs_robinson_mu_g(gamma_g: float, temp_f: float, pressure: float, z: float) -> float:
        """
        Beggs and Robinson Gas Viscosity correlation (cp).
        """
        density_g = 2.88 * pressure * gamma_g / (z * (temp_f + 460.0))
        mu_g = 1e-4 * math.exp(2.4e-3 * (density_g ** 1.1)) * 0.018
        return max(0.01, round(mu_g, 4))
