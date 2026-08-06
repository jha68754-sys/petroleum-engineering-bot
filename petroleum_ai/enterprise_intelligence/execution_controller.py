"""
Execution Controller: Oversees step-by-step execution, error handling, retries, and result aggregation.
"""

from __future__ import annotations
from typing import Callable, Dict, Any, List

class ExecutionController:
    def __init__(self):
        pass

    def execute_with_retry(self, func: Callable, retries: int = 3, *args, **kwargs) -> Any:
        last_error = None
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
        raise RuntimeError(f"Execution failed after {retries} retries. Last error: {last_error}")
