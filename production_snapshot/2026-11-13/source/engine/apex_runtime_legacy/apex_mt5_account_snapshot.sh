#!/bin/bash
# Official MT5 terminal, DEMO account/positions/contract telemetry only.
set -euo pipefail
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 20 9
timeout -k 5s 95s \
  /opt/wine-staging/bin/wine \
  /home/apexmt5/bridge-runtime/python311/python.exe \
  /opt/apex/runtime/apex_mt5_account_export.py \
 | /usr/bin/python3 /opt/apex/runtime/apex_mt5_account_store.py
