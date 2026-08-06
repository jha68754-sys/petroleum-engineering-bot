"""
Comprehensive unit and integration test suite for Petroleum Fluid Intelligence Engine (PFIE).
"""

import unittest
from petroleum_ai.pvt.knowledge.pvt_kb import PVT_KNOWLEDGE_BASE
from petroleum_ai.pvt.calculators.pvt_calculators import (
    calculate_oil_fvf,
    calculate_gas_fvf,
    calculate_bubble_point,
    calculate_z_factor
)
from petroleum_ai.pvt.engines.pvt_engine import PVTEngine
from petroleum_ai.pvt.validators.pvt_validator import PVTValidator
from petroleum_ai.pvt.pvt_plugin import PVTPlugin
from petroleum_ai.core.calculators.calculator_manager import CalculatorManager
from petroleum_ai.core.plugins.plugin_system import PluginManager

class TestPFIEModule(unittest.TestCase):

    def test_pvt_knowledge_base(self):
        self.assertIn("black_oil", PVT_KNOWLEDGE_BASE)
        self.assertIn("gas_condensate", PVT_KNOWLEDGE_BASE)
        self.assertEqual(PVT_KNOWLEDGE_BASE["black_oil"]["confidence"], "High")

    def test_pvt_calculators(self):
        pb = calculate_bubble_point(0.65, 35.0, 180.0, 600.0)
        self.assertGreater(pb, 0)

        bo = calculate_oil_fvf(35.0, 0.65, 180.0, 600.0, method="standing")
        self.assertGreater(bo, 1.0)

        z = calculate_z_factor(3500.0, 180.0, 0.65)
        self.assertGreaterEqual(z, 0.5)

        bg = calculate_gas_fvf(3500.0, 180.0, z)
        self.assertGreater(bg, 0)

    def test_pvt_engine(self):
        eval_res = PVTEngine.evaluate_fluid_properties({
            "fluid_type": "black_oil",
            "api_gravity": 35.0,
            "gas_gravity": 0.65,
            "temperature_f": 180.0,
            "pressure_psia": 3500.0,
            "rs_scf_stb": 600.0,
            "has_lab_data": False
        })
        self.assertEqual(eval_res["fluid_type"], "black_oil")
        self.assertIn("bubble_point_psia", eval_res)

    def test_plugin_registration(self):
        plugin = PluginManager.get_plugin("PVTPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.discipline, "PVT")

    def test_calculator_manager(self):
        res = CalculatorManager.run_calculation("bubble_point", 0.65, 35.0, 180.0, 600.0)
        self.assertGreater(res, 0)

if __name__ == "__main__":
    unittest.main()
