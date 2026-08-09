"""
Production Engineering IPR Engine (Phase 1: IPR only).

Deterministic inflow performance relationship calculations for the live
Telegram bot. Generates all numerical values; the AI layer only interprets.

Models implemented (each documented with equation, reference, assumptions,
units, and applicability):

1. LINEAR IPR (undersaturated, single-phase liquid inflow)
   Equation: q = J * (Pr - Pwf)      and      J = q / (Pr - Pwf)
   Applicable: Pwf >= Pb (single liquid phase; Darcy radial steady-state).
   Reference: Craft & Hawkins, Applied Petroleum Reservoir Engineering;
   Tiab & Donaldson, Petrophysics.
   Units: q [STB/day], Pr/Pwf [psia], J [STB/day/psi].

2. VOGEL IPR (saturated-oil, solution-gas drive)
   Equation: q/qmax = 1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2
   Reference: Vogel, J.V., "Inflow Performance Relationships for
   Solution-Gas Drive Wells", JPT (Jan 1968), pp. 83-92.
   Assumptions: steady-state, solution-gas drive, constant Pr,
   no skin/inflow efficiency effect beyond the calibration test point,
   liquid viscosity ratio effects neglected (Fe = 1).
   Applicability: Pr <= Pb (saturated reservoir). Empirical correlation -
   results are calculated/correlation-based, NOT measured data.
   Units: q, qmax [STB/day], Pr/Pwf [psia].

3. VOGEL QMAX INVERSION (calibration from a single measured test point)
   Equation: qmax = q_test / [1 - 0.2*(Pwf_test/Pr) - 0.8*(Pwf_test/Pr)^2]
   Reference: same as Vogel (1968); standard back-calculation used in
   well-test analysis (Brown, The Technology of Artificial Lift, Vol. 1).
   Requires a valid test point with 0 <= Pwf_test < Pr and q_test > 0.

4. COMPOSITE IPR (undersaturated reservoir, Pr > Pb, inflow path crosses Pb)
   Segment 1 (Pb <= Pwf <= Pr), linear:
       q = J* * (Pr - Pwf)        where J* = q_test / (Pr - Pwf_test)
   Segment 2 (0 <= Pwf < Pb), Vogel-shaped anchored at Pb:
       q = qb + (qo_max - qb) * [1 - 0.2*(Pwf/Pb) - 0.8*(Pwf/Pb)^2]
       qb       = J* * (Pr - Pb)
       qo_max   = qb + (qb * Pb) / (1.8 * (Pr - Pb))
   Reference: Brown, K.E., The Technology of Artificial Lift Methods,
   Vol. 1, Ch. 5; Beggs, H.D., Production Optimization Using Nodal
   Analysis, Ch. 3; Fetkovich, M.J., "The Isochronal Testing of Oil
   Wells", SPE 4529 (1973).
   Continuity: C1-continuous at Pwf = Pb (value AND slope match:
   dq/dPwf = -J* on both sides at Pb).
   Units: all pressures [psia], rates [STB/day].

Engineering guardrails (hard-reject rules):
- PHYSICALLY INVALID:   Pr <= 0, Pb <= 0 (when required), Pwf < 0,
  Pwf > Pr, q_test <= 0, J <= 0, qmax <= 0, model denominator <= 0.
- INSUFFICIENT DATA:    required inputs missing -> clean data-requirement
  message with units; NEVER invent values or return numbers.
- OUTSIDE ASSUMPTIONS:  linear model requested below Pb; Vogel requested
  with Pr > Pb without composite fallback -> clear assumption warning.

Automatic model selection (deterministic, never delegated to the LLM):
- CASE A: Pr <= Pb                    -> Vogel (saturated)
- CASE B: Pr > Pb and Pwf >= Pb       -> Linear (undersaturated)
- CASE C: Pr > Pb and Pwf < Pb        -> Composite (crosses bubble point)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_MODEL_VOGEL = "vogel"
_MODEL_LINEAR = "linear"
_MODEL_COMPOSITE = "composite"

# Human-readable display names for model names and plot labels
MODEL_DISPLAY = {
    _MODEL_VOGEL: "Vogel IPR",
    _MODEL_LINEAR: "Linear PI (Darcy inflow)",
    _MODEL_COMPOSITE: "Composite IPR (linear above Pb + Vogel below Pb)",
}

_PSB = "Pressure must be in psia (psi); rates in STB/day; J in STB/day/psi."


@dataclass
class IPRError:
    """Structured input-validation outcome."""
    kind: str          # "PHYSICALLY_INVALID" | "INSUFFICIENT_DATA" | "OUTSIDE_ASSUMPTIONS"
    message: str


class IPREngine:
    """Deterministic IPR calculation engine. Pure math; no Telegram dependency."""

    # -------------------------------------------------------------- #
    # 1. VOGEL IPR
    # -------------------------------------------------------------- #
    @staticmethod
    def _vogel_factor(pr: float, pwf: float) -> float:
        """Dimensionless Vogel inflow factor q/qmax at given pressures."""
        r = pwf / pr
        return 1.0 - 0.2 * r - 0.8 * r * r

    def vogel_q(self, pr: float, qmax: float, pwf: float) -> float:
        """Vogel IPR: q at Pwf given Pr and qmax (Vogel 1968)."""
        if pr <= 0:
            raise ValueError("PHYSICALLY_INVALID: Reservoir pressure Pr must be > 0 psia.")
        if qmax <= 0:
            raise ValueError("PHYSICALLY_INVALID: Maximum rate qmax must be > 0 STB/day.")
        if pwf < 0:
            raise ValueError("PHYSICALLY_INVALID: Flowing pressure Pwf must be >= 0 psia.")
        if pwf > pr:
            raise ValueError("PHYSICALLY_INVALID: Pwf cannot exceed Pr for a producing well.")
        if pwf >= pr:
            return 0.0
        return round(qmax * self._vogel_factor(pr, pwf), 1)

    # -------------------------------------------------------------- #
    # 2. VOGEL QMAX INVERSION (test point calibration)
    # -------------------------------------------------------------- #
    def vogel_qmax_from_test(self, pr: float, pwf_test: float, q_test: float) -> float:
        """Back-calculate qmax from one measured test point (Brown, TAL Vol.1)."""
        if pr <= 0:
            raise ValueError("PHYSICALLY_INVALID: Pr must be > 0 psia.")
        if q_test <= 0:
            raise ValueError("PHYSICALLY_INVALID: Test rate q_test must be > 0 STB/day.")
        if pwf_test < 0:
            raise ValueError("PHYSICALLY_INVALID: Test pressure Pwf_test must be >= 0 psia.")
        if pwf_test >= pr:
            raise ValueError(
                "PHYSICALLY_INVALID: Test point must be below Pr "
                "(Pwf_test < Pr) to calibrate qmax; at Pwf = Pr no inflow occurs."
            )
        denom = self._vogel_factor(pr, pwf_test)
        if denom <= 0:
            raise ValueError(
                "PHYSICALLY_INVALID: Test point yields zero/negative Vogel factor; "
                "check Pr and Pwf_test."
            )
        return round(q_test / denom, 1)

    # -------------------------------------------------------------- #
    # 3. LINEAR IPR
    # -------------------------------------------------------------- #
    @staticmethod
    def linear_j(q: float, pr: float, pwf: float) -> float:
        """Productivity index from a test point (single-phase Darcy inflow)."""
        if pr <= 0:
            raise ValueError("PHYSICALLY_INVALID: Pr must be > 0 psia.")
        if q <= 0:
            raise ValueError("PHYSICALLY_INVALID: Rate q must be > 0 STB/day.")
        if pwf < 0 or pwf >= pr:
            raise ValueError(
                "PHYSICALLY_INVALID: For a producing well 0 <= Pwf < Pr is required."
            )
        return round(q / (pr - pwf), 3)

    def linear_q(self, pr: float, j: float, pwf: float) -> float:
        """Linear IPR: q = J * (Pr - Pwf), valid for Pwf >= Pb only."""
        if pr <= 0:
            raise ValueError("PHYSICALLY_INVALID: Pr must be > 0 psia.")
        if j <= 0:
            raise ValueError("PHYSICALLY_INVALID: Productivity index J must be > 0 STB/day/psi.")
        if pwf < 0:
            raise ValueError("PHYSICALLY_INVALID: Pwf must be >= 0 psia.")
        if pwf > pr:
            raise ValueError("PHYSICALLY_INVALID: Pwf cannot exceed Pr for a producing well.")
        if pwf >= pr:
            return 0.0
        return round(j * (pr - pwf), 1)

    # -------------------------------------------------------------- #
    # 4. COMPOSITE IPR (Pr > Pb, inflow crosses bubble point)
    # -------------------------------------------------------------- #
    def composite_segments(self, pr: float, pb: float, j_star: float) -> Tuple[float, float]:
        """Return (qb, qo_max) for the composite IPR anchored by straight-line slope J*.

        J* comes from a test point (q_test, pwf_test) above Pb:
            J* = q_test / (Pr - Pwf_test)
        Segment 1 (Pb <= Pwf <= Pr): q = J* (Pr - Pwf)
        Segment 2 (0 <= Pwf < Pb):   q = qb + (qo_max - qb)[1 - 0.2(Pwf/Pb) - 0.8(Pwf/Pb)^2]
        Continuity at Pwf = Pb is C1 by construction (Brown TAL Vol.1; Beggs; Fetkovich 1973).
        """
        if pb is None:
            raise ValueError("INSUFFICIENT_DATA: Bubble-point pressure Pb is required for Composite IPR.")
        if pb <= 0:
            raise ValueError("PHYSICALLY_INVALID: Bubble-point pressure Pb must be > 0 psia.")
        if pb >= pr:
            raise ValueError(
                "OUTSIDE_ASSUMPTIONS: Composite IPR requires Pr > Pb. "
                "Use Vogel IPR for a saturated reservoir (Pr <= Pb)."
            )
        if j_star <= 0:
            raise ValueError("PHYSICALLY_INVALID: J* (straight-line slope) must be > 0 STB/day/psi.")
        qb = j_star * (pr - pb)
        qo_max = qb + (qb * pb) / (1.8 * (pr - pb))
        return round(qb, 1), round(qo_max, 1)

    def composite_q(self, pr: float, pb: float, j_star: float, pwf: float) -> float:
        """Composite IPR rate at Pwf (Pr > Pb assumed by caller via model selection)."""
        qb, qo_max = self.composite_segments(pr, pb, j_star)
        if pwf >= pr:
            return 0.0
        if pwf >= pb:
            return round(j_star * (pr - pwf), 1)
        # Below Pb: Vogel-shaped curve anchored at qb, extending to qo_max at Pwf = 0
        return round(qb + (qo_max - qb) * self._vogel_factor(pb, pwf), 1)

    # -------------------------------------------------------------- #
    # 5. AUTOMATIC MODEL SELECTION (deterministic rules)
    # -------------------------------------------------------------- #
    def select_model(
        self,
        pr: float,
        pb: Optional[float],
        pwf: Optional[float],
    ) -> Tuple[str, str]:
        """Return (model, reason) per deterministic selection rules.

        CASE A: Pr <= Pb            -> Vogel
        CASE B: Pr > Pb, Pwf >= Pb  -> Linear
        CASE C: Pr > Pb, Pwf < Pb   -> Composite
        """
        if pb is not None:
            if pr <= pb:
                return _MODEL_VOGEL, (
                    "Pr is at or below Pb, so the reservoir behaves as a "
                    "saturated system: Vogel IPR applies over the whole curve."
                )
            if pwf is None:
                return _MODEL_COMPOSITE, (
                    "Pr is above Pb. A full IPR curve will cross the bubble point, "
                    "so the Composite IPR (linear above Pb, Vogel below Pb) is used."
                )
            if pwf >= pb:
                return _MODEL_LINEAR, (
                    "Pr is above Pb and the requested Pwf is also at or above Pb, "
                    "so inflow stays in the single-phase (undersaturated) regime: "
                    "linear PI applies."
                )
            return _MODEL_COMPOSITE, (
                "Pr is above Pb while requested Pwf is below Pb, so the inflow "
                "path crosses the bubble-point pressure: Composite IPR applies "
                "(linear above Pb, Vogel below Pb)."
            )
        if pwf is None:
            return _MODEL_VOGEL, (
                "No bubble-point pressure given: the requested point is below Pr, "
                "so Vogel IPR (saturated-oil treatment) is used. "
                "WARNING: providing Pb enables accurate Composite IPR selection "
                "when the reservoir is undersaturated."
            )
        if pr <= pwf:
            raise ValueError("PHYSICALLY_INVALID: Pwf cannot exceed Pr for a producing well.")
        return _MODEL_LINEAR, (
            "No bubble-point pressure given and Pwf < Pr: linear PI is applied "
            "assuming single-phase inflow. WARNING: provide Pb for rigorous "
            "model selection when the reservoir may be undersaturated."
        )

    # -------------------------------------------------------------- #
    # 6. CURVE GENERATION (engine output points, no LLM arithmetic)
    # -------------------------------------------------------------- #
    @staticmethod
    def _curve_pressures(pr: float, n_points: int = 10,
                         include_pb: bool = False, pb: Optional[float] = None) -> List[float]:
        pts = [round(pr - pr * i / (n_points - 1), 1) for i in range(n_points)]
        if include_pb and pb is not None and 0 <= pb <= pr:
            if not any(abs(p - pb) < 0.5 for p in pts):
                pts.append(round(pb, 1))
        pts = sorted(set(pts), reverse=True)
        return pts

    def build_curve(
        self,
        model: str,
        pr: float,
        pwf: Optional[float] = None,
        pb: Optional[float] = None,
        j: Optional[float] = None,
        j_star: Optional[float] = None,
        qmax: Optional[float] = None,
        n_points: int = 10,
    ) -> List[float]:
        """Generate the rate array matching pressure points from Pr down to 0.

        Pressure points are fixed (engine-defined) so curve points are
        deterministic and monotonic; a user test point is NOT interpolated
        into the curve (it is reported separately on the plot).
        """
        ps = self._curve_pressures(pr, n_points, include_pb=(pb is not None), pb=pb)
        qs: List[float] = []
        if model == _MODEL_VOGEL:
            for p in ps:
                qs.append(self.vogel_q(pr, qmax, p))
        elif model == _MODEL_LINEAR:
            for p in ps:
                qs.append(self.linear_q(pr, j, p))
        elif model == _MODEL_COMPOSITE:
            for p in ps:
                qs.append(self.composite_q(pr, pb, j_star, p))
        else:
            raise ValueError(f"Unknown IPR model: {model}")
        return qs

    # -------------------------------------------------------------- #
    # 7. FULL EVALUATION RESULT (text response builder)
    # -------------------------------------------------------------- #
    @staticmethod
    def monotonicity_check(ps: List[float], qs: List[float]) -> bool:
        return all(qs[i] <= qs[i + 1] + 1e-9 for i in range(len(qs) - 1))
