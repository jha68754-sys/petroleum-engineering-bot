"""
Data models for the Petroleum Engineering Bot.

Defines typed structures for PVT data, calculation inputs,
API responses, and chat state using dataclasses and TypedDict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from typing_extensions import TypedDict


# ─────────────────────────────────────────────────────────────────────
#  CHAT STATE
# ─────────────────────────────────────────────────────────────────────

class ChatState(TypedDict):
    """Per-chat persistent state."""
    file_context: Optional[str]      # Segmented document text or __CSV__ prefix
    image_context: Optional[str]     # Local path to uploaded image
    conversation_history: List[Dict[str, str]]  # Message history for context


# ─────────────────────────────────────────────────────────────────────
#  PVT DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────

class PVTDataPoint(TypedDict):
    """A single (pressure, value) data point."""
    pressure: float  # psia
    value: float     # property value


class PVTDataSet(TypedDict):
    """A collection of PVT data points with metadata."""
    relationship_key: str           # e.g., "bo_vs_p"
    points: List[PVTDataPoint]
    saturation_pressure: Optional[float]  # Pb or Pd in psia
    well_name: Optional[str]


class FluidClassification(TypedDict):
    """Result of fluid classification."""
    type_en: str
    type_ar: str
    gor: float
    api: float
    behavior: str
    is_near_critical: bool
    boundary_note: Optional[str]


# ─────────────────────────────────────────────────────────────────────
#  CALCULATION MODELS
# ─────────────────────────────────────────────────────────────────────

class FormulaSpec(TypedDict):
    """Specification for an exact petroleum engineering formula."""
    name_en: str
    name_ar: str
    inputs: List[str]
    units: Dict[str, str]
    formula_str: str
    output_unit: str
    func: Any  # Callable — cannot be serialized


class CorrelationSpec(TypedDict):
    """Specification for a PVT correlation estimate."""
    name_en: str
    name_ar: str
    inputs: List[str]
    units: Dict[str, str]
    formula_str: str
    output_unit: str
    func: Any  # Callable
    applicability: Dict[str, Tuple[float, float]]  # input -> (min, max)


# ─────────────────────────────────────────────────────────────────────
#  PVT PLOT RULES
# ─────────────────────────────────────────────────────────────────────

class PVTPlotRule(TypedDict):
    """Rule defining the expected shape of a PVT property vs pressure."""
    title_en: str
    title_ar: str
    definition: str
    x_axis: str
    y_axis: str
    above_saturation: str
    at_saturation: str
    below_saturation: str
    shape: str
    pivot: str
    common_ai_mistakes: List[str]
    plot_color: str
    y_label: str


class PVTPlotAlias(TypedDict):
    """Maps user-friendly alias to canonical relationship key."""
    alias: str
    key: str


# ─────────────────────────────────────────────────────────────────────
#  SIMULATION TABLE MODELS
# ─────────────────────────────────────────────────────────────────────

class SimTableRequest(TypedDict):
    """Request to generate a simulation table."""
    table_type: str       # PVTO, PVDO, PVTG, PVDG
    simulator: str        # eclipse or cmg
    fluid_type: str       # black_oil, volatile_oil, gas_condensate, etc.


class SimTableResult(TypedDict):
    """Result of simulation table generation."""
    table_type: str
    format: str           # eclipse or cmg
    content: str          # Formatted table text
    filename: str         # Suggested filename
    mime_type: str        # MIME type for Telegram send


# ─────────────────────────────────────────────────────────────────────
#  OFFSET PERSISTENCE
# ─────────────────────────────────────────────────────────────────────

@dataclass
class OffsetState:
    """Persistent offset state for Telegram long-polling."""
    current_offset: int = 0
    last_update_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "current_offset": self.current_offset,
            "last_update_time": self.last_update_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OffsetState:
        """Deserialize from JSON dict."""
        return cls(
            current_offset=data.get("current_offset", 0),
            last_update_time=data.get("last_update_time"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> OffsetState:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(text))


# ─────────────────────────────────────────────────────────────────────
#  AI RESPONSE MODEL
# ─────────────────────────────────────────────────────────────────────

@dataclass
class AIResponse:
    """Structured response from the AI service."""
    content: str
    model: str
    tokens_used: Optional[int] = None
    cached: bool = False


# ─────────────────────────────────────────────────────────────────────
#  UNIT CONVERSION
# ─────────────────────────────────────────────────────────────────────

class UnitConversion(TypedDict):
    """A unit conversion pair."""
    from_unit: str
    to_unit: str
    factor: float
    description: str


# ─────────────────────────────────────────────────────────────────────
#  KNOWLEDGE BASE ENTRY
# ─────────────────────────────────────────────────────────────────────

class KnowledgeEntry(TypedDict):
    """Single entry in the petroleum engineering knowledge base."""
    en: str
    ar: str
    category: str
    unit: str
    def_ar: str
    trend: str
    relationship_key: Optional[str]
    typical_range: str
