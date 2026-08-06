"""
Engineering Graph: Knowledge Graph connecting reservoir, PVT, production, well testing, artificial lift, PEDI, and expert systems.
"""

from __future__ import annotations
from typing import Dict, List, Set, Any

class EngineeringGraph:
    def __init__(self):
        self.nodes: Set[str] = set()
        self.edges: Dict[str, List[str]] = {}

    def add_node(self, node: str) -> None:
        self.nodes.add(node)
        if node not in self.edges:
            self.edges[node] = []

    def add_edge(self, from_node: str, to_node: str) -> None:
        self.add_node(from_node)
        self.add_node(to_node)
        if to_node not in self.edges[from_node]:
            self.edges[from_node].append(to_node)

    def get_graph(self) -> Dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": self.edges
        }
