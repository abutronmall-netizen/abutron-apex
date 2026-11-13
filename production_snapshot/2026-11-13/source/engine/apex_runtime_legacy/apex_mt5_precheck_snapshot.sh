#!/bin/bash
# Official Deriv DEMO broker order_check ONLY; never send an order.
set -euo pipefail
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 20 9
tmp="$(mktemp /var/lib/apex/mt5-market/.order-precheck.XXXXXX)"
trap 'rm -f -- "$tmp"' EXIT
timeout -k 5s 95s /opt/wine-staging/bin/wine \
  /home/apexmt5/bridge-runtime/python311/python.exe \
  /opt/apex/runtime/apex_mt5_order_precheck.py > "$tmp"
/usr/bin/python3 - "$tmp" <<'PY'
import json,sys
from datetime import datetime,timezone
x=json.load(open(sys.argv[1],encoding="utf8"))
assert x.get("schema")=="apex.mt5.order_precheck.v1"
assert x.get("source")=="Deriv DEMO MT5"
assert x.get("orders_placed")==0
assert x.get("execution_authorized") is False
assert x.get("evaluated")==26
assert len(x.get("results",[]))==26
ts=datetime.fromisoformat(x["generated_at_utc"])
assert ts.tzinfo and 0<=(datetime.now(timezone.utc)-ts).total_seconds()<120
assert all(z.get("submitted") is False and z.get("execution_authorized") is False for z in x["results"])
print("PASS official broker checks",x["checked"],"of 26, no orders")
PY
chmod 0640 "$tmp"
mv -f "$tmp" /var/lib/apex/mt5-market/order_precheck_latest.json
