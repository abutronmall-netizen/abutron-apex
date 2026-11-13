#!/bin/bash
# APEX DEMO-only execution; shared MT5 IPC lock prevents concurrent Wine calls.
set -euo pipefail
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 25 9
exec timeout -k 5s 105s /opt/wine-staging/bin/wine /home/apexmt5/bridge-runtime/python311/python.exe /opt/apex/runtime/apex_demo_auto_v2.py --cycle
