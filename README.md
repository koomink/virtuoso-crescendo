# Snowball

Snowball is a Virtuoso app for Maestro. It implements a small set of dynamic
asset allocation strategies and emits a single Maestro `TargetAllocationResult`
with strategy book metadata for per-strategy accounting.

Implemented strategies:

- DGA
- Accelerated Dual Momentum
- GTT-UE
- BAA(A)

Snowball does not fetch data directly, submit orders, manage portfolio state, or
write dashboard state. Maestro owns DataHub, risk, order generation, execution,
state, audit, and dashboard read models.

## Price Data Convention

Snowball requests daily OHLCV bars for price-based strategy logic and only uses
bars strictly before the strategy context date. For example, a June 1 signal
uses the previous trading day close as the latest price, not any June 1 bar.

Monthly moving-average and relative-strength checks in DGA, GTT-UE, and BAA(A)
use monthly endpoint adjusted closes: each month contributes its last available
trading close, and the strategy averages the most recent completed monthly
endpoints before the context month. Point-to-point monthly returns use the
latest available close before each calendar-month cutoff. Snowball keeps this
adjusted-close convention even when external references use raw closes.

BAA(A) treats failed defensive sleeves as a short-duration Treasury proxy and
allocates them to `BIL`, not to `CASH_USD`. GTT-UE keeps a strict unemployment
threshold: recession requires latest unemployment to be greater than the prior
12-observation average, not merely equal to it.

## Ticker Overrides

Default tickers come from `snowball72_strategy_info.md`. You can replace any
individual ticker globally:

```yaml
config:
  ticker_overrides:
    SPY: QQQM
    SCZ: QLD
    TLT: TMF
    TIP: STIP
```

For a specific strategy slot, use `slot_overrides`. Slot overrides take
precedence over global ticker overrides:

```yaml
config:
  slot_overrides:
    dga.offensive.QQQ: QLD
    baa_a.defensive.PDBC: DBC
```

The slot key format is `<strategy_id>.<role>.<default_ticker>`.

## Maestro Registration

```yaml
strategies:
  - id: snowball
    enabled: true
    mode: paper
    weight: 1.0
    entrypoint: "snowball.strategy:SnowballStrategy"
    config:
      selected_strategies: [dga, accelerated_dual_momentum, gtt_ue, baa_a]
      strategy_weights:
        dga: 0.25
        accelerated_dual_momentum: 0.25
        gtt_ue: 0.25
        baa_a: 0.25
      ticker_overrides: {}
      slot_overrides: {}
```

See `configs/snowball_us_etf_paper.example.yaml` for a complete USD paper
configuration.
