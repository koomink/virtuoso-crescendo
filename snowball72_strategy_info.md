# Snowball72 Strategy Information Summary

Collected on: 2026-05-14
Source: [Snowball72 Asset Allocation Strategy Screener](https://snowball72.com/strategy/screener)

> Note: The summary below is based on the `Strategy Information` section of each strategy's detail page. It preserves the core rules and characteristics while organizing them in English.

## DGA

Source: https://snowball72.com/strategy/dga?tab=chart&currency=USD

### Strategy Description

DGA is based on Paul Choi's Dividend & Growth Allocation idea. It uses growth stocks and dividend stocks as offensive assets, and moves into defensive assets when one or more risk-avoidance conditions are triggered.

### Asset Universe

| Category | Assets |
|---|---|
| Offensive assets | U.S. Nasdaq (QQQ), U.S. high dividend (SCHD) |
| Defensive assets | U.S. short-term Treasury bills (BIL), U.S. long-term Treasury bonds (TLT), commodities (PDBC) |
| Canary asset | Treasury Inflation-Protected Securities (TIP) |

### Investment Rules

- Among the two offensive ETFs, select the ETF with the higher momentum score, calculated from the average returns over 1, 3, 6, 9, and 12 months.
- If any one of the following conditions occurs, move from offensive assets to defensive assets.
  - TIP's month-end price is below its 12-month average price.
  - The S&P 500 dividend yield is below 1.6%.
  - The 10-year minus 3-month yield spread is inverted, with the spread below -0.5%.
- When moving into defensive assets, invest 100% in the one defensive ETF whose month-end price is highest relative to its 6-month average price.
- If the selected defensive asset is also below its average price, hold cash.
- Rebalancing frequency: monthly

### Strategy Characteristics

- The offensive assets consist of two equity ETFs representing dividend and growth exposures, which tend to have relatively low correlation with each other.
- The strategy uses TIP, dividend yield, and the long-term/short-term yield spread to respond to rising-rate environments, possible stock market overheating, and potential recession signals.
- It is designed to reduce exposure to periods of rising long-term interest rates, with an emphasis on stability and risk-adjusted return.
- Because several risk-avoidance conditions are used, overfitting is a possible concern. Also, since the strategy concentrates in a single offensive or defensive ETF, high turnover may create inefficiencies from taxes and other costs.

## Accelerated Dual Momentum

Source: https://snowball72.com/strategy/accelerated-dual-momentum?tab=chart&currency=USD

### Strategy Description

This is a dual-momentum strategy introduced by Engineered Portfolio. It evaluates both relative momentum and absolute momentum between equity assets, and shifts into bond assets when conditions are unfavorable.

### Asset Universe

| Category | Assets |
|---|---|
| Offensive assets | U.S. broad equity (SPY), global small-cap equity (SCZ) |
| Defensive assets | U.S. long-term Treasury bonds (TLT), U.S. Treasury Inflation-Protected Securities (TIP) |

### Investment Rules

- At the end of each month, compare the momentum scores of the two offensive assets, calculated from the average returns over 1, 3, and 6 months.
- If the offensive asset with the higher momentum score has a positive score, invest in that ETF.
- If the selected offensive asset has a negative score, invest 100% in the defensive ETF with the higher 1-month return.
- Rebalancing frequency: monthly

### Strategy Characteristics

- This is an aggressive strategy and has relatively high volatility compared with many other strategies.
- It aims to participate in equity market gains during bull markets while avoiding large losses during bear markets.
- The use of relative momentum between global small-cap equities and the S&P 500 is intended to improve returns during rising equity markets.

## GTT-UE

Source: https://snowball72.com/strategy/gttu?tab=chart&currency=USD

### Strategy Description

GTT-UE is one of the strategies from Philosophical Economics. It combines price trend signals with unemployment-rate data, deciding whether to invest in U.S. equities or hold cash based on the economic signal and price trend.

### Asset Universe

| Category | Assets |
|---|---|
| Offensive assets | U.S. broad equity (SPY) |
| Defensive assets | Cash (CASH) |

### Investment Rules

- If the most recently released monthly unemployment rate is higher than the average unemployment rate over the previous 12 months, treat it as a recession signal.
- If there is no recession signal, buy the offensive asset.
- If there is a recession signal but the offensive asset's price is above its 10-month average price, remain invested in the offensive asset.
- If there is a recession signal and the offensive asset's price is below its 10-month average price, hold cash.
- Rebalancing frequency: monthly

### Strategy Characteristics

- Conventional trend-following strategies can be useful for avoiding losses during recessions, but they may be less effective outside recessionary periods.
- This strategy addresses that issue by first identifying the economic regime and then applying the trend-following condition.
- Its focus is less on generating very large excess returns and more on managing losses while maintaining returns.

## BAA(A)

Source: https://snowball72.com/strategy/baa-a?tab=chart&currency=USD

### Strategy Description

BAA(A) is the aggressive version of Bold Asset Allocation, introduced in Dr. Wouter Keller's paper. The strategy separates assets into offensive assets, defensive assets, and canary assets, and concentrates in offensive assets only when all risk signals are favorable.

### Asset Universe

| Category | Assets |
|---|---|
| Offensive assets | U.S. Nasdaq (QQQ), developed-market equities (EFA), emerging-market equities (EEM), U.S. aggregate bonds (AGG) |
| Defensive assets | U.S. aggregate bonds (AGG), U.S. short-term Treasury bills (BIL), U.S. intermediate-term Treasury bonds (IEF), U.S. long-term Treasury bonds (TLT), U.S. Treasury Inflation-Protected Securities (TIP), U.S. corporate bonds (LQD), commodities (PBDC) |
| Canary assets | U.S. broad equity (SPY), emerging-market equities (EEM), developed-market equities (EFA), U.S. aggregate bonds (AGG) |

### Investment Rules

- Calculate the momentum score of the canary assets using the weighted average returns over 1, 3, 6, and 12 months.
- If all canary assets have momentum scores of 0 or higher, invest 100% in the one offensive ETF that is strongest relative to its 12-month average price.
- If any canary asset has a momentum score of 0 or lower, invest equally, one-third each, in the three defensive ETFs that are strongest relative to their 12-month average prices.
- If a defensive-asset candidate is below its 12-month average price, hold that portion in cash.
- Rebalancing frequency: monthly

### Strategy Characteristics

- The canary assets include three regional equity assets as well as U.S. aggregate bonds.
- The strategy uses weighted momentum so that recent performance has a larger impact, and it invests in offensive assets only when there are no risk signals.
- High turnover may lead to higher trading costs and tax-related costs.
- BAA has both aggressive and balanced versions. The aggressive version concentrates in one final offensive asset, while the balanced version selects a larger number of offensive assets for diversification.
