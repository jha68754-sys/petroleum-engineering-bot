"""
6. Engineering Knowledge Index: Searchable index for equations, references, and topics.
"""

from __future__ import annotations
from typing import Dict, List

class KnowledgeIndex:
    """Instant lookup index for engineering equations, references, and topics."""
    _index: Dict[str, Dict[str, List[str]]] = {
        "equations": {
            "ooip": ["OOIP = (7758 * A * h * phi * (1 - Sw)) / Boi", "Craft & Hawkins"],
            "ogip": ["OGIP = (43560 * A * h * phi * (1 - Sw)) / Bgi", "Craft & Hawkins"],
            "vogel": ["q / q_max = 1.0 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2", "Vogel (1968)"],
            "darcy": ["q = (7.08 * k * h * (Pr - Pwf)) / (mu * Bo * (ln(re/rw) + S))", "Tiab & Donaldson"]
        },
        "references": {
            "spe": ["SPE Petroleum Engineering Handbook (Volumes I - VI)"],
            "reservoirs": ["Craft & Hawkins, Applied Petroleum Reservoir Engineering", "Tarek Ahmed, Reservoir Engineering Handbook"],
            "production": ["Economides, Petroleum Production Systems"]
        }
    }

    @classmethod
    def search_index(cls, query: str) -> Dict[str, List[str]]:
        q_lower = query.lower()
        results = {}
        for category, items in cls._index.items():
            matches = []
            for k, val in items.items():
                if q_lower in k or any(q_lower in v.lower() for v in val):
                    matches.extend(val)
            if matches:
                results[category] = matches
        return results
