from pathlib import Path
import hashlib
source=Path("/opt/abutron-research/native-evidence/read-only-sidecar/AbutronDerivReadOnlySidecarV1.mq5")
original=source.read_text()
s=original
s=s.replace('#property version "1.02"','#property version "1.04"')
print("SOURCE_VERSION_PATCHED",s!=original)
if s==original:
    raise SystemExit("SOURCE_VERSION_NOT_EXACT")
anchor="void Status()\n{"
assert s.count(anchor)==1
fn=r'''
// All-time broker-history query and funding/deal export; no OrderSend.
// Separate V3-style evidence file: the existing 45-day V2 proof is unchanged.
datetime last_full_history=0;
int full_history_rows=0;
bool ExportNativeLifetimeHistory()
{
   if(!BrokerOK())return false;
   if(!HistorySelect((datetime)0,TimeCurrent()+120))
   {failures++;return false;}
   int total=HistoryDealsTotal();
   if(total<0 || total>150000){failures++;return false;}
   string dir="ABUTRON_NATIVE_ALLTIME_V1_"+nonce;
   string tmp=dir+".pending";
   string final=dir+".tsv";
   int f=FileOpen(tmp,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(f==INVALID_HANDLE){failures++;return false;}
   string hdr="ABUTRON_DERIV_NATIVE_ALLTIME_V1\n"+nonce+"\n"+
      expected_login+"\nDeriv-Demo\nDEMO\nUSD\n"+
      IntegerToString((long)TimeGMT())+"\n0\n"+
      IntegerToString(total)+"\n"+
      "ticket\tposition_id\torder_id\ttime_utc\ttype\tentry\treason\tmagic\tsymbol\tvolume\tprice\tprofit\tcommission\tfee\tswap\n";
   FileWriteString(f,hdr);
   int written=0;
   for(int i=0;i<total;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0)continue;
      long pos=(long)HistoryDealGetInteger(ticket,DEAL_POSITION_ID);
      long ord=(long)HistoryDealGetInteger(ticket,DEAL_ORDER);
      long clock=(long)HistoryDealGetInteger(ticket,DEAL_TIME);
      long typ=(long)HistoryDealGetInteger(ticket,DEAL_TYPE);
      long entry=(long)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      double vol=HistoryDealGetDouble(ticket,DEAL_VOLUME);
      string sym=HistoryDealGetString(ticket,DEAL_SYMBOL);
      if(clock<=0 || typ<0 || typ>30 || entry<0 || entry>3 || vol<0 ||
         StringLen(sym)>100)
      {FileClose(f);FileDelete(tmp);failures++;return false;}
      string row=StringFormat("%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
          (long)ticket,pos,ord,clock,typ,entry,
          (long)HistoryDealGetInteger(ticket,DEAL_REASON),
          (long)HistoryDealGetInteger(ticket,DEAL_MAGIC),sym,
          DoubleToString(vol,8),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_PRICE),10),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_PROFIT),6),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_COMMISSION),6),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_FEE),6),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_SWAP),6));
      FileWriteString(f,row);
      written++;
   }
   FileWriteString(f,"END\t"+IntegerToString(written)+"\t"+IntegerToString(total)+"\n");
   FileFlush(f);
   FileClose(f);
   if(written!=total || !FileMove(tmp,0,final,FILE_REWRITE))
   {FileDelete(tmp);failures++;return false;}
   full_history_rows=written;
   last_full_history=TimeGMT();
   return true;
}

'''
s=s.replace(anchor,fn+anchor)
anchor='''   if(last_history==0 || TimeGMT()-last_history>=120)ExportHistory();
   Status();'''
assert s.count(anchor)==1
s=s.replace(anchor,'''   if(last_history==0 || TimeGMT()-last_history>=120)ExportHistory();
   if(last_full_history==0 || TimeGMT()-last_full_history>=120)
      ExportNativeLifetimeHistory();
   Status();''')
assert 'OrderSend(' not in s and 'OrderCheck(' not in s
assert s.count('HistorySelect((datetime)0,TimeCurrent()+120)')==1
assert s.count('HistorySelect(TimeCurrent()-45*86400,TimeCurrent()+120)')==1
out=Path("/var/lib/abutron-mcp/abutron-deriv6207-lifetime-qa-20261109")
out.mkdir(mode=0o700,exist_ok=True)
p=out/"AbutronDerivReadOnlySidecarV1.mq5"
p.write_text(s)
p.chmod(0o600)
print("QA_ALLTIME_MQL_SOURCE",p,"len",len(s),"SHA256",hashlib.sha256(s.encode()).hexdigest())
print("ORIGINAL_SHA256",hashlib.sha256(original.encode()).hexdigest())
