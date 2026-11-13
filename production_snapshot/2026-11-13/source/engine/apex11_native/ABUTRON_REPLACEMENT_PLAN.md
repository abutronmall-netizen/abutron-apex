# ABUTRON APEX 1.1.0 replacement — current scope

## Requested engine

Use APEX 1.1.0 RegimeAgent, TrendAgent, MeanReversionAgent, BreakoutAgent, PortfolioAgent and RiskAgent for ABUTRON. Remove six old strategy-family publishers, Qlib/RD-Agent(Q), Qwen factor discovery, and TradingAgents veto from the future production signal decision path. Preserve the user's MT5 broker infrastructure, client/admin portals and required account controls.

## Explicit user rule removals

Eight prior extra strategy, history and authorization gates were removed from this **offline staged source**, documented in `USER_REQUESTED_REMOVALS.md`. Do **not** introduce substitute approval periods or statistical promotion requirements.

## Actual production state

No server deployment was made. The existing Deriv and FP Markets native routers still run the older candidate contracts until the user explicitly authorizes changes to production. The APEX replacement currently creates candidate data, not broker orders. There is no demonstrated positive broker-executed edge.

Before production changes, respect the standing no-deployment instruction. Do not silently switch customer accounts ON or enable LIVE trading. An actual deployment requires user authorization; this is not another strategy approval gate.
