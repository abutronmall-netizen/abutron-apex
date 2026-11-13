#!/bin/bash
# Extra MT5 DEMO closed candles M3 and M30; serializes official terminal IPC.
set -euo pipefail
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 25 9
timeout -k 5s 95s \
  /opt/wine-staging/bin/wine \
  /home/apexmt5/bridge-runtime/python311/python.exe \
  /opt/apex/runtime/apex_mt5_extra_candles.py \
 | env PYTHONPATH=/opt/apex/runtime /usr/bin/python3 /opt/apex/runtime/apex_mt5_extra_candle_store.py
