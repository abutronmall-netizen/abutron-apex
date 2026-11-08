# APEX — Agentic Portfolio EXecution

A multi-agent, multi-asset automated trading desk: crypto, US equities, FX/indices and
**Deriv-style synthetic indices**, running against a **paper/demo account** with a hard
risk governor that can veto or flatten anything the strategy layer proposes.

```
                        ┌──────────────────────────────────────────────┐
      market data  ───▶ │  RegimeAgent ──▶ SignalAgents ──▶ Portfolio  │
   (synthetic / Deriv)  │      │            trend                │      │
                        │      │            mean-reversion       │      │
                        │      │            breakout             ▼      │
                        │      │            carry          RiskAgent    │
                        │      └── regime trust matrix ──▶  (caps, VaR, │
                        │                                   stops, kill)│
                        │                                        │      │
                        │   LlmAdvisor (optional, veto-only) ────┤      │
                        │                                        ▼      │
                        │                              ExecutionAgent   │
                        └────────────────────────────────┬──────────────┘
                                                         ▼
                                          PaperBroker / Deriv demo / Alpaca paper
```

---

## 1. What it actually does

Every bar, one complete decision cycle runs and is written to an audit log:

1. **RegimeAgent** classifies each instrument — `trend_up / trend_down / range / high_vol` —
   from ADX, normalised regression slope and realised-vol percentile.
2. **Signal agents** each form an independent opinion in `[-1, +1]` with a conviction score:
   `trend` (EMA structure), `meanrev` (z-score + RSI), `breakout` (Donchian + ATR buffer),
   `carry` (structural drift — the Boom/Crash asymmetry).
3. **PortfolioAgent** fuses opinions using a *regime-conditional trust matrix*, so
   mean-reversion is trusted in ranges and ignored in trends, and vice versa. It also
   learns **online agent reputation** (EWMA of score × subsequent return) so an agent that
   stops working is quietly demoted. Target weights are vol-targeted to 12% annualised.
3b. **ReflectionMemory** settles every decision 24 bars later against the realised return
   and the benchmark, and scores each agent *per regime* — edge in bps, hit rate, t-stat.
   That matrix is on the dashboard, with plain-English lessons generated from the settled
   statistics (no LLM). It can feed a shrunk trust multiplier back into the ensemble, but
   ships **observe-only** because the measured effect is inside the noise (see
   `docs/tauric-integration.md`).
4. **RiskAgent** runs a fixed ladder of hard limits — per-instrument cap → asset-class cap →
   correlation-cluster cap → stop-loss → net/gross leverage → portfolio vol band → 1-day 95%
   VaR → daily-loss and max-drawdown kill switch. **It can only shrink risk, never create it.**
5. **LlmAdvisor** (optional) may be consulted on a cooldown. It gets three read-only tools
   and may only return `scale ≤ 1.0` plus symbol vetoes. No API key → deterministic
   heuristic fallback, so the pipeline never depends on an LLM being reachable.
6. **ExecutionAgent** diffs target vs current book, applies hysteresis + a cost gate
   (never pay more than a third of the expected edge), slices child orders against a
   participation cap, and fills through a broker with a realistic cost model
   (half-spread + square-root market impact + commission + margin).

Everything is logged to `state/decisions.jsonl`: regimes, every signal and rationale, the
pre- and post-risk weights, risk breaches, advisor output, orders and fills.

![APEX dashboard](docs/dashboard.png)

---

## 2. Quick start

```bash
cd apex
pip install -r requirements.txt      # or: make install

make test                            # 48 unit + integration tests
make dashboard                       # → http://localhost:8000  (live paper desk)
make backtest                        # walk-forward backtest → results/
make sweep                           # multi-seed robustness sweep
make real                            # backtest on REAL market data (no API keys)
make ablate                          # per-agent counterfactual (who actually earns)
make collect                         # pull real bars into data_cache/
make serve                           # dashboard + paper loop on :8000
python3 scripts/remote_report.py     # paste-safe snapshot of a running desk
python3 scripts/run_deriv.py         # Deriv-only automatic signal->order
```

The dashboard streams a full engine state at 2 Hz over SSE: equity curve, regime map,
per-instrument target weights, agent roster with learned reputation, **the reflection
memory matrix (agent × regime edge, hit rate, t-stat) with auto-written lessons**, risk
governor gauges, live book, trade tape and the supervisor's decision notes. `Pause`, `Reset risk` and
`Flatten book` are wired to the API.

---

### Deriv-only: automatic signal → order

```bash
python3 scripts/run_deriv.py                       # paper, prints the decision tape
python3 scripts/run_deriv.py --live-demo           # route orders to a Deriv DEMO account
APEX_CONFIG=config/deriv_only.yaml python3 scripts/run_server.py --port 8001   # desk UI
```

`config/deriv_only.yaml` narrows the universe to the five synthetic indices, raises the
deriv asset-class cap to 200% of equity, and disables the `trend` agent — because the
reflection memory measured it at **t = −5.3 over 11,170 settled votes** on these symbols.

The runner prints one block per cycle, so signal → order is auditable line by line:

```
08:53 bar 1
  R_75     trend_down w= +0.00%  [meanrev+1.00 breakout-1.00]
  R_100    trend_down w= -5.78%  [breakout-0.57]
  BOOM500  high_vol   w= +0.00%  [meanrev-0.36 breakout+0.26 carry+0.85]
  CRASH500 trend_up   w= +0.00%  [meanrev+0.59 carry-0.85]
  stpRNG   trend_up   w= +0.00%  [meanrev+1.00 breakout-1.00]
  -> SELL R_100 3.6744 @ 1573.45 (5,781) increase
```

Measured on the synthetic harness (3200 bars, 5 instruments):

| | value |
|---|---|
| Return | **+7.62%** (CAGR +24.87%) |
| Sharpe / Sortino | **+2.32 / +3.31** |
| Max drawdown | **-3.30%** (Calmar +7.54) |
| Fills / profit factor | 236 / 1.92 |
| Benchmark (EW buy & hold 5 synthetics) | +36.39% |

4-seed robustness, same 2000 bars, before vs after acting on the memory:

| seed | trend on | trend off |
|---|---|---|
| 1000 | -5.22% | **+2.56%** |
| 1037 | +12.36% | -0.37% |
| 1074 | -7.94% | **+2.20%** |
| 1111 | -1.31% | **+2.29%** |
| **mean / median** | **-0.53% / -3.26%** | **+1.67% / +2.24%** |
| **σ across seeds** | 7.80% | **1.19%** |

Three of four seeds improved, the mean flipped positive and the dispersion collapsed by
6.5x. That is the reflection memory paying for itself: it flagged `trend` at t = −6.8 on
these symbols, and the counterfactual sweep confirmed the call at portfolio level.

## 2b. Real market data

`scripts/run_real.py` replays the same engine over **actual bars** — OKX (crypto),
Nasdaq (US equities), FRED (FX + index levels). No keys, everything cached to
`data_cache/`, universe intersected with whatever is reachable.

```bash
python3 scripts/run_real.py            # daily, 7 instruments, ~4 years
python3 scripts/run_real.py --freq 1h  # hourly crypto
```

First real run (2022-11-01 → 2026-10-23, 7 instruments, 1453 bars): **+24.79%, Sharpe
0.94, max DD −9.51%** against an equal-weight buy & hold of **+116.45%, Sharpe 1.20,
max DD −28.7%**. It lost to the benchmark — and at its design frequency (hourly crypto)
it is flat, PF 0.89. Full the write-up, feed caveats and the nine bugs real data
exposed: **[`docs/real-data-test.md`](docs/real-data-test.md)**.

### Per-agent ablation

`make ablate` disables one agent at a time and re-runs the whole book, because a
per-agent edge statistic is marginal and can point the wrong way (the reflection memory
scores `mean_reversion` at −141 bps, t = −3.1 on real bars — remove it and the book
gives up 12.5 points and 0.43 Sharpe).

## 2c. Running it on a server

APEX ships as a container with three roles that share one persistent volume:

```bash
docker build -t apex .
docker run -p 8000:8000 -v apex_data:/var/data \
  -e APEX_ROLES=web,collector,trader -e APEX_SECRETS=doppler -e DOPPLER_TOKEN=... apex
```

| role | process | what it does |
|---|---|---|
| `web` | `run_server.py` | dashboard, API, paper loop |
| `collector` | `collect.py --every 60` | bars + Deriv ticks + `MANIFEST.json` |
| `trader` | `run_deriv.py --live-demo` | Deriv **demo** orders (needs `DERIV_API_TOKEN`) |

`render.yaml` and `fly.toml` are included; `/healthz` drives the platform health check
and returns 503 when the loop stops stepping. Secrets come from Doppler / Infisical / a
mounted file at boot — the host holds only the bootstrap token, and the token itself is
never logged. Full runbook: **[`docs/deploy.md`](docs/deploy.md)**.

## 2d. Execution fidelity

`PaperBroker` models the venue, not just the price: orders **arrive on a later bar**
(`latency_bars: 1`), fill at most `participation_cap` (5%) of the volume that actually
traded, keep the remainder working, expire after `working_order_ttl_bars`, and never
stack. The risk kill switch bypasses latency — an exit is an urgency order.

Measured on real data (`make real`): the old instant-fill model gave +24.79% / Sharpe
0.94 / 168 trades; with venue timing it is +29.60% / 1.09 / 79 trades. That improvement
is one path and mostly noise — the point is that the model no longer assumes a trade at a
price nobody could have got. Write-up, including why NautilusTrader was the only one of
the five most-starred repos worth importing:
**[`docs/from-the-five-repos.md`](docs/from-the-five-repos.md)**.

## 3. Architecture

```
apex/
├── apex/
│   ├── config.py             # YAML config + env overrides
│   ├── engine.py             # ApexEngine: the supervisor (one cycle per bar)
│   ├── live.py               # LiveRunner: accelerated paper-trading loop
│   ├── core/
│   │   ├── models.py         # Quote/Bar/Signal/Order/Fill/Position/Decision
│   │   ├── history.py        # rolling store + time-aligned covariance
│   │   └── bus.py            # event bus + JSONL audit log
│   ├── data/
│   │   ├── synthetic.py      # regime-switching market simulator (5 asset models)
│   │   └── deriv_ws.py       # Deriv v3 WebSocket client (DEMO only) + tick→bar feed
│   ├── strategy/indicators.py# EMA/RSI/ATR/ADX/Donchian/z-score/vol (numpy only)
│   ├── agents/
│   │   ├── regime.py  signals.py  portfolio.py  risk.py  execution.py
│   │   ├── research.py       # event-intelligence overlay (down-only, optional)
│   ├── risk/limits.py        # covariance, portfolio vol, parametric VaR, clusters
│   ├── memory.py             # reflection memory: settle, score agents by regime, lessons
│   ├── llm/advisor.py        # OpenAI-compatible tool-calling advisor (veto-only)
│   ├── brokers/
│   │   ├── paper.py          # full cost model + margin
│   │   └── adapters.py       # Deriv demo (multipliers) + Alpaca paper
│   ├── backtest/             # walk-forward runner + metrics
│   └── api/server.py         # FastAPI: state, SSE stream, controls, health
├── config/default.yaml       # universe, agent params, risk ladder, execution model
├── ui/dashboard.html         # single-file console (no CDN, no build step)
├── scripts/                  # run_server.py, run_backtest.py, sweep.py
├── tests/                    # pytest
└── results/                  # report.json / report.md / equity.csv / trades.csv
```

### The synthetic market

Because you shouldn't need a broker account (or a live market) to evaluate a trading
system, `data/synthetic.py` generates a deterministic, seedable panel for all 13
instruments with: a shared risk factor (so cross-asset correlations are real), sticky
bull/bear/chop regimes per instrument, volatility clustering, fat-tailed shocks,
asset-class session masks (equities keep office hours), and four Deriv-style synthetic
models:

| Model | Symbols | Behaviour |
|---|---|---|
| `volatility` | `R_75`, `R_100` | pure martingale, vol scaled to 75% / 100% |
| `boom` | `BOOM500` | slow up-grind (~50%/yr) + rare violent down-spikes |
| `crash` | `CRASH500` | slow down-grind + rare violent up-spikes |
| `step` | `stpRNG` | discretised walk, 1-in-5 steps |

Synthetic indices are deliberately **independent** of the equity/crypto factor, they trade
24/7, and Boom/Crash are *engineered* with a positive drift and a lethal tail — which is
exactly why the `carry` agent takes the drift and the RiskAgent caps the size.

Swap in real data by implementing `warmup(n) -> {symbol: [Bar]}` and `stream() -> {symbol: Bar}`.
`DerivFeed` in `data/deriv_ws.py` already does this from live Deriv ticks.

---

## 4. Risk governor ladder

| Order | Control | Default |
|---|---|---|
| 1 | Max drawdown kill switch (flatten + halt) | 12% |
| 1 | Daily loss limit | 3% |
| 2 | Per-instrument weight cap | 25% |
| 3 | Asset-class gross cap (crypto/equity/fx/synthetic) | 30/45/40/30% |
| 4a | Correlation-cluster cap (ρ ≥ 0.85 ⇒ one cluster) | 35% |
| 4b | Stop-out cooldown after a stop triggers | 12 bars |
| 5 | ATR stop override per position | 4.0 × ATR |
| 6 | Gross leverage / net exposure | 2.5x / 1.5x |
| 7 | Portfolio vol band | 6–30% (target 12%) |
| 8 | 1-day 95% parametric VaR | 3.5% of equity |

The VaR number is computed from a shrunk covariance matrix built on **time-aligned**
returns — symbols that trade different hours are aligned by timestamp, never by index
(index alignment silently corrupts correlations, and it's the classic way a "diversified"
book turns out to be one trade).

---

## 5. Backtest results

Generated by `make backtest` (3200 hourly bars, 300-bar warm-up, seed 20261101):

<!-- RESULTS:START -->
| Metric | Value |
|---|---|
| Total return | +25.51% |
| Benchmark (equal-weight buy & hold) | +116.45% |
| Excess return | -90.94% |
| CAGR | +7.47% |
| Annualised volatility | 7.82% |
| Sharpe | +0.96 |
| Sortino | +1.18 |
| Max drawdown | -9.27% |
| Calmar | +0.81 |
| Fills | 160 |
| Win rate | 54.2% |
| Profit factor | 2.99 |
| Days simulated | 120.8 |

Per-instrument attribution:

| Symbol | Fills | Realised PnL | Notional traded |
|---|---|---|---|
| QQQ | 22 | +3,880 | 65,291 |
| R_75 | 50 | +1,294 | 139,954 |
| R_100 | 26 | +752 | 67,039 |
| CRASH500 | 20 | +562 | 58,057 |
| BOOM500 | 40 | +296 | 104,135 |
| SPY | 18 | +137 | 63,964 |
| US500 | 22 | +49 | 89,798 |
| NVDA | 6 | +37 | 15,705 |
| stpRNG | 46 | -48 | 134,212 |
| BTCUSD | 26 | -548 | 88,924 |
| ETHUSD | 32 | -1,011 | 92,315 |
| EURUSD | 162 | -1,030 | 244,446 |
| GER40 | 64 | -1,675 | 289,099 |

Reproduce with `make backtest`; artefacts in `results/report.json`, `results/report.md`, `results/equity.csv`, `results/trades.csv`.
<!-- RESULTS:END -->

Multi-seed robustness (`make sweep`, 1600 bars, 3 seeds):

| seed | return | Sharpe | max DD | fills |
|---|---|---|---|---|
| 1000 | +6.26% | +3.54 | -2.05% | 277 |
| 1037 | +11.20% | +6.84 | -1.75% | 345 |
| 1074 | -2.94% | -1.84 | -5.75% | 58 |
| **mean / median / σ** | **+4.84% / +6.26% / 5.86%** | | | |

**Read this before you judge the numbers.** The harness is synthetic: it is built to
exercise the machinery (regimes, costs, limits, kill switches) — not to be a source of
alpha. Hourly technical signals on a near-random panel after realistic spreads produce a
Sharpe near zero regardless of implementation quality. `make sweep` runs the same config across several seeds so you can see the
distribution instead of one lucky path — and as the table above shows, the dispersion is
larger than the mean, which is what "no real edge" looks like from the inside.

What the system *is* graded on here: no lookahead (the same event-driven cycle runs in
backtest and live), costs and margin modelled on every fill, risk limits that actually
bind, and a complete audit trail.

---

## 6. Connecting a Deriv demo account

1. Create a **demo** account at `app.deriv.com`, create an API token with `read` +
   `trade` scope, and export it — never hardcode it:

```bash
export DERIV_API_TOKEN="your_demo_token"
```

2. Sanity-check the connection (blocking, prints ticks):

```python
from apex.data.deriv_ws import DerivClient
c = DerivClient(app_id="1089", token=None)      # public app id, no auth needed for ticks
c.start(["R_75", "BOOM500", "CRASH500"])
print(c.snapshot())
```

3. To trade, pass the token and use `DerivBroker` with `APEX_MODE=live_demo`. The client
   refuses any account where `is_virtual == 0`, so a real-money token cannot be used by
   accident. Stakes are capped at `live.deriv.max_stake_pct` (5%) of equity.

Alpaca paper works the same way (`ALPACA_KEY_ID` / `ALPACA_SECRET_KEY`), and the adapter
rejects any endpoint that is not `paper-api.alpaca.markets`.

---

## 7. Configuration cheatsheet

| Key | Meaning |
|---|---|
| `system.seed` | deterministic market + run |
| `account.leverage` | margin cap (5x) |
| `universe[].max_weight` | per-instrument cap, drives sizing |
| `agents.fusion.rebalance_every` | bars between full re-optimisations (72 = 3 days) |
| `agents.fusion.rebalance_threshold` | hysteresis band, the main turnover dial |
| `agents.fusion.smoothing` | EWMA on target weights |
| `risk.target_annual_vol` | vol target used by the scaler |
| `execution.impact_coef` | square-root impact coefficient |
| `agents.fusion.memory_influence` | reflection memory sized into the ensemble (0 = observe-only) |
| `agents.fusion.memory_horizon` | bars until a decision is settled and scored |
| `agents.research.enabled` | event-intelligence overlay (down-only) |
| `llm.enabled` + `APEX_LLM_API_KEY` | turn the advisory layer on |
| `llm.max_risk_scale` | how far the advisor may cut risk (60%) |

Environment overrides: `APEX_MODE`, `APEX_EQUITY`, `APEX_SEED`, `APEX_TARGET_VOL`,
`APEX_LLM_ENABLED`, `APEX_LLM_MODEL`, `APEX_LLM_BASE_URL`, `APEX_PORT`.

---

## 8. Extending

* **New signal agent** — subclass `SignalAgent`, implement `generate(ctx, symbol) -> Signal|None`,
  register it in `ApexEngine.__init__`, then give it a trust weight per regime in
  `agents/portfolio.py::REGIME_TRUST`. It starts with neutral reputation and earns its size.
* **New instrument** — add an entry to `config/default.yaml::universe` (asset class drives
  the session mask, cost model, annualisation and limits).
* **New venue** — implement `set_quote/submit/equity/positions/flatten` (see
  `brokers/adapters.py`) and pass it to `ApexEngine(broker=...)`.
* **New LLM tool** — add it to `TOOLS` and `_dispatch` in `llm/advisor.py`. Keep it
  read-only: the advisor's only write actions should stay `scale` and `veto`.

---

## 8b. Research & external references

`docs/tauric-integration.md` is a full review of
[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) and
[Trading-R1](https://arxiv.org/abs/2509.11420), with a capability matrix, what was
imported (event-intelligence overlay, reflection memory), what was deliberately rejected
(LLM risk committees, LangGraph in the hot path, LLM-in-the-loop backtests), and a phased
plan with acceptance criteria.

## 9. Honest limitations

* Paper/demo only by design. There is no order-type support beyond market/slice, no
  partial-fill/queue modelling beyond the impact function, and no borrow/financing model.
* The synthetic harness is not a market. Its regimes are more persistent and its reversion
  more regular than reality; treat any positive Sharpe there as *plumbing verified*, not edge.
* The LLM advisor is a risk *reducer*. It is not alpha, it is never on the hot path, and if
  it fails (network, auth, garbage JSON) the system degrades to no-change.
* Two consecutive regimes can be misclassified during transitions; the hysteresis,
  reputation decay and stop cooldowns exist precisely to blunt that.

**Not investment advice. Run it on a demo account until you can explain every number it
prints.**
