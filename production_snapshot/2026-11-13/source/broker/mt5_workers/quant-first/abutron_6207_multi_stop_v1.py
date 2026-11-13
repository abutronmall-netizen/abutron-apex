#!/usr/bin/env python3
"""Hard-stop new 6207 DEMO entries; never touch open positions or SL/TP."""
import datetime as dt,json,os,subprocess,time
from pathlib import Path
TRIAL='abutron-6207-multi-trial-dispatch.timer'
LOG=Path('/var/lib/abutron-6207-pilot/multi-trial-stop-v1.json')
def main():
 if os.geteuid()!=0:raise SystemExit('ROOT_REQUIRED')
 now=dt.datetime.now(dt.timezone.utc)
 if now<dt.datetime(2026,11,7,14,0,tzinfo=dt.timezone.utc):
  raise SystemExit('NOT_THE_16_00_SAST_CUTOFF')
 r=subprocess.run(['/usr/bin/systemctl','disable','--now',TRIAL],capture_output=True,text=True,timeout=15)
 if r.returncode!=0:raise SystemExit('STOP_TIMER_FAILED_FAIL_CLOSED_RUNTIME_EXPIRY_ACTIVE')
 # The 6207-only ACK sees the expired scoped lease and revokes effective ON.
 ack=subprocess.run(['/usr/bin/systemctl','start','abutron-6207-native-activation-ack.service'],
   capture_output=True,text=True,timeout=15)
 record={'schema':'abutron.6207.multi_demo_cutoff.v1','stopped_at_utc':now.isoformat(),
 'new_entry_timer_disabled':r.returncode==0,'native_ack_refreshed':ack.returncode==0,
 'global_dispatcher_untouched':True,'all_open_positions_preserved':True,
 'broker_side_protective_sl_tp_untouched':True,'scope':'Deriv DEMO 6207 only'}
 fd=os.open(LOG,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as f:
  json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 print('6207_DEMO_TRIAL_16_00_SAST_NEW_ENTRIES_STOPPED',record['stopped_at_utc'],
 'ack_result',ack.returncode,flush=True)
if __name__=='__main__':main()
