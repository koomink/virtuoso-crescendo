"""Generate the dashboard book-performance cache.

Fetches market data (yfinance + FRED), reads the live crescendo
execution_overrides from the signal config, runs the per-book backtest with
those overrides applied, and writes monthly equity series + metrics to a JSON
cache consumed by the Maestro dashboard (Virtuoso tab, Strategy Books panel).

Usage:
    python generate_book_performance.py \
        --signal-config /root/maestro-operator/symphony_signal.yaml \
        --data-dir /root/maestro-operator/var/backtest_data \
        --output /root/maestro-operator/var/book_performance.json

Data fetch failures fall back to the existing cache in --data-dir so a
transient network problem degrades to slightly stale curves instead of a
missing panel.
"""

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leverage_comparison import (  # noqa: E402
    BOOKS,
    Market,
    backtest_book,
    metrics,
)

PRICE_SYMBOLS = [
    "QQQ", "SCHD", "BIL", "TLT", "PDBC", "TIP", "SPY", "SCZ",
    "EFA", "EEM", "AGG", "IEF", "LQD", "QLD", "SSO",
]
FRED_SERIES = ["UNRATE", "T10Y3M"]
WINDOWS = {
    "dga": date(2016, 1, 1),
    "accelerated_dual_momentum": date(2008, 7, 1),
    "gtt_ue": date(2007, 6, 1),
    "baa_a": date(2016, 1, 1),
}
BOOK_LABELS = {
    "dga": "DGA",
    "accelerated_dual_momentum": "Accelerated Dual Momentum",
    "gtt_ue": "GTT-UE",
    "baa_a": "BAA(A)",
}
COMBINED_START = date(2016, 1, 1)


def refresh_data(data_dir: Path) -> list[str]:
    warnings: list[str] = []
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yfinance as yf

        frame = yf.download(PRICE_SYMBOLS, start="1999-01-01", auto_adjust=True, progress=False)
        close = frame["Close"]
        if close.dropna(how="all").empty:
            raise RuntimeError("yfinance returned no rows")
        close.to_csv(data_dir / "adj_close.csv")
        dividends = yf.Ticker("SPY").dividends
        if len(dividends):
            dividends.to_csv(data_dir / "spy_dividends.csv")
    except Exception as exc:  # noqa: BLE001 - degrade to cached data
        warnings.append(f"price refresh failed, using cache: {exc}")
    try:
        import requests

        for series in FRED_SERIES:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            (data_dir / f"{series}.csv").write_text(response.text)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"macro refresh failed, using cache: {exc}")
    return warnings


def live_execution_maps(signal_config_path: Path) -> dict[str, dict[str, str]]:
    raw = yaml.safe_load(signal_config_path.read_text())
    overrides: dict[str, str] = {}
    for strategy in raw.get("strategies", []):
        if strategy.get("id") in {"crescendo_us", "crescendo"}:
            overrides = dict((strategy.get("config") or {}).get("execution_overrides") or {})
            break
    maps: dict[str, dict[str, str]] = {book: {} for book in WINDOWS}
    for slot_key, execution_symbol in overrides.items():
        parts = str(slot_key).split(".")
        if len(parts) != 3 or parts[0] not in maps:
            continue
        maps[parts[0]][parts[2]] = str(execution_symbol)
    return maps


def series_payload(equity, holdings=None) -> dict:
    monthly = equity.resample("ME").last()
    payload = {
        "dates": [stamp.strftime("%Y-%m-%d") for stamp in monthly.index],
        "equity": [round(float(value), 4) for value in monthly.values],
        "metrics": {key: round(float(value), 4) for key, value in metrics(equity).items()},
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal-config", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    warnings = refresh_data(args.data_dir)
    market = Market(str(args.data_dir))
    end = market.dates[-1]
    exec_maps = live_execution_maps(args.signal_config)

    books: dict[str, dict] = {}
    combined_parts = []
    for book, start in WINDOWS.items():
        exec_map = exec_maps.get(book, {})
        equity, _ = backtest_book(market, book, start, end, False, exec_map=exec_map)
        payload = series_payload(equity)
        payload["label"] = BOOK_LABELS[book]
        payload["exec_map"] = exec_map
        payload["window_start"] = start.isoformat()
        books[book] = payload
        common_equity, _ = backtest_book(
            market, book, COMBINED_START, end, False, exec_map=exec_map
        )
        combined_parts.append(common_equity.pct_change().fillna(0.0))

    combined_equity = (1 + sum(combined_parts) / len(combined_parts)).cumprod()
    combined = series_payload(combined_equity)
    combined["label"] = "Combined (equal weight)"
    combined["window_start"] = COMBINED_START.isoformat()

    output = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_through": end.isoformat(),
        "note": "Simulated monthly-rebalance backtest with live execution_overrides applied; dividends reinvested; costs excluded.",
        "warnings": warnings,
        "books": books,
        "combined": combined,
    }
    tmp_path = args.output.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(output))
    tmp_path.replace(args.output)
    print(
        f"book_performance status=ok books={len(books)} data_through={end.isoformat()} "
        f"warnings={len(warnings)}"
    )
    for warning in warnings:
        print(f"book_performance warning={warning}")


if __name__ == "__main__":
    main()
