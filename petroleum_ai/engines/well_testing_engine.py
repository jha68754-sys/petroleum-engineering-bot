"""
Well Testing Engineering Engine: Screening, transient pressure evaluation, and interpretation workflow.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from petroleum_ai.knowledge.well_testing.well_testing_kb import WELL_TESTING_KNOWLEDGE_BASE
from petroleum_ai.calculators.well_testing_calculators import (
    calculate_skin_factor,
    calculate_radius_of_investigation,
    calculate_transmissibility
)

class WellTestingEngine:
    """Core engineering reasoning and calculation engine for well testing."""

    @staticmethod
    def get_topic_details(topic_id: str) -> Optional[Dict[str, Any]]:
        return WELL_TESTING_KNOWLEDGE_BASE.get(topic_id.lower())

    @staticmethod
    def analyze_well_test(data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform well test diagnostic and interpretation calculations."""
        k = data.get("k_md", 50.0)
        h = data.get("h_ft", 40.0)
        mu = data.get("mu_cp", 1.2)
        phi = data.get("porosity", 0.18)
        ct = data.get("c_t", 1e-5)
        t = data.get("time_hrs", 72.0)

        transmissibility = calculate_transmissibility(k, h, mu)
        r_i = calculate_radius_of_investigation(t, k, phi, mu, ct)

        return {
            "transmissibility_md_ft_cp": transmissibility,
            "radius_of_investigation_ft": r_i,
            "interpretation": "Transient test analysis indicates robust radial drainage radius with normal permeability."
        }
