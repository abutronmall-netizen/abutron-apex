#!/usr/bin/python3
"""Publish strict broker-native partial FP research; never route, enable, or send orders."""
import json,importlib.util,os,grp
from pathlib import Path

DIR=Path('/opt/apex-client-mt5/fpmarkets-research-partial')
OUT=Path('/var/lib/abutron-fp-scanner/partial-latest.json')

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,str(path))
 x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x);return x

def run():
 scanner=module('fp_partial_native_scanner_runner',DIR/'fp_partial_scanner.py')
 ui=module('fp_partial_broker_ui_runner',DIR/'fp_partial_ui.py')
 helper=module('fp_scanner_atomic_runner','/opt/apex-client-mt5/fpmarkets-scanner/fp_apex_readonly_scanner.py')
 doc=scanner.build()
 if not (doc['orders_enabled'] is False and doc['execution_authorized'] is False
   and doc['account_controls_modified'] is False and doc['symbols']==13
   and 0<doc['symbols_verified']<=13 and doc['timeframe_series']==doc['symbols_verified']*6):
  raise RuntimeError('FP_PARTIAL_REPORT_UNSAFE')
 # Production entry authority: original APEX EMA/RSI + conservative candle quality.
 # The historical SMC/ICT setup lifecycle must NEVER promote held signals.
 doc['setup_lifecycle_version']='RETIRED_NOT_A_TRADE_ENTRY_SOURCE'
 doc['pending_ict_setups']=0
 doc['ready_ict_setups']=0
 doc['smc_ict_passed']=0
 for row in doc['instruments']:
  row['smc']={'status':'REMOVED','score':0,'reasons':[]}
  row['ict']={'status':'REMOVED'}
  row['requires_ai_and_smc_and_ict']=False
  row['setup_lifecycle']={'phase':'RETIRED','note':'NO_SMC_ICT_ENTRY_PROMOTION'}
 if not (doc['orders_enabled'] is False and doc['execution_authorized'] is False
   and doc['account_controls_modified'] is False and doc['symbols']==13
   and all(r.get('proposal') not in ('BUY','SELL') or
       r.get('entry_quality',{}).get('status')=='PASS'
       for r in doc['instruments'])):
  raise RuntimeError('FP_NATIVE_ENTRY_QUALITY_CONTRACT_DENIED')
 # Validate complete UI and identity before committing scanner setup state.
 ui.create(doc)
 helper.atomic(OUT,doc)
 os.chown(OUT,0,grp.getgrnam('apexagent').gr_gid)
 result=ui.publish(doc)
 assert result['orders_enabled'] is False
 return result

if __name__=='__main__':print(json.dumps(run(),sort_keys=True))
