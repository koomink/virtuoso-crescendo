from datetime import UTC, datetime, timedelta
from pathlib import Path

from maestro.sdk import BaseStrategyPlugin, DataBundle, StrategyContext, TargetAllocationResult

from snowball.strategy import SnowballStrategy


def test_snowball_strategy_contract_and_ticker_overrides():
    strategy = SnowballStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="snowball",
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

    source = Path("src/snowball/strategy.py").read_text()
    assert "from maestro.sdk import" in source
    assert "maestro.portfolio" not in source
    assert "maestro.execution" not in source
    assert "maestro.datahub" not in source
    assert "yfinance" not in source.lower()


def test_slot_override_takes_precedence_over_global_override():
    strategy = SnowballStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="snowball",
        config={
            "selected_strategies": ["dga"],
            "ticker_overrides": {"QQQ": "QQQM"},
            "slot_overrides": {"dga.offensive.QQQ": "QLD"},
        },
    )

    requests = strategy.build_data_requests(context)

    assert "QLD" in {request.symbol for request in requests}
    assert "QQQM" not in {request.symbol for request in requests}


def test_snowball_runs_four_default_strategies_with_books():
    strategy = SnowballStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="snowball",
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


def test_dga_treats_dividend_yield_above_one_as_percent_value():
    strategy = SnowballStrategy()
    context = StrategyContext(
        cycle_id="test",
        timestamp=datetime.now(UTC),
        run_mode="paper",
        strategy_id="snowball",
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


def _rising_prices() -> list[float]:
    return [100 + index for index in range(14)]


def result_data_bundle(data: dict) -> DataBundle:
    return DataBundle(requests=[], data=data, generated_at=datetime.now(UTC), source="test")


def _symbol_data(symbol: str, closes: list[float]) -> dict:
    start = datetime(2025, 1, 31, tzinfo=UTC)
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
