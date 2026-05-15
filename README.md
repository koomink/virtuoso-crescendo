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
