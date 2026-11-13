#!/bin/bash
set -euo pipefail
case "${1:-}" in --preflight|--apply) ;; *) exit 2 ;; esac
export HOME=/home/apexmt5 DISPLAY=:1 WINEPREFIX=/home/apexmt5/.mt5 WINEARCH=win64 WINEDEBUG=-all
cd /home/apexmt5/mt5-work
exec 9>/var/lib/apex/mt5-market/mt5-bridge.lock
flock -w 15 9
exec timeout -k 5s 65s /opt/wine-staging/bin/wine /home/apexmt5/bridge-runtime/python311/python.exe /opt/apex/runtime/apex_per_trade_switch_20261101.py "$1"
