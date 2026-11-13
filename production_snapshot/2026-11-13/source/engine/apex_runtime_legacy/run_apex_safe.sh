#!/usr/bin/env bash
# Preserve the original AgenticTrading repo's published safe, no-money-at-risk
# startup script; only replace the ASGI module target with the APEX gateway.
set -euo pipefail
cd /opt/apex/apps/agentictrading
SCRATCH="${ATL_LOCAL_DIR:-/home/apexagent/.local/share/apex-lab}"
mkdir -p "$SCRATCH/bar_cache"
[ -f "$SCRATCH/backtest.db" ] || cp dashboard/storage/data/backtest.db "$SCRATCH/backtest.db"
PORT="${1:-8888}"
exec env \
  PYTHONPATH=/opt/apex/runtime \
  DATABASE_PATH="$SCRATCH/backtest.db" \
  ATL_BAR_CACHE_DIR="$SCRATCH/bar_cache" \
  ROBINHOOD_EXECUTE=false \
  ATL_BAR_CACHE_WARM=0 \
  LEADERBOARD_DAILY_AUTO_DEPLOY=0 \
  ENABLE_VNPY_SIMULATION=true \
  ALPACA_API_KEY= ALPACA_SECRET_KEY= \
  ANTHROPIC_API_KEY= OPENAI_API_KEY= DEEPSEEK_API_KEY= \
  COMMONSTACK_API_KEY= OPENROUTER_API_KEY= \
  USERS_DATABASE_URL= CONTENT_DATABASE_URL= AGENT_RUNS_DATABASE_URL= \
  BREVO_API_KEY= \
  ATL_STRIPE_TEST_BILLING_ENABLED= STRIPE_SECRET_KEY= STRIPE_WEBHOOK_SECRET= \
  IFIND_REFRESH_TOKEN= IFIND_ACCESS_TOKEN= \
  /opt/apex/apps/agentictrading/.venv/bin/python -m uvicorn apex_gateway:app --host 127.0.0.1 --port "$PORT"
