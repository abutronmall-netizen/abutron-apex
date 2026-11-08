# Real-data test — 2022-11-01 → 2026-10-23

The APEX engine on **actual market data** instead of the synthetic generator. Same
agents, same risk governor, same cost model, same walk-forward loop — only the bars
changed.

```
python3 scripts/run_real.py              # daily bars, ~4 years, 7 instruments
python3 scripts/run_real.py --freq 1h    # hourly crypto
python3 scripts/agent_ablation.py        # per-agent counterfactual on real bars
```

> **Revision note.** The first version of this document reported +14.62% / Sharpe 0.96.
> It was measured before the sizing bug in §4.1 was found. Everything below is
> post-fix; the bug changed the return by 10 points and the Sharpe by nothing, which
> is exactly what a sizing bug should do.

---

## 1. Where the data came from

No API keys. Each source is cached to `data_cache/<SYMBOL>[_1D].csv` so a run is
reproducible offline.

| Instrument | Source | Endpoint | Bars | Window |
|---|---|---|---|---|
| BTCUSD | OKX | `/api/v5/market/history-candles?bar=1D` | 1500 | 2022-09-24 → 2026-11-01 |
| ETHUSD | OKX | same | 1500 | 2022-09-24 → 2026-11-01 |
| SPY | Nasdaq | `/api/quote/SPY/chart` | 1003 | 2022-11-01 → 2026-10-30 |
| QQQ | Nasdaq | `/api/quote/QQQ/chart` | 1003 | 2022-11-01 → 2026-10-30 |
| NVDA | Nasdaq | `/api/quote/NVDA/chart` | 1003 | 2022-11-01 → 2026-10-30 |
| EURUSD | FRED | `fredgraph.csv?id=DEXUSEU` | 995 | 2022-11-01 → 2026-10-23 |
| US500 | FRED | `fredgraph.csv?id=SP500` | 1001 | 2022-11-01 → 2026-10-28 |

Aligned panel: **7 instruments × 1453 daily bars**, 2022-11-01 → 2026-10-23.

* FRED publishes a close only — `o = h = l = c`, so the breakout agent degenerates to a
  close-channel on those two instruments.
* Equities/FX have holes (weekends, holidays). The panel forward-fills closes and marks
  the symbol **inactive** for that row, so the engine never trades a stale price.

### What could not be reached from this sandbox

| Feed | Status | Why |
|---|---|---|
| Deriv synthetics (R_75 … stpRNG) | **blocked** | `ws.derivws.com` returns HTTP 520 for every handshake *and* for plain HTTPS GETs. Not a code problem — `deriv.com` and `api.deriv.com` answer normally. |
| Yahoo Finance (hourly equities) | rate-limited | First request succeeded, the burst got 429s and the IP stayed throttled. Source is wired; it works from a normal connection. |
| Stooq (hourly equities/FX) | blocked | JavaScript proof-of-work challenge on every request. |
| GER40 | no free source found | Dropped rather than simulated. |

**Everything reported below is real.** The five Deriv synthetics are simply absent, so
this test says nothing about them either way.

---

## 2. Result (post-fix)

![APEX vs buy & hold on real data](real_equity.png)

Over 1152 trading days (3.15 years):

| | APEX | Equal-weight buy & hold |
|---|---|---|
| Total return | **+24.79%** | **+116.45%** |
| CAGR | +7.27% | +27.74% |
| Volatility (ann) | **7.83%** | 22.63% |
| Sharpe | 0.94 | **1.20** |
| Sortino | 1.14 | — |
| Max drawdown | **−9.51%** | −28.70% |
| Calmar | 0.76 | 0.97 |
| Trades / PF / win | 168 / 2.94 / 53.9% | — |
| Turnover | 6.96x | 0 |

Attribution:

| Symbol | PnL | Trades | Buy & hold over the window |
|---|---|---|---|
| NVDA | +10,462 | 10 | +1457.7% |
| QQQ | +5,349 | 16 | +156.0% |
| SPY | +5,249 | 16 | +97.6% |
| US500 | +4,235 | 28 | +97.7% |
| EURUSD | −1,088 | 52 | +13.5% |
| ETHUSD | −2,437 | 14 | +48.0% |
| BTCUSD | −3,634 | 32 | +291.0% |

**Verdict: the platform still loses to buy & hold, on return and on Sharpe.** It is
disciplined — 7.8% volatility, a 9.5% worst drawdown, PF 2.94, positive in 4 of 7
instruments — but an equal-weight long-only basket in a historic bull run is a brutal
benchmark for a low-beta book, and APEX did not beat it risk-adjusted either (0.94 vs
1.20).

The equity sleeve earned **+25,295**; crypto gave back **−6,071**.

### At the design frequency it is flat

The agents were tuned on hourly bars, so the honest test is hourly. 4,320 real hourly
BTC/ETH bars (6 months):

| | APEX | Buy & hold |
|---|---|---|
| Return | +0.17% | +3.90% |
| Sharpe | 0.12 | — |
| **Profit factor** | **0.89** | — |
| Trades | 110 | — |

PF below 1: at the cadence the system was designed for, gross alpha does not cover
costs. The daily result above is a better number from an *off-label* frequency — the
24-bar lookbacks silently became 24-day lookbacks.

---

## 3. Per-agent ablation — the headline finding

Per-agent memory statistics are **marginal**: they score a signal alone, with no regard
for how it interacts with the fusion, the caps or the vol target. The trustworthy
measurement is a counterfactual run. On real daily bars:

| book | return | Sharpe | max DD | PF | trades | marginal |
|---|---|---|---|---|---|---|
| all agents | +24.79% | 0.94 | −9.51% | 2.94 | 168 | — |
| without **trend** | +10.32% | 0.86 | −6.79% | 1.66 | 138 | **−14.47% / −0.08** |
| without **mean_reversion** | +12.34% | 0.51 | −10.18% | 2.09 | 188 | **−12.45% / −0.43** |
| without **breakout** | +25.51% | 0.96 | −9.27% | 2.99 | 160 | +0.72% / +0.02 |

Read the third column: removing trend costs 14.5 points, so **trend is the engine**.
Removing mean-reversion costs 12.5 points and 0.43 Sharpe — yet the reflection memory
scores `mean_reversion` at **−141 bps, t = −3.1** on the same data. That statistic says
"throw it away"; the counterfactual says it is the second most valuable agent (it acts
as a brake on trend, and the two together are worth more than either alone).
Breakout is a marginal drag (−0.72%, −0.02 Sharpe) — noise, not a finding.

This is why the ablation script now exists and why no agent is disabled on the strength
of a t-stat alone.

---

## 4. Bugs this test found — all fixed

### 4.1 The sizing bug (the expensive one)

`PortfolioAgent._vol_target()` annualised the realised portfolio return stream with a
**hard-coded `sqrt(6240)`** — the hourly constant. On daily bars the true factor is
`sqrt(365.25)`, so the estimated volatility was **4.1x too high**, the scale factor
`target/realised` was 4.1x too small, and the book was sized at roughly a quarter of its
intended risk. The system wasn't cautious by design; it was mis-measuring.

Measured effect on the real daily test:

| | before | after |
|---|---|---|
| avg gross exposure | 29.6% (max 52.7%) | ~76–80% |
| realised vol | 4.60% | 7.83% |
| return | +14.62% | **+24.79%** |
| Sharpe | 0.96 | 0.94 |
| max drawdown | −4.36% | −9.51% |

Ten points of return appeared and the Sharpe did not move — the signature of a pure
sizing bug. Realised vol is still short of the 12% target because per-instrument caps
(20–35%) bind; that is policy, not a defect.

### 4.2 Everything else that was hard-coded to hourly

| # | Bug | Fix |
|---|---|---|
| 1 | `compute_metrics` annualised with a constant 6240 regardless of bar spacing → daily Sharpe reported **3.98** instead of 0.96 | inferred from timestamps; `bars_per_year_used` written into every report |
| 2 | `_benchmark` had the same bug → benchmark Sharpe 4.94 instead of 1.20 | same fix |
| 3 | `bars_per_year` had no daily table (crypto needs 365, equities 252) | `set_period("1D")` switch |
| 4 | session masks dropped every daily row (all hours ≥ 7) | masks off in daily mode |
| 5 | panel builder indexed the grid instead of the data → `IndexError` on a weekend tail | forward-fills the data row |
| 6 | `tail_ratio` divided by a percentile that can be ~0 → emitted **5,183,140,626.75** | floored and clamped to [0, 10] |
| 7 | skew/kurtosis computed from raw moments with `nan_to_num` in the wrong place | clean moment helpers |
| 8 | feed clients assumed a friendly server | FRED needs `--http1.1` (drops HTTP/2 streams for browser UAs), OKX/Nasdaq need pagination and UA headers, Yahoo needs pacing |
| 9 | memory state shared between the 13-instrument desk and the deriv-only desk | per-profile `memory_file` |

Regression tests now cover the period switch, timestamp-inferred annualisation, panel
alignment/forward-fill, the "never trade an inactive symbol" invariant, tail-ratio
bounds and the vol-target annualisation. `make test` → **35 passed**.

---

## 5. What to do next

1. **Nothing beats beta by accident.** APEX is a low-beta, vol-targeted book; it will
   lose return races to a bull market by construction. The only fair scoreboard is
   Sharpe against a matched-vol benchmark, and there it currently loses. Fixing that is
   a research problem, not a bug.
2. **Crypto is the leak.** −6,071 in a window when BTC tripled. Ask the ablation script
   what is happening inside the crypto sleeve before allocating more.
3. **Re-tune per frequency.** `rebalance_every`, lookbacks and `memory.H` are all
   hour-shaped. A daily profile needs its own numbers.
4. **Get hourly equities.** Daily bars are ~1,000 samples: enough to reject a claim, not
   enough to accept one. Yahoo hourly works from a normal connection — 5x the samples.
5. **Never trust a per-agent statistic.** Use `make ablate`.
