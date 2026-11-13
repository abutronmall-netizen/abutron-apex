#!/usr/bin/python3
"""ABUTRON client MT5 worker: isolated UID, broker-native feed plus gated order bridge.
MT5 credentials arrive via systemd's private runtime credential mount, not argv/env/CRM.
"""
import os,sys,json,subprocess,time,shutil,secrets,uuid,signal
from pathlib import Path
SRC=Path("/opt/abutron/client-mt5-template-v3")
WARM=Path("/opt/abutron/fpmarkets-mql-bootstrap-v1")
FP_SC_SERVERS=Path("/opt/abutron/fpmarkets-sc-servers-v1.dat")
FP_SC_SHA256="d5f0376015341141e6dc2a87ab1bb4b6d45c8bbb7c86b47e69a870d460358baa"
WINE="/opt/abutron/apex-wine-source/bin/wine"
FP_MODES={"FPMarketsSC-Demo":"DEMO","FPMarketsSC-Demo Server":"DEMO",
 "FPMarketsLtd-Demo2":"DEMO","FPMarketsSC-Live":"LIVE","FPMarketsLtd-Live2":"LIVE"}
ALLOWED={("FP Markets",server):"FP_MARKETS" for server in FP_MODES}
def status(path,obj):
 tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(obj,separators=(",",":")))
 tmp.chmod(0o600);os.replace(tmp,path)

def handoff_event(journal_bytes):
    """An MT5 updater handoff in exactly the newly appended journal range."""
    if not journal_bytes: return False
    try:
        text=journal_bytes.decode("utf-16-le",errors="replace") if b"\x00" in journal_bytes[:80] else journal_bytes.decode("utf-8",errors="replace")
    except UnicodeError:
        return False
    low=text.lower()
    return ("liveupdate" in low and "/update" in low and "terminal64.exe" in low)

def cgroup_terminal_running():
    """Inspect only this systemd service cgroup; never probe another user's MT5."""
    try:
        lines=Path("/proc/self/cgroup").read_text().splitlines()
        names=[line.split("::",1)[1] for line in lines if line.startswith("0::")]
        if len(names)!=1 or "/abutron-client-mt5-" not in names[0]:
            return False
        group=Path("/sys/fs/cgroup")/names[0].lstrip("/")
        for p in (group/"cgroup.procs").read_text().splitlines():
            if not p.isdigit() or int(p)==os.getpid(): continue
            proc=Path("/proc")/p
            try:
                name=(proc/"comm").read_text().strip().lower()
                if name.startswith("terminal64"):return True
                # Wine may expose the launcher as preloader; verify its command line.
                if name in ("wine64-preloader","wine-preloader","wine64"):
                    argv=(proc/"cmdline").read_bytes().decode("utf-8","ignore").lower()
                    if "terminal64.exe" in argv:return True
            except (FileNotFoundError,ProcessLookupError,PermissionError):
                continue
    except (OSError,ValueError,IndexError):
        pass
    return False

def hold_zero_exit_for_native_proof(returncode,exact_fresh_heartbeat,seconds_since_exit):
    """Allow account-bound native proof to outlive a Wine launcher handoff.

    Never infer a session from exit code 0 or an old file. The caller may
    continue only while exact current-nonce EA proof stays fresh; without it,
    the grace is short and bounded. This does NOT authorize any order.
    """
    if returncode != 0 or seconds_since_exit < 0:
        return False
    if exact_fresh_heartbeat:
        return True
    return seconds_since_exit < 18.0

def exit_action(returncode,was_connected,attached,handoff,attempt,total_elapsed):
    """No restart without fresh MT5 updater evidence; no trading permission changes."""
    if attached:return "MONITOR_CHILD"
    if was_connected:return "STOP"
    if returncode==0 and handoff and attempt<3 and total_elapsed<220:
        return "RETRY_UPDATE"
    return "STOP"


FP1636_V101_HISTORY_SHA256="3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"
FP0512_V101_HISTORY_SHA256="3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"

def stage_fp1636_v101_history_binary(terminal,cid,server,mode):
 """Restore only the already-approved no-order V101 history indicator at restart.

 This only stages a file; MT5 must attach the indicator before history is proven.
 Never modify broker positions, orders, EA flags or another FP customer's files.
 """
 if cid not in ("80cf848587fcec6311dd93560c1c46c6","35b81a287b6a030f2f46ff426b135e6c","14eef404262094655b2040c8ced86a53") or server!="FPMarketsSC-Demo" or mode!="DEMO":
  return "SKIP_NON_APPROVED_FP_DEMO"
 import hashlib
 trusted=Path("/usr/local/lib/abutron-fp1636-v101/AbutronFPAccountHistoryV101.ex5" if cid=="80cf848587fcec6311dd93560c1c46c6" else "/usr/local/lib/abutron-fp1636-v101/AbutronFPAccountHistoryV101.ex5")
 expected=(FP1636_V101_HISTORY_SHA256 if cid=="80cf848587fcec6311dd93560c1c46c6" else FP0512_V101_HISTORY_SHA256)
 if (not trusted.is_file() or trusted.is_symlink() or
    hashlib.sha256(trusted.read_bytes()).hexdigest()!=expected):
  return "SKIP_UNTRUSTED_V101_BINARY"
 dest=terminal/"MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5"
 if dest.is_symlink():return "SKIP_SYMLINKED_HISTORY_DESTINATION"
 dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(trusted,dest)
 if hashlib.sha256(dest.read_bytes()).hexdigest()!=expected:
  return "SKIP_COPY_VERIFICATION_FAILED"
 return "FP1636_V101_BINARY_STAGED_NO_ORDER"



FP1636_V307_FEED_SHA256="459c84b607d0eed0ed7cbb06808b12dd7b1eadaabfaa6ffacb591074d0086c6c"
FP1636_V307_CHART_SHA256="1ffb07eb34d32bcb08fa69b572b93ef81ce6664c4eff32d4984d0e4b88ffd778"
FP1636_V305_DEFAULT_CHART_SHA256="b0b867ee5b2009dcd9c89e3001b69e23271e686d27634410d21278cb39ed6622"

def stage_fp1636_v307_feed(terminal,cid,server,mode):
 """Restore only exact FP1636 DEMO read-only V307 with V101 after-auth attachment."""
 if cid!="80cf848587fcec6311dd93560c1c46c6" or server!="FPMarketsSC-Demo" or mode!="DEMO":
  return "SKIP_NON_FP1636_DEMO"
 import hashlib
 fname="AbutronFPMarketsNativeFeedParallelV307_FP1636.ex5"
 trusted=Path("/usr/local/lib/abutron-fp1636-v101")/fname
 dest=terminal/"MQL5/Experts/ABUTRON"/fname
 if trusted.is_symlink() or dest.is_symlink() or not trusted.is_file():
  return "SKIP_FP1636_V307_UNTRUSTED_PATH"
 if hashlib.sha256(trusted.read_bytes()).hexdigest()!=FP1636_V307_FEED_SHA256:
  return "SKIP_FP1636_V307_HASH_MISMATCH"
 dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(trusted,dest)
 if hashlib.sha256(dest.read_bytes()).hexdigest()!=FP1636_V307_FEED_SHA256:
  return "SKIP_FP1636_V307_COPY_MISMATCH"
 return "FP1636_V307_READONLY_FEED_STAGED"

def stage_fp1636_v101_restart_chart(terminal,cid,server,mode):
 """Stage FP1636-only read-only V307 feed chart; MT5 EA attaches V101 post-auth."""
 if cid!="80cf848587fcec6311dd93560c1c46c6" or server!="FPMarketsSC-Demo" or mode!="DEMO":
  return "SKIP_NON_FP1636_DEMO"
 import hashlib
 src=Path("/usr/local/lib/abutron-fp1636-v101/AbutronFP1636V307ReadOnly.chart03.chr")
 profile=terminal/"MQL5/Profiles/Charts/Default/chart03.chr"
 window=terminal/"MQL5/Profiles/Charts/Default/order.wnd"
 indicator=terminal/"MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5"
 v307=terminal/"MQL5/Experts/ABUTRON/AbutronFPMarketsNativeFeedParallelV307_FP1636.ex5"
 if any(x.is_symlink() for x in (src,profile,window,indicator,v307)):
  return "SKIP_FP1636_PROFILE_SYMLINK"
 if not all(x.is_file() for x in (src,profile,window,indicator,v307)):
  return "SKIP_FP1636_PROFILE_MISSING"
 if hashlib.sha256(indicator.read_bytes()).hexdigest()!=FP1636_V101_HISTORY_SHA256:
  return "SKIP_FP1636_V101_EX5_NOT_VERIFIED"
 if hashlib.sha256(v307.read_bytes()).hexdigest()!=FP1636_V307_FEED_SHA256:
  return "SKIP_FP1636_V307_FEED_NOT_VERIFIED"
 if hashlib.sha256(profile.read_bytes()).hexdigest()!=FP1636_V305_DEFAULT_CHART_SHA256:
  return "SKIP_FP1636_BASE_PROFILE_NOT_ATTESTED"
 if hashlib.sha256(src.read_bytes()).hexdigest()!=FP1636_V307_CHART_SHA256:
  return "SKIP_FP1636_V307_PROFILE_NOT_ATTESTED"
 if "chart03.chr" not in window.read_bytes().decode("utf-16"):
  return "SKIP_FP1636_ORDER_WINDOW_NOT_ATTESTED"
 shutil.copy2(src,profile)
 if hashlib.sha256(profile.read_bytes()).hexdigest()!=FP1636_V307_CHART_SHA256:
  raise RuntimeError("FP1636_V307_CHART_COPY_UNVERIFIED")
 return "FP1636_V307_V101_POST_AUTH_AUTOATTACH_PROFILE_STAGED"



def stage_fp0512_v101_restart_chart(terminal,cid,server,mode):
 """FP0512 only: stage the approved V101 read-only history chart, never order chart01."""
 if (cid,server,mode)!=("35b81a287b6a030f2f46ff426b135e6c","FPMarketsSC-Demo","DEMO"):
  return "SKIP_NON_FP0512"
 import hashlib
 approved=Path("/usr/local/lib/abutron-fp0512-v101-history/AbutronFP0512ReadOnlyV101.chart03.chr")
 chart=terminal/"MQL5/Profiles/Charts/Default/chart03.chr"
 indicator=terminal/"MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5"
 if any(x.is_symlink() for x in (approved,chart,indicator)) or not all(x.is_file() for x in (approved,chart,indicator)):
  return "SKIP_FP0512_HISTORY_PROFILE_MISSING"
 source_hash=hashlib.sha256(chart.read_bytes()).hexdigest()
 expected_hash="5b6f33d5df985227a59d44e76e54b8140f49d189bd9a722ce9dbee5bdd5aa843"
 if source_hash not in ("b0b867ee5b2009dcd9c89e3001b69e23271e686d27634410d21278cb39ed6622",expected_hash):
  return "SKIP_FP0512_READONLY_BASE_PROFILE_CHANGED"
 if (hashlib.sha256(approved.read_bytes()).hexdigest()!=expected_hash or
     hashlib.sha256(indicator.read_bytes()).hexdigest()!="3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"):
  return "SKIP_FP0512_V101_RELEASE_UNATTESTED"
 shutil.copy2(approved,chart)
 if hashlib.sha256(chart.read_bytes()).hexdigest()!=expected_hash:
  raise RuntimeError("FP0512_V101_READONLY_PROFILE_INSTALL_FAILED")
 return "FP0512_V101_HISTORY_INDICATOR_PERSISTED_ON_READONLY_CHART03"

def stage_fp0512_v102_stop_risk(terminal,cid,server,mode):
    """Restore independent NO-ORDER broker stop-risk expert on chart04 at next MT5 boot.

    Scope ONLY FP0512 DEMO; preserve existing order bridge chart01 and feed
    chart03. This function never restarts terminals or submits broker orders.
    """
    if (cid,server,mode)!=("35b81a287b6a030f2f46ff426b135e6c",
                           "FPMarketsSC-Demo","DEMO"):
        return "SKIP_NON_FP0512"
    import re,hashlib
    source=Path('/usr/local/lib/abutron-fp0512-risk-v102/AbutronFPStopRiskROV102.ex5')
    expected_sha='6e1bdc27a05777d299ca2ebf122c33e4bdb7768ca886473048e7e9212d80f1fd'
    if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected_sha:
        raise RuntimeError('FP0512_RISK_V102_BINARY_NOT_APPROVED')
    charts=terminal/'MQL5/Profiles/Charts/Default'
    template=charts/'chart03.chr'
    target=charts/'chart04.chr'
    order=charts/'order.wnd'
    binary=terminal/'MQL5/Experts/ABUTRON/AbutronFPStopRiskROV102.ex5'
    if any(x.is_symlink() for x in (template,target,order,binary)) or not all(x.is_file() for x in (template,order)) or (target.exists() and not target.is_file()):
        raise RuntimeError('FP0512_RISK_V102_CHART_TEMPLATE_INVALID')
    data=template.read_text(encoding='utf-16')
    blocks=re.findall(r'<expert>.*?</expert>',data,re.S)
    if len(blocks)!=1 or 'name=AbutronFPMarketsNativeFeedParallelV305' not in blocks[0] or data.count('id=92432578086933')!=1:
        raise RuntimeError('FP0512_RISK_CHART03_EXPECTATION_CHANGED')
    expert='<expert>\r\nname=AbutronFPStopRiskROV102\r\npath=Experts\\ABUTRON\\AbutronFPStopRiskROV102.ex5\r\nexpertmode=1\r\n<inputs>\r\n</inputs>\r\n</expert>'
    # Reuse only the chart shell; do not clone the V101 indicator to chart04.
    # Two writers of the same native V101 file would race and corrupt history.
    if data.count('<window>') != 1 or data.count('</window>') != 1:
        raise RuntimeError('FP0512_RISK_CHART03_INDICATOR_WINDOW_EXPECTATION_CHANGED')
    head=data.split('<window>',1)[0]
    if head.count('windows_total=1') != 1:
        raise RuntimeError('FP0512_RISK_CHART03_WINDOW_COUNT_UNEXPECTED')
    chart4=head.replace('windows_total=1','windows_total=0')
    chart4=chart4.replace('id=92432578086933','id=92432578086934').replace(blocks[0],expert)
    chart4+='</chart>\r\n'
    if ('AbutronFPNativeOrderBridge' in chart4 or
        'AbutronFPAccountHistoryV101' in chart4 or
        chart4.count('AbutronFPStopRiskROV102')!=2):
        raise RuntimeError('FP0512_RISK_CHART04_CONTAINS_UNRELATED_EXPERT_OR_INDICATOR')
    raw_order=order.read_text(encoding='utf-16')
    order_list=raw_order.splitlines()
    if order_list==['chart03.chr','chart02.chr']:
        order_list.insert(0,'chart01.chr')
    if order_list!=['chart01.chr','chart03.chr','chart02.chr']:
        raise RuntimeError('FP0512_ORDER_WND_UNEXPECTED')
    raw_order='\r\n'.join(order_list)+'\r\n' 
    binary.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,binary)
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=expected_sha:
        raise RuntimeError('FP0512_RISK_COPY_INTEGRITY_INVALID')
    target.write_text(chart4,encoding='utf-16')
    order.write_text(raw_order.rstrip('\r\n')+'\r\nchart04.chr\r\n',encoding='utf-16')
    return 'FP0512_V102_BROKER_NATIVE_ORDER_CALC_PROFIT_OBSERVER_CHART04_STAGED'

def stage_fp0512_single_writer_release(terminal,cid,server,mode):
 """FP0512 only: restore sole active V114 order EA and protected read-only charts."""
 if (cid,server,mode)!=("35b81a287b6a030f2f46ff426b135e6c","FPMarketsSC-Demo","DEMO"):
  return "SKIP_NON_FP0512"
 import hashlib
 root=Path("/usr/local/lib/abutron-fp0512-session-risk-v114")
 folder=terminal/"MQL5"
 releases=(
  ("AbutronFPNativeOrderBridgeV101.ex5",
   "Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5",
   "5463e4073a1991fb3b52d1fe253a4fa2da035b5a4889a8ab8d32cee856048d06"),
  ("AbutronFP0512OrderOn.chart01.chr",
   "Profiles/Charts/Default/chart01.chr",
   "228812d9a3d765b837810009bd8f22c9a752c65ee5976ea578805781ccf7f411"),
  ("AbutronFP0512NoDuplicateWriter.chart02.chr",
   "Profiles/Charts/Default/chart02.chr",
   "f7335d4789fcf4d2440aa87dcb92a48c42a57db8d20960228a41f5516930be00"))
 for name,relative,expected in releases:
  source=root/name
  target=folder/relative
  if (source.is_symlink() or not source.is_file() or
      target.is_symlink() or not target.parent.is_dir() or
      hashlib.sha256(source.read_bytes()).hexdigest()!=expected):
   raise RuntimeError("FP0512_RESTART_RELEASE_NOT_ATTESTED")
  shutil.copy2(source,target)
  if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
   raise RuntimeError("FP0512_RESTART_RELEASE_COPY_FAILED")
 return "FP0512_ORDER_BRIDGE_V114_SINGLE_WRITER_CHART01_ON_CHART02_NONE"

# FP1622 DEMO: account-bound V307 no-order native feed attaches V101 history.
# No changes to other accounts' profile, licensed seats or trade switches.
FP1622_V307_SHA256="db6eb2f047ddf6a14ad55b3730852ca7f3dc80c62efeee9a4f18b9945ea47f26"
FP1622_HISTORY_V101_SHA256="3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"
FP1622_ID="14eef404262094655b2040c8ced86a53"
def stage_fp1622_v101_native_history(terminal,cid,server,mode):
 """1622-only verified binary + native indicator restart attachment, no broker orders."""
 if (cid,server,mode)!=(FP1622_ID,"FPMarketsSC-Demo","DEMO"):
  return "SKIP_NON_FP1622"
 import hashlib
 release=Path("/usr/local/lib/abutron-fp1622-v101")
 copies=(
  (release/"AbutronFPMarketsNativeFeedParallelV307_FP1622.ex5",
   terminal/"MQL5/Experts/ABUTRON/AbutronFPMarketsNativeFeedParallelV307_FP1622.ex5",
   FP1622_V307_SHA256),
  (release/"AbutronFPAccountHistoryV101.ex5",
   terminal/"MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5",
   FP1622_HISTORY_V101_SHA256))
 for src,dest,digest in copies:
  if src.is_symlink() or not src.is_file() or dest.is_symlink() or hashlib.sha256(src.read_bytes()).hexdigest()!=digest:
   raise RuntimeError("FP1622_NATIVE_RELEASE_UNVERIFIED")
  dest.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(src,dest)
  if hashlib.sha256(dest.read_bytes()).hexdigest()!=digest:
   raise RuntimeError("FP1622_NATIVE_COPY_UNVERIFIED")
 base=Path("/usr/local/lib/abutron-fp1636-v101/AbutronFP1636V307ReadOnly.chart03.chr")
 chart=terminal/"MQL5/Profiles/Charts/Default/chart03.chr"
 if base.is_symlink() or chart.is_symlink() or not base.is_file() or not chart.is_file():
  raise RuntimeError("FP1622_CHART_PATH_INVALID")
 raw=base.read_bytes()
 if (hashlib.sha256(raw).hexdigest()!="1ffb07eb34d32bcb08fa69b572b93ef81ce6664c4eff32d4984d0e4b88ffd778" or
     hashlib.sha256(chart.read_bytes()).hexdigest()!="b0b867ee5b2009dcd9c89e3001b69e23271e686d27634410d21278cb39ed6622"):
  raise RuntimeError("FP1622_BASELINE_CHART_NOT_ATTESTED")
 old="AbutronFPMarketsNativeFeedParallelV307_FP1636".encode("utf-16-le")
 new="AbutronFPMarketsNativeFeedParallelV307_FP1622".encode("utf-16-le")
 if raw.count(old)!=2:raise RuntimeError("FP1622_CHART_V307_BASE_UNEXPECTED")
 data=raw.replace(old,new)
 chart.write_bytes(data)
 if chart.read_bytes()!=data:raise RuntimeError("FP1622_CHART_WRITE_UNVERIFIED")
 return "FP1622_V307_V101_NATIVE_HISTORY_STAGED_NO_ORDERS"

def stage_fp1622_v113_native_bridge(terminal,cid,server,mode):
 """Account-bound 1622 DEMO adaptive V113 bridge: CRM, broker and risk remain separate."""
 if (cid,server,mode)!=(FP1622_ID,"FPMarketsSC-Demo","DEMO"):
  return "SKIP_NON_FP1622_NATIVE_BRIDGE"
 import hashlib
 source=Path("/usr/local/lib/abutron-fp1636-native-risk-v113/AbutronFPNativeOrderBridgeV101.ex5")
 dest=terminal/"MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5"
 expected="76f3503c1661642438e690239d667758f0211fe4790623541345051f0a728a1c"
 if source.is_symlink() or not source.is_file() or dest.is_symlink():
  raise RuntimeError("FP1622_NATIVE_BRIDGE_RELEASE_PATH_UNTRUSTED")
 if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
  raise RuntimeError("FP1622_NATIVE_V113_BINARY_HASH_UNVERIFIED")
 dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(source,dest)
 if hashlib.sha256(dest.read_bytes()).hexdigest()!=expected:
  raise RuntimeError("FP1622_NATIVE_V113_RESTORE_UNVERIFIED")
 return "FP1622_ADAPTIVE_V113_INSTALLED_FOR_BROKER_BOUND_DEMO"

def stage_fp1622_adaptive_input_for_demo(terminal,cid,server,mode):
 """Scope DEMO-only V113 input approval to licensed FP1622; native risk remains enforced."""
 if (cid,server,mode)!=(FP1622_ID,"FPMarketsSC-Demo","DEMO"):
  return "SKIP_NON_FP1622_ADAPTIVE_INPUT"
 import hashlib
 bridge=terminal/"MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5"
 chart=terminal/"MQL5/Profiles/Charts/Default/chart01.chr"
 expected="76f3503c1661642438e690239d667758f0211fe4790623541345051f0a728a1c"
 if bridge.is_symlink() or not bridge.is_file() or hashlib.sha256(bridge.read_bytes()).hexdigest()!=expected:
  raise RuntimeError("FP1622_NATIVE_V113_BEFORE_INPUT_UNVERIFIED")
 if chart.is_symlink():
  raise RuntimeError("FP1622_CHART_BEFORE_INPUT_SYMLINK")
 if not chart.is_file():
  source=Path("/usr/local/lib/abutron-fp1622-v101/AbutronFP1622Chart01Baseline.chr")
  expected_chart="11b5b819ebdd157e7ef1503dc194bc1416fa01aecf94df837d45a9631924b743"
  if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected_chart:
   raise RuntimeError("FP1622_NATIVE_CHART01_RELEASE_UNVERIFIED")
  chart.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(source,chart)
 raw=chart.read_bytes()
 old="AdaptiveV2ReconcilerApproved=false".encode("utf-16-le")
 new="AdaptiveV2ReconcilerApproved=true".encode("utf-16-le")
 if raw.count(old)!=1 or raw.count(new)!=0 or raw.count("EnableNativeDemoOrders=true".encode("utf-16-le"))!=1:
  raise RuntimeError("FP1622_SCOPED_ADAPTIVE_INPUT_CONTRACT_CHANGED")
 chart.write_bytes(raw.replace(old,new))
 if chart.read_bytes().count(new)!=1:
  raise RuntimeError("FP1622_SCOPED_ADAPTIVE_INPUT_WRITE_FAILED")
 return "FP1622_ADAPTIVE_V113_INPUT_STAGED_BROKER_GATES_STILL_REQUIRED"

def stage_fp1622_exclusive_writer_chart(terminal,cid,server,mode):
 """One V113 order bridge on chart01, read-only feed on chart02 for FP1622 only."""
 if (cid,server,mode)!=(FP1622_ID,"FPMarketsSC-Demo","DEMO"):
  return "SKIP_NON_FP1622_EXCLUSIVE_WRITER_CHART"
 import hashlib
 source=Path("/usr/local/lib/abutron-fp1622-v101/AbutronFP1622ReadOnlyChart02.chr")
 target=terminal/"MQL5/Profiles/Charts/Default/chart02.chr"
 expected="9336c72582f50f4adee5a2d640a7bb3a2f4673d06575006c5e587d66d0797c1c"
 if source.is_symlink() or not source.is_file() or target.is_symlink():
  raise RuntimeError("FP1622_READONLY_CHART_SOURCE_INVALID")
 data=source.read_bytes()
 if hashlib.sha256(data).hexdigest()!=expected:
  raise RuntimeError("FP1622_NATIVE_READONLY_CHART_HASH_UNVERIFIED")
 content=data.decode("utf-16")
 if "AbutronFPNativeOrderBridgeV101" in content or content.count("AbutronFPMarketsNativeFeedParallelV305")!=2:
  raise RuntimeError("FP1622_READONLY_FEED_CHART_HAS_ORDER_BRIDGE")
 target.parent.mkdir(parents=True,exist_ok=True)
 target.write_bytes(data)
 if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
  raise RuntimeError("FP1622_READONLY_CHART_COPY_NOT_VERIFIED")
 return "FP1622_EXCLUSIVE_V113_WRITER_CHART01_READONLY_V305_CHART02"

FP_HISTORY_READONLY_SHA256="5f1996c4a06b8ad29cf4dc615bebce356c3ba3d6e5e25d7b28abb19a966f5683"

def stage_fp_demo_history(terminal,files,nonce,challenge_owner,login,server,mode):
 """Prepare FP DEMO history proofs on first MT5 boot. Never attach, trade or override an EA.

 This optional add-on must never block the already-working broker data feed.
 The indicator is copied from the FP-only MQL5 bootstrap and its SHA is fixed.
 """
 if server!="FPMarketsSC-Demo" or mode!="DEMO":return "SKIP_NON_FP_DEMO"
 import hashlib
 indicator=terminal/"MQL5"/"Indicators"/"ABUTRON"/"AbutronFPAccountHistoryV100.ex5"
 if not indicator.is_file() or indicator.is_symlink() or hashlib.sha256(indicator.read_bytes()).hexdigest()!=FP_HISTORY_READONLY_SHA256:
  return "SKIP_FP_HISTORY_BINARY_UNVERIFIED"
 request=files/"ABUTRON_FP_HISTORY_REQUEST_V1.txt"
 if request.exists() or request.is_symlink():return "SKIP_FP_HISTORY_REQUEST_ALREADY_PRESENT"
 payload="\r\n".join(["ABUTRON_FP_HISTORY_REQUEST_V1",nonce,challenge_owner,
                         "FP_MARKETS",server,str(login),mode])+"\r\n"
 fd=os.open(str(request),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w",encoding="ascii",newline="") as f:
  f.write(payload);f.flush();os.fsync(f.fileno())
 return "FP_HISTORY_REQUEST_STAGED_READONLY"

FP_SIDECAR_READONLY_SHA256="55748a797f1d5d6298fb59d7c438add02051ee14ebb98ff4b729907fd082abe9"

def stage_fp_demo_sidecar(terminal,files,nonce,challenge_owner,login,server,mode):
 """FP DEMO 13x6 companion indicator request: evidence only, no trading."""
 if server!="FPMarketsSC-Demo" or mode!="DEMO":return "SKIP_NON_FP_DEMO"
 import hashlib
 sidecar=terminal/"MQL5"/"Indicators"/"ABUTRON"/"AbutronFPMarketsNativeSidecarV100.ex5"
 if not sidecar.is_file() or sidecar.is_symlink() or hashlib.sha256(sidecar.read_bytes()).hexdigest()!=FP_SIDECAR_READONLY_SHA256:
  return "SKIP_FP_SIDECAR_BINARY_UNVERIFIED"
 request=files/"ABUTRON_FP_SIDECAR_REQUEST_V1.txt"
 if request.exists() or request.is_symlink():return "SKIP_FP_SIDECAR_REQUEST_ALREADY_PRESENT"
 payload="\r\n".join(["ABUTRON_FP_SIDECAR_REQUEST_V1",nonce,challenge_owner,
                        "FP_MARKETS",server,str(login),mode])+"\r\n"
 fd=os.open(str(request),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w",encoding="ascii",newline="") as f:
  f.write(payload);f.flush();os.fsync(f.fileno())
 return "FP_SIDECAR_REQUEST_STAGED_READONLY"

def main():
 # Keep a single isolated Xvfb display alive across the ENTIRE MT5 update
 # lifecycle. xvfb-run shuts down its X server when the launched command exits;
 # it must wrap this supervisor, not each individual terminal launch.
 if os.environ.get("ABUTRON_MT5_XVFB_CHILD") != "1":
  # xvfb-run's default /tmp/xvfb-run.* cookie can be removed by tmpfiles
  # while the account's isolated MT5 X server remains alive. Store the X11
  # authorization cookie under systemd's per-account runtime directory instead.
  # Never print or persist the cookie in logs, DB or the shared MT5 template.
  runtime=Path(os.environ["RUNTIME_DIRECTORY"])
  if not runtime.is_dir() or runtime.is_symlink() or runtime.stat().st_uid!=os.geteuid():
   raise RuntimeError("FP X11 runtime directory identity not verified")
  authfile=runtime/"fp-mt5-xauthority"
  fd=os.open(str(authfile),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  os.close(fd)
  env=dict(os.environ)
  env["ABUTRON_MT5_XVFB_CHILD"]="1"
  # FP LIVE 86073492 alone: avoid occupied global X11 socket near :109.
  # All other accounts retain their original automatic Xvfb display selection.
  display_args=(["-a","-n","240"] if
                runtime.name=="abutron-client-mt5-38f731a629055234670f5a86f5409eba"
                else ["-a","-n","241"] if runtime.name=="abutron-client-mt5-6c396441ac5d4b76b2f1ffaf2951beb3"
                else ["-a"])
  cmd=["/usr/bin/xvfb-run",*display_args,"-f",str(authfile),"-s",
       "-screen 0 1280x800x24 -nolisten tcp",
       "/usr/bin/python3","-B",os.path.abspath(__file__)]
  try:
   if runtime.name=="abutron-client-mt5-6c396441ac5d4b76b2f1ffaf2951beb3":
    trace=Path(os.environ["STATE_DIRECTORY"])/"fp2582-startup-diagnostic.log"
    if trace.is_symlink():raise RuntimeError("FP2582_DIAG_SYMLINK_DENIED")
    with open(trace,"wb") as f:
     os.chmod(trace,0o600)
     return subprocess.run(cmd,env=env,stdin=subprocess.DEVNULL,
                          stdout=f,stderr=f,check=False).returncode
   return subprocess.run(cmd,env=env,stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         check=False).returncode
  finally:
   authfile.unlink(missing_ok=True)
 if not os.environ.get("DISPLAY"):
  raise RuntimeError("Isolated MT5 X display missing")
 state=Path(os.environ["STATE_DIRECTORY"]);runtime=Path(os.environ["RUNTIME_DIRECTORY"])
 cred=Path(os.environ["CREDENTIALS_DIRECTORY"])/"mt5"
 if not cred.is_file():raise RuntimeError("Missing private systemd credential")
 doc=json.loads(cred.read_text())
 if set(doc)!={"id","broker","server","login","password","mode"}:raise RuntimeError("Invalid broker credential payload")
 cid=doc["id"];broker=doc["broker"];server=doc["server"];login=doc["login"]
 mode=doc["mode"]
 if broker!="FP Markets" or len(cid)!=32 or (broker,server) not in ALLOWED or mode!=FP_MODES[server]:
  raise RuntimeError("Invalid broker identity")
 if not str(login).isdigit() or not str(doc["password"]):raise RuntimeError("Invalid MT5 credentials")
 terminal=state/"terminal";prefix=state/"wine";health=state/"worker-health.json"
 status(health,{"status":"STARTING","id":cid,"heartbeat_fresh":False})
 # The manager only starts this worker after the previous service is stopped.
 # Never reuse a failed terminal profile carrying stale or inherited broker cache.
 if terminal.exists():
  # MT5 can leave files not removable by the next isolated DynamicUser.
  # Preserve the stopped session without removing any broker journals.
  if terminal.is_symlink() or not terminal.is_dir():
   raise RuntimeError("UNSAFE_EXISTING_FP_TERMINAL")
  retired=state/("terminal-retired-"+str(time.time_ns()))
  terminal.rename(retired)
 shutil.copytree(SRC,terminal,symlinks=False)
 # Warm only stock MQL5 libraries; never copy a prior account profile, config, logs or state.
 if WARM.is_dir():
  for name in ("Include","Indicators","Experts/Examples","Scripts/Examples"):
   standard=WARM/name
   if standard.is_dir():shutil.copytree(standard,terminal/"MQL5"/name,dirs_exist_ok=True,symlinks=False)
 # Restore approved FP 0512/1636 read-only V101 history indicator to fresh DEMO terminals.
 # The active MT5 chart attachment remains independent and never authorizes orders.
 stage_fp1636_v101_history_binary(terminal,cid,server,mode)
 # FP account terminals must never contain the Deriv execution bridge binaries.
 experts=terminal/"MQL5"/"Experts"/"ABUTRON"
 if experts.is_dir():
  for binary in experts.glob("*.ex5"):binary.unlink()
 assert terminal.joinpath("terminal64.exe").is_file()
 # Exact FP Markets SC broker servers, taken from the official FPMarketsSC MT5 installer.
 # This is FP-only; the Deriv baseline and its broker server list remain untouched.
 if server.startswith("FPMarketsSC-"):
  import hashlib
  if not FP_SC_SERVERS.is_file() or hashlib.sha256(FP_SC_SERVERS.read_bytes()).hexdigest()!=FP_SC_SHA256:
   raise RuntimeError("FP Markets SC trusted server catalogue missing or altered")
  shutil.copy2(FP_SC_SERVERS,terminal/"Config"/"servers.dat")
 assert terminal.joinpath("Config/servers.dat").is_file()
 # Update the read-only proof script even when reusing an existing client profile.
 # Otherwise failed accounts continue to run the older EX5 on their next attempt.
 # Pin FP-only broker-native feed to the currently proven 13x6 binary.
 # The shared MT5 template is older and must never silently replace it.
 import hashlib
 trusted=WARM/"Experts"/"ABUTRON"/"AbutronFPMarketsNativeFeedEA.ex5"
 if (not trusted.is_file() or trusted.is_symlink() or
     hashlib.sha256(trusted.read_bytes()).hexdigest()!="b4af8d9af21887d670bb5ea4963b15bfe756ac96218b95ede1c10dcf5681edcc"):
  raise RuntimeError("FP Markets 13x6 read-only native feed binary unavailable or altered")
 experts.mkdir(parents=True,exist_ok=True)
 shutil.copy2(trusted,experts/"AbutronFPMarketsNativeFeedEA.ex5")
 # Restore the exact approved FP DEMO feed, USD50/100 bridge and signed
 # research charts after the worker wipes the previous per-client terminal.
 # No credentials, broker logins or account permissions are copied.
 # The portal remains OFF until the separate native broker ACK approves DEMO.
 if server=="FPMarketsSC-Demo" and mode=="DEMO":
  try:
   bundle=Path("/opt/abutron/fpmarkets-0512-recovery-bundle-v1")
   approved={"Experts/ABUTRON/AbutronFPMarketsNativeFeedParallelV305.ex5": "845c6a30034b2e0b6aa33625e6582b1a9130d568a8621ec980c4aca77455897e", "Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5": "0c20f13984a57f67c40e3f23859bb61c356527be3936178891ad90e12e5bcf8b", "Profiles/Charts/Default/chart02.chr": "0ae283c83672e7af3d2603f9339b23ff4c8db97a339728bec70689b61f70ad19", "Profiles/Charts/Default/chart03.chr": "b0b867ee5b2009dcd9c89e3001b69e23271e686d27634410d21278cb39ed6622", "Profiles/Charts/Default/order.wnd": "5929212f2670a4b5030df33ae235223c74189fb4dd2bb93c3381f860c1dd83ca"}
   if bundle.is_symlink() or not bundle.is_dir():
    raise ValueError("FP_STARTUP_RECOVERY_BUNDLE_MISSING")
   for rel,digest in approved.items():
    src_file=bundle/rel
    if src_file.is_symlink() or not src_file.is_file() or src_file.stat().st_size>1000000:
     raise ValueError("FP_RECOVERY_SOURCE_NOT_TRUSTED")
    if hashlib.sha256(src_file.read_bytes()).hexdigest()!=digest:
     raise ValueError("FP_RECOVERY_HASH_MISMATCH")
    target=terminal/"MQL5"/rel
    if target.is_symlink():raise ValueError("FP_RECOVERY_DESTINATION_SYMLINK")
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src_file,target)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
     raise ValueError("FP_RECOVERY_COPY_MISMATCH")
  except (OSError,ValueError,TypeError):
   # Preserve normal broker authentication and the original native feed.
   # The native order ACK independently fails closed if the bridge is absent.
   print("FP_DEMO_OPTIONAL_VERIFIED_RECOVERY_NOT_STAGED",file=sys.stderr)
 # Only FP1636 DEMO: authenticated V307 feed restores the V101 indicator.
 # No change to FP0512, LIVE, account controls, or native order bridge.
 feed_release=stage_fp1636_v307_feed(terminal,cid,server,mode)
 if feed_release.startswith("SKIP_") and cid=="80cf848587fcec6311dd93560c1c46c6":
  print("FP1636_V307_FEED_NOT_ATTESTED:"+feed_release,file=sys.stderr)
 chart_restore=stage_fp1636_v101_restart_chart(terminal,cid,server,mode)
 if chart_restore.startswith("SKIP_") and cid=="80cf848587fcec6311dd93560c1c46c6":
  print("FP1636_V101_PROFILE_RESTORE_NOT_ATTESTED:"+chart_restore,file=sys.stderr)
 stage_fp0512_v101_status=stage_fp0512_v101_restart_chart(terminal,cid,server,mode)
 # FP0512 only: pinned V306 read-only feed restores the V101 exporter after
 # MT5 discards saved indicator entries; the trading writer is not modified.
 if (cid,server,mode)==("35b81a287b6a030f2f46ff426b135e6c","FPMarketsSC-Demo","DEMO"):
  import hashlib
  hist_feed=Path('/usr/local/lib/abutron-fp0512-v101-feed-v306/AbutronFPMarketsNativeFeedParallelV305.ex5')
  feed_target=terminal/'MQL5/Experts/ABUTRON/AbutronFPMarketsNativeFeedParallelV305.ex5'
  approved_sha='615ba5a53590a90400033a4259f1931a49157b2551b77cde483bc6861c3352b8'
  old_sha='845c6a30034b2e0b6aa33625e6582b1a9130d568a8621ec980c4aca77455897e'
  if (hist_feed.is_symlink() or feed_target.is_symlink() or
      not hist_feed.is_file() or not feed_target.is_file() or
      hashlib.sha256(hist_feed.read_bytes()).hexdigest()!=approved_sha or
      hashlib.sha256(feed_target.read_bytes()).hexdigest() not in (old_sha,approved_sha)):
   raise RuntimeError('FP0512_V101_AUTOATTACH_FEED_BINARY_INTEGRITY_INVALID')
  shutil.copy2(hist_feed,feed_target)
  if hashlib.sha256(feed_target.read_bytes()).hexdigest()!=approved_sha:
   raise RuntimeError('FP0512_V101_AUTOATTACH_FEED_INSTALL_FAILED')
 stage_fp0512_release_status=stage_fp0512_single_writer_release(terminal,cid,server,mode)
 stage_fp0512_risk_status=stage_fp0512_v102_stop_risk(terminal,cid,server,mode)
 if cid=="35b81a287b6a030f2f46ff426b135e6c":
  print("FP0512_HISTORY_CHART:"+stage_fp0512_v101_status+";RELEASE:"+stage_fp0512_release_status,file=sys.stderr)
 # Account-specific FP1622 read-only V101 history recovery, preserving its CRM OFF state.
 stage_fp1622_v101_native_history(terminal,cid,server,mode)
 # FP1622 only: restore pinned adaptive V113 without changing other FP accounts.
 stage_fp1622_v113_native_bridge(terminal,cid,server,mode)
 # Restore native DEMO V113 approved input to 1622 only (CRM OFF until verified).
 stage_fp1622_adaptive_input_for_demo(terminal,cid,server,mode)
 # Deduplicate FP1622 native order bridge: chart02 read-only, chart01 V113 sole writer.
 stage_fp1622_exclusive_writer_chart(terminal,cid,server,mode)
 # Account-specific FP1636 adaptive bridge: reuse the proven FP0512
 # native V113 release while keeping FP0512's running terminal untouched.
 # The MT5 challenge still binds every order to FP1636's own nonce/login.
 if cid=="80cf848587fcec6311dd93560c1c46c6" and server=="FPMarketsSC-Demo" and mode=="DEMO":
  import hashlib
  source=Path("/usr/local/lib/abutron-fp1636-native-risk-v113/AbutronFPNativeOrderBridgeV101.ex5")
  target=terminal/"MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5"
  expected="76f3503c1661642438e690239d667758f0211fe4790623541345051f0a728a1c"
  if (source.is_symlink() or target.is_symlink() or not source.is_file()
      or hashlib.sha256(source.read_bytes()).hexdigest()!=expected):
   raise RuntimeError("FP1636_ADAPTIVE_NATIVE_RELEASE_NOT_VERIFIED")
  shutil.copy2(source,target)
  if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
   raise RuntimeError("FP1636_NATIVE_BRIDGE_COPY_INVALID")
 # Preserve the already-authorized FP DEMO order-EA input on fresh MT5 profiles.
 # MT5 generates chart01 after startup unless the verified account chart is staged.
 if (broker,server,mode)==("FP Markets","FPMarketsSC-Demo","DEMO") and cid in {
     "35b81a287b6a030f2f46ff426b135e6c",
     "80cf848587fcec6311dd93560c1c46c6"}:
  import hashlib
  slot=("0512" if cid=="35b81a287b6a030f2f46ff426b135e6c" else "1636")
  expected="909c9ad70f9bddace51768996d6d9e9fae2b9bde96225c52054080533012a0c6"
  source=Path("/usr/local/lib/abutron-fp-demo-on-chart-v1")/slot/"chart01.chr"
  if (not source.is_file() or source.is_symlink() or
      hashlib.sha256(source.read_bytes()).hexdigest()!=expected):
   raise RuntimeError("FP_DEMO_APPROVED_CHART_RELEASE_MISSING")
  chart=terminal/"MQL5/Profiles/Charts/Default/chart01.chr"
  if chart.is_symlink():raise RuntimeError("FP_DEMO_CHART_SYMLINK")
  chart.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(source,chart)
  if hashlib.sha256(chart.read_bytes()).hexdigest()!=expected:
   raise RuntimeError("FP_DEMO_APPROVED_CHART_NOT_INSTALLED")
 # FP1636: restore ONE native order writer; the shared FP recovery bundle's
 # chart02 contains a second EA with adaptive approval OFF, corrupting V2 proof.
 # The approved chart02 replacement is read-only and has a distinct chart ID.
 if (cid,server,mode)==("80cf848587fcec6311dd93560c1c46c6","FPMarketsSC-Demo","DEMO"):
  import hashlib
  ro=Path('/usr/local/lib/abutron-fp1636-single-writer-v1/chart02.chr')
  target=terminal/'MQL5/Profiles/Charts/Default/chart02.chr'
  chart1=terminal/'MQL5/Profiles/Charts/Default/chart01.chr'
  order=terminal/'MQL5/Profiles/Charts/Default/order.wnd'
  expected='b68b88e6b112370840d6f9f23388d84e23bcebf1ba1e306927f61bd163aeb25f'
  if any(v.is_symlink() for v in (ro,target,chart1,order)) or not all(v.is_file() for v in (ro,target,chart1,order)) or hashlib.sha256(ro.read_bytes()).hexdigest()!=expected:
   raise RuntimeError('FP1636_SINGLE_WRITER_PROFILE_RELEASE_INVALID')
  primary=chart1.read_text('utf-16')
  if primary.count('name=AbutronFPNativeOrderBridgeV101')!=1 or primary.count('AdaptiveV2ReconcilerApproved=true')!=1:
   raise RuntimeError('FP1636_PRIMARY_NATIVE_WRITER_NOT_APPROVED')
  shutil.copy2(ro,target)
  if hashlib.sha256(target.read_bytes()).hexdigest()!=expected or '<expert>' in target.read_text('utf-16'):
   raise RuntimeError('FP1636_DUPLICATE_WRITER_NOT_REMOVED')
  orderlines=order.read_text('utf-16').splitlines()
  if orderlines==['chart03.chr','chart02.chr']:
   orderlines.insert(0,'chart01.chr')
  if orderlines!=['chart01.chr','chart03.chr','chart02.chr']:
   raise RuntimeError('FP1636_CHART_ORDER_UNEXPECTED')
  order.write_text('\r\n'.join(orderlines)+'\r\n',encoding='utf-16')
 # FP DEMO 2582: verified V113 account-bound native bridge and separate V101
 # broker-history indicator; exactly one order writer; never touches LIVE.
 if (cid,server,mode)==("6c396441ac5d4b76b2f1ffaf2951beb3","FPMarketsSC-Demo","DEMO"):
  import hashlib
  release=Path("/usr/local/lib/abutron-fp2582-v113")
  pinned={
   "AbutronFPNativeOrderBridgeV101.ex5":("MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5","76f3503c1661642438e690239d667758f0211fe4790623541345051f0a728a1c"),
   "AbutronFPAccountHistoryV101.ex5":("MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5","3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"),
   "chart01.chr":("MQL5/Profiles/Charts/Default/chart01.chr","057c64953bc39953440d36bc16dc908d1d70539a08a07b5b6ab94308dd957102"),
   "chart02.chr":("MQL5/Profiles/Charts/Default/chart02.chr","39bdfb605cfae35ad02b0cbb32f96494aeb14e4a90a34b467ece5d47ca529e68"),
   "AbutronFPMarketsNativeFeedParallelV305.ex5":("MQL5/Experts/ABUTRON/AbutronFPMarketsNativeFeedParallelV305.ex5","615ba5a53590a90400033a4259f1931a49157b2551b77cde483bc6861c3352b8"),
   "chart03.chr":("MQL5/Profiles/Charts/Default/chart03.chr","5b6f33d5df985227a59d44e76e54b8140f49d189bd9a722ce9dbee5bdd5aa843"),
   "order.wnd":("MQL5/Profiles/Charts/Default/order.wnd","249de3043f50fad845ce326f834b8e62d8f7ad9c35a09135fb49cf59fccc9243")}
  for filename,(rel,digest) in pinned.items():
   source=release/filename;dest=terminal/rel
   if (source.is_symlink() or not source.is_file() or dest.is_symlink()
       or hashlib.sha256(source.read_bytes()).hexdigest()!=digest):
    raise RuntimeError("FP2582_RELEASE_INTEGRITY_INVALID")
   dest.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(source,dest)
   if hashlib.sha256(dest.read_bytes()).hexdigest()!=digest:
    raise RuntimeError("FP2582_RELEASE_INSTALL_MISMATCH")
  chart1=(terminal/"MQL5/Profiles/Charts/Default/chart01.chr").read_text("utf-16")
  chart3=(terminal/"MQL5/Profiles/Charts/Default/chart03.chr").read_text("utf-16")
  chart2=(terminal/"MQL5/Profiles/Charts/Default/chart02.chr").read_text("utf-16")
  if (chart1.count("name=AbutronFPNativeOrderBridgeV101")!=1
      or chart1.count("AdaptiveV2ReconcilerApproved=true")!=1
      or "AbutronFPNativeOrderBridge" in chart2 or "<expert>" in chart2
      or "AbutronFPNativeOrderBridge" in chart3
      or chart3.count("name=AbutronFPMarketsNativeFeedParallelV305")!=1
      or chart3.count("AbutronFPAccountHistoryV101.ex5")!=1):
   raise RuntimeError("FP2582_SINGLE_WRITER_OR_HISTORY_PROFILE_INVALID")
 # The obsolete script is never used by the dedicated FP worker.
 (terminal/"MQL5"/"Scripts"/"ABUTRON"/"AbutronFPMarketsNativeFeedV2.ex5").unlink(missing_ok=True)
 files=terminal/"MQL5"/"Files";files.mkdir(parents=True,exist_ok=True)
 # Root-owned systemd order-preflight binds an account-specific order folder.
 # Prepare it before starting MT5, under this account's isolated DynamicUser.
 # Directories alone cannot enable trading; broker/AI/SMC/ICT gates remain.
 if server=="FPMarketsSC-Demo" and mode=="DEMO":
  for sub in ("ABUTRON_FP","ABUTRON_FP/receipts","ABUTRON_FP/evidence"):
   folder=files/sub
   if folder.is_symlink():raise RuntimeError("FP account order folder is symlinked")
   folder.mkdir(mode=0o700,parents=True,exist_ok=True)
   if folder.stat().st_uid!=os.geteuid():raise RuntimeError("FP account order folder owner invalid")
 nonce=secrets.token_hex(16);challenge_owner=str(uuid.uuid4())
 challenge=files/"ABUTRON_MT5_CUSTOMER_CHALLENGE_V6.txt"
 challenge.write_text("\r\n".join(["ABUTRON_MT5_CUSTOMER_V6",nonce,challenge_owner,
  ALLOWED[(broker,server)],login,server,mode])+"\r\n")
 # Staged history indicator remains read-only and cannot alter native feed EA.
 # Do not break a broker login if an optional diagnostic binary is unavailable.
 try:
  stage_fp_demo_history(terminal,files,nonce,challenge_owner,login,server,mode)
 except (OSError,ValueError,UnicodeError):
  print("FP_HISTORY_READONLY_ADDON_NOT_STAGED",file=sys.stderr)
 try:
  stage_fp_demo_sidecar(terminal,files,nonce,challenge_owner,login,server,mode)
 except (OSError,ValueError,UnicodeError):
  print("FP_SIDECAR_READONLY_ADDON_NOT_STAGED",file=sys.stderr)
 auth=runtime/"auth.ini"
 auth.write_text("[Common]\r\nLogin="+login+"\r\nPassword="+doc["password"]+
  "\r\nServer="+server+"\r\nKeepPrivate=0\r\nProxyEnable=0\r\n"+
  "[Experts]\r\nEnabled=1\r\nAllowLiveTrading="+("1" if broker=="FP Markets" and mode=="DEMO" else "0")+"\r\nAllowDllImport=0\r\n"+
  "[StartUp]\r\nExpert=ABUTRON\\AbutronFPMarketsNativeFeedEA\r\n"+
  "Symbol=EURUSD"+
  "\r\nPeriod=M1\r\nShutdownTerminal=0\r\n")
 auth.chmod(0o600)
 doc["password"]=None
 env={**os.environ,"HOME":str(state),"WINEPREFIX":str(prefix),
    "WINEARCH":"win64","WINEDEBUG":"-all",
    "WINEDLLOVERRIDES":"mscoree,mshtml="}
 exe=terminal/"terminal64.exe"
 winconfig="Z:"+str(auth).replace("/","\\")
 args=[WINE,str(exe),"/portable","/config:"+winconfig]
 # MT5 may exit with code 0 to hand off an automatic LiveUpdate process.
 # Restart only if this specific event appears in the current launch's journal.
 # The official Python IPC bridge is not used. The native EA only accepts authorized per-account requests.
 heartbeat=files/("ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt")
 proof={"nonce":nonce,"proof_owner":challenge_owner,"broker":broker,"server":server,"mode":mode}
 started=time.monotonic();last_ok=0.0;was_connected=False
 process=None
 journal=terminal/"logs"/(time.strftime("%Y%m%d")+".log")
 try:
  # Bounded startup attempts; one session nonce, challenge and credential mount.
  # The Wine launcher may exit while LiveUpdate hands the real MT5 terminal
  # to a child within THIS systemd cgroup. Follow it without spawning another.
  for attempt in range(4):
   previous_bytes=journal.stat().st_size if journal.is_file() else 0
   process=subprocess.Popen(args,env=env,cwd=str(state),stdin=subprocess.DEVNULL,
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=False)
   post_exit_since=None
   while True:
    elapsed=time.monotonic()-started
    if heartbeat.is_file():
     try:lines=heartbeat.read_text(encoding="utf-8-sig").splitlines()
     except (OSError,UnicodeError):lines=[]
     try:fresh=time.time()-heartbeat.stat().st_mtime<13
     except OSError:fresh=False
     expected=["ABUTRON_MT5_NATIVE_HEARTBEAT_V1",nonce,challenge_owner,
      ALLOWED[(broker,server)],server,mode,"CONNECTED","NO_ORDER_FUNCTIONS"]
     authenticated=bool(fresh and lines==expected)
    else:authenticated=False
    if authenticated:
     was_connected=True;last_ok=time.monotonic()
     if auth.exists():auth.unlink()
     status(health,{**proof,"status":"CONNECTED","id":cid,
        "heartbeat_fresh":True,"verified_at":int(time.time())})
    elif was_connected:
     status(health,{**proof,"status":"BROKER_SESSION_LOST","id":cid,
        "heartbeat_fresh":False})
    elif elapsed<240:
     status(health,{**proof,"status":"CONNECTING","id":cid,"heartbeat_fresh":False})
    else:
     status(health,{**proof,"status":"AUTH_TIMEOUT","id":cid,"heartbeat_fresh":False})
     return 2
    if process.poll() is None:
     post_exit_since=None
     time.sleep(2)
     continue
    if cgroup_terminal_running():
     # Wine's original Popen returned but the MT5 terminal is still alive.
     # Never detach this worker or mark Connected without fresh native proof.
     post_exit_since=None
     time.sleep(2)
     continue
    # A bounded grace allows the Wine updater to spawn its child after the
    # launcher exits. This must not be mistaken for a successful broker login.
    if post_exit_since is None:post_exit_since=time.monotonic()
    # MT5 may authorize the broker and publish its 3-second native heartbeat
    # after Wine's launcher has already returned 0. The original 12-second
    # handoff window exited even as the genuine broker heartbeat arrived.
    # Follow the exact account/session proof; if it stops renewing, fail closed.
    if hold_zero_exit_for_native_proof(process.returncode,authenticated,
                                       time.monotonic()-post_exit_since):
     time.sleep(1)
     continue
    break
   if process.returncode!=0 or was_connected or attempt>=3 or time.monotonic()-started>=220:
    break
   try:
    data=journal.read_bytes()
    tail=data[previous_bytes:] if len(data)>previous_bytes else b""
   except OSError:
    tail=b""
   decision=exit_action(process.returncode,was_connected,
              cgroup_terminal_running(),handoff_event(tail),attempt,time.monotonic()-started)
   if decision=="MONITOR_CHILD":
    # A late child appeared after the launcher exit. Monitor its proof using
    # the same exact account/session nonce; never spawn a competing terminal.
    while cgroup_terminal_running() and time.monotonic()-started<240:
     if heartbeat.is_file():
      try:
       lines=heartbeat.read_text(encoding="utf-8-sig").splitlines()
       fresh=time.time()-heartbeat.stat().st_mtime<13
      except (OSError,UnicodeError):
       lines=[];fresh=False
      expected=["ABUTRON_MT5_NATIVE_HEARTBEAT_V1",nonce,challenge_owner,
         ALLOWED[(broker,server)],server,mode,"CONNECTED","NO_ORDER_FUNCTIONS"]
      if fresh and lines==expected:
       was_connected=True
       if auth.exists():auth.unlink()
       status(health,{**proof,"status":"CONNECTED","id":cid,
              "heartbeat_fresh":True,"verified_at":int(time.time())})
      else:
       status(health,{**proof,"status":"BROKER_SESSION_LOST" if was_connected else "CONNECTING",
          "id":cid,"heartbeat_fresh":False})
     time.sleep(2)
    break
   if decision!="RETRY_UPDATE":break
   status(health,{**proof,"status":"CONNECTING","id":cid,
          "heartbeat_fresh":False,"restart_reason":"MT5_LIVE_UPDATE","attempt":attempt+1})
   time.sleep(4)
  status(health,{**proof,"status":"PROCESS_EXITED","id":cid,"heartbeat_fresh":False,
                 "process_exit_code":process.returncode,
                 "authenticated_native_proof_seen":was_connected})
  return 1
 finally:
  auth.unlink(missing_ok=True)
  if process is not None and process.poll() is None:
   process.terminate()
   try:process.wait(timeout=7)
   except subprocess.TimeoutExpired:process.kill()
if __name__=="__main__":
 try:sys.exit(main() or 0)
 except Exception as exc:
  if os.environ.get("RUNTIME_DIRECTORY","").endswith("abutron-client-mt5-6c396441ac5d4b76b2f1ffaf2951beb3"):
   import re
   msg=str(exc)
   safe=msg if re.fullmatch(r"[A-Z][A-Z0-9_]{3,100}",msg) else type(exc).__name__
   print("FP2582_BOOT_FAILURE:"+safe,file=sys.stderr)
  print("ISOLATED_MT5_WORKER_FAILED",file=sys.stderr)
  sys.exit(1)
