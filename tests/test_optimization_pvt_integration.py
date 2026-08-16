"""Increment 7 pressure-dependent Black-Oil optimization integration tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ.setdefault("GROQ_API_KEY", "dummy")

from handlers import text_handlers as th
from services import nodal_engine
from services import production_optimizer as po
from services.black_oil_pvt import BlackOilPvtProvider


BASE_IPR = {
    "ipr_model": "linear", "pr": 3000.0, "pb": None, "j": 1.5,
    "j_star": None, "qmax": None, "q_test": None, "pwf_test": None,
}
BASE_VLP = {
    "thp": 100.0, "tvd": 8000.0, "tubing_id_in": 1.995,
    "gor": 1000.0, "rs": 600.0, "api": 35.0, "gamma_g": 0.65,
    "mu_l": 1.0, "bo": 1.4, "t_wh": 120.0, "geothermal": 1.5,
}
PVT_CONTEXT = {
    "pressure_psia": 2000.0,
    "temperature_f": 180.0,
    "oil_api": 35.0,
    "gas_specific_gravity": 0.65,
    "separator_pressure_psia": 100.0,
    "separator_temperature_f": 60.0,
    "bubble_point_psia": 1800.0,
}
BASE_TEXT = (
    "model=linear pr=3000 j=1.5 thp=100 tvd=8000 id=1.995 gor=1000 "
    "rs=600 api=35 gamma_g=0.65 mu_l=1 bo=1.4 t_wh=120 geothermal=1.5"
)
PVT_TEXT = BASE_TEXT + (
    " pvt_mode=pressure_dependent pvt_model=black_oil_v1"
    " pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35"
    " pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100"
    " pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)


class RecordingNodal:
    """Record calls while delegating every calculation to real NodalEngine."""

    def __init__(self):
        self.real = nodal_engine.NodalEngine()
        self.calls = []

    def solve(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.real.solve(**kwargs)


class TestIncrement7OptimizerPropagation(unittest.TestCase):
    def test_provider_context_reaches_every_candidate(self):
        opt = po.ProductionOptimizer()
        recorder = RecordingNodal()
        opt.nodal = recorder
        provider = BlackOilPvtProvider()

        result = opt.optimize(
            "thp", values=[100.0, 200.0], objective="max_oil_rate",
            base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR,
            pvt_provider=provider, pvt_context=PVT_CONTEXT,
        )

        self.assertEqual(len(result.candidates), 2)
        self.assertEqual([call["thp"] for call in recorder.calls],
                         [100.0, 200.0])
        self.assertTrue(all(call["pvt_provider"] is provider
                            for call in recorder.calls))
        self.assertTrue(all(call["pvt_context"] == PVT_CONTEXT
                            for call in recorder.calls))
        self.assertTrue(all(c.point.nodal and c.point.nodal.pvt_metadata
                            for c in result.candidates))

    def test_legacy_optimizer_has_no_provider_metadata(self):
        result = po.ProductionOptimizer().optimize(
            "thp", values=[100.0, 200.0], objective="max_oil_rate",
            base_kwargs=BASE_VLP, ipr_kwargs=BASE_IPR,
        )
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all(not c.point.nodal.pvt_metadata
                            for c in result.candidates
                            if c.point.nodal is not None))


class TestIncrement7TelegramOptimize(unittest.TestCase):
    def _o(self, text):
        return th.handle_calc_optimize({"text": text}, None)

    def test_legacy_optimize_contract_is_unchanged(self):
        text, png, err = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{BASE_TEXT}")
        self.assertIsNone(png)
        self.assertIsNone(err)
        self.assertIn("Production Optimization Result", text)
        self.assertIn("Candidate count: 2", text)
        self.assertIn("BEST FEASIBLE CANDIDATE", text)
        self.assertNotIn("Pressure-Dependent PVT Provenance", text)

    def test_pressure_dependent_optimize_has_real_candidates_and_provenance(self):
        text, png, err = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{PVT_TEXT}")
        self.assertIsNone(png)
        self.assertIsNone(err)
        self.assertIn("Production Optimization Result", text)
        self.assertIn("Candidate count: 2", text)
        self.assertIn("Feasible candidate count:", text)
        self.assertIn("thp = 100 psia", text)
        self.assertIn("thp = 200 psia", text)
        self.assertIn("BEST FEASIBLE CANDIDATE", text)
        self.assertIn("Pressure-Dependent PVT Provenance:", text)
        self.assertIn("PVT Mode: pressure_dependent", text)
        self.assertIn("PVT Model: black_oil_v1", text)
        self.assertIn("PVT Provider: BlackOilPvtProvider", text)
        self.assertIn("PVT Status: CORRELATION_LIMITATION, OK", text)
        self.assertIn("Limitations:", text)
        self.assertNotIn("traceback", text.lower())

    def test_optimizer_pvt_changes_evaluated_candidate_results(self):
        legacy, _, _ = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{BASE_TEXT}")
        pressure_dependent, _, _ = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{PVT_TEXT}")
        self.assertNotEqual(legacy, pressure_dependent)
        self.assertIn("Pressure-Dependent PVT Provenance", pressure_dependent)

    def test_missing_black_oil_state_is_rejected(self):
        text, png, err = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{BASE_TEXT} pvt_mode=pressure_dependent "
            f"pvt_model=black_oil_v1 pvt_pressure_psia=2000")
        self.assertIsNone(png)
        self.assertIsNone(err)
        self.assertIn("pressure-dependent Black-Oil PVT is missing", text)
        self.assertNotIn("Production Optimization Result", text)

    def test_unsupported_selector_is_rejected_without_fallback(self):
        text, _, _ = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{BASE_TEXT} pvt_mode=pressure_dependent pvt_model=black_oil_v2 "
            f"pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
            f"pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
            f"pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800")
        self.assertIn("unsupported pvt_model", text)
        self.assertNotIn("Production Optimization Result", text)

    def test_invalid_black_oil_state_is_case_status_not_fabricated_result(self):
        text, png, err = self._o(
            f"/calc optimize type=thp thp=100,200 objective=max_oil_rate "
            f"{BASE_TEXT} pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
            f"pvt_pressure_psia=-1 pvt_temperature_f=180 pvt_oil_api=35 "
            f"pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
            f"pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800")
        self.assertIsNone(png)
        self.assertIsNone(err)
        self.assertIn("PHYSICALLY_INVALID", text)
        self.assertIn("Candidate count: 2", text)
        self.assertNotIn("traceback", text.lower())


if __name__ == "__main__":
    unittest.main()
