#!/bin/bash
set -euo pipefail
cd /home/apexmt5/mt5-work
# Serialize official MT5 Python IPC with APEX account/risk collectors.
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 20 9

timeout -k 5s 105s \
  /opt/wine-staging/bin/wine \
  /home/apexmt5/bridge-runtime/python311/python.exe \
  /opt/apex/runtime/apex_mt5_export.py \
  | /usr/bin/python3 \
    /opt/apex/runtime/apex_mt5_store.py
