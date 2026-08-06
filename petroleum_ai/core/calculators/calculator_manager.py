"""
3. Universal Engineering Calculator Manager: Plugin-based calculator registry and runner.
"""

from __future__ import annotations
from typing import Any, Callable, Dict, Optional

class CalculatorManager:
    """Central registry and runner for all engineering calculators."""
    _calculators: Dict[str, Callable[..., Any]] = {}

    @classmethod
    def register_calculator(cls, name: str, func: Callable[..., Any]) -> None:
        cls._calculators[name.lower()] = func

    @classmethod
    def run_calculation(cls, name: str, *args: Any, **kwargs: Any) -> Any:
        calc_name = name.lower()
        if calc_name not in cls._calculators:
            raise ValueError(f"Calculator '{name}' is not registered in CalculatorManager.")
        return cls._calculators[calc_name](*args, **kwargs)

    @classmethod
    def list_calculators(cls) -> list[str]:
        return list(cls._calculators.keys())
