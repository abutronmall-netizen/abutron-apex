# The five most-starred AI trading repos — what I took, what I refused

Source: [FullStack Alpha, *I opened the 5 most-starred AI trading repos on GitHub*](https://medium.com/@fullstackalpha/i-opened-the-5-most-starred-ai-trading-repos-on-github-ad4e6eb65265)
(Oct 2026). The lineup: **TradingAgents**, **ai-hedge-fund**, **OpenBB**, **FinRobot**,
**NautilusTrader**.

The article's own conclusion is the right place to start, because it matches what this
project has measured the hard way:

> "No repo on this list hands you a guaranteed edge... Four of those five never touch a
> brokerage account."

That is exactly the finding of [`real-data-test.md`](real-data-test.md): the bottleneck in
APEX was never the absence of more agents or more opinions — it was execution fidelity,
measurement discipline and costs. So the useful imports are **infrastructure**, not
alpha.

---

## Verdict per repo

| Repo | What it actually is | Verdict for APEX |
|---|---|---|
| **NautilusTrader** | Rust-native, multi-venue execution engine. Same strategy code in backtest and live. LGPL-3.0. | **Adopted — the one real import.** Backtest/live parity: latency, partial fills, order TTL, no order stacking. |
| **OpenBB** | Research/data layer over ~30 providers via one SDK. | **Deferred, not adopted.** Correct answer on a real server; here the blocker is egress, not provider choice. See below. |
| **TradingAgents** | LLM analyst debate → memo. | Already adopted in an earlier pass — see [`tauric-integration.md`](tauric-integration.md). Nothing new. |
| **ai-hedge-fund** | Investor-persona agents that vote on a stock. Own README calls it a proof of concept. | **Refused.** APEX already runs a weighted multi-agent vote with regime-conditional trust and a reflection memory that settles every call. Personas add opinions, not signals, and no measured edge. |
| **FinRobot** | Academic agent toolkit. | **Refused.** Its own README warns the local API is unauthenticated in browser mode. It generates research reports; APEX does not need a report generator. |

---

## The one change that shipped: venue behaviour

`PaperBroker` used to fill an order **at the price that generated it**. A signal computed
on bar *t*'s close was executed at bar *t*'s mid — a trade nobody could have made. That is
precisely the gap NautilusTrader's README warns about ("venue, timing and reconciliation
behaviour a simulation may not reproduce"), and it flatters every backtest in the repo.

Now, per `config/default.yaml → execution`:

```yaml
latency_bars: 1            # an order fills on a later bar, never the one that made it
working_order_ttl_bars: 3  # unfilled remainder is cancelled, not carried forever
participation_cap: 0.05    # at most 5% of the volume that actually traded
```

Behaviour added to `apex/brokers/paper.py`:

1. **Deferred arrival.** `submit()` validates (dust, margin) then rests the order; it fills
   when `begin_bar()` reaches `due`. The fill price is the *next* bar's book — good or bad.
2. **Partial fills.** A fill is capped at `participation_cap × bar volume`; the remainder
   stays working and can fill on later bars (`partial_fills` counter).
3. **Order expiry.** Anything unfilled after `ttl` bars is cancelled and logged
   (`expired_orders`), instead of silently resting through the whole backtest.
4. **No stacking.** Re-signalling the same symbol+side while an order rests **replaces**
   it (`replaced_orders`). Without this the book quietly doubles: the first draft of this
   change pushed gross exposure from 0.30x to 0.56x of equity on the synthetic harness.
5. **Kill switch bypasses latency.** `flatten()` goes straight to the fill path. A risk
   exit is an urgency order; it must not be delayed by our own simulation.

### Measured effect

Real data, 7 instruments, 2022-11 → 2026-10 (the `make real` window):

| | latency 0 (old) | latency 1 (now) |
|---|---|---|
| Return | +24.79% | +29.60% |
| Sharpe | 0.94 | 1.09 |
| Max drawdown | −9.51% | −6.82% |
| Trades | 168 | 79 |
| Profit factor | 2.94 | 6.03 |

Synthetic harness, 900 bars, seed 42:

| | latency 0 | latency 1 |
|---|---|---|
| Fills | 168 | 209 (69 partial) |
| Equity | 98,133 | 98,689 |
| Gross / equity | 0.30 | 0.51 |

**Do not read the improvement as a win.** It is one path with 79 trades, and the fills
that disappeared were churn. What can be said with confidence is narrower and more useful:
the model is now conservative in the right direction (you cannot trade a price you have
not seen, you cannot take more than the market traded, you cannot leave an order resting
forever), and the accounting still reconciles to the cent
(`equity == cash + unrealised + realised`, error `0.000000`) with partials, expiries and
replacements all active. The honest expectation is that this change makes future results
*look worse*, because it removes a structural optimism.

All five behaviours are covered by tests: `test_order_never_fills_on_the_bar_that_created_it`,
`test_participation_cap_partially_fills_and_carries_the_remainder`,
`test_working_order_expires_after_ttl`, `test_working_orders_do_not_stack`,
`test_kill_switch_flatten_ignores_latency`. Suite: **48 passed**.

---

## Why OpenBB is deferred rather than adopted

OpenBB is the right library for the job the article assigns it — one SDK over ~30
providers, which would fix APEX's real data problem (Yahoo rate-limits this IP, Stooq
serves a JavaScript challenge, so the real-data test runs on 7 of 13 instruments).

It is deferred for two honest reasons:

1. **The blocker here is egress, not provider choice.** The sandbox reaches a fixed
   allowlist of domains; adding OpenBB adds providers reachable only from a machine with
   open network. On the box in [`deploy.md`](deploy.md) it is a genuine upgrade.
2. **It is a dependency with teeth** — a provider abstraction layer that would touch every
   fetch path in `apex/data/real.py`, and I would be shipping it untested against 30 live
   endpoints from a sandbox that can reach four of them. Shipping an untested data layer
   is how backtests quietly start using the wrong series.

The concrete next step is written down rather than guessed at: move `real.py` behind a
provider chain (primary → fallback → cooldown on repeated failure, health visible in
`MANIFEST.json`), then verify on the server where all providers are reachable.

---

## What the article gets right, and where I disagree

*Right:* "Stars count clicks." "Backtested only means something if you know the data
window, the slippage assumptions and the sample size." Both apply to this repo — which is
why every number above carries its window and its trade count.

*Where I'd push back:* the piece treats execution engines as the strictly later step
("NautilusTrader only after a strategy has survived a real backtest"). In practice the
execution model **is part of the backtest**. A strategy that only survives with zero
latency and full fills has not survived a real backtest, it has survived an optimistic
one. That is why the Nautilus lesson was worth importing *before* any alpha work, not
after.
