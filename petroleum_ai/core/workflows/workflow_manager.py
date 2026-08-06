"""
4. Engineering Workflow Manager: Standardizes the 8-step engineering problem-solving lifecycle.
"""

from __future__ import annotations
from typing import Any, Dict, List
from petroleum_ai.reasoning.framework import EngineeringReasoningFramework, EngineeringContext

class WorkflowManager:
    """Executes the standard 8-step petroleum engineering problem-solving workflow."""

    @staticmethod
    def execute_workflow(query: str, provided_data: Dict[str, Any]) -> EngineeringContext:
        # Step 1: Problem / Intent Detection
        discipline = EngineeringReasoningFramework.detect_intent(query)

        # Step 2: Missing Data Collection
        missing = EngineeringReasoningFramework.collect_missing_data(discipline, provided_data)

        # Step 3: Engineering Validation & Assumptions
        reasoning = EngineeringReasoningFramework.perform_reasoning(discipline, provided_data)

        # Step 4: Equation Selection & Correlations
        equations = reasoning["equations"]
        correlations = reasoning["correlations"]

        # Step 5: Calculation (simulated or executed via CalculatorManager)
        # Step 6: Engineering Reasoning & Uncertainty
        uncertainty = reasoning["uncertainty"]

        # Step 7: Recommendations
        recs = EngineeringReasoningFramework.generate_recommendations(discipline, provided_data)

        # Confidence Evaluation
        conf_level, conf_reason = EngineeringReasoningFramework.evaluate_confidence(discipline, provided_data, missing)

        # References
        refs = EngineeringReasoningFramework.attach_references(discipline)

        context = EngineeringContext(
            query=query,
            discipline=discipline,
            provided_data=provided_data,
            missing_data=missing,
            assumptions=reasoning["assumptions"],
            constraints=reasoning["constraints"],
            selected_equations=equations,
            correlations=correlations,
            calculation_sequence=reasoning["calculation_sequence"],
            uncertainty=uncertainty,
            recommendations=recs,
            confidence_level=conf_level,
            confidence_reason=conf_reason,
            references=refs
        )
        return context
