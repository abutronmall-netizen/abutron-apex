#!/bin/bash
# Root stages redacted, provenance-verified broker snapshots, then drops
# privileges BEFORE opening the Wine MT5 API. No Kronos. DEMO only.
set -euo pipefail
/usr/bin/python3 /opt/apex/runtime/apex_demo_feed_stage.py
exec /usr/sbin/runuser -u apexmt5 -g apexmt5 -G apexagent --   /bin/bash /opt/apex/runtime/apex_demo_auto_cycle.sh
