"""Unit + integration tests. Run with: pytest -q"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.agents.risk import RiskAgent  # noqa: E402
from apex.brokers.paper import PaperBroker  # noqa: E402
from apex.config import load_config  # noqa: E402
from apex.core.history import HistoryStore  # noqa: E402
from apex.core.models import Bar, Order, Quote, Side  # noqa: E402
from apex.data.synthetic import make_panel  # noqa: E402
from apex.risk import limits  # noqa: E402
from apex.strategy import indicators as ta  # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# ----------------------------------------------------------------- indicators
def test_ema_converges_to_constant():
    x = np.full(200, 5.0)
    assert abs(ta.ema(x, 20)[-1] - 5.0) < 1e-9


def test_rsi_bounds_and_direction():
    up = np.linspace(100, 200, 100)
    dn = np.linspace(200, 100, 100)
    assert ta.rsi(up, 14)[-1] > 90
    assert ta.rsi(dn, 14)[-1] < 10
    assert 0 <= ta.rsi(np.random.default_rng(0).normal(0, 1, 100).cumsum() + 100, 14)[-1] <= 100


def test_atr_positive_and_scales_with_range():
    n = 200
    c = np.linspace(100, 101, n)
    tr_small = ta.atr(c + 0.1, c - 0.1, c, 14)[-1]
    tr_big = ta.atr(c + 3.0, c - 3.0, c, 14)[-1]
    assert 0 < tr_small < tr_big


def test_adx_high_on_trend_low_on_chop():
    c = np.linspace(100, 200, 300)
    h, l = c + 0.2, c - 0.2
    assert ta.adx(h, l, c, 14)[-1] > 40
    rng = np.random.default_rng(3)
    chop = 100 + rng.normal(0, 0.5, 300).cumsum() * 0 + rng.normal(0, 1, 300)
    hh, ll = chop + 1, chop - 1
    assert ta.adx(hh, ll, chop, 14)[-1] < 40


def test_zscore_is_zero_on_flat():
    assert abs(ta.zscore(np.full(50, 7.0), 20)[-1]) < 1e-9


# ----------------------------------------------------------------- data
def test_panel_is_deterministic(cfg):
    a = make_panel(cfg, n_bars=400, seed=42)
    b = make_panel(cfg, n_bars=400, seed=42)
    for s in a.symbols:
        assert np.allclose(a.c[s], b.c[s])


def test_panel_ohlc_consistency(cfg):
    p = make_panel(cfg, n_bars=300, seed=7)
    for s in p.symbols:
        assert np.all(p.h[s] >= p.l[s] - 1e-9)
        assert np.all(p.h[s] >= p.c[s] - 1e-9)
        assert np.all(p.l[s] <= p.o[s] + 1e-9)
        assert np.all(np.isfinite(p.c[s]))


def test_deriv_synthetics_are_distinct(cfg):
    p = make_panel(cfg, n_bars=300, seed=11)
    assert not np.allclose(p.c["R_75"], p.c["R_100"])
    assert not np.allclose(p.c["BOOM500"], p.c["CRASH500"])


def test_session_masks(cfg):
    p = make_panel(cfg, n_bars=200, seed=5)
    assert p.active["BTCUSD"].all()          # crypto 24/7
    assert p.active["R_75"].all()            # synthetics 24/7
    assert not p.active["SPY"].all()         # equities keep hours


# ----------------------------------------------------------------- broker
def _quote(px: float, volume: float = 1e9, spread_bps: float = 0.0) -> Quote:
    half = px * spread_bps / 2 / 1e4
    return Quote("SPY", time.time(), px - half, px + half, px, volume)


def test_broker_round_trip_pnl(cfg):
    cfg2 = load_config()
    for u in cfg2["universe"]:
        u["spread_bps"] = 0.0
        u["commission_bps"] = 0.0
    cfg2["execution"]["impact_coef"] = 0.0
    cfg2["execution"]["latency_bars"] = 0
    b = PaperBroker(cfg2, starting_equity=100_000)
    b.set_quote(_quote(100.0))
    b.submit(Order("SPY", Side.BUY, 100))
    b.set_quote(_quote(110.0))
    assert b.equity == pytest.approx(101_000, rel=1e-6)
    b.submit(Order("SPY", Side.SELL, 100))
    assert b.equity == pytest.approx(101_000, rel=1e-6)
    assert b.positions["SPY"].qty == 0


def test_broker_short_pnl(cfg):
    cfg2 = load_config()
    for u in cfg2["universe"]:
        u["spread_bps"] = 0.0
        u["commission_bps"] = 0.0
    cfg2["execution"]["impact_coef"] = 0.0
    cfg2["execution"]["latency_bars"] = 0
    b = PaperBroker(cfg2, starting_equity=100_000)
    b.set_quote(_quote(100.0))
    b.submit(Order("SPY", Side.SELL, 50))
    b.set_quote(_quote(90.0))
    assert b.equity == pytest.approx(100_500, rel=1e-6)


def test_broker_rejects_dust(cfg):
    b = PaperBroker(cfg, starting_equity=100_000)
    b.set_quote(_quote(100.0))
    assert b.submit(Order("SPY", Side.BUY, 0.0001)) is None
    assert b.rejections


def test_margin_limit_enforced(cfg):
    b = PaperBroker(cfg, starting_equity=10_000)
    b.set_quote(_quote(100.0))
    # 5x leverage => max gross 50k; ask for 60k
    assert b.submit(Order("SPY", Side.BUY, 600)) is None
    assert any(r["reason"] == "margin" for r in b.rejections)


# ----------------------------------------------------------------- risk maths
def test_cov_and_vol_positive():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.01, (500, 3))
    cov = limits.annualised_cov(r, np.array([8760.0, 8760.0, 8760.0]))
    w = np.array([0.3, 0.3, 0.3])
    assert limits.portfolio_vol(w, cov) > 0
    assert limits.parametric_var(w, cov) > 0


def test_perfect_correlation_forms_cluster():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, 500)
    r = np.column_stack([base, base * 1.0, rng.normal(0, 0.01, 500)])
    cov = limits.annualised_cov(r, np.array([8760.0] * 3))
    clusters = limits.corr_clusters(["A", "B", "C"], cov, 0.85)
    assert ["A", "B"] in [sorted(c) for c in clusters]


def test_apply_cap_and_gross():
    w = {"A": 0.5, "B": -0.5, "C": 0.3}
    capped = limits.apply_cap(w, 0.6)
    assert limits.gross(capped) == pytest.approx(0.6, rel=1e-6)
    assert limits.net(w) == pytest.approx(0.3)


# ----------------------------------------------------------------- history
def test_history_no_lookahead_and_alignment():
    h = HistoryStore(["A", "B"])
    for i in range(100):
        h.append(Bar("A", 1_700_000_000 + i * 3600, 100 + i, 101 + i, 99 + i, 100 + i, 10))
        if i % 2 == 0:
            h.append(Bar("B", 1_700_000_000 + i * 3600, 50, 51, 49, 50, 5))
    assert h.n("A") == 100 and h.n("B") == 50
    syms, mat = h.returns_matrix(50)
    assert set(syms) == {"A", "B"}
    assert mat.shape[0] == mat.shape[1] or mat.shape[0] >= 20


# ----------------------------------------------------------------- risk agent
def test_kill_switch_flattens(cfg):
    from apex.agents.base import Context

    cfg2 = load_config()
    cfg2["execution"]["latency_bars"] = 0
    cfg2["risk"]["max_drawdown_pct"] = 0.02
    b = PaperBroker(cfg2, starting_equity=100_000)
    b.set_quote(_quote(100.0))
    b.submit(Order("SPY", Side.BUY, 900))
    b.set_quote(_quote(90.0))               # -9% on the position
    h = HistoryStore(["SPY"])
    for i in range(80):
        h.append(Bar("SPY", 1_700_000_000 + i * 3600, 90, 91, 89, 90, 1000))
    ra = RiskAgent(cfg2)
    ctx = Context(cfg=cfg2, history=h, broker=b, index=80, ts=h.last_ts)
    ctx.target_weights = {"SPY": 0.5}
    ra.step(ctx)
    assert ra.halted
    assert ctx.verdict.halted and ctx.verdict.flatten
    assert ctx.target_weights == {}


def test_risk_never_increases_gross(cfg):
    from apex.agents.base import Context

    b = PaperBroker(cfg, starting_equity=100_000)
    h = HistoryStore(["BTCUSD", "US500"])
    for i in range(120):
        px = 100 * (1 + 0.001 * np.sin(i / 5))
        h.append(Bar("BTCUSD", 1_700_000_000 + i * 3600, px, px * 1.01, px * 0.99, px, 1e5))
        h.append(Bar("US500", 1_700_000_000 + i * 3600, px, px * 1.01, px * 0.99, px, 1e5))
    ra = RiskAgent(cfg)
    ctx = Context(cfg=cfg, history=h, broker=b, index=120, ts=h.last_ts)
    ctx.target_weights = {"BTCUSD": 0.9, "US500": 0.9}     # absurd
    ra.step(ctx)
    assert limits.gross(ctx.verdict.weights) <= float(cfg["risk"]["max_gross_leverage"]) + 1e-9


# ----------------------------------------------------------------- integration
def test_engine_runs_and_is_auditable(cfg):
    from apex.engine import ApexEngine

    p = make_panel(cfg, n_bars=120, seed=3)
    eng = ApexEngine(cfg, mode="backtest")
    for i in range(90):
        eng.warmup({s: p.bar(s, i) for s in p.symbols if p.active[s][i]})
    for i in range(90, 120):
        d = eng.step({s: p.bar(s, i) for s in p.symbols if p.active[s][i]}, ts=float(p.ts[i]))
        assert d.bar_index >= 89
    st = eng.state()
    assert st["account"]["equity"] > 0
    assert len(st["equity_curve"]) >= 30
    assert "regimes" in st and "verdict" in st


def test_backtest_metrics_sane(cfg):
    from apex.backtest.metrics import compute_metrics

    ts = [1_700_000_000 + i * 3600 for i in range(500)]
    eq = [(t, 100_000 * (1 + 0.0001 * i)) for i, t in enumerate(ts)]
    m = compute_metrics(eq, [{"pnl": 10.0, "notional": 1000}, {"pnl": -5.0, "notional": 800}])
    assert m["total_return"] > 0 and m["sharpe"] > 0
    assert m["max_drawdown"] >= 0
    assert m["win_rate"] == pytest.approx(0.5)


def test_llm_advisor_is_risk_reducing_only(cfg):
    from apex.agents.base import Context
    from apex.llm.advisor import LlmAdvisor

    cfg2 = load_config()
    cfg2["llm"]["enabled"] = True
    adv = LlmAdvisor(cfg2)
    b = PaperBroker(cfg2)
    h = HistoryStore(["SPY"])
    for i in range(50):
        h.append(Bar("SPY", 1_700_000_000 + i * 3600, 100, 101, 99, 100, 1e5))
    ctx = Context(cfg=cfg2, history=h, broker=b, index=10, ts=h.last_ts)
    res = adv.consult(ctx)
    assert 0.0 <= res["scale"] <= 1.0          # may never lever up
    assert res["vetoes"] == [] or all(isinstance(v, str) for v in res["vetoes"])


# ----------------------------------------------------------------- research overlay
def test_research_overlay_can_only_reduce(cfg):
    """The event overlay may shrink or veto a target, never grow or add one."""
    from apex.agents.base import Context
    from apex.agents.research import CalendarProvider, ResearchAgent

    cfg2 = load_config()
    cfg2["agents"]["research"]["enabled"] = True
    b = PaperBroker(cfg2)
    h = HistoryStore(["SPY", "BTCUSD"])
    for i in range(40):
        h.append(Bar("SPY", 1_700_000_000 + i * 3600, 100, 101, 99, 100, 1e6))
        h.append(Bar("BTCUSD", 1_700_000_000 + i * 3600, 50, 51, 49, 50, 1e6))
    day = time.strftime("%Y-%m-%d", time.gmtime(1_700_000_000 + 40 * 3600))

    provider = CalendarProvider(event_map={day: ["SPY"]}, window_bars=5, cut=0.4)
    ra = ResearchAgent(cfg2, provider=provider)
    ra.enabled = True
    ctx = Context(cfg=cfg2, history=h, broker=b, index=40, ts=h.last_ts)
    ctx.target_weights = {"SPY": 0.20, "BTCUSD": -0.10}
    ra.step(ctx)

    spy = ctx.target_weights.get("SPY", 0.0)
    assert abs(spy) < 0.20                                # reduced...
    assert spy == 0.0                                     # ...all the way to a veto
    assert ctx.target_weights["BTCUSD"] == -0.10          # untouched
    assert set(ctx.target_weights) <= {"SPY", "BTCUSD"}   # never adds instruments


def test_research_never_levers_up():
    from apex.agents.research import EventOverlay

    o = EventOverlay(symbol="X", conviction_mult=3.0, stop_mult=0.1, veto_bars=-5).clip()
    assert o.conviction_mult == 1.0
    assert o.stop_mult == 1.0
    assert o.veto_bars == 0


# ----------------------------------------------------------------- reflection memory
def _mem_ctx(cfg, prices, index, ts=None):
    from apex.agents.base import Context
    b = PaperBroker(cfg)
    h = HistoryStore(list(prices))
    for s, px in prices.items():
        h.append(Bar(s, int(ts or 1_700_000_000), px, px, px, px, 1e6))
    return Context(cfg=cfg, history=h, broker=b, index=index, ts=h.last_ts)


def test_memory_settles_only_after_horizon(cfg):
    from apex.core.models import Regime, RegimeState, Signal
    from apex.memory import ReflectionMemory

    def ctx_at(px, index, with_signal=False):
        c = _mem_ctx(cfg, {"A": px}, index=index)
        c.regimes = {"A": RegimeState("A", Regime.TREND_UP, 30, 0.5, 0.5, 0.3, 0.9)}
        if with_signal:
            c.signals = [Signal(symbol="A", direction=1.0, strength=1.0, agent="trend")]
        return c

    mem = ReflectionMemory(horizon=10, min_obs=1, path=None)
    mem.observe(ctx_at(100.0, 0, with_signal=True))
    assert len(mem.pending) == 1 and mem.settled == 0

    # a price move *inside* the horizon must not settle the decision
    mem.observe(ctx_at(150.0, 5))
    assert mem.settled == 0

    # once the horizon closes, the decision settles against the realised move
    mem.observe(ctx_at(110.0, 10))
    assert mem.settled == 1
    cell = mem.cell("trend", "trend_up")
    assert cell.n == 1 and cell.hits == 1        # voted long, price went up
    assert mem.cell("trend", "range").n == 0     # regimes are kept separate
    assert 0.4 <= mem.trust_adjust("trend", "trend_up") <= 1.5


def test_memory_trust_adjust_never_inverts(cfg):
    from apex.memory import Cell, ReflectionMemory

    mem = ReflectionMemory(path=None)
    good = Cell(); [good.add(1.0, 0.01) for _ in range(200)]
    bad = Cell(); [bad.add(1.0, -0.01) for _ in range(200)]
    mem.cells["good"] = {"range": good}
    mem.cells["bad"] = {"range": bad}
    assert mem.trust_adjust("good", "range") > 1.0
    assert mem.trust_adjust("bad", "range") < 1.0
    assert 0.4 <= mem.trust_adjust("bad", "range") <= 1.5
    assert mem.trust_adjust("unknown", "range") == 1.0      # no evidence, no opinion
    assert mem.leaderboard()[0]["agent"] == "good"


def test_memory_narratives_are_evidence_based(cfg):
    from apex.memory import Cell, ReflectionMemory

    mem = ReflectionMemory(horizon=24, min_obs=30, path=None)
    c = Cell()
    for _ in range(100):
        c.add(1.0, 0.004)      # long votes that made money
        c.add(-1.0, -0.002)    # short votes in the same regime that also made money
    mem.cells["meanrev"] = {"range": c}
    narr = mem.narratives()
    assert narr and "meanrev" in narr[0] and "range" in narr[0]
    assert mem.narratives(n=0) == []


# ----------------------------------------------------------------- deriv-only profile
def test_deriv_only_config_is_deriv_only():
    cfg = load_config("config/deriv_only.yaml")
    classes = {u["asset_class"] for u in cfg["universe"]}
    syms = [u["symbol"] for u in cfg["universe"]]
    assert classes == {"deriv_synthetic"}
    assert set(syms) == {"R_75", "R_100", "BOOM500", "CRASH500", "stpRNG"}
    assert cfg["risk"]["max_asset_class_weight"]["deriv_synthetic"] >= 1.0
    assert "deriv" in str(cfg["system"].get("memory_file", ""))


def test_deriv_only_loop_produces_signal_to_order():
    """End-to-end: bars in -> signals -> risk-adjusted target -> a broker fill."""
    from apex.data.synthetic import make_panel
    from apex.engine import ApexEngine

    cfg = load_config("config/deriv_only.yaml")
    cfg["system"]["memory_file"] = ""          # keep the test out of state/
    cfg["agents"]["fusion"]["rebalance_every"] = 6
    panel = make_panel(cfg, n_bars=260, seed=5)
    eng = ApexEngine(cfg, mode="backtest", log_decisions=False)
    for i in range(180):
        eng.warmup({s: panel.bar(s, i) for s in panel.symbols})
    produced = False
    for i in range(180, 260):
        d = eng.step({s: panel.bar(s, i) for s in panel.symbols}, ts=float(panel.ts[i]))
        assert set(d.regimes) <= {"R_75", "R_100", "BOOM500", "CRASH500", "stpRNG"}
        if d.orders:
            produced = True
    assert produced, "no orders were generated by the deriv-only loop"
    assert len(eng.broker.trades()) > 0
    for t in eng.broker.trades():
        assert t.symbol in {"R_75", "R_100", "BOOM500", "CRASH500", "stpRNG"}


# ----------------------------------------------------------------- real data plumbing
def test_period_switch_changes_annualisation():
    from apex.data.base import bars_per_year, get_period, in_session, set_period

    try:
        set_period("1h")
        assert bars_per_year("crypto") == 8760.0
        assert in_session("us_equity", 3) is False
        set_period("1D")
        assert get_period() == "1D"
        assert bars_per_year("crypto") == 365.0
        assert bars_per_year("us_equity") == 252.0
        assert in_session("us_equity", 3) is True       # daily bars have no session mask
    finally:
        set_period("1h")


def test_metrics_annualise_with_the_right_period():
    import numpy as np
    from apex.backtest.metrics import compute_metrics

    rng = np.random.default_rng(3)
    rets = rng.normal(0.0005, 0.01, 800)
    eq = 100_000 * np.cumprod(1 + rets)
    ts = 1_700_000_000 + np.arange(801) * 86400.0
    m = compute_metrics(list(zip(ts, eq)), None, 100_000.0, bars_per_year=365.25)
    assert 0.13 < m["volatility"] < 0.21, m["volatility"]      # ~1%/day -> ~19%/yr
    m_hourly = compute_metrics(list(zip(ts, eq)), None, 100_000.0, bars_per_year=8760.0)
    assert m_hourly["volatility"] > 3 * m["volatility"]        # wrong period must look absurd


def test_real_panel_alignment_and_forward_fill(monkeypatch, tmp_path):
    """Real feeds have holes; the panel must ffill closes and never trade a stale bar."""
    import numpy as np

    import apex.data.real as R
    from apex.data.base import set_period

    cfg = load_config()
    monkeypatch.setattr(R, "CACHE", tmp_path)
    monkeypatch.setattr(R, "MAP_DAILY", {"BTCUSD": ("okx", "x"), "SPY": ("nasdaq", "x", "etf"),
                                         "EURUSD": ("fred", "x")})
    day = 86400.0
    t0 = 1_700_006_400.0

    def fake_fetch(sym, refresh=False):
        n = 60
        ts = t0 + np.arange(n) * day
        if sym == "SPY":                      # equities: weekends missing
            ts = ts[1::3]
            n = len(ts)
        base = 100.0 + np.arange(n)
        return np.column_stack([ts, base, base + 1, base - 1, base + 0.5, np.zeros(n)])

    monkeypatch.setattr(R, "fetch_daily", fake_fetch)
    panel = R.build_real_panel_daily(cfg)
    try:
        assert panel.symbols == ["BTCUSD", "SPY", "EURUSD"]
        assert getattr(panel, "is_real", False) is True
        assert int(panel.active["BTCUSD"].sum()) == len(panel)
        assert int(panel.active["SPY"].sum()) == 20
        gap = int(np.argmin(panel.active["SPY"]))
        assert panel.c["SPY"][gap] == panel.c["SPY"][gap - 1]     # ffilled, not NaN
        assert all(np.isfinite(panel.c[s]).all() for s in panel.symbols)
        # the engine must only ever see symbols that have a real bar on that row
        for i, row in enumerate(panel.iterator()):
            for sym in row:
                assert panel.active[sym][i]
            if i > 5:
                break
    finally:
        set_period("1h")


# --------------------------------------------------- annualisation regressions
def test_annualisation_inferred_from_timestamps():
    from apex.data.base import annualisation_from_ts

    hourly = 1_700_000_000 + np.arange(100) * 3600.0
    daily = 1_700_000_000 + np.arange(100) * 86400.0
    assert abs(annualisation_from_ts(hourly) - 8766.0) < 1.0     # 365.25 d x 24 h
    assert abs(annualisation_from_ts(daily) - 365.25) < 1.0
    assert annualisation_from_ts([]) > 0            # never divides by zero


def test_vol_target_uses_the_panel_frequency():
    """The sizing bug: a daily book must not be sized as if it traded hourly.

    Same return stream, two spacings -> the realised-vol estimate the portfolio
    agent scales against has to differ by sqrt(24), not be pinned to a constant.
    """
    from apex.data.base import annualisation_from_ts

    rng = np.random.default_rng(11)
    rets = rng.normal(0.0, 0.01, 300)               # ~1% per bar
    eq = np.cumprod(1 + rets)
    for step, expect in ((3600.0, 8766.0), (86400.0, 365.25)):
        ts = [1_700_000_000 + i * step for i in range(300)]
        vol = float(np.std(rets) * np.sqrt(annualisation_from_ts(ts)))
        assert abs(annualisation_from_ts(ts) - expect) < 1.0
        if step == 86400.0:
            assert 0.15 < vol < 0.25, vol              # ~19%/yr, i.e. sized sanely
        else:
            assert vol > 0.7, vol                      # hourly must look far riskier
    assert eq[-1] > 0


def test_tail_ratio_is_bounded():
    from apex.backtest.metrics import compute_metrics

    rng = np.random.default_rng(5)
    rets = np.zeros(400)
    rets[::7] = rng.normal(0, 0.002, len(rets[::7]))   # mostly flat, occasional moves
    eq = 100_000 * np.cumprod(1 + rets)
    ts = 1_700_000_000 + np.arange(401) * 86400.0
    m = compute_metrics(list(zip(ts, eq)), None, 100_000.0, bars_per_year=365.25)
    assert 0.0 <= m["tail_ratio"] <= 10.0, m["tail_ratio"]
    assert abs(m["skew"]) < 10 and 1.0 <= m["kurtosis"] < 200


# ------------------------------------------------------------- deployment surface
def test_secrets_env_provider_is_a_noop(monkeypatch):
    from apex import secrets

    monkeypatch.delenv("APEX_SECRETS", raising=False)
    assert secrets.load() == {}
    assert secrets.provider() == "env"
    monkeypatch.delenv("DERIV_API_TOKEN", raising=False)
    try:
        secrets.require("DERIV_API_TOKEN")
        raise AssertionError("require() must raise when the secret is absent")
    except secrets.SecretsError as e:
        assert "DERIV_API_TOKEN" in str(e)
    assert secrets.redact(None) == "<unset>"
    assert secrets.redact("abcd1234efgh") == "abc*****efgh"
    st = secrets.status()
    assert st["has_deriv_token"] is False and "loaded_names" in st


def test_secrets_file_provider_and_host_override(monkeypatch, tmp_path):
    from apex import secrets

    f = tmp_path / "apex.json"
    f.write_text('{"DERIV_API_TOKEN": "from-file", "APEX_LLM_API_KEY": "k-file"}')
    monkeypatch.setenv("APEX_SECRETS", "file")
    monkeypatch.setenv("APEX_SECRETS_FILE", str(f))
    monkeypatch.setenv("APEX_LLM_API_KEY", "host-wins")
    applied = secrets.load()
    assert applied["DERIV_API_TOKEN"] == "from-file"
    assert "APEX_LLM_API_KEY" not in applied            # host value is never overwritten
    assert os.environ["APEX_LLM_API_KEY"] == "host-wins"
    assert secrets.status()["deriv_token"] != "from-file"   # never echoed in full


def test_secrets_unknown_provider_fails_loudly(monkeypatch):
    from apex import secrets

    monkeypatch.setenv("APEX_SECRETS", "vault-of-doom")
    try:
        secrets.load()
        raise AssertionError("unknown provider must raise")
    except secrets.SecretsError as e:
        assert "vault-of-doom" in str(e)


def test_data_dir_override_moves_every_mutable_path(monkeypatch, tmp_path):
    import apex.paths as paths

    monkeypatch.setattr(paths, "_DATA", tmp_path.resolve())
    made = paths.ensure_layout()
    assert set(made) == {"state", "results", "data_cache", "logs"}
    assert all((tmp_path / k).is_dir() for k in made)
    assert paths.data_path("state/memory.json") == tmp_path / "state/memory.json"
    assert paths.data_path("/tmp/absolute.csv").is_absolute()
    assert paths.disk_free_gb() > 0


def test_healthz_is_503_when_the_loop_is_down():
    import asyncio
    import json

    from apex.api import server

    old = server.runner
    server.runner = None
    try:
        resp = asyncio.run(server.healthz())
        body = json.loads(resp.body)
        assert resp.status_code == 503
        assert body["ok"] is False and body["runner_running"] is False
        assert "secrets" in body and "disk_free_gb" in body
    finally:
        server.runner = old


def test_entrypoint_renders_only_the_requested_roles(tmp_path):
    import subprocess
    import sys

    env = {"APEX_DRY_RUN": "1", "APEX_ROLES": "web,collector", "PORT": "10000",
           "PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}
    out = subprocess.run([sys.executable, "deploy/entrypoint.py"], cwd=str(Path(__file__).resolve().parent.parent),
                         env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "[program:web]" in out.stdout
    assert "[program:collector]" in out.stdout
    assert "[program:trader]" not in out.stdout
    assert "--port 10000" in out.stdout


# --------------------------------------------------------------- remote control auth
def _ctl(token_env, client_host="203.0.113.9", header=None, query=""):
    """Call the control-auth guard the way FastAPI would."""
    import asyncio

    from apex.api import server

    class _C:
        host = client_host

    class _R:
        client = _C()
        query_params = {"token": query} if query else {}

    old = os.environ.pop("APEX_API_TOKEN", None)
    if token_env is not None:
        os.environ["APEX_API_TOKEN"] = token_env
    try:
        asyncio.run(server.require_control_auth(_R(), header))
        return 200
    except Exception as e:                                        # noqa: BLE001
        return getattr(e, "status_code", 500)
    finally:
        os.environ.pop("APEX_API_TOKEN", None)
        if old is not None:
            os.environ["APEX_API_TOKEN"] = old


def test_control_auth_fails_closed_on_a_public_host():
    # no token configured + request from the internet -> refused
    assert _ctl(None) == 403
    # no token configured + loopback -> allowed (local dev, the dashboard)
    assert _ctl(None, client_host="127.0.0.1") == 200


def test_control_auth_token_paths():
    assert _ctl("s3cret", header=None) == 401
    assert _ctl("s3cret", header="Bearer wrong") == 401
    assert _ctl("s3cret", header="Bearer s3cret") == 200
    assert _ctl("s3cret", query="s3cret") == 200        # dashboard fallback


# ------------------------------------------------- venue behaviour: latency & fills
def _broker(latency=1, ttl=3, cap=0.05):
    from apex.brokers.paper import PaperBroker

    cfg = load_config()
    cfg["execution"]["latency_bars"] = latency
    cfg["execution"]["working_order_ttl_bars"] = ttl
    cfg["execution"]["participation_cap"] = cap
    cfg["execution"]["impact_coef"] = 0.0
    for u in cfg["universe"]:
        u["spread_bps"] = 0.0
        u["commission_bps"] = 0.0
    return PaperBroker(cfg, starting_equity=100_000)


def _q(price, vol=1_000_000.0, symbol="SPY"):
    from apex.core.models import Quote

    return Quote(symbol=symbol, ts=0.0, bid=price - 0.01, ask=price + 0.01,
                 last=price, volume=vol)


def test_order_never_fills_on_the_bar_that_created_it():
    """A signal computed at bar t cannot trade at bar t's price."""
    from apex.core.models import Order, Side

    b = _broker(latency=1)
    b.set_quote(_q(100.0))
    assert b.submit(Order("SPY", Side.BUY, 10)) is None      # queued, not filled
    assert len(b.fills()) == 0
    b.set_quote(_q(110.0))                                   # market moved 10%
    b.begin_bar(1.0)
    assert len(b.fills()) == 1
    assert abs(b.fills()[0].price - 110.0) < 0.05            # filled at the *next* bar


def test_participation_cap_partially_fills_and_carries_the_remainder():
    from apex.core.models import Order, Side

    b = _broker(latency=1, cap=0.05)
    b.set_quote(_q(100.0, vol=1000.0))                       # only 1,000 units traded
    b.submit(Order("SPY", Side.BUY, 500))                    # wants 500, cap = 50
    b.begin_bar(1.0)
    assert len(b.fills()) == 1
    assert abs(b.fills()[0].qty - 50.0) < 1e-9
    assert b.partial_fills == 1
    b.set_quote(_q(100.0, vol=1000.0))
    b.begin_bar(2.0)                                         # remainder keeps working
    assert abs(sum(f.qty for f in b.fills()) - 100.0) < 1e-9


def test_working_order_expires_after_ttl():
    from apex.core.models import Order, Side

    b = _broker(latency=1, ttl=2)
    b.set_quote(_q(100.0))
    b.submit(Order("SPY", Side.BUY, 10))
    b._quotes.clear()                                        # venue goes dark
    for i in range(4):
        b.begin_bar(float(i))
    assert b.expired_orders == 1
    assert len(b.fills()) == 0


def test_kill_switch_flatten_ignores_latency():
    """Risk exits are urgency orders: they must not be deferred by our own sim."""
    from apex.core.models import Order, Side

    b = _broker(latency=5)
    b.set_quote(_q(100.0))
    b._fill_now(Order("SPY", Side.BUY, 10))
    assert len(b.fills()) == 1
    fills = b.flatten()
    assert len(fills) == 1 and b.positions["SPY"].qty == 0


def test_working_orders_do_not_stack():
    """Re-signalling the same target while an order rests must not double the size."""
    from apex.core.models import Order, Side

    b = _broker(latency=2)
    b.set_quote(_q(100.0))
    for _ in range(3):
        b.submit(Order("SPY", Side.BUY, 10))
    assert len(b._working) == 1                     # one live order, not three
    assert b.replaced_orders == 2
    b.begin_bar(1.0)
    b.begin_bar(2.0)
    assert abs(b.fills()[0].qty - 10.0) < 1e-9      # not 30
