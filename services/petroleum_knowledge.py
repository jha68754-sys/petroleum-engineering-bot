"""Deterministic Petroleum Engineering Knowledge Layer V1.

This module is deliberately separate from the released numerical engines.  It
loads a reviewed, version-controlled JSON dataset, resolves safe aliases, and
renders engineering-first explanations.  It never calculates a new petroleum
result; calculation questions are bridged only to released command paths.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


_DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "data" / "petroleum_knowledge_v1.json"


@dataclass(frozen=True)
class KnowledgeRecord:
    """Publicly useful knowledge fields for one canonical engineering term."""

    canonical_id: str
    symbol: str
    canonical_english_name: str
    canonical_arabic_name: str
    aliases: Tuple[str, ...]
    arabic_aliases: Tuple[str, ...]
    english_aliases: Tuple[str, ...]
    abbreviation: Optional[str]
    definition: str
    definition_ar: str
    engineering_meaning: str
    engineering_meaning_ar: str
    unit: str
    si_unit: str
    common_field_units: Tuple[str, ...]
    dimensional_meaning: str
    domain: str
    related_terms: Tuple[str, ...]
    formula: Optional[str]
    formula_variables: Dict[str, str]
    usage: str
    notes: str
    limitations: str
    source: Tuple[str, ...]
    verification_status: str
    version: str

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "KnowledgeRecord":
        return cls(
            canonical_id=str(payload["canonical_id"]),
            symbol=str(payload["symbol"]),
            canonical_english_name=str(payload["canonical_english_name"]),
            canonical_arabic_name=str(payload["canonical_arabic_name"]),
            aliases=tuple(str(v) for v in payload.get("aliases", [])),
            arabic_aliases=tuple(str(v) for v in payload.get("arabic_aliases", [])),
            english_aliases=tuple(str(v) for v in payload.get("english_aliases", [])),
            abbreviation=(str(payload["abbreviation"]) if payload.get("abbreviation") else None),
            definition=str(payload.get("definition", "")),
            definition_ar=str(payload.get("definition_ar", "")),
            engineering_meaning=str(payload.get("engineering_meaning", "")),
            engineering_meaning_ar=str(payload.get("engineering_meaning_ar", "")),
            unit=str(payload.get("unit", "not specified")),
            si_unit=str(payload.get("si_unit", "not applicable")),
            common_field_units=tuple(str(v) for v in payload.get("common_field_units", [])),
            dimensional_meaning=str(payload.get("dimensional_meaning", "")),
            domain=str(payload.get("domain", "Petroleum Engineering")),
            related_terms=tuple(str(v) for v in payload.get("related_terms", [])),
            formula=(str(payload["formula"]) if payload.get("formula") else None),
            formula_variables={str(k): str(v) for k, v in payload.get("formula_variables", {}).items()},
            usage=str(payload.get("usage", "")),
            notes=str(payload.get("notes", "")),
            limitations=str(payload.get("limitations", "")),
            source=tuple(str(v) for v in payload.get("source", [])),
            verification_status=str(payload.get("verification_status", "UNVERIFIED / REVIEW REQUIRED")),
            version=str(payload.get("version", "1.0")),
        )

    def to_public_dict(self) -> Dict[str, Any]:
        """Return a user-safe representation without implementation fields."""
        return {
            "symbol": self.symbol,
            "english_name": self.canonical_english_name,
            "arabic_name": self.canonical_arabic_name,
            "definition": self.definition,
            "definition_ar": self.definition_ar,
            "unit": self.unit,
            "si_unit": self.si_unit,
            "domain": self.domain,
            "related_terms": list(self.related_terms),
            "verification_status": self.verification_status,
        }


@dataclass(frozen=True)
class KnowledgeResolution:
    """Resolution result that makes ambiguity explicit to callers."""

    matches: Tuple[KnowledgeRecord, ...]
    topic: str

    @property
    def is_ambiguous(self) -> bool:
        return len(self.matches) > 1

    @property
    def record(self) -> Optional[KnowledgeRecord]:
        return self.matches[0] if len(self.matches) == 1 else None


_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_NON_WORD = re.compile(r"[^\w\u0600-\u06FF]+", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize_term(value: str) -> str:
    """Normalize Arabic/English symbols, punctuation, spacing, and case."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace("ـ", "")
    # Arabic punctuation sits inside the Arabic Unicode block, so remove it
    # explicitly before the general word-token cleanup.
    text = text.translate(str.maketrans({"؟": " ", "،": " ", "؛": " ", "۔": " ", "٪": " "}))
    # Common Arabic spelling variants used in technical transliteration.
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))
    text = text.replace("μ", "mu").replace("Δ", "delta")
    # Users commonly attach the Arabic conjunction to a following Latin symbol,
    # e.g. "Rs وGOR". Separate it so both engineering terms resolve.
    text = re.sub(r"و(?=[a-z])", "و ", text)
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    text = _NON_WORD.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a normalized alias without matching it inside another word."""
    if not phrase:
        return False
    return f" {phrase} " in f" {text} "


def _unique(records: Iterable[KnowledgeRecord]) -> Tuple[KnowledgeRecord, ...]:
    seen = set()
    result: List[KnowledgeRecord] = []
    for record in records:
        if record.canonical_id not in seen:
            seen.add(record.canonical_id)
            result.append(record)
    return tuple(result)


class PetroleumKnowledgeLayer:
    """Load and query the deterministic Petroleum Engineering knowledge set."""

    def __init__(self, dataset_path: Optional[Path | str] = None) -> None:
        path = Path(dataset_path) if dataset_path else _DEFAULT_DATASET
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "petroleum_knowledge_v1":
            raise ValueError("Unsupported petroleum knowledge dataset schema")
        self.dataset_status = str(payload.get("dataset_status", "UNVERIFIED / REVIEW REQUIRED"))
        self.coverage_gaps: Tuple[Dict[str, str], ...] = tuple(
            {str(key): str(value) for key, value in item.items()}
            for item in payload.get("coverage_gaps", [])
            if isinstance(item, dict)
        )
        self.records: Tuple[KnowledgeRecord, ...] = tuple(
            KnowledgeRecord.from_dict(item) for item in payload.get("records", [])
        )
        if not self.records:
            raise ValueError("Petroleum knowledge dataset is empty")
        self._by_id = {record.canonical_id: record for record in self.records}
        self._aliases: Dict[str, Tuple[str, ...]] = self._build_alias_index()

    def _build_alias_index(self) -> Dict[str, Tuple[str, ...]]:
        index: Dict[str, List[str]] = {}
        for record in self.records:
            values = [
                record.canonical_id,
                record.symbol,
                record.canonical_english_name,
                record.canonical_arabic_name,
                record.abbreviation or "",
                *record.aliases,
                *record.arabic_aliases,
                *record.english_aliases,
            ]
            for value in values:
                key = normalize_term(value)
                if not key:
                    continue
                index.setdefault(key, []).append(record.canonical_id)
        return {key: tuple(dict.fromkeys(ids)) for key, ids in index.items()}

    def get(self, canonical_id: str) -> Optional[KnowledgeRecord]:
        return self._by_id.get(str(canonical_id).strip().casefold())

    def aliases(self) -> Tuple[str, ...]:
        return tuple(sorted(self._aliases))

    def resolve_terms(self, query: str) -> List[KnowledgeRecord]:
        """Return safely matched terms, longest aliases first."""
        normalized = normalize_term(query)
        if not normalized:
            return []
        exact = self._aliases.get(normalized)
        if exact:
            return [self._by_id[item] for item in exact]
        matches: List[KnowledgeRecord] = []
        for alias in sorted(self._aliases, key=len, reverse=True):
            if _contains_phrase(normalized, alias):
                matches.extend(self._by_id[item] for item in self._aliases[alias])
        unique = list(_unique(matches))
        padded = f" {normalized} "

        def first_position(record: KnowledgeRecord) -> int:
            values = [
                record.canonical_id,
                record.symbol,
                record.canonical_english_name,
                record.canonical_arabic_name,
                record.abbreviation or "",
                *record.aliases,
                *record.arabic_aliases,
                *record.english_aliases,
            ]
            positions = [
                padded.find(f" {normalize_term(value)} ")
                for value in values
                if normalize_term(value)
            ]
            visible = [position for position in positions if position >= 0]
            return min(visible) if visible else len(padded)

        return sorted(unique, key=first_position)

    def resolve(self, query: str) -> KnowledgeResolution:
        matches = self.resolve_terms(query)
        return KnowledgeResolution(tuple(matches), normalize_term(query))

    def _record_by_id(self, canonical_id: str) -> Optional[KnowledgeRecord]:
        return self._by_id.get(canonical_id)

    def _related_records(self, record: KnowledgeRecord) -> List[KnowledgeRecord]:
        return [
            related for related_id in record.related_terms
            if (related := self._record_by_id(related_id)) is not None
        ]

    def _looks_like_knowledge_question(self, text: str) -> bool:
        normalized = normalize_term(text)
        if not normalized:
            return False
        markers = (
            "what is", "what does", "define", "definition", "meaning", "unit", "units",
            "formula", "equation", "variable", "variables", "related", "where is", "used",
            "difference", "compare", "versus", " vs ", "explain", "calculate", "compute",
            "ما معنى", "شن معنى", "شنو معنى", "ماهو", "ما هو", "عرف", "عرفلي", "عرّف", "اشرح",
            "وحدة", "وحده", "معادلة", "قانون", "صيغة", "الصيغة", "الفرق", "قارن", "مرتبط", "المرتبط", "يستخدم", "احسب", "حساب",
        )
        return any(
            _contains_phrase(normalized, normalize_term(marker))
            for marker in markers
        ) or normalized in self._aliases

    @staticmethod
    def _intent(text: str) -> str:
        normalized = normalize_term(text)

        def has_any(values: Sequence[str]) -> bool:
            return any(
                _contains_phrase(normalized, normalize_term(value))
                for value in values
            )

        if has_any(("difference", "compare", "versus", "vs", "الفرق", "قارن")):
            return "comparison"
        if has_any(("unit", "units", "وحدة", "وحده")):
            return "unit"
        if has_any(("formula", "equation", "variable", "variables", "معادلة", "قانون", "صيغة", "الصيغة")):
            return "formula"
        if has_any(("related", "مرتبط", "المرتبط")):
            return "related"
        if has_any(("relationship", "relation", "علاقة", "العلاقه")):
            return "relationship"
        if has_any(("where is", "used", "يستخدم")):
            return "context"
        if has_any(("calculate", "compute", "احسب", "حساب")):
            return "calculation"
        return "definition"

    @staticmethod
    def _topic_without_intent(text: str) -> str:
        normalized = normalize_term(text)
        patterns = (
            r"^(?:what is|what does)\s+(?:the\s+)?(?:definition of|meaning of|unit of|formula for)\s+",
            r"^(?:the\s+)?(?:definition of|meaning of|unit of|formula for)\s+",
            r"^(?:what is|what does|define|explain)\s+",
            r"^(?:ما معني|شن معني|شنو معني|ماهو|ما هو|عرفلي|عرف|اشرح|وحده|معادله|صيغه|الصيغه|الفرق بين|المرتبط|قارن)\s+",
            r"^(?:شن|شنو)\s+(?:وحده|معني|معادله)\s+",
        )
        topic = normalized
        for _ in range(3):
            previous = topic
            for pattern in patterns:
                topic = re.sub(pattern, "", topic, count=1)
            if topic == previous:
                break
        topic = re.sub(r"\b(?:the|of|is|does|what|mean|give|me|definition|difference|between|and|versus|vs)\b", " ", topic)
        return _SPACE.sub(" ", topic).strip(" ?:،")

    def _unknown_response(self, text: str) -> str:
        topic = self._topic_without_intent(text) or "that term"
        if topic in {"pressure", "ضغط", "الضغط"} or "pressure" in topic and len(topic.split()) <= 2:
            return (
                "I do not have one unambiguous meaning for that pressure term. "
                "This is not one unambiguous meaning. Please specify reservoir pressure, upstream pressure, downstream pressure, Pwf, Pwh, or THP.\n\n"
                "لا يوجد معنى واحد غير ملتبس لهذا المصطلح. حدّد ضغط المكمن أو ضغط المنبع أو ضغط المصب أو Pwf أو Pwh أو THP."
            )
        return (
            f"I do not have a verified Petroleum Engineering record for: {topic}.\n"
            "I will not invent a definition or numerical answer. Please try a supported term such as Bo, Rs, Bg, Pb, Pwf, PI, IPR, VLP, API Gravity, Porosity, or Permeability.\n\n"
            f"لا أملك سجلًا هندسيًا موثقًا للمصطلح: {topic}. لن أخترع تعريفًا أو قيمة رقمية. جرّب مصطلحًا مدعومًا مثل Bo أو Rs أو Bg أو Pb أو Pwf أو PI أو IPR أو VLP أو API Gravity أو Porosity أو Permeability."
        )

    def _ambiguous_response(self, records: Sequence[KnowledgeRecord]) -> str:
        options = "، ".join(f"{item.symbol} — {item.canonical_arabic_name}" for item in records[:6])
        return (
            "The question matches more than one engineering concept. Please choose one of these: "
            f"{options}.\n\n"
            "السؤال يطابق أكثر من مفهوم هندسي. اختر واحدًا من المصطلحات الظاهرة ثم أعد السؤال بصورة محددة."
        )

    @staticmethod
    def _status(record: KnowledgeRecord) -> str:
        return "VERIFIED" if record.verification_status == "VERIFIED" else "UNVERIFIED / REVIEW REQUIRED"

    def _format_definition(self, record: KnowledgeRecord) -> str:
        related = self._related_records(record)
        related_text = ", ".join(item.symbol for item in related) or "none listed"
        lines = [
            f"{record.symbol} — {record.canonical_english_name}",
            record.canonical_arabic_name,
            "",
            "Definition:",
            record.definition,
            record.definition_ar,
            "",
            "Engineering meaning:",
            record.engineering_meaning,
            record.engineering_meaning_ar,
            "",
            f"Unit: {record.unit}",
            f"SI unit: {record.si_unit}",
            f"Engineering domain: {record.domain}",
            f"Used for: {record.usage}",
            f"Related: {related_text}",
            f"Verification status: {self._status(record)}",
        ]
        if record.formula:
            lines.extend(["", f"Common relationship: {record.formula}"])
        if record.notes:
            lines.extend(["", f"Engineering note: {record.notes}"])
        if record.limitations:
            lines.extend([f"Limitation: {record.limitations}"])
        return "\n".join(lines)

    def _format_unit(self, record: KnowledgeRecord) -> str:
        common = ", ".join(record.common_field_units) or record.unit
        return (
            f"{record.symbol} — {record.canonical_english_name}\n"
            f"{record.canonical_arabic_name}\n\n"
            f"Common unit: {record.unit}\n"
            f"SI unit where applicable: {record.si_unit}\n"
            f"Common field conventions: {common}\n"
            f"Dimensional meaning: {record.dimensional_meaning}\n\n"
            f"Note: {record.notes or 'State the pressure, temperature, and reporting basis when relevant.'}\n"
            f"Verification status: {self._status(record)}"
        )

    def _format_formula(self, record: KnowledgeRecord) -> str:
        if not record.formula:
            return (
                f"{record.symbol} — {record.canonical_english_name}\n"
                "No single formula is presented for this term because its numerical value is state, model, or process dependent.\n"
                "لا توجد معادلة واحدة لهذا المصطلح لأن قيمته تعتمد على الحالة أو النموذج أو عملية الإزاحة."
            )
        variables = "; ".join(f"{key}: {value}" for key, value in record.formula_variables.items())
        return (
            f"{record.symbol} — {record.canonical_english_name}\n"
            f"Common relationship: {record.formula}\n"
            f"Variables: {variables or 'No separate variables listed.'}\n\n"
            "This is an explanatory relationship. The released deterministic calculation engines remain the source of numerical results."
        )

    def _format_multiple_definitions(self, records: Sequence[KnowledgeRecord]) -> str:
        """Answer an explicit multi-term definition request without calling it ambiguous."""
        sections = [self._format_definition(record) for record in records[:4]]
        return "\n\n--------------------\n\n".join(sections)

    def _format_relationship(self, records: Sequence[KnowledgeRecord]) -> str:
        if len(records) < 2:
            return self._format_definition(records[0]) if records else self._unknown_response("")
        left, right = records[0], records[1]
        if {left.canonical_id, right.canonical_id} == {"rs", "bo"}:
            return (
                "Rs and Bo are coupled black-oil PVT properties.\n"
                "Rs describes the gas dissolved in the oil, while Bo describes the reservoir volume of oil plus dissolved gas relative to stock-tank oil.\n\n"
                "نسبة Rs تصف الغاز المذاب في النفط، بينما يصف Bo حجم النفط والغاز المذاب عند ظروف المكمن مقارنة بحجم النفط عند الظروف القياسية.\n\n"
                "They are evaluated consistently with pressure, temperature, composition, separator conditions, and bubble-point behavior. They are used together in black-oil PVT, material balance, reservoir simulation, and well-performance calculations, but they are not interchangeable."
            )
        return (
            f"{left.symbol} and {right.symbol} are related through the stated engineering context.\n"
            f"{left.symbol}: {left.engineering_meaning}\n"
            f"{right.symbol}: {right.engineering_meaning}\n\n"
            f"They may be used together in {left.domain} and {right.domain}, but they retain different definitions and units."
        )

    def _format_comparison(self, records: Sequence[KnowledgeRecord]) -> str:
        if len(records) < 2:
            return self._format_definition(records[0]) if records else self._unknown_response("")
        left, right = records[0], records[1]
        if {left.canonical_id, right.canonical_id} == {"bhp", "pwf"}:
            distinction = (
                "BHP is a broader bottomhole-pressure term whose condition must be stated; "
                "Pwf normally denotes flowing bottomhole pressure. Local reporting conventions should be stated."
            )
            distinction_ar = (
                "BHP مصطلح أوسع لضغط قاع البئر ويجب تحديد حالته، بينما يدل Pwf عادةً على ضغط قاع البئر أثناء الجريان. "
                "يجب توضيح اصطلاح التقرير المحلي."
            )
        else:
            distinction = (
                f"{left.symbol} is defined as: {left.definition} "
                f"{right.symbol} is defined as: {right.definition}"
            )
            distinction_ar = (
                f"{left.symbol}: {left.definition_ar} {right.symbol}: {right.definition_ar}"
            )
        return (
            f"{left.symbol} vs {right.symbol}\n"
            f"{left.canonical_english_name} — {left.canonical_arabic_name} مقابل "
            f"{right.canonical_english_name} — {right.canonical_arabic_name}\n\n"
            f"{left.symbol}: {left.definition_ar}\n"
            f"{right.symbol}: {right.definition_ar}\n\n"
            f"Main distinction: {distinction}\n"
            f"التوضيح الرئيسي: {distinction_ar}\n\n"
            f"Units: {left.symbol} = {left.unit}; {right.symbol} = {right.unit}\n"
            f"Engineering domains: {left.domain}; {right.domain}\n\n"
            "The two terms may be used together in petroleum calculations, but they are not interchangeable."
        )

    def _calculation_bridge(self, records: Sequence[KnowledgeRecord]) -> str:
        record = records[0] if records else None
        if record is None:
            return self._unknown_response("calculation")
        routes = {
            "bo": "/calc vlp, /calc nodal, /calc system, or /calc gas_lift with complete explicit Black-Oil PVT context",
            "bg": "/calc vlp, /calc nodal, /calc system, or /calc gas_lift with complete explicit Black-Oil PVT context",
            "bw": "/calc vlp, /calc nodal, or /calc system with the required water-property inputs",
            "rs": "/calc vlp, /calc nodal, /calc system, or /calc gas_lift with complete explicit Black-Oil PVT context",
            "pwf": "/calc ipr, /calc vlp, /calc nodal, or /calc system",
            "pi": "/calc ipr or /calc nodal",
            "ipr": "/calc ipr or /calc nodal",
            "vlp": "/calc vlp or /calc nodal",
            "thp": "/calc vlp, /calc nodal, /calc sensitivity, or /calc system",
            "pwh": "/calc vlp, /calc nodal, or /calc system",
            "choke": "/calc choke or /calc system",
            "gas_lift": "/calc gas_lift",
            "water_cut": "/calc water_cut",
            "wor": "/calc wor",
            "gor": "/calc gor_produced",
            "api_gravity": "/calc api",
            "porosity": "/calc ooip when porosity is an input; no standalone porosity calculator is provided",
            "permeability": "/calc darcy when permeability is an input; no standalone permeability estimator is provided",
        }
        route = routes.get(record.canonical_id)
        if route:
            if record.canonical_id in {"bo", "bg", "bw", "rs"}:
                return (
                    f"Calculation bridge for {record.symbol}:\n"
                    f"There is no standalone /calc {record.symbol.lower()} command in the released bot. "
                    f"{record.symbol} is evaluated as a PVT property inside an existing deterministic path: {route}.\n"
                    "Provide the required pressure, temperature, fluid, and model inputs, then read the property provenance, units, limitations, and status returned by that engine.\n\n"
                    "The Knowledge Layer does not create a second calculator or invent a number."
                )
            return (
                f"Calculation bridge for {record.symbol}:\n"
                f"Use the released deterministic path: {route}.\n\n"
                "The Knowledge Layer does not create a second calculator or invent a number. "
                "Supply the required engineering inputs and read the model, units, limitations, and status returned by the calculation engine."
            )
        return (
            f"The bot can explain {record.symbol}, but it does not currently expose a standalone validated calculator for that specific property.\n"
            "No numerical answer is fabricated."
        )

    def _has_unmatched_topic_words(
        self, text: str, records: Sequence[KnowledgeRecord]
    ) -> bool:
        """Reject partial matches such as 'super permeability magic'."""
        topic = self._topic_without_intent(text)
        stopwords = {
            "the", "of", "is", "does", "what", "mean", "give", "me", "to", "and", "versus", "vs",
            "unit", "units", "formula", "equation", "variable", "variables",
            "related", "relationship", "relation", "where", "used", "difference", "between", "calculate", "compute",
            "ما", "هو", "هي", "شن", "شنو", "معني", "عرفلي", "وحده", "معادله", "صيغه", "الصيغه", "المرتبط", "الفرق", "بين",
            "مرتبط", "يستخدم", "اشرح", "عرف", "احسب", "حساب", "و", "ب",
        }
        for word in stopwords:
            topic = re.sub(rf"(?:^|\s){re.escape(word)}(?=\s|$)", " ", topic)
        aliases: List[str] = []
        for record in records:
            aliases.extend([
                normalize_term(record.canonical_id),
                normalize_term(record.symbol),
                normalize_term(record.canonical_english_name),
                normalize_term(record.canonical_arabic_name),
                *(normalize_term(value) for value in record.aliases),
                *(normalize_term(value) for value in record.arabic_aliases),
                *(normalize_term(value) for value in record.english_aliases),
            ])
        for alias in sorted({value for value in aliases if value}, key=len, reverse=True):
            topic = topic.replace(alias, " ")
        return bool(_SPACE.sub(" ", topic).strip())

    def _answer_single(self, text: str) -> Optional[str]:
        """Answer one knowledge question or return None for the general AI path."""
        if not self._looks_like_knowledge_question(text):
            return None
        intent = self._intent(text)
        records = self.resolve_terms(text)
        if records and intent != "calculation" and self._has_unmatched_topic_words(text, records):
            records = []
        if intent == "comparison":
            if len(records) < 2:
                return self._ambiguous_response(records) if records else self._unknown_response(text)
            return self._format_comparison(records[:2])
        if intent == "relationship":
            if len(records) < 2:
                return self._ambiguous_response(records) if records else self._unknown_response(text)
            return self._format_relationship(records[:2])
        if len(records) > 1:
            return self._format_multiple_definitions(records)
        if not records:
            return self._unknown_response(text)
        record = records[0]
        if intent == "unit":
            return self._format_unit(record)
        if intent == "formula":
            return self._format_formula(record)
        if intent == "related":
            related = self._related_records(record)
            if not related:
                return f"{record.symbol} has no related terms listed in the verified V1 knowledge set."
            return f"Related to {record.symbol}: " + ", ".join(
                f"{item.symbol} — {item.canonical_english_name}" for item in related
            )
        if intent == "context":
            return f"{record.symbol} — {record.canonical_english_name}\nUsed for: {record.usage}\n\nEngineering note: {record.notes}"
        if intent == "calculation":
            return self._calculation_bridge(records)
        return self._format_definition(record)

    @staticmethod
    def _split_questions(text: str) -> List[str]:
        """Split an explicit batch of questions without fuzzy semantic guessing."""
        raw = str(text or "").strip()
        if not raw:
            return []
        # Newlines are the primary batch boundary. The prefix lookahead also
        # handles clients that flatten pasted multi-line text into one line.
        parts = re.split(r"(?:\r?\n+)|(?<=\?|؟|\.)\s+", raw)
        expanded: List[str] = []
        prefix = re.compile(
            r"(?i)(?=what\s+(?:is|does)|define\b|"
            r"explain\b|calculate\b|compute\b|"
            r"ما\s+معنى|شن\s+معنى|شنو\s+معنى|الفرق\b|قارن\b|"
            r"عرفلي?\b|اشرح\b|شن\s+وحدة|شنو\s+وحدة)"
        )
        for part in parts:
            part = part.strip(" \\t\\r\\n")
            if not part:
                continue
            # Do not split a single sentence. This second pass is only useful
            # when two known question prefixes are present in the same line.
            matches = list(prefix.finditer(part))
            if len(matches) > 1:
                starts = [match.start() for match in matches]
                for start, end in zip(starts, starts[1:] + [len(part)]):
                    fragment = part[start:end].strip()
                    if fragment:
                        expanded.append(fragment)
            else:
                expanded.append(part)
        return expanded

    def answer(self, text: str) -> Optional[str]:
        """Answer one question or an explicit all-knowledge batch."""
        questions = self._split_questions(text)
        if len(questions) <= 1:
            return self._answer_single(text)
        answers = [self._answer_single(question) for question in questions]
        # A mixed natural message still belongs to the general AI path. A
        # fully recognized batch is answered deterministically as one reply.
        if any(answer is None for answer in answers):
            return None
        sections = []
        for index, (question, answer) in enumerate(zip(questions, answers), start=1):
            sections.append(f"Question {index}: {question}\n\n{answer}")
        return "\n\n====================\n\n".join(sections)


_DEFAULT_LAYER = PetroleumKnowledgeLayer()


def answer_knowledge_question(text: str) -> Optional[str]:
    return _DEFAULT_LAYER.answer(text)


def resolve_knowledge_term(text: str) -> KnowledgeResolution:
    return _DEFAULT_LAYER.resolve(text)


def get_knowledge_record(canonical_id: str) -> Optional[KnowledgeRecord]:
    return _DEFAULT_LAYER.get(canonical_id)


def knowledge_usage() -> str:
    return (
        "Usage: /define <term>\n\n"
        "Examples: /define Bo | /define Rs | /define Pwf | /define PI\n"
        "You can also ask naturally: What is Bo? | ما معنى Rs؟ | الفرق بين Bo و Bg؟"
    )


__all__ = [
    "KnowledgeRecord",
    "KnowledgeResolution",
    "PetroleumKnowledgeLayer",
    "answer_knowledge_question",
    "get_knowledge_record",
    "knowledge_usage",
    "normalize_term",
    "resolve_knowledge_term",
]
