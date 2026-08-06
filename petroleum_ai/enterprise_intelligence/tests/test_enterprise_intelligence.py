"""
Comprehensive Unit and Integration Tests for Enterprise Intelligence Fabric (EIF).
"""

import unittest
from petroleum_ai.enterprise_intelligence.enterprise_brain import EnterpriseBrain
from petroleum_ai.enterprise_intelligence.context_manager import ContextManager
from petroleum_ai.enterprise_intelligence.memory_manager import MemoryManager
from petroleum_ai.enterprise_intelligence.engineering_validator import EngineeringValidator

class TestEnterpriseIntelligenceFabric(unittest.TestCase):
    def setUp(self):
        self.brain = EnterpriseBrain()
        self.validator = EngineeringValidator()

    def test_brain_processing(self):
        payload = {"porosity": 0.22, "water_saturation": 0.25}
        result = self.brain.process_request("reservoir", payload)
        self.assertEqual(result["status"], "ENTERPRISE_INTELLIGENCE_PROCESSED")
        self.assertIn("reasoning", result)
        self.assertIn("orchestration", result)

    def test_validator(self):
        errors = self.validator.validate_inputs({"porosity": 0.50, "water_saturation": 1.2})
        self.assertGreater(len(errors), 0)

        valid_errors = self.validator.validate_inputs({"porosity": 0.2, "water_saturation": 0.3})
        self.assertEqual(len(valid_errors), 0)

    def memory_and_context(self):
        cm = ContextManager()
        cm.update_engineering_context("well", {"well_name": "Well-A"})
        ctx = cm.get_context()
        self.assertEqual(ctx["well"]["well_name"], "Well-A")

if __name__ == "__main__":
    unittest.main()
