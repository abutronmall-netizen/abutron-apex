#!/bin/bash
# Recompute official broker minimum-lot hypothetical stop-loss in USD.
# Only order_calc_profit() is called. No orders or broker mutations.
set -euo pipefail
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 20 9
tmp="$(mktemp /var/lib/apex/mt5-market/.contract-risk.XXXXXX)"
trap 'rm -f -- "$tmp"' EXIT
timeout -k 5s 95s \
  /opt/wine-staging/bin/wine \
  /home/apexmt5/bridge-runtime/python311/python.exe \
  /opt/apex/runtime/apex_deriv_contract_probe.py > "$tmp"
/usr/bin/python3 - "$tmp" <<'PY'
import json,math,sys
from datetime import datetime,timezone
p=sys.argv[1]
data=json.load(open(p,encoding="utf8"))
assert data.get("status")=="inspection_only"
assert data.get("orders_placed")==0
assert data.get("source")=="Deriv USD DEMO MT5"
assert data.get("calculated_count")==13
assert len(data.get("instruments",[]))==13
t=datetime.fromisoformat(data["checked_at_utc"])
assert t.tzinfo and 0 <= (datetime.now(timezone.utc)-t).total_seconds() < 120
for s in data["instruments"]:
 assert s.get("verified") is True and s.get("minimum_lot",0)>0
 for field in ("buy_sl_est_usd","sell_sl_est_usd"):
  assert isinstance(s.get(field),(float,int)) and math.isfinite(float(s[field])) and s[field]>=0
print("VALIDATED",data["checked_at_utc"],"contracts",len(data["instruments"]),"orders",data["orders_placed"])
PY
chmod 0640 "$tmp"
mv -f "$tmp" /var/lib/apex/mt5-market/contract_risk_latest.json
