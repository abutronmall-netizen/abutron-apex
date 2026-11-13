#!/bin/bash
set -euo pipefail
mode="${1:---preflight}"
if [[ "$mode" != "--preflight" && "$mode" != "--cycle" ]]; then exit 2; fi
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 25 9
exec timeout -k 5s 105s /opt/wine-staging/bin/wine /home/apexmt5/bridge-runtime/python311/python.exe /opt/apex/runtime/apex_demo_auto_v3.py "$mode"
