"""
Engineering Trace: Documenting decision rationale, references, calculations, confidence, and inputs.
"""

from __future__ import annotations
from typing import Dict, List, Any

class EngineeringTrace:
    def __init__(self):
        self.traces: List[Dict[str, Any]] = []

    def log_trace(self, decision: str, why: str, reference: str, calculation: str, confidence: float, inputs: Dict[str, Any]) -> None:
        self.traces.append({
            "decision": decision,
            "why": why,
            "reference": reference,
            "calculation": calculation,
            "confidence": confidence,
            "inputs": inputs
        })

    def get_traces(self) -> List[Dict[str, Any]]:
        return self.traces
