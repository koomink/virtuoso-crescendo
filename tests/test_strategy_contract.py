from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from maestro.sdk import BaseStrategyPlugin, DataBundle, StrategyContext, TargetAllocationResult

from crescendo.strategy import CrescendoStrategy


def test_crescendo_strategy_contract_and_ticker_overrides():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={
            "selected_strategies": ["accelerated_dual_momentum"],
            "ticker_overrides": {
                "SPY": "QQQM",
                "SCZ": "QLD",
                "TLT": "TMF",
                "TIP": "STIP",
            },
        },
    )

    requests = strategy.build_data_requests(context)
    symbols = {request.symbol for request in requests}
    result = strategy.run(
        DataBundle(
            requests=requests,
            data={
                "QQQM": _symbol_data("QQQM", [100, 101, 102, 103, 104, 105, 106]),
                "QLD": _symbol_data("QLD", [100, 102, 104, 106, 108, 110, 112]),
                "TMF": _symbol_data("TMF", [100, 100, 100, 100, 100, 100, 101]),
                "STIP": _symbol_data("STIP", [100, 100, 100, 100, 100, 100, 100]),
            },
            generated_at=datetime.now(UTC),
            source="test",
        ),
        context,
    )

    assert isinstance(strategy, BaseStrategyPlugin)
    assert isinstance(result, TargetAllocationResult)
    assert strategy.manifest().sdk_contract_version == "1.1"
    assert strategy.manifest().result_type == "target_allocation"
    assert symbols == {"QQQM", "QLD", "TMF", "STIP"}
    assert result.allocations == {"QLD": 1.0}
    assert result.strategy_books[0].book_id == "accelerated_dual_momentum"
    assert result.strategy_books[0].allocations == {"QLD": 1.0}

    source = (Path(__file__).parents[1] / "src" / "crescendo" / "strategy.py").read_text()
    assert "from maestro.sdk import" in source
    assert "maestro.portfolio" not in source
    assert "maestro.execution" not in source
    assert "maestro.datahub" not in source
    assert "yfinance" not in source.lower()


def test_crescendo_requests_daily_ohlcv_for_price_based_strategies():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={},
    )

    requests = strategy.build_data_requests(context)
    ohlcv_requests = [request for request in requests if request.data_type == "ohlcv"]

    assert ohlcv_requests
    assert {request.timeframe for request in ohlcv_requests} == {"1d"}
    assert all((request.lookback or 0) >= 420 for request in ohlcv_requests)


def test_adm_uses_daily_prices_before_signal_date():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["accelerated_dual_momentum"]},
    )
    data = {
        "SPY": _dated_symbol_data(
            "SPY",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 105),
                ("2026-05-01", 200),
            ],
        ),
        "SCZ": _dated_symbol_data(
            "SCZ",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 106),
                ("2026-05-01", 90),
            ],
        ),
        "TLT": _dated_symbol_data("TLT", [("2026-03-31", 100), ("2026-04-30", 101)]),
        "TIP": _dated_symbol_data("TIP", [("2026-03-31", 100), ("2026-04-30", 100)]),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    assert result.allocations == {"SCZ": 1.0}


def test_execution_override_maps_only_emitted_allocations_not_signals():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={
            "selected_strategies": ["accelerated_dual_momentum"],
            "execution_overrides": {"accelerated_dual_momentum.offensive.SPY": "SSO"},
        },
    )
    # Signal data only exists for SPY/SCZ: the winner must be picked from
    # SPY prices while the emitted allocation is swapped to SSO.
    data = {
        "SPY": _dated_symbol_data(
            "SPY",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 120),
            ],
        ),
        "SCZ": _dated_symbol_data(
            "SCZ",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 105),
            ],
        ),
        "TLT": _dated_symbol_data("TLT", [("2026-03-31", 100), ("2026-04-30", 101)]),
        "TIP": _dated_symbol_data("TIP", [("2026-03-31", 100), ("2026-04-30", 100)]),
    }

    requests = strategy.build_data_requests(context)
    result = strategy.run(
        DataBundle(
            requests=requests,
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    request_symbols = {request.symbol for request in requests}
    assert "SSO" in request_symbols
    assert "SPY" in request_symbols
    sso_request = next(request for request in requests if request.symbol == "SSO")
    assert sso_request.intended_use == "tradable"

    assert result.allocations == {"SSO": 1.0}
    book = result.strategy_books[0]
    assert book.allocations == {"SSO": 1.0}
    assert book.metadata["signal_allocations"] == {"SPY": 1.0}
    assert "SPY" in book.rationale


def test_execution_override_leaves_non_overridden_winner_untouched():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={
            "selected_strategies": ["accelerated_dual_momentum"],
            "execution_overrides": {"accelerated_dual_momentum.offensive.SPY": "SSO"},
        },
    )
    data = {
        "SPY": _dated_symbol_data(
            "SPY",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 105),
            ],
        ),
        "SCZ": _dated_symbol_data(
            "SCZ",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 120),
            ],
        ),
        "TLT": _dated_symbol_data("TLT", [("2026-03-31", 100), ("2026-04-30", 101)]),
        "TIP": _dated_symbol_data("TIP", [("2026-03-31", 100), ("2026-04-30", 100)]),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    assert result.allocations == {"SCZ": 1.0}
    assert "signal_allocations" not in result.strategy_books[0].metadata


def test_books_carry_signal_evidence_and_state():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["accelerated_dual_momentum"]},
    )
    data = {
        "SPY": _dated_symbol_data(
            "SPY",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 120),
            ],
        ),
        "SCZ": _dated_symbol_data(
            "SCZ",
            [
                ("2025-10-31", 100),
                ("2026-01-30", 100),
                ("2026-03-31", 100),
                ("2026-04-30", 105),
            ],
        ),
        "TLT": _dated_symbol_data("TLT", [("2026-03-31", 100), ("2026-04-30", 101)]),
        "TIP": _dated_symbol_data("TIP", [("2026-03-31", 100), ("2026-04-30", 100)]),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    book = result.strategy_books[0]
    assert book.metadata["book_state"] == "risk_on"
    evidence = book.metadata["signal_evidence"]
    assert isinstance(evidence, list) and evidence
    assert {"label", "detail", "status"} <= set(evidence[0])
    statuses = {gate["status"] for gate in evidence}
    assert statuses <= {"pass", "fail", "info"}
    top_gate = next(gate for gate in evidence if gate["label"].startswith("top momentum"))
    assert top_gate["status"] == "pass"


def test_execution_override_rejects_unknown_slot():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={
            "selected_strategies": ["accelerated_dual_momentum"],
            "execution_overrides": {"accelerated_dual_momentum.offensive.QQQ": "QLD"},
        },
    )

    with pytest.raises(ValueError, match="Unknown execution_overrides slot"):
        strategy.build_data_requests(context)


def test_month_based_sma_uses_monthly_endpoints_before_signal_date():
    strategy = CrescendoStrategy()
    as_of = datetime(2026, 5, 1, tzinfo=UTC)
    bundle = result_data_bundle(
        {
            "SPY": _dated_symbol_data(
                "SPY",
                [
                    ("2026-01-30", 100),
                    ("2026-02-13", 1000),
                    ("2026-02-27", 110),
                    ("2026-03-16", 1),
                    ("2026-03-31", 120),
                    ("2026-04-15", 1000),
                    ("2026-04-30", 130),
                    ("2026-05-01", 1000),
                ],
            )
        }
    )

    assert strategy._sma("SPY", bundle, 3, as_of) == 120


def test_month_based_sma_uses_last_available_close_when_month_end_is_closed():
    strategy = CrescendoStrategy()
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    bundle = result_data_bundle(
        {
            "SPY": _dated_symbol_data(
                "SPY",
                [
                    ("2026-03-31", 100),
                    ("2026-04-30", 200),
                    ("2026-05-29", 300),
                    ("2026-06-01", 1000),
                ],
            )
        }
    )

    assert strategy._sma("SPY", bundle, 3, as_of) == 200


def test_slot_override_takes_precedence_over_global_override():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={
            "selected_strategies": ["dga"],
            "ticker_overrides": {"QQQ": "QQQM"},
            "slot_overrides": {"dga.offensive.QQQ": "QLD"},
        },
    )

    requests = strategy.build_data_requests(context)

    assert "QLD" in {request.symbol for request in requests}
    assert "QQQM" not in {request.symbol for request in requests}


def test_crescendo_runs_four_default_strategies_with_books():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={},
    )
    requests = strategy.build_data_requests(context)
    symbols = {request.symbol for request in requests}
    data = {
        symbol: _symbol_data(symbol, _rising_prices())
        for symbol in symbols
        if symbol not in {"UNRATE", "T10Y3M"}
    }
    data["UNRATE"] = _macro_data("UNRATE", [4.0] * 13)
    data["T10Y3M"] = _macro_data("T10Y3M", [0.5] * 13)
    data["SPY"]["metrics"] = {"dividend_yield": 0.02}

    result = strategy.run(
        DataBundle(requests=requests, data=data, generated_at=datetime.now(UTC), source="test"),
        context,
    )

    assert set(result.allocations)
    assert round(sum(result.allocations.values()), 10) == 1.0
    assert {book.book_id for book in result.strategy_books} == {
        "dga",
        "accelerated_dual_momentum",
        "gtt_ue",
        "baa_a",
    }
    assert round(sum(book.target_weight for book in result.strategy_books), 10) == 1.0


def test_crescendo_can_emit_usd_sleeve_for_live_approval():
    strategy = CrescendoStrategy()
    manifest = strategy.manifest()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="live_approval",
        strategy_id="crescendo",
        config={
            "sleeve": "USD",
            "selected_strategies": ["accelerated_dual_momentum"],
        },
    )
    data = {
        "SPY": _symbol_data("SPY", [100, 101, 102, 103, 104, 105, 106]),
        "SCZ": _symbol_data("SCZ", [100, 102, 104, 106, 108, 110, 112]),
        "TLT": _symbol_data("TLT", [100, 100, 100, 100, 100, 100, 101]),
        "TIP": _symbol_data("TIP", [100, 100, 100, 100, 100, 100, 100]),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime.now(UTC),
            source="test",
        ),
        context,
    )

    assert "live_approval" in manifest.supported_modes
    assert manifest.can_run_live is True
    assert result.allocations == {}
    assert result.allocation_sleeves == {"USD": {"SCZ": 1.0}}


def test_dga_fundamental_request_uses_context_timestamp_as_of():
    strategy = CrescendoStrategy()
    timestamp = datetime(2026, 5, 1, tzinfo=UTC)
    context = StrategyContext(
        cycle_id="test",
        timestamp=timestamp,
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["dga"]},
    )

    requests = strategy.build_data_requests(context)
    dividend_request = next(
        request
        for request in requests
        if request.symbol == "SPY" and request.data_type == "fundamental"
    )

    assert dividend_request.fields == ["dividend_yield"]
    assert dividend_request.as_of == timestamp


def test_dga_fails_when_dividend_yield_metric_is_missing():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["dga"]},
    )
    data = {
        "QQQ": _symbol_data("QQQ", [100 + index for index in range(14)]),
        "SCHD": _symbol_data("SCHD", [100 + index * 0.5 for index in range(14)]),
        "BIL": _symbol_data("BIL", [100 + index * 0.1 for index in range(14)]),
        "TLT": _symbol_data("TLT", [100 - index * 0.1 for index in range(14)]),
        "PDBC": _symbol_data("PDBC", [100 + index * 2 for index in range(14)]),
        "TIP": _symbol_data("TIP", [100 + index * 0.2 for index in range(14)]),
        "SPY": _symbol_data("SPY", [100 + index for index in range(14)]),
        "T10Y3M": _macro_data("T10Y3M", [0.5] * 13),
    }

    with pytest.raises(ValueError, match="Missing dividend_yield"):
        strategy.run(
            DataBundle(
                requests=strategy.build_data_requests(context),
                data=data,
                generated_at=datetime.now(UTC),
                source="test",
            ),
            context,
        )


def test_dga_treats_dividend_yield_above_one_as_percent_value():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["dga"]},
    )
    data = {
        "QQQ": _symbol_data("QQQ", [100 + index for index in range(14)]),
        "SCHD": _symbol_data("SCHD", [100 + index * 0.5 for index in range(14)]),
        "BIL": _symbol_data("BIL", [100 + index * 0.1 for index in range(14)]),
        "TLT": _symbol_data("TLT", [100 - index * 0.1 for index in range(14)]),
        "PDBC": _symbol_data("PDBC", [100 + index * 2 for index in range(14)]),
        "TIP": _symbol_data("TIP", [100 + index * 0.2 for index in range(14)]),
        "SPY": _symbol_data("SPY", [100 + index for index in range(14)]),
        "T10Y3M": _macro_data("T10Y3M", [0.5] * 13),
    }
    data["SPY"]["metrics"] = {"dividend_yield": 1.03}

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime.now(UTC),
            source="test",
        ),
        context,
    )

    assert strategy._dividend_yield("SPY", result_data_bundle(data)) == 0.0103
    assert result.allocations == {"PDBC": 1.0}


def test_dga_defensive_ranking_uses_monthly_endpoint_average():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["dga"]},
    )
    data = {
        "QQQ": _monthly_symbol_data("QQQ", [100, 100, 100, 100, 100, 100, 100]),
        "SCHD": _monthly_symbol_data("SCHD", [100, 100, 100, 100, 100, 100, 100]),
        "BIL": _monthly_symbol_data("BIL", [100, 100, 100, 100, 100, 100, 100]),
        "TLT": _monthly_symbol_data("TLT", [100, 100, 100, 100, 100, 100, 110]),
        "PDBC": _monthly_symbol_data("PDBC", [90, 90, 90, 90, 90, 90, 120]),
        "TIP": _monthly_symbol_data("TIP", [100] * 12 + [80]),
        "SPY": _monthly_symbol_data("SPY", [100] * 13),
        "T10Y3M": _macro_data("T10Y3M", [0.5] * 13),
    }
    data["SPY"]["metrics"] = {"dividend_yield": 0.02}

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    assert result.allocations == {"PDBC": 1.0}


def test_gtt_ue_keeps_strict_unemployment_threshold_with_monthly_endpoint_trend():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["gtt_ue"]},
    )
    data = {
        "SPY": _monthly_symbol_data("SPY", [100] * 10 + [90]),
        "UNRATE": _macro_data("UNRATE", [4.0] * 13),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    assert result.allocations == {"SPY": 1.0}


def test_gtt_ue_result_is_unaffected_by_macro_observation_input_order():
    def _run(observations: list[dict]) -> dict:
        strategy = CrescendoStrategy()
        context = StrategyContext(
            cycle_id="test",
            timestamp=datetime(2026, 5, 1, tzinfo=UTC),
            run_mode="paper",
            strategy_id="crescendo",
            config={"selected_strategies": ["gtt_ue"]},
        )
        data = {
            "SPY": _monthly_symbol_data("SPY", [100] * 10 + [90]),
            "UNRATE": {
                "series_id": "UNRATE",
                "observations": observations,
                "source": "test",
            },
        }
        result = strategy.run(
            DataBundle(
                requests=strategy.build_data_requests(context),
                data=data,
                generated_at=datetime(2026, 5, 1, tzinfo=UTC),
                source="test",
            ),
            context,
        )
        return result.allocations

    chronological_observations = [
        {"date": f"2025-{index + 1:02d}-01", "value": 4.0, "source": "test"} for index in range(12)
    ] + [{"date": "2026-01-01", "value": 5.0, "source": "test"}]
    reversed_observations = list(reversed(chronological_observations))

    forward_result = _run(chronological_observations)
    reverse_result = _run(reversed_observations)

    assert forward_result == reverse_result
    assert forward_result == {"CASH_USD": 1.0}


def test_baa_offensive_ranking_uses_monthly_endpoint_average():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["baa_a"]},
    )
    data = {
        "QQQ": _monthly_symbol_data("QQQ", [100] * 12 + [108]),
        "EFA": _monthly_symbol_data(
            "EFA",
            [100] * 12 + [110],
            extra_bars=[("2026-04-15", 1000)],
        ),
        "EEM": _monthly_symbol_data("EEM", [90] * 12 + [110]),
        "AGG": _monthly_symbol_data("AGG", [100] * 12 + [101]),
        "SPY": _monthly_symbol_data("SPY", [100] * 12 + [110]),
        "BIL": _monthly_symbol_data("BIL", [100] * 13),
        "IEF": _monthly_symbol_data("IEF", [100] * 13),
        "TLT": _monthly_symbol_data("TLT", [100] * 13),
        "TIP": _monthly_symbol_data("TIP", [100] * 13),
        "LQD": _monthly_symbol_data("LQD", [100] * 13),
        "PDBC": _monthly_symbol_data("PDBC", [100] * 13),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    assert result.allocations == {"EEM": 1.0}


def test_baa_defensive_failed_sleeves_fall_back_to_bil_proxy():
    strategy = CrescendoStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        run_mode="paper",
        strategy_id="crescendo",
        config={"selected_strategies": ["baa_a"]},
    )
    data = {
        "SPY": _monthly_symbol_data("SPY", [120] * 12 + [100]),
        "EEM": _monthly_symbol_data("EEM", [120] * 12 + [100]),
        "EFA": _monthly_symbol_data("EFA", [120] * 12 + [100]),
        "AGG": _monthly_symbol_data("AGG", [200] * 12 + [190]),
        "BIL": _monthly_symbol_data("BIL", [100] * 12 + [50]),
        "IEF": _monthly_symbol_data("IEF", [180] * 12 + [170]),
        "TLT": _monthly_symbol_data("TLT", [100] * 12 + [80]),
        "TIP": _monthly_symbol_data("TIP", [100] * 12 + [70]),
        "LQD": _monthly_symbol_data("LQD", [100] * 12 + [60]),
        "PDBC": _monthly_symbol_data("PDBC", [100] * 12 + [120]),
        "QQQ": _monthly_symbol_data("QQQ", [100] * 13),
    }

    result = strategy.run(
        DataBundle(
            requests=strategy.build_data_requests(context),
            data=data,
            generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="test",
        ),
        context,
    )

    assert result.allocations == {
        "PDBC": pytest.approx(1.0 / 3.0),
        "BIL": pytest.approx(2.0 / 3.0),
    }


def _rising_prices() -> list[float]:
    return [100 + index for index in range(14)]


def result_data_bundle(data: dict) -> DataBundle:
    return DataBundle(requests=[], data=data, generated_at=datetime.now(UTC), source="test")


def _symbol_data(symbol: str, closes: list[float]) -> dict:
    latest = datetime(2026, 5, 27, tzinfo=UTC)
    start = latest - timedelta(days=30 * (len(closes) - 1))
    return {
        "symbol": symbol,
        "bars": [
            {
                "symbol": symbol,
                "timestamp": (start + timedelta(days=30 * index)).isoformat(),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000,
                "source": "test",
            }
            for index, close in enumerate(closes)
        ],
        "latest_price": {
            "symbol": symbol,
            "timestamp": start.isoformat(),
            "price": closes[-1],
            "source": "test",
        },
    }


def _dated_symbol_data(symbol: str, closes: list[tuple[str, float]]) -> dict:
    return {
        "symbol": symbol,
        "bars": [
            {
                "symbol": symbol,
                "timestamp": f"{timestamp}T00:00:00+00:00",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000,
                "source": "test",
            }
            for timestamp, close in closes
        ],
        "latest_price": {
            "symbol": symbol,
            "timestamp": f"{closes[-1][0]}T00:00:00+00:00",
            "price": closes[-1][1],
            "source": "test",
        },
    }


def _monthly_symbol_data(
    symbol: str,
    closes: list[float],
    extra_bars: list[tuple[str, float]] | None = None,
) -> dict:
    dates = [
        "2025-04-30",
        "2025-05-30",
        "2025-06-30",
        "2025-07-31",
        "2025-08-29",
        "2025-09-30",
        "2025-10-31",
        "2025-11-28",
        "2025-12-31",
        "2026-01-30",
        "2026-02-27",
        "2026-03-31",
        "2026-04-30",
    ]
    if len(closes) > len(dates):
        raise ValueError("Too many monthly closes for test helper")
    bars = list(zip(dates[-len(closes) :], closes, strict=True))
    if extra_bars:
        bars.extend(extra_bars)
    return _dated_symbol_data(symbol, sorted(bars, key=lambda item: item[0]))


def _macro_data(symbol: str, values: list[float]) -> dict:
    return {
        "series_id": symbol,
        "observations": [
            {"date": f"2025-{index + 1:02d}-01", "value": value, "source": "test"}
            for index, value in enumerate(values)
        ],
        "latest": {"date": "2026-01-01", "value": values[-1], "source": "test"},
        "source": "test",
    }
