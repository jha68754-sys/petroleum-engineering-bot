"""Deterministic Engineering Q&A / Reasoning Layer V1.

This module orchestrates the released PetroleumKnowledgeLayer.  It does not
own a second dataset, perform web retrieval, call an LLM, or calculate a new
engineering result.  It resolves intent and context, composes a readable
answer from verified Knowledge V1 records, and delegates numerical work only
to the calculation paths already described by Knowledge V1.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from services.petroleum_knowledge import (
    KnowledgeRecord,
    PetroleumKnowledgeLayer,
    answer_knowledge_question,
    normalize_term,
)
from services.engineering_language import arabic_domain, is_arabic_text


class EngineeringQALayer:
    """Compose deterministic engineering answers from the existing Knowledge V1."""

    def __init__(self, knowledge: Optional[PetroleumKnowledgeLayer] = None) -> None:
        self.knowledge = knowledge or PetroleumKnowledgeLayer()

    @staticmethod
    def _has_phrase(text: str, *phrases: str) -> bool:
        normalized = normalize_term(text)
        padded = f" {normalized} "
        return any(f" {normalize_term(phrase)} " in padded for phrase in phrases)

    def _topic_is_bare_ambiguous_symbol(self, text: str) -> Optional[str]:
        """Return an unqualified symbol whose meaning must be clarified."""
        topic = self.knowledge._topic_without_intent(text)
        if topic in {"p", "pressure", "ضغط", "الضغط"}:
            return "P"
        if topic in {"t", "temperature", "حراره", "درجه الحراره", "درجة الحرارة"}:
            return "T"
        if topic in {"b", "gor"}:
            return topic.upper()
        return None

    def _is_candidate(self, text: str) -> bool:
        normalized = normalize_term(text)
        if not normalized:
            return False
        if self._topic_is_bare_ambiguous_symbol(text):
            return True
        return self.knowledge._looks_like_knowledge_question(text)

    @staticmethod
    def _is_unknown_answer(answer: Optional[str]) -> bool:
        return bool(answer) and (
            answer.startswith("I do not have a verified Petroleum Engineering record")
            or answer.startswith("لا أملك سجلًا هندسيًا موثقًا")
        )

    @staticmethod
    def _unique_sources(records: Sequence[KnowledgeRecord]) -> List[str]:
        sources: List[str] = []
        for record in records:
            for source in record.source:
                if source and source not in sources:
                    sources.append(source)
        return sources

    def _source_footer(self, records: Sequence[KnowledgeRecord]) -> str:
        sources = self._unique_sources(records)
        if not sources:
            return "\n\nSource basis: No verified source is available for this response."
        status = " / ".join(dict.fromkeys(
            "VERIFIED" if record.verification_status == "VERIFIED"
            else "UNVERIFIED / REVIEW REQUIRED"
            for record in records
        ))
        return "\n\nSource basis: " + "; ".join(sources) + f"\nVerification status: {status}"

    @staticmethod
    def _clarify_symbol(symbol: str) -> str:
        prompts = {
            "P": (
                "P is a context-dependent pressure symbol. Please specify reservoir pressure, upstream pressure, downstream pressure, Pwf, Pwh, or THP.\n"
                "الحرف P يرمز إلى ضغط يعتمد معناه على السياق. حدّد ضغط المكمن أو ضغط المنبع أو ضغط المصب أو Pwf أو Pwh أو THP."
            ),
            "T": (
                "T is a context-dependent temperature symbol. Please specify reservoir temperature, flowing temperature, separator temperature, or another stated temperature basis.\n"
                "الحرف T يرمز إلى درجة حرارة تعتمد على السياق. حدّد درجة حرارة المكمن أو الجريان أو الفاصل أو أساسًا حراريًا آخر."
            ),
            "B": (
                "B is not one unambiguous formation-volume-factor symbol. Please specify Bo, Bg, or Bw.\n"
                "الحرف B ليس رمزًا واحدًا واضحًا لمعامل حجم التكوين. حدّد Bo أو Bg أو Bw."
            ),
            "GOR": (
                "GOR can refer to a stated produced-gas reporting basis, while solution gas-oil ratio is Rs. Please specify produced GOR, solution GOR (Rs), or another gas ratio.\n"
                "قد يشير GOR إلى نسبة الغاز المنتج وفق أساس قياس محدد، بينما نسبة الغاز المذاب هي Rs. حدّد produced GOR أو solution GOR (Rs) أو نسبة غاز أخرى."
            ),
        }
        return prompts[symbol] + "\n\nStatus: clarification required; no numerical value was inferred."

    def _intent(self, text: str) -> str:
        """Classify the question with deterministic precedence for mixed intents."""
        if self._has_phrase(text, "difference", "compare", "versus", "vs", "الفرق", "قارن"):
            return "comparison"
        if self._has_phrase(text, "related", "related concepts", "المصطلحات المرتبطة", "مرتبط", "المرتبط", "المرتبطة"):
            return "related"
        if self._has_phrase(text, "relationship", "relation", "علاقة", "العلاقه"):
            return "relationship"
        if self._has_phrase(text, "definition and unit", "definition unit", "meaning and unit", "تعريف ووحدة", "معنى ووحدة", "تعريف و وحدة", "معنى و وحدة"):
            return "definition_unit"
        if self._has_phrase(text, "unit", "units", "وحدة", "وحده"):
            return "unit"
        if self._has_phrase(text, "formula", "equation", "variable", "variables", "معادلة", "قانون", "صيغة", "الصيغة"):
            return "formula"
        if self._has_phrase(text, "calculate", "compute", "احسب", "احسبلي", "حساب"):
            return "calculation"
        if self._has_phrase(text, "where used", "used for", "where do we use", "وين نستخدم", "نستخدم", "الاستخدام", "استخدام", "يستخدم"):
            return "usage"
        if self._has_phrase(text, "engineering meaning", "engineering significance", "المعنى الهندسي", "معناها هندسيا", "هندسيا", "هندسيًا"):
            return "engineering_meaning"
        if self._has_phrase(text, "when", "if", "below", "under", "تحت", "لما", "عندما", "ينزل", "ينخفض", "يصير"):
            return "context"
        if self._has_phrase(text, "explain", "in simple terms", "simply", "اشرح", "ببساطة", "بطريقة بسيطة"):
            return "explanation"
        return "definition"

    def _format_definition_and_unit(self, record: KnowledgeRecord) -> str:
        return (
            f"{record.symbol} — {record.canonical_english_name}\n"
            f"{record.canonical_arabic_name}\n\n"
            "Definition:\n"
            f"{record.definition}\n{record.definition_ar}\n\n"
            "Engineering meaning:\n"
            f"{record.engineering_meaning}\n{record.engineering_meaning_ar}\n\n"
            f"Common unit: {record.unit}\n"
            f"SI unit where applicable: {record.si_unit}\n"
            f"Common field conventions: {', '.join(record.common_field_units) or record.unit}\n"
            f"Verification status: {record.verification_status}"
        ) + self._source_footer([record])

    def _format_engineering_meaning(self, records: Sequence[KnowledgeRecord]) -> str:
        sections = []
        for record in records[:4]:
            sections.append(
                f"{record.symbol} — {record.canonical_english_name}\n"
                f"Engineering meaning:\n{record.engineering_meaning}\n{record.engineering_meaning_ar}\n"
                f"Domain: {record.domain}\nUsed for: {record.usage}\n"
                f"Verification status: {record.verification_status}"
            )
        return "\n\n--------------------\n\n".join(sections) + self._source_footer(records[:4])

    def _format_usage(self, records: Sequence[KnowledgeRecord]) -> str:
        sections = []
        for record in records[:4]:
            sections.append(
                f"{record.symbol} — {record.canonical_english_name}\n"
                f"Used for: {record.usage}\n"
                f"المعنى التطبيقي: {record.engineering_meaning_ar}\n"
                f"Related: {', '.join(record.related_terms) or 'none listed'}\n"
                f"Verification status: {record.verification_status}"
            )
        return "\n\n--------------------\n\n".join(sections) + self._source_footer(records[:4])

    def _format_explanation(self, records: Sequence[KnowledgeRecord]) -> str:
        sections = []
        for record in records[:3]:
            related = ", ".join(record.related_terms) or "none listed"
            sections.append(
                f"{record.symbol} — {record.canonical_english_name}\n"
                "Simple engineering explanation:\n"
                f"{record.definition}\n{record.definition_ar}\n\n"
                f"Why it matters: {record.engineering_meaning}\n{record.engineering_meaning_ar}\n\n"
                f"Used for: {record.usage}\nRelated: {related}\n"
                f"Verification status: {record.verification_status}"
            )
        return "\n\n--------------------\n\n".join(sections) + self._source_footer(records[:3])

    def _format_condition(self, records: Sequence[KnowledgeRecord]) -> str:
        by_id = {record.canonical_id: record for record in records}
        rs = by_id.get("rs")
        pb = by_id.get("pb")
        bo = by_id.get("bo")
        if rs and pb:
            lines = [
                "Pressure condition: below Pb",
                f"Rs response: {rs.formula or rs.engineering_meaning}",
                "استجابة Rs: عند انخفاض الضغط تحت Pb، تنخفض Rs مع تحرر الغاز من المحلول. "
                f"{rs.engineering_meaning_ar}",
                "",
                f"Pb meaning: {pb.engineering_meaning}",
                f"معنى Pb: {pb.engineering_meaning_ar}",
            ]
            if bo:
                lines.extend([
                    "",
                    f"Bo context: {bo.engineering_meaning}",
                    f"سياق Bo: {bo.engineering_meaning_ar}",
                    "Bo must be evaluated at the stated fluid state; this answer does not infer a numerical Bo trend.",
                ])
            lines.extend([
                "",
                "This is a state relationship from the verified Knowledge record, not a numerical calculation.",
                "هذه علاقة حالة مستخرجة من سجل Knowledge موثق، وليست حسابًا عدديًا.",
            ])
            return "\n".join(lines) + self._source_footer([record for record in (rs, pb, bo) if record])
        if records:
            base = self.knowledge._format_relationship(records[:2]) if len(records) >= 2 else self.knowledge._format_definition(records[0])
            return base + self._source_footer(records[:2])
        return self.knowledge._unknown_response("pressure condition")

    def _format_relationship(self, records: Sequence[KnowledgeRecord]) -> str:
        ids = {record.canonical_id for record in records}
        if ids == {"rs", "pb"}:
            rs = next(record for record in records if record.canonical_id == "rs")
            pb = next(record for record in records if record.canonical_id == "pb")
            return (
                "Rs and Pb are linked through the oil PVT phase boundary.\n"
                f"Rs relationship: {rs.formula or rs.engineering_meaning}\n"
                f"Pb role: {pb.engineering_meaning}\n\n"
                "العلاقة بين Rs وPb مرتبطة بحد التشبع في PVT النفط.\n"
                "علاقة Rs: تحت Pb تنخفض Rs مع تحرر الغاز من المحلول. "
                f"{rs.engineering_meaning_ar}\n"
                f"دور Pb: {pb.engineering_meaning_ar}\n\n"
                "No numerical value is inferred without a defined PVT state and method."
                + self._source_footer(records)
            )
        if ids == {"rs", "gor"}:
            rs = next(record for record in records if record.canonical_id == "rs")
            gor = next(record for record in records if record.canonical_id == "gor")
            return (
                "Rs and GOR describe different gas-to-oil concepts.\n"
                f"Rs: {rs.definition}\n{rs.definition_ar}\n"
                f"GOR: {gor.definition}\n{gor.definition_ar}\n\n"
                "They can be used together, but they are not interchangeable.\n"
                "يمكن استخدامهما معًا، لكنهما ليسا مصطلحين متبادلين."
                + self._source_footer(records)
            )
        base = self.knowledge._format_relationship(records[:2])
        return base + self._source_footer(records[:2])

    def _format_three_or_more_comparison(self, records: Sequence[KnowledgeRecord]) -> str:
        title = " vs ".join(record.symbol for record in records[:4])
        sections = [title]
        for record in records[:4]:
            sections.append(
                f"{record.symbol} — {record.canonical_english_name}\n"
                f"{record.definition}\n{record.definition_ar}\n"
                f"Unit: {record.unit}; SI unit: {record.si_unit}"
            )
        sections.append(
            "Main distinction: These phase-specific or concept-specific terms retain different definitions, volume bases, and units; they are not interchangeable.\n"
            "التوضيح الرئيسي: لكل مصطلح تعريف وأساس حجمي ووحدة بحسب الطور أو المفهوم، ولا يجوز اعتبارها متبادلة."
        )
        return "\n\n".join(sections) + self._source_footer(records[:4])

    def _format_comparison(self, records: Sequence[KnowledgeRecord], include_usage: bool = False) -> str:
        if len(records) >= 3:
            base = self._format_three_or_more_comparison(records)
        else:
            base = self.knowledge._format_comparison(records[:2]) + self._source_footer(records[:2])
        if include_usage:
            usage = "\n\nUsage of each term:\n" + "\n".join(
                f"{record.symbol}: {record.usage}" for record in records[:4]
            )
            base += usage
        return base

    def _arabic_source_footer(self, records: Sequence[KnowledgeRecord]) -> str:
        sources = self._unique_sources(records)
        status = "؛ ".join(dict.fromkeys(
            "موثق" if record.verification_status == "VERIFIED" else "غير موثق ويحتاج مراجعة"
            for record in records
        ))
        if not sources:
            return "\n\nأساس المصدر: لا يتوفر مصدر موثق لهذا الرد.\nحالة التحقق: " + status
        return "\n\nأساس المصدر: " + "؛ ".join(sources) + f"\nحالة التحقق: {status}"

    @staticmethod
    def _arabic_unknown(text: str) -> str:
        topic = str(text or "").strip()
        return (
            f"لا أملك سجلًا هندسيًا موثقًا للمصطلح أو السؤال: {topic}.\n"
            "لن أخترع تعريفًا أو قيمة رقمية. حدّد مصطلحًا نفطيًا معروفًا مثل Bo أو Rs أو Bg أو Pb أو Pwf أو PI أو IPR أو VLP."
        )

    @staticmethod
    def _arabic_clarify(symbol: str) -> str:
        prompts = {
            "P": "الحرف P رمز يعتمد معناه على السياق. حدّد ضغط المكمن، أو ضغط رأس البئر، أو ضغط المنبع، أو ضغط المصب، أو Pwf.",
            "T": "الحرف T رمز يعتمد معناه على السياق. حدّد درجة حرارة المكمن، أو درجة حرارة الجريان، أو درجة حرارة الفاصل.",
            "B": "الحرف B ليس رمزًا واحدًا كافيًا. حدّد معامل حجم تكوين النفط Bo، أو الغاز Bg، أو الماء Bw.",
            "GOR": "حدّد هل تقصد نسبة الغاز إلى النفط المنتج GOR، أم نسبة الغاز المذاب إلى النفط Rs؛ فهما ليسا مصطلحين متبادلين.",
        }
        return prompts.get(symbol, "يرجى تحديد المصطلح النفطي المقصود قبل الإجابة.") + "\n\nالحالة: يلزم توضيح المصطلح؛ لم تُستنتج قيمة رقمية."

    @staticmethod
    def _arabic_record_heading(record: KnowledgeRecord) -> str:
        return f"{record.symbol} — {record.canonical_arabic_name} ({record.canonical_english_name})"

    def _arabic_definition(self, record: KnowledgeRecord) -> str:
        related = "، ".join(item.symbol for item in self.knowledge._related_records(record)) or "لا توجد قائمة مرتبطة"
        lines = [
            self._arabic_record_heading(record),
            "",
            "التعريف:",
            record.definition_ar,
            "",
            "المعنى الهندسي:",
            record.engineering_meaning_ar,
            "",
            f"الوحدة الشائعة: {record.unit}",
            f"وحدة النظام الدولي عند انطباقها: {record.si_unit}",
            f"المجال الهندسي: {arabic_domain(record.domain)}",
            f"المصطلحات المرتبطة: {related}",
            f"حالة التحقق: {'موثق' if record.verification_status == 'VERIFIED' else 'غير موثق ويحتاج مراجعة'}",
        ]
        if record.notes:
            lines.extend(["", f"ملاحظة هندسية: {record.notes}"])
        if record.limitations:
            lines.append(f"القيد: {record.limitations}")
        return "\n".join(lines) + self._arabic_source_footer([record])

    def _arabic_unit(self, record: KnowledgeRecord) -> str:
        common = "، ".join(record.common_field_units) or record.unit
        return (
            f"{self._arabic_record_heading(record)}\n\n"
            f"الوحدة الشائعة: {record.unit}\n"
            f"وحدة النظام الدولي عند انطباقها: {record.si_unit}\n"
            f"اصطلاحات الحقل: {common}\n"
            f"المعنى البُعدي: {record.dimensional_meaning}\n\n"
            f"ملاحظة: {record.notes or 'يجب تحديد حالة المائع وأساس القياس عند الحاجة.'}\n"
            f"حالة التحقق: {'موثق' if record.verification_status == 'VERIFIED' else 'غير موثق ويحتاج مراجعة'}"
        ) + self._arabic_source_footer([record])

    def _arabic_formula(self, record: KnowledgeRecord) -> str:
        if not record.formula:
            return (
                f"{self._arabic_record_heading(record)}\n\n"
                "لا توجد معادلة واحدة لهذا المصطلح؛ فقيمته تعتمد على حالة المائع أو النموذج أو عملية الحساب.\n"
                "لم تُستنتج قيمة رقمية."
            )
        variables = "؛ ".join(f"{key}: {value}" for key, value in record.formula_variables.items())
        return (
            f"{self._arabic_record_heading(record)}\n\n"
            f"العلاقة الشائعة: {record.formula}\n"
            f"المتغيرات: {variables or 'لا توجد متغيرات منفصلة مسجلة.'}\n\n"
            "هذه علاقة تفسيرية؛ أما القيم الرقمية فتصدر فقط من مسارات الحساب الحتمية المعتمدة."
        ) + self._arabic_source_footer([record])

    def _arabic_comparison(self, records: Sequence[KnowledgeRecord], include_usage: bool = False) -> str:
        sections = [f"مقارنة المصطلحات: {' مقابل '.join(record.symbol for record in records[:4])}"]
        for record in records[:4]:
            sections.extend([
                "",
                self._arabic_record_heading(record),
                f"التعريف: {record.definition_ar}",
                f"الوحدة: {record.unit}",
            ])
        sections.extend([
            "",
            "الخلاصة الهندسية: لكل مصطلح تعريف وأساس حجمي ووحدة بحسب الطور أو المفهوم؛ ولا يجوز اعتبار هذه المصطلحات متبادلة.",
        ])
        if include_usage:
            sections.extend([
                "",
                "الاستخدام الهندسي لكل مصطلح:",
            ])
            for record in records[:4]:
                sections.append(f"{record.symbol}: {record.usage}")
        return "\n".join(sections) + self._arabic_source_footer(records[:4])

    def _arabic_relationship(self, records: Sequence[KnowledgeRecord]) -> str:
        ids = {record.canonical_id for record in records}
        by_id = {record.canonical_id: record for record in records}
        if ids == {"rs", "pb"}:
            rs, pb = by_id["rs"], by_id["pb"]
            text = (
                "العلاقة بين Rs وPb مرتبطة بحد التشبع في خواص النفط (PVT).\n"
                f"استجابة Rs: {rs.engineering_meaning_ar}\n"
                f"دور Pb: {pb.engineering_meaning_ar}\n\n"
                "هذه علاقة حالة، وليست حسابًا عدديًا."
            )
        elif ids == {"rs", "gor"}:
            rs, gor = by_id["rs"], by_id["gor"]
            text = (
                "Rs وGOR يصفان مفهومين مختلفين للغاز والنفط.\n"
                f"Rs: {rs.definition_ar}\n"
                f"GOR: {gor.definition_ar}\n\n"
                "يمكن استخدامهما معًا في حسابات النفط، لكنهما ليسا مصطلحين متبادلين."
            )
        else:
            text = "\n".join(
                [f"العلاقة بين {' و'.join(record.symbol for record in records[:2])} ضمن السياق الهندسي المحدد:"]
                + [f"{record.symbol}: {record.engineering_meaning_ar}" for record in records[:2]]
                + ["\nتظل التعريفات والوحدات مختلفة ويجب تحديد حالة المائع عند التطبيق."]
            )
        return text + self._arabic_source_footer(records[:2])

    def _arabic_context(self, records: Sequence[KnowledgeRecord]) -> str:
        by_id = {record.canonical_id: record for record in records}
        if "rs" in by_id and "pb" in by_id:
            rs, pb = by_id["rs"], by_id["pb"]
            return (
                "حالة الضغط: أقل من Pb\n"
                f"استجابة Rs: عند انخفاض الضغط تحت Pb، تنخفض Rs مع تحرر الغاز من المحلول. {rs.engineering_meaning_ar}\n\n"
                f"معنى Pb: {pb.engineering_meaning_ar}\n\n"
                "هذه علاقة حالة مستخرجة من سجل Knowledge موثق، وليست حسابًا عدديًا."
            ) + self._arabic_source_footer([rs, pb])
        return self._arabic_definition(records[0]) if records else self._arabic_unknown("حالة الضغط")

    def _arabic_calculation_bridge(self, records: Sequence[KnowledgeRecord]) -> str:
        record = records[0] if records else None
        if record is None:
            return self._arabic_unknown("الحساب")
        routes = {
            "bo": "/calc vlp أو /calc nodal أو /calc system أو /calc gas_lift مع سياق Black-Oil كامل",
            "bg": "/calc vlp أو /calc nodal أو /calc system أو /calc gas_lift مع سياق Black-Oil كامل",
            "bw": "/calc vlp أو /calc nodal أو /calc system مع مدخلات الماء المطلوبة",
            "rs": "/calc vlp أو /calc nodal أو /calc system أو /calc gas_lift مع سياق Black-Oil كامل",
            "pwf": "/calc ipr أو /calc vlp أو /calc nodal أو /calc system",
            "pi": "/calc ipr أو /calc nodal",
            "ipr": "/calc ipr أو /calc nodal",
            "vlp": "/calc vlp أو /calc nodal",
            "thp": "/calc vlp أو /calc nodal أو /calc sensitivity أو /calc system",
            "pwh": "/calc vlp أو /calc nodal أو /calc system",
            "choke": "/calc choke أو /calc system",
            "gas_lift": "/calc gas_lift",
            "water_cut": "/calc water_cut",
            "wor": "/calc wor",
            "gor": "/calc gor_produced",
            "api_gravity": "/calc api",
            "porosity": "/calc ooip عندما تكون المسامية مدخلًا؛ لا يوجد حاسبة مسامية مستقلة",
            "permeability": "/calc darcy عندما تكون النفاذية مدخلًا؛ لا يوجد مقدّر نفاذية مستقل",
        }
        route = routes.get(record.canonical_id)
        if not route:
            return f"يمكن للبوت شرح {record.symbol}، لكن لا توجد حاسبة مستقلة موثقة له حاليًا.\nلن تُختلق قيمة رقمية."
        if record.canonical_id in {"bo", "bg", "bw", "rs"}:
            return (
                f"جسر الحساب للمصطلح {record.symbol} ({record.canonical_arabic_name}):\n"
                f"لا يوجد أمر مستقل /calc {record.symbol.lower()} في الإصدار المعتمد. تُقيَّم الخاصية داخل المسار الحتمي: {route}.\n"
                "قدّم الضغط والحرارة وبيانات المائع واختيار النموذج المطلوبة، ثم اقرأ المصدر والوحدات والقيود والحالة.\n\n"
                "طبقة Knowledge لا تنشئ حاسبة ثانية ولا تختلق رقمًا."
            )
        return (
            f"مسار الحساب الحتمي للمصطلح {record.symbol}: {route}.\n\n"
            "قدّم المدخلات الهندسية المطلوبة، ثم اقرأ النموذج والوحدات والقيود والحالة التي يعيدها محرك الحساب.\n"
            "لن تُختلق قيمة رقمية."
        ) + self._arabic_source_footer([record])

    def _answer_one_ar(self, text: str) -> Tuple[Optional[str], bool]:
        if not self._is_candidate(text):
            return None, False
        bare_symbol = self._topic_is_bare_ambiguous_symbol(text)
        if bare_symbol:
            return self._arabic_clarify(bare_symbol), True
        records = self.knowledge.resolve_terms(text)
        intent = self._intent(text)
        if not records:
            return self._arabic_unknown(text), True
        if intent == "comparison":
            return self._arabic_comparison(
                records,
                include_usage=self._has_phrase(text, "where used", "used for", "وين نستخدم", "نستخدم", "استخدام"),
            ), True
        if intent == "relationship":
            return self._arabic_relationship(records), True
        if intent == "definition_unit":
            return self._arabic_definition(records[0]), True
        if intent == "unit":
            return self._arabic_unit(records[0]), True
        if intent == "formula":
            return self._arabic_formula(records[0]), True
        if intent == "calculation":
            return self._arabic_calculation_bridge(records), True
        if intent == "related":
            related = self.knowledge._related_records(records[0])
            if related:
                items = "، ".join(f"{item.symbol} — {item.canonical_arabic_name}" for item in related[:8])
                return f"المصطلحات المرتبطة بـ {records[0].symbol}: {items}" + self._arabic_source_footer(records[:1]), True
            return f"لا توجد مصطلحات مرتبطة مسجلة بـ {records[0].symbol}." + self._arabic_source_footer(records[:1]), True
        if intent == "context":
            return self._arabic_context(records), True
        if intent == "engineering_meaning":
            return (
                "\n\n--------------------\n\n".join(
                    f"{self._arabic_record_heading(record)}\nالمعنى الهندسي:\n{record.engineering_meaning_ar}\nالمجال: {arabic_domain(record.domain)}\nحالة التحقق: موثق"
                    for record in records[:4]
                ) + self._arabic_source_footer(records[:4]),
                True,
            )
        if intent == "usage":
            return (
                "\n\n--------------------\n\n".join(
                    f"{self._arabic_record_heading(record)}\nالمعنى التطبيقي: {record.engineering_meaning_ar}\nالمجال: {arabic_domain(record.domain)}"
                    for record in records[:4]
                ) + self._arabic_source_footer(records[:4]),
                True,
            )
        if intent == "explanation":
            return (
                "\n\n--------------------\n\n".join(
                    f"{self._arabic_record_heading(record)}\nالتعريف المبسط: {record.definition_ar}\n\nلماذا يهم هندسيًا؟ {record.engineering_meaning_ar}"
                    for record in records[:3]
                ) + self._arabic_source_footer(records[:3]),
                True,
            )
        return self._arabic_definition(records[0]), True

    def _answer_one(self, text: str) -> Tuple[Optional[str], bool]:
        if is_arabic_text(text):
            return self._answer_one_ar(text)
        candidate = self._is_candidate(text)
        if not candidate:
            return None, False

        bare_symbol = self._topic_is_bare_ambiguous_symbol(text)
        if bare_symbol:
            return self._clarify_symbol(bare_symbol), True

        records = self.knowledge.resolve_terms(text)
        intent = self._intent(text)
        if intent == "comparison":
            if len(records) < 2:
                answer = self.knowledge._answer_single(text)
                return answer, True
            return self._format_comparison(
                records,
                include_usage=self._has_phrase(text, "where used", "used for", "وين نستخدم", "نستخدم", "استخدام"),
            ), True
        if intent == "relationship":
            if len(records) < 2:
                answer = self.knowledge._answer_single(text)
                if answer and records and not self._is_unknown_answer(answer):
                    answer += self._source_footer(records[:4])
                return answer, True
            return self._format_relationship(records), True
        if intent == "definition_unit":
            if records:
                return self._format_definition_and_unit(records[0]), True
        if intent == "unit":
            if records:
                return self.knowledge._format_unit(records[0]) + self._source_footer(records[:1]), True
        if intent == "formula":
            if records:
                return self.knowledge._format_formula(records[0]) + self._source_footer(records[:1]), True
        if intent == "calculation":
            if records:
                return self.knowledge._calculation_bridge(records), True
        if intent == "related":
            if records:
                related = self.knowledge._related_records(records[0])
                if related:
                    answer = f"Related to {records[0].symbol}: " + ", ".join(
                        f"{item.symbol} — {item.canonical_english_name}" for item in related
                    )
                    return answer + self._source_footer(records[:1]), True
        if intent == "context":
            return self._format_condition(records), True
        if intent == "engineering_meaning":
            if records:
                return self._format_engineering_meaning(records), True
        if intent == "usage":
            if records:
                return self._format_usage(records), True
        if intent == "explanation":
            if records:
                return self._format_explanation(records), True

        answer = self.knowledge._answer_single(text)
        if answer is None:
            return None, True
        if records and not self._is_unknown_answer(answer):
            answer += self._source_footer(records[:4])
        return answer, True

    def answer(self, text: str) -> Optional[str]:
        """Answer one question or an explicit batch; return None for general AI text."""
        raw = str(text or "").strip()
        if not raw:
            return None
        questions = self.knowledge._split_questions(raw)
        if len(questions) <= 1:
            answer, _ = self._answer_one(raw)
            return answer

        answers: List[str] = []
        for index, question in enumerate(questions, start=1):
            answer, candidate = self._answer_one(question)
            if not candidate or answer is None:
                # Preserve the existing AI path for genuinely general text.
                return None
            if self._is_unknown_answer(answer):
                answer = "UNVERIFIED / NOT CURRENTLY COVERED\n" + answer
            answers.append(f"Question {index}: {question}\n\n{answer}")
        return "\n\n====================\n\n".join(answers)


_DEFAULT_QA_LAYER = EngineeringQALayer()


def answer_engineering_question(text: str) -> Optional[str]:
    """Public deterministic Q&A entry point used before the general AI path."""
    return _DEFAULT_QA_LAYER.answer(text)


__all__ = ["EngineeringQALayer", "answer_engineering_question"]
