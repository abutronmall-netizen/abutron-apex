from pathlib import Path
import hashlib
p=Path("/usr/local/sbin/abutron-fp-dual-native-reconcile-ro")
b=Path("/var/backups/abutron-six-account-risk-reconcile-before-20261109T2023Z/abutron-fp-dual-native-reconcile-ro")
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
expected="7f42d9d2abad78b2f7722b86322c8ee9ba9166778276f7d1c987ada8d29f3a47"
assert sha(p)==expected and sha(b)==expected, "WRAPPER_BACKUP_HASH_MISMATCH"
s=p.read_text()
find='''import json
import os
from pathlib import Path'''
replace='''import json
import os
import re
import time
from pathlib import Path'''
assert s.count(find)==1
s=s.replace(find,replace)
find='''            try:
                data.append(account(cid, login, pin, history, adaptive, db))
            except Exception as exc:
                data.append({"account_suffix": login[-4:],
                             "state": "BLOCKED", "error_type": type(exc).__name__})'''
replace='''            # Native history and bridge files are published asynchronously.
            # Retry only a bounded number of READ-ONLY full attestations; never
            # reuse a prior ACK or stale report to override a genuine denial.
            last_code="UNVERIFIED"
            for attempt in range(3):
                try:
                    row=account(cid, login, pin, history, adaptive, db)
                    data.append(row)
                    break
                except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
                    # Safe opaque code only; never include MT5 credentials.
                    raw=str(exc)
                    last_code=(raw if re.fullmatch(r"[A-Z0-9_]{4,120}",raw)
                               else type(exc).__name__)
                    if attempt<2:
                        time.sleep((2,5)[attempt])
            else:
                data.append({"account_suffix": login[-4:],
                             "state": "BLOCKED",
                             "error_code": last_code,
                             "bounded_readonly_retries_exhausted":True})'''
assert s.count(find)==1
s=s.replace(find,replace)
find='''        r.get("broker_verified_ack_count") != receipts.get("ACK")):
        raise ValueError("FP_NATIVE_RECEIPTS_OR_RECONCILIATION_UNVERIFIED")'''
replace='''        r.get("broker_verified_ack_count") != receipts.get("ACK")):
        # Preserve validated broker-native failure codes; never leak secrets.
        blockers=r.get("blockers",[])
        codes=[x for x in blockers if type(x) is str and
               re.fullmatch(r"[A-Z0-9_]{4,80}",x)]
        if codes:
            raise ValueError(codes[0])
        raise ValueError("FP_NATIVE_RECEIPTS_OR_RECONCILIATION_UNVERIFIED")'''
assert s.count(find)==1
s=s.replace(find,replace)
compile(s,str(p),"exec")
Path("/var/lib/abutron-mcp/abutron-fp-dual-reconcile-bounded-retry-candidate.py").write_text(s)
print("CANDIDATE_FP_BOUNDED_RETRY_CREATED","bytes",len(s))
