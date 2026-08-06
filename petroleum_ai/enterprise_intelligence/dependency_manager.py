"""
Dependency Manager: Manages module dependencies and execution graph dependencies.
"""

from __future__ import annotations
from typing import Dict, List, Set

class DependencyManager:
    def __init__(self):
        self.dependencies: Dict[str, Set[str]] = {}

    def add_dependency(self, module: str, depends_on: str) -> None:
        if module not in self.dependencies:
            self.dependencies[module] = set()
        self.dependencies[module].add(depends_on)

    def get_dependencies(self, module: str) -> List[str]:
        return list(self.dependencies.get(module, set()))
