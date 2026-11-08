# Can TauricResearch improve APEX?

**Verdict: yes — but only in one direction, and it is not the direction it looks like.**

TradingAgents is a better *research* firm than APEX. APEX is a better *trading system*
than TradingAgents. Bolting their agent graph onto APEX's hot loop would make APEX
slower, more expensive, less testable and more dangerous. Taking their **event
intelligence + reflection memory** and putting it behind APEX's existing down-only
guardrail gives you the one thing APEX genuinely lacks: a reason to *not* trade that
isn't derived from price.

I've built that layer: `apex/agents/research.py` (disabled by default, 2 new tests).

---

## 1. What is actually in the org

| Repo | What it is | State |
|---|---|---|
| **[TradingAgents](https://github.com/TauricResearch/TradingAgents)** | Multi-agent LLM trading *firm* simulation, LangGraph, Apache-2.0 | ~120k ★, 22.9k forks, actively released (v0.7.1, Oct 2026) |
| **[Trading-R1](https://github.com/TauricResearch/Trading-R1)** | An LLM fine-tuned (SFT + 3-stage RL curriculum) to produce risk-aware, volatility-adjusted trading theses ([arXiv 2509.11420](https://arxiv.org/abs/2509.11420)) | Paper published; **terminal still "coming soon"**, repo last touched Sep 2025 |

TradingAgents' pipeline (per decision, per ticker):

```
Analyst team (parallel)          Researcher team            Trader       Risk team          Portfolio Mgr
fundamentals ─┐
sentiment   ─┼─▶ reports ──▶  bull ⇄ bear debate  ──▶  proposal ──▶ risky ⇄ neutral ⇄ safe ──▶ approve/reject
news        ─┤                     (N rounds)                         (N rounds)                  │
technical   ─┘                                                                                     ▼
                                                                                        simulated exchange
```

Plus the parts that don't make the diagram: a **memory log** that settles past decisions
against realised return *and alpha vs a regional benchmark*, writes a one-paragraph
reflection, and feeds the most recent lessons back into the Portfolio Manager;
**checkpoint resume**; a **backtest grid** over tickers × dates; and a serious amount of
**point-in-time discipline** (SEC EDGAR served *as filed*, not as later restated).

That last point matters more than the agent zoo, and I'll come back to it.

---

## 2. Capability matrix

| Dimension | APEX (yours) | TradingAgents | Who wins |
|---|---|---|---|
| **Universe** | 13 instruments: crypto, US equities, FX/indices, **Deriv synthetics** (R_75, Boom/Crash, Step), 24/7 session masks | Yahoo-covered equities + spot crypto (`BTC-USD`) | **APEX** — they have no concept of a synthetic index |
| **Decision cadence** | ~2 ms per cycle, 13 instruments, every bar | Seconds–minutes, **tens of LLM calls per decision**, one ticker per run | **APEX**, decisively |
| **Risk enforcement** | Deterministic ladder: VaR, correlation clusters, vol targeting, ATR stops, gross/net caps, kill switch — *code that returns floats* | A risk **debate** producing prose the PM reads | **APEX**, by a mile. Their "risk team" cannot enforce a number |
| **Execution realism** | Half-spread + square-root impact + participation caps + margin + per-fill audit | Simulated exchange, essentially no cost model | **APEX** |
| **Why-did-it-happen** | Indicator rationale strings (`z=+2.1 vs 40-bar mean, RSI 71`) | Fundamentals, filings, news, social sentiment, dated theses | **TradingAgents**, decisively |
| **Learning from mistakes** | Numeric EWMA reputation per agent×instrument | Textual reflection per decision, settled vs realised return **and benchmark alpha** | **TradingAgents** — richer, and explainable |
| **Backtest integrity** | Lookahead-free by construction (event-driven, same code path live/backtest) | Lookahead-free only because they spent *four releases* fixing it | Draw |
| **Provider flexibility** | One advisor, one OpenAI-compatible endpoint | 15+ providers, quick/deep model tiers on different providers per role | **TradingAgents** |
| **Setup cost** | `pip install -r requirements.txt`, runs offline | API keys, `pip install .`, LangGraph, per-run LLM spend | **APEX** |

---

## 3. What is worth stealing — ranked

### ① Event intelligence as a *veto*, not a signal  ★★★★★
APEX is blind to everything that isn't price. An FOMC print, an earnings date, a
halted venue, a regulatory headline — none of that exists in a Donchian channel. Their
analyst team is precisely a machine for "what is about to make my chart meaningless".

**How to use it without breaking APEX:** the research output is not a signal, it is a
*risk overlay* — `{conviction_mult ≤ 1, stop_mult ≥ 1, veto_bars ≥ 0}`. It runs once a
day, not once a bar. `→ shipped in apex/agents/research.py`.

### ② Reflection memory with benchmark-relative settlement  ★★★★☆
APEX's reputation layer knows *that* the trend agent is bad; it can't say *why*. Their
memory log records the decision, waits out the holding period, computes PnL **and alpha
vs the regional benchmark**, then writes a lesson paragraph that the next run reads.

**Cheap version for APEX** (no LLM needed): settle each decision at horizon H, store
`{regime, agent votes, realised return, alpha vs sector benchmark}` and fit a small
per-(agent, regime) hit-rate table. That turns the reputation EWMA from a black box into
something you can put on the dashboard. **LLM version:** generate the paragraph only for
the 10 worst and 10 best decisions per week — ~20 calls/week, not 20 calls/decision.

### ③ Bull-vs-bear debate for *bounded* decisions  ★★★☆☆
Their adversarial debate is a genuinely better aggregation rule than APEX's weighted
average when signals conflict — a thesis that survives a bearish attack is worth more
than a 0.62 score. But it is unaffordable per bar.

**Use it at re-optimisation points, on the top-k names only** (k≈3 by proposed |weight|),
with a strict token budget: 2 debates/day × 2 rounds ≈ 8 calls/day. If the bear wins,
cut conviction and log the invalidation level; if it can't produce one, ignore the debate.

### ④ Quick/deep model tiers  ★★★☆☆
Trivial to copy, real quality/cost win: a cheap model for routine overlays, an expensive
one for the daily review. `llm.model` / `llm.model_deep`.

### ⑤ The point-in-time checklist  ★★★★★ (for real data, worthless for synthetic)
Their changelog is a catalogue of lookahead bugs they had to fix: *"fix for model dates
that could read filings made after the run date"*, *"backtests scored from the first close
after each decision"*, *"backtests that see only data published by each analysis date"*.
When you swap APEX's synthetic panel for real feeds, this is your acceptance checklist:
every feature must be a function of data **published** before `ctx.ts`, and fills must
happen at the first price *after* the decision.

### ⑥ Trading-R1 — interesting, not actionable
A model trained with RL to write volatility-adjusted theses is a better *advisor* than a
prompted GPT — but the terminal isn't released, the eval is 6 equities/ETFs, and you
cannot self-host the weights from a repo that isn't there. Revisit when it lands. The
*idea* worth copying now: **size the thesis by realised vol**, which APEX already does.

---

## 4. What NOT to steal

| Tempting | Why it's wrong for APEX |
|---|---|
| Replace the agent ensemble with their graph | APEX runs 13 instruments every bar; they run 1 ticker per multi-minute session. Wrong shape of machine. |
| Let the "risk team" talk instead of computing | An LLM saying "risk looks elevated" cannot cap gross at 2.5×. Keep floats, keep the ladder. |
| LangGraph as the orchestrator | Correct for checkpointed, human-in-the-loop, minutes-long research runs. Wrong for a millisecond loop with a kill switch — you'd add latency, hidden state and a failure mode near the order path. Use it *around* APEX for the daily research job, not *inside* it. |
| LLM in the hot path | Every LLM call is a timeout risk on the path to an order. APEX's advisor is already off the critical path; keep it that way. |
| Treating 120k stars as evidence of edge | It's evidence of a great *demo and README*. Their own disclaimer says research use only. Popularity is not Sharpe. |
| Dropping the synthetic harness for Yahoo data | You'd inherit their entire lookahead problem on day one, and lose deterministic, cost-free regression tests. |

---

## 5. The architecture I'd actually run

Two planes, one direction of authority:

```
┌───────────────────── RESEARCH PLANE (slow, LLM, minutes) ─────────────────────┐
│  TradingAgents-style analyst team · bull/bear debate · reflection memory      │
│  cadence: 1×/day per instrument  ·  budget: ~40-100 LLM calls/day             │
│  output: EventOverlay{symbol, conviction_mult ≤1, stop_mult ≥1, veto_bars ≥0, │
│                        thesis, invalidation}                                  │
└───────────────────────────────────┬───────────────────────────────────────────┘
                                    │  down-only, clipped, logged
                                    ▼
┌───────────────────── EXECUTION PLANE (fast, deterministic, ms) ───────────────┐
│  Regime → Signals → Portfolio → RiskAgent → [overlay] → Execution → Broker    │
│  authority: ONLY this plane can size, hedge, flatten or halt                  │
│  invariant: no research output can increase exposure, ever                   │
└───────────────────────────────────────────────────────────────────────────────┘
```

The rule that keeps you solvent: **research may only remove risk.** It is the same
guardrail already protecting the LLM advisor — an LLM that hallucinates can cost you
opportunity, never capital.

---

## 6. The look-ahead trap (read this before any LLM backtest)

An LLM asked to analyse "NVDA on 2026-09-01" already knows what NVDA did in October.
Every backtest that puts a language model in the decision loop is therefore suspect until
proven otherwise — which is exactly why TauricResearch's release notes are dominated by
point-in-time fixes rather than features.

Rules for APEX if you enable the research layer:

1. The prompt may contain **only** data timestamped before `ctx.ts`. No raw price series
   extending past the decision.
2. Fill at the **first price after** the decision, never the bar that produced it.
3. Backtest the overlay layer **empty first**, then enabled — the delta is the only honest
   measure of what the LLM contributed.
4. Keep `research.enabled: false` in CI. LLM non-determinism must never be able to turn a
   green build red.

---

## 7. What I shipped today

`apex/agents/research.py` — the contract from §5, working, with no API key required:

| Piece | Notes |
|---|---|
| `EventOverlay.clip()` | Hard guardrail: `conviction_mult ∈ [0,1]`, `stop_mult ∈ [1,3]`, `veto_bars ≥ 0`. Clipping is **not** configurable. |
| `CalendarProvider` | Deterministic blackout windows (`{"2026-11-05": ["SPY","US500"]}`). Zero hallucination surface. |
| `LlmResearchProvider` | OpenAI-compatible, JSON out, rejects any symbol not in the input list. |
| `HeuristicProvider` | Offline fallback: vol-percentile breakouts + agent disagreement. |
| `ResearchAgent` | Refreshes every `refresh_every` bars (default 24), applies a down-only transform to the post-risk book, logs every overlay into the decision record. |
| Wiring | Runs **after** `RiskAgent`, **before** `ExecutionAgent` — so it can only trim an already-legal book. Failures degrade to pass-through. |
| Config | `agents.research: {enabled: false, refresh_every: 24, max_veto_bars: 24}` |
| Tests | `test_research_overlay_can_only_reduce`, `test_research_never_levers_up` (24 tests total, all green) |

Deliberately **off by default**: enabling a new risk input after publishing a backtest
without re-running `make sweep` is exactly the kind of unmeasured change that makes a
strategy look better and behave worse.

### P2 shipped — reflection memory (`apex/memory.py`)

Every decision is logged with an open horizon. Once `H = 24` bars have passed it is
**settled** against the realised return and the equal-weight benchmark, which updates a
sufficient-statistics cell per `(agent, regime)`:

```
agent      trend_up    trend_dn     range      high_vol        <- edge, bps per 24 bars
trend          -41         -46        -119        -202
meanrev         +5         -13        +133        +457
breakout      +325        -638        -377       -1021
carry          +22         -26         -62        +143
```

That table is on the live dashboard, with `n`, hit rate and t-stat per cell, plus
plain-English lessons derived only from settled statistics — e.g.
*"meanrev pays in high vol: +457bps per 24 bars over 54 votes (hit 70%, t=+1.4)"*,
*"breakout hurts in trend down: -630bps over 151 votes (hit 57%, t=+0.3) — right often,
wrong big"*. The last clause appears automatically when hit rate and edge disagree,
which is the useful case: a strategy that is right 57% of the time and still loses money
is losing in a fat left tail, and that is exactly what the risk ladder exists to cap.

**Measured A/B** (`--set agents.fusion.memory_influence=1.0`, 1600 bars, 5 seeds):

| seed | off | on | Δ sharpe |
|---|---|---|---|
| 1000 | +6.26% / S3.54 | +6.60% / S3.73 | +0.19 |
| 1037 | +11.20% / S6.84 | +11.45% / S6.92 | +0.08 |
| 1074 | -2.94% / S-1.84 | -2.83% / S-1.81 | +0.03 |
| 1111 | +0.58% / S0.36 | +0.19% / S0.15 | -0.21 |
| 1148 | +11.11% / S5.87 | +9.26% / S5.12 | -0.75 |

> **Note (post-fix):** the returns in this table are unchanged, but the Sharpe figures were computed before the annualisation bug was fixed (§4.1 of `real-data-test.md`). Recompute with `make ablate` / the sweeps before quoting them; the *verdict* below rests on returns and is unaffected.

| **mean** | **+5.24% / S2.95** | **+4.93% / S2.82** | **-0.13** |
| **median** | **+6.26%** | **+6.60%** | **+0.19** |

**Verdict: a wash.** Median improves, mean does not, and the seed-to-seed σ is 5.6% — the
effect is inside the noise. So `memory_influence` ships at **0.0 (observe-only)**: the
memory explains the book, and it must earn the right to size it. Flip one line and re-run
`make sweep` yourself once you have real data with a real edge to learn from.

---

## 8. Phased plan, with acceptance criteria

| Phase | Work | Done when |
|---|---|---|
| **P0 (shipped)** | Overlay contract + calendar/heuristic providers | ✅ 27 tests green, backtest unchanged with the flag off |
| **P1** | Calendar from a real source (earnings + FOMC + index rebalance) | ≤2 line changes to `default.yaml`; overlay fires on ≥90% of known events in a 3-month replay |
| **P2 (shipped)** | Numeric reflection memory: settle decisions at horizon H, per-(agent, regime) edge table live on the dashboard | ✅ explainable: 4 agents × 4 regimes with edge bps, hit rate, t-stat; measured A/B below |
| **P3** | LLM research provider on the daily cadence, budget-capped, with `research.enabled=false` in CI | Overlay-on vs overlay-empty backtest delta measured over ≥5 seeds; adopt only if median improves |
| **P4** | Bull/bear debate at re-optimisation, top-3 names only | <10 calls/day; each debate must emit an `invalidation` level or be discarded |
| **P5** | If Trading-R1 ships weights: swap it in behind the same `EventOverlay` contract | Same guardrail tests still pass, unchanged |

The contract never changes across P0→P5. That's the point: you can upgrade the brain
underneath without ever re-auditing what it's allowed to do to your book.
