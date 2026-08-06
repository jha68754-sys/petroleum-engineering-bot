"""
Workflow Manager: Dynamically builds engineering workflows based on problem type and context.
"""

from __future__ import annotations
from typing import List, Dict, Any

class WorkflowManager:
    def __init__(self):
        self.workflows: Dict[str, List[str]] = {
            "reservoir": ["reservoir_module", "pvt_module", "recommendation_engine"],
            "production": ["production_module", "well_testing_module", "artificial_lift_module", "recommendation_engine"],
            "integrated": ["reservoir_module", "production_module", "well_testing_module", "artificial_lift_module", "recommendation_engine"]
        }

    def build_workflow(self, problem_type: str) -> List[str]:
        return self.workflows.get(problem_type, ["reservoir_module", "production_module", "recommendation_engine"])
