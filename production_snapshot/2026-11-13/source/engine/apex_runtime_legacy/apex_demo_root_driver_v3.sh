#!/bin/bash
# Root stages vetted broker snapshot; execution drops to restricted apexmt5.
set -euo pipefail
export HOME=/home/apexmt5
export DISPLAY=:1
export WINEPREFIX=/home/apexmt5/.mt5
export WINEARCH=win64
export WINEDEBUG=-all
/usr/bin/python3 /opt/apex/runtime/apex_demo_feed_stage.py
exec /usr/sbin/runuser -u apexmt5 -g apexmt5 -G apexagent -- /bin/bash /opt/apex/runtime/apex_demo_auto_cycle_v3.sh "${1:---preflight}"
