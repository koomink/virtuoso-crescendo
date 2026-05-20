from dataclasses import dataclass

from maestro.sdk import (
    BaseStrategyPlugin,
    DataBundle,
    DataRequest,
    StrategyBookAllocation,
    StrategyContext,
    StrategyManifest,
    TargetAllocationResult,
)

STRATEGY_ID = "snowball"
STRATEGY_VERSION = "0.1.0"
CASH_SYMBOL = "CASH_USD"
SELECTED_STRATEGIES = ["dga", "accelerated_dual_momentum", "gtt_ue", "baa_a"]


@dataclass(frozen=True)
class StrategySpec:
    name: str
    roles: dict[str, list[str]]


DEFAULT_SPECS = {
    "dga": StrategySpec(
        name="DGA",
        roles={
            "offensive": ["QQQ", "SCHD"],
            "defensive": ["BIL", "TLT", "PDBC"],
            "canary": ["TIP"],
            "macro": ["SPY", "T10Y3M"],
            "cash": [CASH_SYMBOL],
        },
    ),
    "accelerated_dual_momentum": StrategySpec(
        name="Accelerated Dual Momentum",
        roles={
            "offensive": ["SPY", "SCZ"],
            "defensive": ["TLT", "TIP"],
            "cash": [CASH_SYMBOL],
        },
    ),
    "gtt_ue": StrategySpec(
        name="GTT-UE",
        roles={
            "offensive": ["SPY"],
            "macro": ["UNRATE"],
            "cash": [CASH_SYMBOL],
        },
    ),
    "baa_a": StrategySpec(
        name="BAA(A)",
        roles={
            "offensive": ["QQQ", "EFA", "EEM", "AGG"],
            "defensive": ["AGG", "BIL", "IEF", "TLT", "TIP", "LQD", "PDBC"],
            "canary": ["SPY", "EEM", "EFA", "AGG"],
            "cash": [CASH_SYMBOL],
        },
    ),
}
MACRO_SYMBOLS = {"UNRATE", "T10Y3M"}


class SnowballStrategy(BaseStrategyPlugin):
    def manifest(self) -> StrategyManifest:
        return StrategyManifest(
            sdk_contract_version="1.1",
            strategy_id=STRATEGY_ID,
            name="Snowball",
            version=STRATEGY_VERSION,
            description="Dynamic asset allocation strategy collection for Maestro.",
            supported_modes=["paper", "live_approval"],
            supported_asset_types=["cash", "etf", "us_etf"],
            result_type="target_allocation",
            requires_data=["ohlcv", "fundamental", "macro"],
            can_run_live=True,
            allow_direct_external_data_calls=False,
            estimated_runtime_seconds=10,
        )

    def build_data_requests(self, context: StrategyContext) -> list[DataRequest]:
        universe = self._configured_universe(context)
        requests: dict[tuple[str, str], DataRequest] = {}
        for strategy_id in self._selected_strategies(context):
            for role, symbols in universe[strategy_id].items():
                for index, symbol in enumerate(symbols):
                    if symbol.startswith("CASH"):
                        continue
                    data_type = self._data_type_for(strategy_id, role, index)
                    requests[(symbol, data_type)] = DataRequest(
                        symbol=symbol,
                        asset_type="etf" if data_type != "macro" else "stock",
                        data_type=data_type,
                        intended_use="tradable" if role != "macro" else "research",
                        timeframe="1mo" if data_type == "ohlcv" else None,
                        lookback=380 if data_type == "ohlcv" else 13,
                    )
            if strategy_id == "dga":
                dividend_symbol = universe[strategy_id]["macro"][0]
                if dividend_symbol not in MACRO_SYMBOLS:
                    requests[(dividend_symbol, "fundamental")] = DataRequest(
                        symbol=dividend_symbol,
                        asset_type="etf",
                        data_type="fundamental",
                        intended_use="research",
                        fields=["dividend_yield"],
                    )
        return list(requests.values())

    def _data_type_for(self, strategy_id: str, role: str, index: int) -> str:
        if role != "macro":
            return "ohlcv"
        if strategy_id == "dga" and index == 0:
            return "fundamental"
        return "macro"

    def run(self, data_bundle: DataBundle, context: StrategyContext) -> TargetAllocationResult:
        selected = self._selected_strategies(context)
        weights = self._strategy_weights(context, selected)
        universe = self._configured_universe(context)
        books = []
        combined: dict[str, float] = {}

        for strategy_id in selected:
            allocations, rationale = self._run_sub_strategy(
                strategy_id,
                universe[strategy_id],
                data_bundle,
            )
            book = StrategyBookAllocation(
                book_id=strategy_id,
                label=DEFAULT_SPECS[strategy_id].name,
                target_weight=weights[strategy_id],
                allocations=allocations,
                rationale=rationale,
                metadata={"universe": universe[strategy_id]},
            )
            books.append(book)
            for symbol, allocation in allocations.items():
                combined[symbol] = combined.get(symbol, 0.0) + allocation * weights[strategy_id]

        combined = self._fill_cash(combined, self._cash_symbol(context))
        sleeve = context.config.get("sleeve")
        return TargetAllocationResult(
            strategy_id=context.strategy_id,
            strategy_version=STRATEGY_VERSION,
            timestamp=context.timestamp,
            allocations={} if sleeve else combined,
            allocation_sleeves={str(sleeve): combined} if sleeve else {},
            strategy_books=books,
            confidence=1.0,
            time_horizon="monthly",
            rationale="Weighted Snowball dynamic asset allocation target.",
            metadata={
                "selected_strategies": selected,
                "ticker_overrides": context.config.get("ticker_overrides", {}),
                "slot_overrides": context.config.get("slot_overrides", {}),
            },
        )

    def _run_sub_strategy(
        self,
        strategy_id: str,
        universe: dict[str, list[str]],
        data_bundle: DataBundle,
    ) -> tuple[dict[str, float], str]:
        if strategy_id == "dga":
            return self._run_dga(universe, data_bundle)
        if strategy_id == "accelerated_dual_momentum":
            return self._run_adm(universe, data_bundle)
        if strategy_id == "gtt_ue":
            return self._run_gtt_ue(universe, data_bundle)
        if strategy_id == "baa_a":
            return self._run_baa_a(universe, data_bundle)
        raise ValueError(f"Unsupported Snowball strategy: {strategy_id}")

    def _run_dga(
        self,
        universe: dict[str, list[str]],
        data_bundle: DataBundle,
    ) -> tuple[dict[str, float], str]:
        canary = universe["canary"][0]
        dividend_symbol, spread_symbol = universe["macro"]
        risk_off = (
            self._latest_close(canary, data_bundle) < self._sma(canary, data_bundle, 12)
            or self._dividend_yield(dividend_symbol, data_bundle) < 0.016
            or self._latest_macro(spread_symbol, data_bundle) < -0.5
        )
        if not risk_off:
            winner = max(
                universe["offensive"],
                key=lambda symbol: self._average_return(symbol, data_bundle, [1, 3, 6, 9, 12]),
            )
            return {winner: 1.0}, f"DGA selected offensive asset {winner}."
        defensive = max(
            universe["defensive"],
            key=lambda symbol: self._relative_to_sma(symbol, data_bundle, 6),
        )
        if self._latest_close(defensive, data_bundle) < self._sma(defensive, data_bundle, 6):
            return {universe["cash"][0]: 1.0}, "DGA risk-off signal selected cash."
        return {defensive: 1.0}, f"DGA risk-off signal selected defensive asset {defensive}."

    def _run_adm(
        self,
        universe: dict[str, list[str]],
        data_bundle: DataBundle,
    ) -> tuple[dict[str, float], str]:
        winner = max(
            universe["offensive"],
            key=lambda symbol: self._average_return(symbol, data_bundle, [1, 3, 6]),
        )
        if self._average_return(winner, data_bundle, [1, 3, 6]) > 0:
            return {winner: 1.0}, f"ADM selected positive momentum offensive asset {winner}."
        defensive = max(
            universe["defensive"],
            key=lambda symbol: self._return(symbol, data_bundle, 1),
        )
        return {defensive: 1.0}, f"ADM selected defensive asset {defensive}."

    def _run_gtt_ue(
        self,
        universe: dict[str, list[str]],
        data_bundle: DataBundle,
    ) -> tuple[dict[str, float], str]:
        offensive = universe["offensive"][0]
        unemployment = self._macro_values(universe["macro"][0], data_bundle)
        recession = unemployment[-1] > sum(unemployment[-13:-1]) / 12
        trend_ok = self._latest_close(offensive, data_bundle) > self._sma(
            offensive,
            data_bundle,
            10,
        )
        if not recession or trend_ok:
            return {offensive: 1.0}, f"GTT-UE selected offensive asset {offensive}."
        return {universe["cash"][0]: 1.0}, "GTT-UE recession and trend signal selected cash."

    def _run_baa_a(
        self,
        universe: dict[str, list[str]],
        data_bundle: DataBundle,
    ) -> tuple[dict[str, float], str]:
        canary_scores = [
            self._weighted_momentum(symbol, data_bundle, [1, 3, 6, 12])
            for symbol in universe["canary"]
        ]
        if all(score >= 0 for score in canary_scores):
            winner = max(
                universe["offensive"],
                key=lambda symbol: self._relative_to_sma(symbol, data_bundle, 12),
            )
            return {winner: 1.0}, f"BAA(A) selected offensive asset {winner}."

        ranked = sorted(
            universe["defensive"],
            key=lambda symbol: self._relative_to_sma(symbol, data_bundle, 12),
            reverse=True,
        )[:3]
        allocations: dict[str, float] = {}
        for symbol in ranked:
            if self._latest_close(symbol, data_bundle) >= self._sma(symbol, data_bundle, 12):
                target = symbol
            else:
                target = universe["cash"][0]
            allocations[target] = allocations.get(target, 0.0) + (1.0 / 3.0)
        return allocations, "BAA(A) selected defensive allocation."

    def _selected_strategies(self, context: StrategyContext) -> list[str]:
        selected = context.config.get("selected_strategies", SELECTED_STRATEGIES)
        output = [str(strategy_id) for strategy_id in selected]
        unknown = sorted(set(output) - set(DEFAULT_SPECS))
        if unknown:
            raise ValueError(f"Unsupported Snowball strategies: {', '.join(unknown)}")
        return output

    def _strategy_weights(
        self,
        context: StrategyContext,
        selected: list[str],
    ) -> dict[str, float]:
        configured = context.config.get("strategy_weights", {})
        if not configured:
            return {strategy_id: 1.0 / len(selected) for strategy_id in selected}
        weights = {strategy_id: float(configured.get(strategy_id, 0.0)) for strategy_id in selected}
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Snowball strategy_weights must have a positive total")
        return {strategy_id: weight / total for strategy_id, weight in weights.items()}

    def _configured_universe(self, context: StrategyContext) -> dict[str, dict[str, list[str]]]:
        return {
            strategy_id: {
                role: [
                    self._override_symbol(strategy_id, role, symbol, context)
                    for symbol in symbols
                ]
                for role, symbols in spec.roles.items()
            }
            for strategy_id, spec in DEFAULT_SPECS.items()
        }

    def _override_symbol(
        self,
        strategy_id: str,
        role: str,
        symbol: str,
        context: StrategyContext,
    ) -> str:
        slot_overrides = context.config.get("slot_overrides", {})
        ticker_overrides = context.config.get("ticker_overrides", {})
        slot_key = f"{strategy_id}.{role}.{symbol}"
        return str(slot_overrides.get(slot_key, ticker_overrides.get(symbol, symbol)))

    def _cash_symbol(self, context: StrategyContext) -> str:
        return str(context.config.get("cash_symbol", CASH_SYMBOL))

    def _fill_cash(self, allocations: dict[str, float], cash_symbol: str) -> dict[str, float]:
        total = sum(allocations.values())
        if total < 1.0:
            allocations[cash_symbol] = allocations.get(cash_symbol, 0.0) + (1.0 - total)
        if total > 1.0:
            return {symbol: weight / total for symbol, weight in allocations.items()}
        return allocations

    def _average_return(self, symbol: str, data_bundle: DataBundle, months: list[int]) -> float:
        return sum(self._return(symbol, data_bundle, month) for month in months) / len(months)

    def _weighted_momentum(self, symbol: str, data_bundle: DataBundle, months: list[int]) -> float:
        weights = [12 / month for month in months]
        weighted_returns = (
            self._return(symbol, data_bundle, month) * weight
            for month, weight in zip(months, weights, strict=True)
        )
        return sum(weighted_returns) / sum(weights)

    def _relative_to_sma(self, symbol: str, data_bundle: DataBundle, months: int) -> float:
        return self._latest_close(symbol, data_bundle) / self._sma(symbol, data_bundle, months)

    def _return(self, symbol: str, data_bundle: DataBundle, months: int) -> float:
        closes = self._closes(symbol, data_bundle)
        if len(closes) <= months:
            raise ValueError(f"Not enough OHLCV bars for {symbol}: need {months + 1}")
        previous = closes[-months - 1]
        if previous <= 0:
            raise ValueError(f"Invalid historical close for {symbol}")
        return closes[-1] / previous - 1.0

    def _sma(self, symbol: str, data_bundle: DataBundle, months: int) -> float:
        closes = self._closes(symbol, data_bundle)
        if len(closes) < months:
            raise ValueError(f"Not enough OHLCV bars for {symbol}: need {months}")
        return sum(closes[-months:]) / months

    def _latest_close(self, symbol: str, data_bundle: DataBundle) -> float:
        return self._closes(symbol, data_bundle)[-1]

    def _closes(self, symbol: str, data_bundle: DataBundle) -> list[float]:
        payload = data_bundle.data.get(symbol)
        if not isinstance(payload, dict):
            raise ValueError(f"Missing data for {symbol}")
        bars = payload.get("bars")
        if not isinstance(bars, list) or not bars:
            raise ValueError(f"Missing OHLCV bars for {symbol}")
        return [float(bar["close"]) for bar in bars]

    def _dividend_yield(self, symbol: str, data_bundle: DataBundle) -> float:
        payload = data_bundle.data.get(symbol)
        if not isinstance(payload, dict):
            raise ValueError(f"Missing dividend data for {symbol}")
        metrics = payload.get("metrics") or {}
        value = metrics.get("dividend_yield")
        if value is None:
            raise ValueError(f"Missing dividend_yield for {symbol}")
        dividend_yield = float(value)
        if dividend_yield > 1.0:
            return dividend_yield / 100.0
        return dividend_yield

    def _latest_macro(self, symbol: str, data_bundle: DataBundle) -> float:
        return self._macro_values(symbol, data_bundle)[-1]

    def _macro_values(self, symbol: str, data_bundle: DataBundle) -> list[float]:
        payload = data_bundle.data.get(symbol)
        if not isinstance(payload, dict):
            raise ValueError(f"Missing macro data for {symbol}")
        observations = payload.get("observations")
        if not isinstance(observations, list) or len(observations) < 13:
            raise ValueError(f"Not enough macro observations for {symbol}: need 13")
        return [float(observation["value"]) for observation in observations]


class SnowballUSStrategy(SnowballStrategy):
    def manifest(self) -> StrategyManifest:
        return super().manifest().model_copy(
            update={
                "strategy_id": "snowball_us",
                "name": "Snowball US",
                "description": "US-market Snowball dynamic asset allocation profile.",
            }
        )
