#!/usr/bin/env python3
"""Read-only drift check of the 12 user-exported ABUTRON source files."""
import hashlib
import json
from pathlib import Path

manifest=Path(__file__).resolve().parents[1]/'native_interface/ORIGINAL_PRODUCTION_SOURCE_HASHES.json'
report=json.loads(manifest.read_text())
changed=[];missing=[];same=[]
for rel,provenance in report['source_files'].items():
    path=Path('/')/rel
    if not path.is_file() or path.is_symlink():
        missing.append(rel)
        continue
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    (same if actual==provenance['sha256'] else changed).append(rel)
print(json.dumps({'schema':'abutron.apex11.production.source.drift.v1',
   'exported_source_files':len(report['source_files']),
   'unchanged':len(same),'changed':changed,'missing':missing,
   'source_files_overwritten':0,
   'ready_for_exact_source_review':not bool(changed or missing)},indent=2))
raise SystemExit(2 if changed or missing else 0)
