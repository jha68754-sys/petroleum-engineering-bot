"""
Regression test for the production startup bug:
KeyError: 'shape' in services/ai_service.py _build_engineering_context().

Root cause: some PVT plot rules (gor, wor, watercut, pressure, production,
kr, ipr, vlp, nodal) do not define optional metadata keys such as 'shape'
or 'pivot'. _build_engineering_context() accessed rule['shape'] directly,
crashing AIService() construction and preventing the bot from starting.

Fix: the context builder now only emits 'Shape' / 'Pivot' lines when the
optional key is present in the rule, and all other optional metadata is
already accessed via dict.get().
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ai_service import AIService
from constants import PVT_PLOT_RULES
from services.pvt_engine import PLOT_ALIASES


class TestShapelessRuleRegression(unittest.TestCase):
    """Ensure rules without optional 'shape' metadata never crash startup."""

    def test_all_rules_build_engineering_context(self):
        rules_without_shape = [
            k for k, v in PVT_PLOT_RULES.items() if "shape" not in v
        ]
        self.assertGreater(len(rules_without_shape), 0)
        ai = AIService()
        ctx = ai._build_engineering_context()
        self.assertIsNotNone(ctx)
        self.assertGreater(len(ctx), 0)
        for key in rules_without_shape:
            self.assertIn(key, ctx)

    def test_shapeless_rules_produce_png_directly(self):
        from handlers.command_registry import registry
        import handlers.text_handlers  # noqa: F401

        inv = {v: k for k, v in PLOT_ALIASES.items()}
        for rule_key, v in PVT_PLOT_RULES.items():
            if "shape" in v:
                continue
            alias = inv.get(rule_key, rule_key)
            handler = registry.dispatch(f"/plot {alias} x=1,2,3 v=10,20,30")
            text, png, _ = handler(
                {"text": f"/plot {alias} x=1,2,3 v=10,20,30", "chat": {"id": 1}},
                None,
            )
            self.assertIsNotNone(png, f"/plot {alias} ({rule_key}) returned no PNG")
            self.assertNotIn("No document uploaded", str(text))


if __name__ == "__main__":
    unittest.main()
