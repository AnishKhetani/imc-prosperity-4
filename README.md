# IMC Prosperity 4 (2026): solo algorithmic trading entry, 525th of 18,800+ teams

**Result: 525th of 18,800+ teams (top 3%), competing solo.**

This repo holds my Python trading bots, backtests and research for **IMC Prosperity 4**, IMC Trading's 2026 global algorithmic trading competition. Prosperity runs five rounds. Each round a team submits a Python `Trader` that trades new products on a simulated exchange, and also plays a manual trading challenge. Teams can have up to five players; I entered alone.

If you are preparing for a future Prosperity (Prosperity 5 and on), the most reusable parts are the Round 3 post-mortem, the Round 4 write-up, the Monte Carlo stress tests and the variant system for switching strategies mid-round.

## Strategies by round

### Rounds 1 and 2: market making on two products
Code: [`rounds/round1-2/`](rounds/round1-2/). Round 1 trader: [`submission_r1_backup.py`](rounds/round1-2/submissions/submission_r1_backup.py). Round 2 trader: [`submission_r2_final.py`](rounds/round1-2/submissions/submission_r2_final.py).

- **ASH_COATED_OSMIUM:** market making around a fixed fair value of 10,000; take mispriced orders and quote one tick inside the bots' best price.
- **INTARIAN_PEPPER_ROOT:** market making around an EMA of the mid, with order-book imbalance and position skew in Round 1; it drifts upward each day.
- **Round 2 risk:** a four-tier inventory ladder (normal, aggressive, emergency, hard stop) at a position limit of 80.
- **Manual challenges:** notes on the Round 1 exchange auction (DRYLAND_FLAX, EMBER_MUSHROOM) and a Round 2 game-theory optimiser in [`rounds/round1-2/manual/`](rounds/round1-2/manual/).
- `scripts/` and `variants/` hold the log analysis, fill analysis, grid searches and the strategy variants tested along the way.

### Round 3: options market making with a delta hedge
Code: [`rounds/round3/`](rounds/round3/). Latest trader: [`submission_r3_v12.py`](rounds/round3/submission_r3_v12.py). Post-mortem: [`POSTMORTEM_R3.md`](rounds/round3/POSTMORTEM_R3.md).

- **HYDROGEL_PACK:** mean-reversion market making with a trend block and a circuit breaker.
- **VELVETFRUIT_EXTRACT:** market making on the underlying, which also hedges the vouchers' delta.
- **VEV vouchers:** European calls priced with Black-Scholes off a pooled implied-volatility EMA; quote the liquid strikes, skip the dead and deep in-the-money ones, halve size when expiry is under a day.
- **Testing:** a Monte Carlo stress test across scenarios ([`montecarlo.py`](rounds/round3/montecarlo.py)) and data forensics in `scripts/`.
- **Manual challenge:** a game-theory solver for the bidding problem, modelling other players' bids ([`rounds/round3/manual/`](rounds/round3/manual/)).

### Round 4: market making, options (vouchers) and counterparty signals
Full write-up: [`R4_STRATEGY_SUMMARY.md`](R4_STRATEGY_SUMMARY.md). Code: [`submission_r4_final.py`](submission_r4_final.py).

- **HYDROGEL_PACK:** mean-reversion market making around an EMA blended with a fixed anchor, with a trend block and a PnL circuit breaker.
- **VELVETFRUIT_EXTRACT:** market making on the highest-volume product; it also acts as the delta-hedge for the voucher book. The largest PnL source in Round 4 backtests.
- **Vouchers VEV_4000 to VEV_6500 (call options on VELVETFRUIT_EXTRACT):** priced with Black-Scholes from a pooled implied-volatility EMA; quote the live strikes, sell-only on far out-of-the-money strikes, delta-hedged in the underlying.
- **Counterparty research:** ranked the named traders by PnL and used the informed ones as a small fair-value skew on vouchers only, after A/B tests showed it hurt the underlying.
- Extra Round 4 parameter sweeps and counterparty analysis: [`rounds/round4-research/`](rounds/round4-research/).

### Round 5: 50 products in 10 groups, position limit 10
Code: [`submission.py`](submission.py). Live playbook: [`R5_DECISION_COMMANDER.md`](R5_DECISION_COMMANDER.md).

- **PEBBLES:** synthetic fair value from the five legs, which sum to a constant.
- **SNACKPACK_CHOCOLATE / SNACKPACK_VANILLA:** pair trade (statistical arbitrage) on a cointegrated spread; the other SNACKPACK flavours are market made with wide spreads.
- **ROBOT_DISHES / ROBOT_IRONING:** tick-fade market making on negative return autocorrelation.
- **GALAXY_SOUNDS, UV_VISOR, OXYGEN_SHAKE, PANEL, MICROCHIP, SLEEP_POD, TRANSLATOR and the other ROBOT products:** baseline market making with tight or wide quotes by product.
- **Risk:** per-strategy emergency brakes, a portfolio drawdown brake and a four-level fallback down to full liquidation.

## Testing before submitting

- [`montecarlo.py`](montecarlo.py): Monte Carlo simulator calibrated to Round 5 data, with synthetic order books, a fill engine, bootstrap resampling of the round's data and stress scenarios.
- [`r5_stress_harness.py`](r5_stress_harness.py): runs the trader through five stress scenarios (regime shift, no insider, crowded trade, limit stress, correlation break) and checks for position-limit breaches.
- [`variants/`](variants/): contingency versions of the Round 5 trader (no counterparty signal, high volatility, adversarial fills, inventory trap, signal loss, emergency brake), built from one source by `variants/build.py` and checked by `validate_variants.py`.
- [`scripts/`](scripts/): backtest runners for Rounds 4 and 5, grid search, data forensics (plots in `scripts/forensic_output/plots/`) and submission checks.
- [`visualiser/`](visualiser/): a Streamlit dashboard (order book, PnL and position over time), inspired by Frankfurt Hedgehogs' Prosperity 3 dashboard. [`tools/leaderboard_monitor.py`](tools/leaderboard_monitor.py) compares leaderboard snapshots and flags fast-moving teams.

## Tools used

Backtests run on [jmerle's open-source Prosperity backtester](https://github.com/jmerle/imc-prosperity-3-backtester) (`prosperity3bt`), adapted for Prosperity 4 product names, and the traders log in the format his visualiser reads.

## Not included

IMC's round data, logs and artwork, and other teams' public repos that I studied, are not in this repo.

---

Keywords: IMC Prosperity 4, Prosperity 4 Round 1, Round 2, Round 3, Round 4, Round 5, Prosperity 2026, IMC trading competition, algorithmic trading, market making, statistical arbitrage, pairs trading, options pricing, Black-Scholes, implied volatility, Monte Carlo backtesting, Python trading bot.
