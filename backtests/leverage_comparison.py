"""Backtest: base (QQQ/SPY) vs leveraged (QLD/SSO) execution of Crescendo books.

Signals are always computed on the base (unlevered) symbols, replicating the
rules in src/crescendo/strategy.py. The leveraged variant only swaps the
executed offensive winner (signal/execution separation via execution_overrides):

    dga:                        QQQ -> QLD   (SCHD unchanged)
    accelerated_dual_momentum:  SPY -> SSO   (SCZ unchanged)
    gtt_ue:                     SPY -> SSO
    baa_a:                      QQQ -> QLD   (EFA/EEM/AGG unchanged)

Rebalances on the first trading day of each month; the as_of cutoff excludes
that day's bar (mirrors _price_before's strict `<` cutoff). Positions are
entered at that day's close. Prices are dividend-adjusted (yfinance
auto_adjust), so ETF expense ratios and distributions are embedded. UNRATE is
lagged 38 days past its reference-month start to approximate publication.

Usage: python leverage_comparison.py <data_dir>
where data_dir holds adj_close.csv, spy_dividends.csv, UNRATE.csv, T10Y3M.csv.
"""

import sys
from calendar import monthrange
from datetime import date, timedelta

import numpy as np
import pandas as pd

CASH = "CASH_USD"

BOOKS = {
    "dga": {
        "offensive": ["QQQ", "SCHD"],
        "defensive": ["BIL", "TLT", "PDBC"],
        "canary": ["TIP"],
        "cash": CASH,
        "exec_map": {"QQQ": "QLD"},
    },
    "accelerated_dual_momentum": {
        "offensive": ["SPY", "SCZ"],
        "defensive": ["TLT", "TIP"],
        "cash": CASH,
        "exec_map": {"SPY": "SSO"},
    },
    "gtt_ue": {
        "offensive": ["SPY"],
        "cash": CASH,
        "exec_map": {"SPY": "SSO"},
    },
    "baa_a": {
        "offensive": ["QQQ", "EFA", "EEM", "AGG"],
        "defensive": ["AGG", "BIL", "IEF", "TLT", "TIP", "LQD", "PDBC"],
        "canary": ["SPY", "EEM", "EFA", "AGG"],
        "cash": "BIL",
        "exec_map": {"QQQ": "QLD"},
    },
}

UNRATE_PUBLICATION_LAG_DAYS = 38


class Market:
    def __init__(self, data_dir: str) -> None:
        close = pd.read_csv(f"{data_dir}/adj_close.csv", index_col=0, parse_dates=True)
        self.close = close.sort_index()
        self.dates = [d.date() for d in self.close.index]
        div = pd.read_csv(f"{data_dir}/spy_dividends.csv", index_col=0)
        div.index = pd.to_datetime(div.index, utc=True).tz_localize(None)
        self.spy_div = div.iloc[:, 0].sort_index()
        unrate = pd.read_csv(f"{data_dir}/UNRATE.csv", parse_dates=[0])
        unrate.columns = ["date", "value"]
        self.unrate = unrate.dropna()
        t10y3m = pd.read_csv(f"{data_dir}/T10Y3M.csv", parse_dates=[0])
        t10y3m.columns = ["date", "value"]
        t10y3m["value"] = pd.to_numeric(t10y3m["value"], errors="coerce")
        self.t10y3m = t10y3m.dropna()

    def series(self, symbol: str) -> pd.Series:
        return self.close[symbol].dropna()

    def price_before(self, symbol: str, cutoff: date) -> float:
        s = self.series(symbol)
        s = s[s.index.date < cutoff]
        if s.empty:
            raise LookupError(f"no bars for {symbol} before {cutoff}")
        return float(s.iloc[-1])

    def monthly_endpoints(self, symbol: str, cutoff: date) -> pd.Series:
        s = self.series(symbol)
        s = s[
            (s.index.date < cutoff)
            & (
                (s.index.year * 100 + s.index.month)
                < (cutoff.year * 100 + cutoff.month)
            )
        ]
        return s.groupby([s.index.year, s.index.month]).last()

    def sma_months(self, symbol: str, months: int, cutoff: date) -> float:
        endpoints = self.monthly_endpoints(symbol, cutoff)
        if len(endpoints) < months:
            raise LookupError(f"not enough monthly endpoints for {symbol}")
        return float(endpoints.iloc[-months:].mean())

    def ret_months(self, symbol: str, months: int, cutoff: date) -> float:
        latest = self.price_before(symbol, cutoff)
        previous = self.price_before(symbol, shift_months(cutoff, months))
        return latest / previous - 1.0

    def avg_ret(self, symbol: str, months_list: list[int], cutoff: date) -> float:
        return sum(self.ret_months(symbol, m, cutoff) for m in months_list) / len(months_list)

    def weighted_momentum(self, symbol: str, months_list: list[int], cutoff: date) -> float:
        weights = [12 / m for m in months_list]
        total = sum(
            self.ret_months(symbol, m, cutoff) * w
            for m, w in zip(months_list, weights, strict=True)
        )
        return total / sum(weights)

    def rel_to_sma(self, symbol: str, months: int, cutoff: date) -> float:
        return self.price_before(symbol, cutoff) / self.sma_months(symbol, months, cutoff)

    def spy_dividend_yield(self, cutoff: date) -> float:
        window = self.spy_div[
            (self.spy_div.index.date < cutoff)
            & (self.spy_div.index.date >= cutoff - timedelta(days=365))
        ]
        return float(window.sum()) / self.price_before("SPY", cutoff)

    def t10y3m_latest(self, cutoff: date) -> float:
        s = self.t10y3m[self.t10y3m["date"].dt.date < cutoff]
        return float(s["value"].iloc[-1])

    def unrate_observations(self, cutoff: date) -> list[float]:
        available = self.unrate[
            self.unrate["date"].dt.date
            <= cutoff - timedelta(days=UNRATE_PUBLICATION_LAG_DAYS)
        ]
        return available["value"].tolist()


def shift_months(value: date, months: int) -> date:
    month_index = value.month - months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def run_dga(m: Market, cutoff: date) -> dict[str, float]:
    u = BOOKS["dga"]
    risk_off = (
        m.price_before("TIP", cutoff) < m.sma_months("TIP", 12, cutoff)
        or m.spy_dividend_yield(cutoff) < 0.016
        or m.t10y3m_latest(cutoff) < -0.5
    )
    if not risk_off:
        winner = max(u["offensive"], key=lambda s: m.avg_ret(s, [1, 3, 6, 9, 12], cutoff))
        return {winner: 1.0}
    defensive = max(u["defensive"], key=lambda s: m.rel_to_sma(s, 6, cutoff))
    if m.price_before(defensive, cutoff) < m.sma_months(defensive, 6, cutoff):
        return {u["cash"]: 1.0}
    return {defensive: 1.0}


def run_adm(m: Market, cutoff: date) -> dict[str, float]:
    u = BOOKS["accelerated_dual_momentum"]
    winner = max(u["offensive"], key=lambda s: m.avg_ret(s, [1, 3, 6], cutoff))
    if m.avg_ret(winner, [1, 3, 6], cutoff) > 0:
        return {winner: 1.0}
    defensive = max(u["defensive"], key=lambda s: m.ret_months(s, 1, cutoff))
    return {defensive: 1.0}


def run_gtt_ue(m: Market, cutoff: date) -> dict[str, float]:
    u = BOOKS["gtt_ue"]
    observations = m.unrate_observations(cutoff)
    if len(observations) < 13:
        raise LookupError("not enough UNRATE observations")
    recession = observations[-1] > sum(observations[-13:-1]) / 12
    trend_ok = m.price_before("SPY", cutoff) > m.sma_months("SPY", 10, cutoff)
    if not recession or trend_ok:
        return {"SPY": 1.0}
    return {u["cash"]: 1.0}


def run_baa_a(m: Market, cutoff: date) -> dict[str, float]:
    u = BOOKS["baa_a"]
    canary_scores = [m.weighted_momentum(s, [1, 3, 6, 12], cutoff) for s in u["canary"]]
    if all(score >= 0 for score in canary_scores):
        winner = max(u["offensive"], key=lambda s: m.rel_to_sma(s, 12, cutoff))
        return {winner: 1.0}
    ranked = sorted(u["defensive"], key=lambda s: m.rel_to_sma(s, 12, cutoff), reverse=True)[:3]
    allocations: dict[str, float] = {}
    for symbol in ranked:
        if m.price_before(symbol, cutoff) >= m.sma_months(symbol, 12, cutoff):
            target = symbol
        else:
            target = u["cash"]
        allocations[target] = allocations.get(target, 0.0) + 1.0 / 3.0
    return allocations


SIGNALS = {
    "dga": run_dga,
    "accelerated_dual_momentum": run_adm,
    "gtt_ue": run_gtt_ue,
    "baa_a": run_baa_a,
}


def month_first_trading_days(m: Market, start: date, end: date) -> list[date]:
    days: list[date] = []
    seen: set[tuple[int, int]] = set()
    for d in m.dates:
        if d < start or d > end:
            continue
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            days.append(d)
    return days


def daily_returns(m: Market, symbol: str) -> pd.Series:
    if symbol == CASH:
        return pd.Series(dtype=float)
    return m.series(symbol).pct_change()


def backtest_book(
    m: Market,
    book: str,
    start: date,
    end: date,
    leveraged: bool,
    exec_map: dict[str, str] | None = None,
) -> tuple[pd.Series, list[tuple[date, dict[str, float]]]]:
    rebalance_days = month_first_trading_days(m, start, end)
    if exec_map is None:
        exec_map = BOOKS[book]["exec_map"] if leveraged else {}
    holdings_by_period: list[tuple[date, dict[str, float]]] = []
    for day in rebalance_days:
        signal_allocations = SIGNALS[book](m, day)
        executed = {}
        for symbol, weight in signal_allocations.items():
            mapped = exec_map.get(symbol, symbol)
            executed[mapped] = executed.get(mapped, 0.0) + weight
        holdings_by_period.append((day, executed))

    returns_cache = {
        symbol: daily_returns(m, symbol)
        for _, alloc in holdings_by_period
        for symbol in alloc
    }
    # Positions are entered at the close of each rebalance day, so a day's
    # return always belongs to the holdings entered at a *previous* close;
    # the switch to new holdings happens after that day's return is booked.
    all_days = [d for d in m.dates if rebalance_days[0] <= d <= end]
    equity = []
    value = 1.0
    period_index = -1
    current: dict[str, float] = {}
    for d in all_days:
        day_ret = 0.0
        for symbol, weight in current.items():
            if symbol == CASH:
                continue
            r = returns_cache[symbol].get(pd.Timestamp(d), np.nan)
            if r is not None and not np.isnan(r):
                day_ret += weight * r
        value *= 1.0 + day_ret
        equity.append((d, value))
        while (
            period_index + 1 < len(holdings_by_period)
            and holdings_by_period[period_index + 1][0] <= d
        ):
            period_index += 1
            current = holdings_by_period[period_index][1]
    series = pd.Series(
        [v for _, v in equity], index=pd.to_datetime([d for d, _ in equity])
    )
    return series, holdings_by_period


def metrics(equity: pd.Series) -> dict[str, float]:
    returns = equity.pct_change().dropna()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = equity.iloc[-1] ** (1 / years) - 1
    vol = returns.std() * np.sqrt(252)
    sharpe = (returns.mean() * 252) / vol if vol > 0 else float("nan")
    drawdown = equity / equity.cummax() - 1
    monthly = equity.resample("ME").last().pct_change().dropna()
    return {
        "years": years,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "mdd": drawdown.min(),
        "worst_month": monthly.min(),
        "best_month": monthly.max(),
        "final_multiple": equity.iloc[-1],
    }


def yearly_returns(equity: pd.Series) -> pd.Series:
    return equity.resample("YE").last().pct_change().dropna()


def main() -> None:
    data_dir = sys.argv[1]
    m = Market(data_dir)
    end = m.dates[-1]
    windows = {
        "dga": date(2016, 1, 1),
        "accelerated_dual_momentum": date(2008, 7, 1),
        "gtt_ue": date(2007, 6, 1),
        "baa_a": date(2016, 1, 1),
    }

    all_equities: dict[tuple[str, str], pd.Series] = {}
    print("=" * 100)
    print(f"{'book':<28} {'variant':<10} {'window':<24} {'CAGR':>7} {'Vol':>7} "
          f"{'Sharpe':>7} {'MDD':>8} {'WorstM':>8} {'Mult':>7}")
    print("=" * 100)
    for book, start in windows.items():
        for leveraged in (False, True):
            label = "2x-exec" if leveraged else "base"
            equity, holdings = backtest_book(m, book, start, end, leveraged)
            all_equities[(book, label)] = equity
            stats = metrics(equity)
            print(
                f"{book:<28} {label:<10} "
                f"{equity.index[0].date()}~{equity.index[-1].date()}  "
                f"{stats['cagr']:>6.1%} {stats['vol']:>6.1%} {stats['sharpe']:>7.2f} "
                f"{stats['mdd']:>7.1%} {stats['worst_month']:>7.1%} "
                f"{stats['final_multiple']:>6.2f}x"
            )

    print()
    print("Common window (2016-01 ~ ) including equal-weight 4-book combo")
    print("=" * 100)
    common_start = date(2016, 1, 1)
    combo: dict[str, pd.Series] = {}
    for leveraged in (False, True):
        label = "2x-exec" if leveraged else "base"
        parts = []
        for book in windows:
            equity, _ = backtest_book(m, book, common_start, end, leveraged)
            stats = metrics(equity)
            print(
                f"{book:<28} {label:<10} "
                f"{equity.index[0].date()}~{equity.index[-1].date()}  "
                f"{stats['cagr']:>6.1%} {stats['vol']:>6.1%} {stats['sharpe']:>7.2f} "
                f"{stats['mdd']:>7.1%} {stats['worst_month']:>7.1%} "
                f"{stats['final_multiple']:>6.2f}x"
            )
            parts.append(equity.pct_change().fillna(0.0))
        combo_returns = sum(parts) / len(parts)
        equity = (1 + combo_returns).cumprod()
        combo[label] = equity
        stats = metrics(equity)
        print(
            f"{'COMBINED (equal weight)':<28} {label:<10} "
            f"{equity.index[0].date()}~{equity.index[-1].date()}  "
            f"{stats['cagr']:>6.1%} {stats['vol']:>6.1%} {stats['sharpe']:>7.2f} "
            f"{stats['mdd']:>7.1%} {stats['worst_month']:>7.1%} "
            f"{stats['final_multiple']:>6.2f}x"
        )

    print()
    print("Yearly returns, base vs 2x-exec (common window)")
    print("=" * 100)
    for book in list(windows) + ["COMBINED"]:
        if book == "COMBINED":
            base_y = yearly_returns(combo["base"])
            lev_y = yearly_returns(combo["2x-exec"])
        else:
            base_equity, _ = backtest_book(m, book, common_start, end, False)
            lev_equity, _ = backtest_book(m, book, common_start, end, True)
            base_y = yearly_returns(base_equity)
            lev_y = yearly_returns(lev_equity)
        rows = [
            f"{y.year}: {b:>6.1%}/{lv:>6.1%}"
            for (y, b), lv in zip(base_y.items(), lev_y.values, strict=True)
        ]
        print(f"{book}")
        for i in range(0, len(rows), 5):
            print("   " + "   ".join(rows[i : i + 5]))


if __name__ == "__main__":
    main()
