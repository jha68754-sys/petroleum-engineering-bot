"""
Unit tests for petroleum_ai package.
"""

import unittest
from petroleum_ai.calculators.ooip import calculate_ooip
from petroleum_ai.calculators.ogip import calculate_ogip
from petroleum_ai.calculators.vogel import calculate_vogel_ipr
from petroleum_ai.calculators.darcy import calculate_radial_darcy_flow

class TestPetroleumAI(unittest.TestCase):

    def test_ooip(self):
        val = calculate_ooip(640, 50, 0.20, 0.25, 1.25)
        self.assertGreater(val, 0)

    def test_ogip(self):
        val = calculate_ogip(640, 50, 0.20, 0.25, 0.85)
        self.assertGreater(val, 0)

    def test_vogel(self):
        q = calculate_vogel_ipr(1000, 3000, 2000)
        self.assertGreater(q, 0)

    def test_darcy(self):
        q = calculate_radial_darcy_flow(50, 30, 3000, 2000, 1.2, 1.1, 1000, 0.5, 0.0)
        self.assertGreater(q, 0)

if __name__ == "__main__":
    unittest.main()
