"""
Engineering Orchestrator: Coordinates multi-discipline workflows across Reservoir, Production,
Well Testing, and Artificial Lift engineering modules, utilizing ERF and Universal Calculators.
"""

from __future__ import annotations
from typing import Any, Dict, List
from petroleum_ai.reasoning.framework import EngineeringReasoningFramework, EngineeringContext
from petroleum_ai.engines.reservoir_engine import ReservoirEngine
from petroleum_ai.engines.production_engine import ProductionEngine
from petroleum_ai.engines.well_testing_engine import WellTestingEngine
from petroleum_ai.engines.artificial_lift_engine import ArtificialLiftEngine
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager

class EngineeringOrchestrator:
    """Orchestrates multi-module engineering workflows and generates unified enterprise reports."""

    @staticmethod
    def execute_complete_workflow(query: str, provided_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute full cross-discipline workflow:
        Reservoir → Production → Well Testing → Artificial Lift → Recommendation → Confidence → Professional Report
        """
        # Step 1: Initialize ERF Context & Missing Data
        discipline = EngineeringReasoningFramework.detect_intent(query)
        missing_data = EngineeringReasoningFramework.collect_missing_data(discipline, provided_data)

        # Step 2: Execute Reservoir Module calculations if reservoir data exists
        reservoir_results = {}
        try:
            reservoir_results = ReservoirEngine.analyze_reservoir(provided_data)
        except Exception as e:
            reservoir_results = {"status": "skipped", "reason": str(e)}

        # Step 3: Execute Production Module calculations
        production_results = {}
        try:
            production_results = ProductionEngine.analyze_production(provided_data)
        except Exception as e:
            production_results = {"status": "skipped", "reason": str(e)}

        # Step 4: Execute Well Testing Module calculations
        well_testing_results = {}
        try:
            well_testing_results = WellTestingEngine.analyze_well_test(provided_data)
        except Exception as e:
            well_testing_results = {"status": "skipped", "reason": str(e)}

        # Step 5: Execute Artificial Lift Module screening & selection
        lift_results = {}
        try:
            # Construct summary parameters for artificial lift screening
            lift_data = {
                "q_rate_stb_day": provided_data.get("q_stb_day", 1500.0),
                "depth_ft": provided_data.get("depth_ft", 8000.0),
                "gor_scf_stb": provided_data.get("gor_scf_stb", 500.0),
                "water_cut": provided_data.get("water_cut", 0.2)
            }
            screened = ArtificialLiftEngine.screen_lift_systems(lift_data)
            best_system = ArtificialLiftEngine.recommend_best_system(lift_data)
            lift_results = {
                "screened_systems": screened,
                "recommended_system": best_system
            }
        except Exception as e:
            lift_results = {"status": "skipped", "reason": str(e)}

        # Step 6: ERF Reasoning & Recommendations
        reasoning = EngineeringReasoningFramework.perform_reasoning(discipline, provided_data)
        recommendations = EngineeringReasoningFramework.generate_recommendations(discipline, provided_data)
        confidence_level, confidence_reason = EngineeringReasoningFramework.evaluate_confidence(discipline, provided_data, missing_data)
        references = EngineeringReasoningFramework.attach_references(discipline)

        # Build Engineering Context
        context = EngineeringContext(
            query=query,
            discipline=discipline,
            provided_data=provided_data,
            missing_data=missing_data,
            assumptions=reasoning["assumptions"],
            constraints=reasoning["constraints"],
            selected_equations=reasoning["equations"],
            correlations=reasoning["correlations"],
            calculation_sequence=reasoning["calculation_sequence"],
            uncertainty=reasoning["uncertainty"],
            recommendations=recommendations,
            confidence_level=confidence_level,
            confidence_reason=confidence_reason,
            references=references
        )

        # Step 7: Unified Professional Report Generation
        base_report = EngineeringReasoningFramework.generate_report(context)

        orchestrated_report = f"""
{base_report}

---

## Cross-Discipline Orchestrated Results

### 1. Reservoir Engineering Findings
- **OOIP / Compressibility:** `{reservoir_results}`

### 2. Production Engineering Findings
- **Productivity Index & Vogel IPR:** `{production_results}`

### 3. Well Testing Findings
- **Transmissibility & Radius of Investigation:** `{well_testing_results}`

### 4. Artificial Lift Recommendations
- **Screening & Optimal Lift:** `{lift_results}`
"""

        return {
            "status": "success",
            "discipline": discipline,
            "missing_data": missing_data,
            "reservoir_results": reservoir_results,
            "production_results": production_results,
            "well_testing_results": well_testing_results,
            "lift_results": lift_results,
            "confidence_level": confidence_level,
            "unified_report": orchestrated_report
        }
