"""Read-only, sanitized, time-bounded APEX production diagnostics."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,stat
PATH=Path("/var/lib/abutron-unified-decision/ui-health.json")
SCHEMA="abutron.apex.runtime_health.readonly.v1"
def snapshot():
    unavailable={"schema":SCHEMA,"available":False,"reason":"VERIFIED_HEALTH_UNAVAILABLE"}
    try:
        if PATH.is_symlink():return unavailable
        info=PATH.stat()
        if not stat.S_ISREG(info.st_mode) or not 100<=info.st_size<=32000:return unavailable
        d=json.loads(PATH.read_text())
        if d.get("schema")!=SCHEMA or d.get("execution_authority") is not False:return unavailable
        t=datetime.fromisoformat(d["checked_at_utc"].replace("Z","+00:00"))
        age=(datetime.now(timezone.utc)-t).total_seconds()
        if t.tzinfo is None or not -15<=age<=90:return {**unavailable,"reason":"HEALTH_EVIDENCE_STALE"}
        for k in ("fpmarkets","deriv","icmarkets"):
            if not isinstance(d.get(k),dict):return unavailable
        return {"available":True,**d}
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,OverflowError):
        return unavailable
