import math
import unittest

from handlers import text_handlers as th
from services.gas_lift_engine import GasLiftEngine, GasLiftError, GasLiftInput


class TestGasLiftEngineV1(unittest.TestCase):
    def setUp(self):
        self.engine = GasLiftEngine()
        self.base = GasLiftInput(
            thp_psia=100.0,
            tvd_ft=8000.0,
            injection_pressure_psia=1200.0,
            gas_injection_rate_mscfd=1000.0,
            gas_specific_gravity=0.65,
            average_temperature_f=180.0,
            liquid_rate_stbd=3000.0,
            reservoir_pressure_psia=3000.0,
            productivity_index_stbd_psi=1.5,
        )

    def test_known_reference_case_is_deterministic_and_units_are_explicit(self):
        result = self.engine.calculate(self.base)
        self.assertEqual(result.status, "OK")
        self.assertAlmostEqual(result.injection_depth_ft, 8000.0, places=6)
        self.assertAlmostEqual(result.thp_psia, 100.0)
        self.assertAlmostEqual(result.tvd_ft, 8000.0)
        self.assertGreater(result.injected_gas_in_situ_bpd, 0.0)
        self.assertGreater(result.predicted_liquid_rate_stbd, 0.0)
        self.assertGreater(result.predicted_oil_rate_stbd, 0.0)
        self.assertLess(result.bottomhole_pressure_with_lift_psia,
                        result.bottomhole_pressure_without_lift_psia)
        self.assertIn("steady-state pressure-balance", result.provenance)

    def test_repeatability(self):
        first = self.engine.calculate(self.base)
        second = self.engine.calculate(self.base)
        self.assertEqual(first, second)

    def test_lower_available_injection_pressure_moves_point_shallower(self):
        result = self.engine.calculate(
            GasLiftInput(
                thp_psia=100.0,
                tvd_ft=8000.0,
                injection_pressure_psia=300.0,
                gas_injection_rate_mscfd=1000.0,
                gas_specific_gravity=0.65,
                average_temperature_f=180.0,
                liquid_rate_stbd=3000.0,
            )
        )
        self.assertGreater(result.injection_depth_ft, 0.0)
        self.assertLess(result.injection_depth_ft, 8000.0)
        self.assertLessEqual(abs(result.pressure_margin_at_injection_psi), 0.01)

    def test_requested_depth_requires_pressure_balance(self):
        with self.assertRaisesRegex(GasLiftError, "PHYSICALLY_INVALID_STATE"):
            self.engine.calculate(
                GasLiftInput(
                    thp_psia=100.0,
                    tvd_ft=8000.0,
                    injection_pressure_psia=200.0,
                    gas_injection_rate_mscfd=1000.0,
                    gas_specific_gravity=0.65,
                    average_temperature_f=180.0,
                    liquid_rate_stbd=3000.0,
                    injection_depth_ft=8000.0,
                )
            )

    def test_invalid_fraction_and_negative_pressure_are_rejected(self):
        with self.assertRaisesRegex(GasLiftError, "INVALID_INPUT"):
            self.engine.calculate(self.base.__class__(**{
                **self.base.__dict__, "water_cut": 1.2
            }))
        with self.assertRaisesRegex(GasLiftError, "INVALID_INPUT"):
            self.engine.calculate(self.base.__class__(**{
                **self.base.__dict__, "thp_psia": 0.0
            }))

    def test_applicability_limit_is_typed(self):
        with self.assertRaisesRegex(GasLiftError, "CORRELATION_LIMITATION"):
            self.engine.calculate(self.base.__class__(**{
                **self.base.__dict__, "tvd_ft": 40000.0
            }))

    def test_no_pressure_balance_is_typed_as_numerical_failure(self):
        with self.assertRaisesRegex(GasLiftError, "NUMERICAL_NON_CONVERGENCE"):
            self.engine.calculate(self.base.__class__(**{
                **self.base.__dict__, "injection_pressure_psia": 50.0
            }))

    def test_provider_seam_is_reserved_for_increment_9(self):
        with self.assertRaisesRegex(GasLiftError, "reserved for Increment 9"):
            self.engine.calculate(self.base, pvt_provider=object(), pvt_context={})


class TestGasLiftTelegramContract(unittest.TestCase):
    VALID = (
        "/calc gas_lift thp=100 tvd=8000 p_inj=1200 q_gas=1000 "
        "gamma_g=0.65 t_avg=180 q_liquid=3000 pr=3000 j=1.5"
    )

    def test_valid_route_and_professional_result(self):
        text, png, caption = th.handle_calc({"text": self.VALID}, None)
        self.assertIsNone(png)
        self.assertIsNone(caption)
        self.assertIn("Gas-Lift Calculation Result", text)
        self.assertIn("Injection depth", text)
        self.assertIn("ENGINEERING STATUS", text)
        self.assertIn("Status: OK", text)
        self.assertIn("psia", text)
        self.assertIn("Mscf/day", text)
        self.assertNotIn("Traceback", text)

    def test_invalid_route_returns_typed_error_without_traceback(self):
        text, png, caption = th.handle_calc(
            {"text": "/calc gas_lift thp=-1 tvd=8000 p_inj=1200 q_gas=1000 "
                     "gamma_g=0.65 t_avg=180 q_liquid=3000"},
            None,
        )
        self.assertIsNone(png)
        self.assertIsNone(caption)
        self.assertTrue(text.startswith("Error: INVALID_INPUT:"))
        self.assertNotIn("Traceback", text)

    def test_missing_input_is_typed(self):
        text, _, _ = th.handle_calc(
            {"text": "/calc gas_lift thp=100 tvd=8000"}, None
        )
        self.assertTrue(text.startswith("Error: INSUFFICIENT_INPUT:"))

    def test_black_oil_options_are_not_accepted_in_increment_8(self):
        text, _, _ = th.handle_calc(
            {"text": self.VALID + " pvt_mode=pressure_dependent"}, None
        )
        self.assertTrue(text.startswith("Error: INVALID_INPUT:"))
        self.assertIn("reserved for Increment 9", text)

    def test_legacy_screening_module_is_not_replaced(self):
        from services.artificial_lift_engine import ArtificialLiftEngine
        self.assertTrue(hasattr(ArtificialLiftEngine, "screen_lift_system"))


if __name__ == "__main__":
    unittest.main()
