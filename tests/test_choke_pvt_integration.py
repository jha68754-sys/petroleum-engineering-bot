from dataclasses import replace

import pytest

from handlers import text_handlers as th
from services.black_oil_pvt import BlackOilPvtProvider
from services.choke_engine import ChokeEngine, ChokeError, ChokeInput


BASE = ChokeInput(
    upstream_pressure_psia=1000.0,
    downstream_pressure_psia=200.0,
    choke_size_64th_in=16.0,
    gor_scf_stb=1000.0,
    liquid_rate_bpd=1000.0,
    oil_api=35.0,
    gas_specific_gravity=0.65,
    choke_model="gilbert_1954",
)

PVT_CONTEXT = {
    "pressure_psia": 2000.0,
    "temperature_f": 180.0,
    "oil_api": 35.0,
    "gas_specific_gravity": 0.65,
    "separator_pressure_psia": 100.0,
    "separator_temperature_f": 60.0,
    "bubble_point_psia": 1800.0,
}

PVT_ARGS = (
    "pvt_mode=pressure_dependent pvt_model=black_oil_v1 "
    "pvt_pressure_psia=2000 pvt_temperature_f=180 pvt_oil_api=35 "
    "pvt_gas_specific_gravity=0.65 pvt_separator_pressure_psia=100 "
    "pvt_separator_temperature_f=60 pvt_bubble_point_psia=1800"
)

VALID_COMMAND = (
    "/calc choke choke_model=gilbert_1954 p_up=1000 p_down=200 "
    "choke=16 gor=1000 q_liquid=1000 " + PVT_ARGS
)


class RecordingProvider(BlackOilPvtProvider):
    def __init__(self):
        super().__init__()
        self.states = []

    def evaluate(self, state):
        self.states.append(state)
        return super().evaluate(state)


def test_a_legacy_choke_result_is_unchanged_and_has_no_pvt_metadata():
    result = ChokeEngine().calculate(BASE, pvt_provider=None, pvt_context=None)

    assert result.status == "OK"
    assert result.calculated_rate_bpd == pytest.approx(427.43, abs=0.01)
    assert result.pressure_ratio == pytest.approx(0.2, abs=1e-12)
    assert result.pvt_metadata == {}
    assert any("Black-Oil PVT: Not required" in item for item in result.limitations)


def test_b_explicit_selector_binds_the_existing_black_oil_provider():
    text, png, error = th.handle_calc({"text": VALID_COMMAND}, None)

    assert png is None
    assert error is None
    assert "PVT Mode: pressure_dependent" in text
    assert "PVT Model: black_oil_v1" in text
    assert "PVT Provider: BlackOilPvtProvider" in text
    assert "Pressure-Dependent PVT Provenance" in text
    assert "PVT Status: OK\\nNOTE: Results are CALCULATED" in text
    assert "Traceback" not in text


def test_c_valid_black_oil_choke_is_deterministic_and_evaluated_at_upstream_pressure():
    provider = RecordingProvider()
    result = ChokeEngine().calculate(BASE, pvt_provider=provider, pvt_context=PVT_CONTEXT)

    assert result.status == "OK"
    assert result.calculated_rate_bpd == pytest.approx(427.43, abs=0.01)
    assert result.pvt_metadata["enabled"] is True
    assert result.pvt_metadata["provider"] == "RecordingProvider"
    assert result.pvt_metadata["evaluation_strategy"] == "upstream_choke_pressure"
    assert result.pvt_metadata["properties_consumed"] == []
    assert result.pvt_metadata["evaluation_points"] == [
        {"name": "upstream_choke", "pressure_psia": 1000.0, "temperature_f": 180.0}
    ]
    assert [state.pressure_psia for state in provider.states] == [1000.0]


def test_d_required_black_oil_context_is_validated():
    with pytest.raises(ChokeError, match="INSUFFICIENT_DATA"):
        ChokeEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=None)

    text, png, error = th.handle_calc(
        {"text": VALID_COMMAND.replace("pvt_bubble_point_psia=1800", "")},
        None,
    )
    assert png is None
    assert error is None
    assert "pressure-dependent Black-Oil PVT is missing" in text
    assert "Choke Performance" not in text
    assert "Traceback" not in text


def test_e_invalid_physical_pvt_state_is_typed():
    invalid = dict(PVT_CONTEXT)
    invalid["temperature_f"] = -500.0

    with pytest.raises(ChokeError, match="PHYSICALLY_INVALID_STATE"):
        ChokeEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=invalid)

    text, png, error = th.handle_calc(
        {"text": VALID_COMMAND.replace("pvt_pressure_psia=2000", "pvt_pressure_psia=-1")},
        None,
    )
    assert png is None
    assert error is None
    assert "PHYSICALLY_INVALID_STATE" in text
    assert "Choke Performance" not in text
    assert "Traceback" not in text


def test_f_unsupported_pvt_mode_fails_without_legacy_fallback():
    command = VALID_COMMAND.replace("pvt_mode=pressure_dependent", "pvt_mode=legacy")
    text, png, error = th.handle_calc({"text": command}, None)

    assert png is None
    assert error is None
    assert "unsupported pvt_mode" in text
    assert "Choke Performance" not in text


def test_g_unsupported_pvt_model_fails_without_legacy_fallback():
    command = VALID_COMMAND.replace("pvt_model=black_oil_v1", "pvt_model=black_oil_v2")
    text, png, error = th.handle_calc({"text": command}, None)

    assert png is None
    assert error is None
    assert "unsupported pvt_model" in text
    assert "Choke Performance" not in text


def test_h_explicit_provider_failure_never_returns_legacy_result():
    provider = BlackOilPvtProvider()
    provider.DAK_MAX_ITERATIONS = 0

    with pytest.raises(ChokeError, match="NUMERICAL_NON_CONVERGENCE"):
        ChokeEngine().calculate(BASE, pvt_provider=provider, pvt_context=PVT_CONTEXT)

    text, png, error = th.handle_calc(
        {"text": VALID_COMMAND.replace("pvt_pressure_psia=2000", "pvt_pressure_psia=-1")},
        None,
    )
    assert png is None
    assert error is None
    assert "Choke Performance" not in text
    assert "Traceback" not in text


def test_i_choke_pressure_relationship_remains_physically_valid():
    result = ChokeEngine().calculate(BASE, pvt_provider=BlackOilPvtProvider(), pvt_context=PVT_CONTEXT)
    assert result.upstream_pressure_psia > result.downstream_pressure_psia
    assert result.pressure_ratio == pytest.approx(
        result.downstream_pressure_psia / result.upstream_pressure_psia,
        abs=1e-12,
    )
    assert result.upstream_pressure_psia - result.downstream_pressure_psia == pytest.approx(
        800.0,
        abs=1e-12,
    )

    with pytest.raises(ChokeError, match="upstream_pressure_psia must be greater"):
        ChokeEngine().calculate(
            replace(BASE, downstream_pressure_psia=1000.0),
            pvt_provider=BlackOilPvtProvider(),
            pvt_context=PVT_CONTEXT,
        )


def test_j_correlation_limitations_remain_visible_and_typed():
    limited = dict(PVT_CONTEXT)
    limited["non_hydrocarbon_fraction"] = 0.05
    result = ChokeEngine().calculate(
        BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=limited,
    )

    assert result.status == "OK"
    assert result.pvt_metadata["statuses"] == ["CORRELATION_LIMITATION"]
    assert result.pvt_metadata["limitations"]
    assert any("sour-gas" in item for item in result.pvt_metadata["limitations"])


def test_k_repeated_identical_black_oil_input_is_exactly_repeatable():
    first = ChokeEngine().calculate(
        BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )
    second = ChokeEngine().calculate(
        BASE,
        pvt_provider=BlackOilPvtProvider(),
        pvt_context=PVT_CONTEXT,
    )

    assert first == second
    assert first.pvt_metadata["pressure_range_psia"] == [1000.0, 1000.0]
    assert first.pvt_metadata["pvt_evaluations"] == 1


def test_context_without_provider_is_rejected_deterministically():
    with pytest.raises(ChokeError, match="pvt_context cannot be supplied"):
        ChokeEngine().calculate(BASE, pvt_provider=None, pvt_context=PVT_CONTEXT)


def test_legacy_handler_has_no_black_oil_provenance():
    command = "/calc choke p_up=1000 p_down=200 choke=16 gor=1000 q_liquid=1000"
    text, png, error = th.handle_calc({"text": command}, None)

    assert png is None
    assert error is None
    assert "Status: OK" in text
    assert "PVT Provider: BlackOilPvtProvider" not in text
    assert "Pressure-Dependent PVT Provenance" not in text
