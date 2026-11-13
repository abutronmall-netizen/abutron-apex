#property strict
#property version "1.04"
#property description "ABUTRON isolated broker-native ticks + deal history. NO ORDER OPERATIONS."

string SYM[5]={"Volatility 10 Index.0","Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0","Volatility 100 Index.0"};
ulong cursor[5];
string nonce="";
string expected_login="";
bool verified=false;
int cycles=0;
int total_ticks=0;
int last_deal_count=0;
datetime last_history=0;
int failures=0;

bool Hex32(string s)
{
   if(StringLen(s)!=32)return false;
   for(int i=0;i<32;i++){
      int c=StringGetCharacter(s,i);
      if(!((c>=48 && c<=57)||(c>=97 && c<=102)))return false;
   }
   return true;
}
bool ReadMarker()
{
   int f=FileOpen("ABUTRON_ISOLATED_READONLY_TERMINAL_V1.txt",FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(f==INVALID_HANDLE)return false;
   string schema=FileReadString(f);
   expected_login=FileReadString(f);
   nonce=FileReadString(f);
   FileClose(f);
   return schema=="ABUTRON_ISOLATED_READONLY_TERMINAL_V1" && Hex32(nonce)
       && StringLen(expected_login)>=4 && StringFind("|6207|7593|9244|","|"+StringSubstr(expected_login,StringLen(expected_login)-4)+"|")>=0;
}
bool BrokerOK()
{
   if(TerminalInfoInteger(TERMINAL_CONNECTED)==0 ||
      AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO ||
      AccountInfoString(ACCOUNT_SERVER)!="Deriv-Demo" ||
      AccountInfoString(ACCOUNT_CURRENCY)!="USD" ||
      IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))!=expected_login)
      return false;
   string company=AccountInfoString(ACCOUNT_COMPANY);
   StringToLower(company);
   return StringFind(company,"deriv")>=0;
}
int OnInit()
{
   // Broker terminal may expose trading permission; this signed EA has no
   // trading API calls, DLL imports, web requests or order-router access.
   if(MQLInfoInteger(MQL_TRADE_ALLOWED)!=0)
      Print("ABUTRON_SIDECAR_BYTECODE_NO_ORDER_FUNCTIONS");
   if(!ReadMarker())
   {
      Print("ABUTRON_SIDECAR_DENIED_NOT_ISOLATED");
      return INIT_FAILED;
   }
   datetime now=TimeGMT();
   for(int i=0;i<5;i++)cursor[i]=(ulong)((long)now-30)*1000;
   EventSetTimer(10);
   Print("ABUTRON_SIDECAR_READY_NO_ORDERS");
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){EventKillTimer();}

void CaptureTicks()
{
   ulong right=(ulong)((long)TimeGMT()-2)*1000;
   int good=0;
   for(int k=0;k<5;k++)
   {
      if(!SymbolSelect(SYM[k],true)){failures++;continue;}
      ulong left=cursor[k]+1;
      if(right<=left)continue;
      if(right-left>120000)left=right-120000;
      MqlTick ticks[];
      ResetLastError();
      int n=CopyTicksRange(SYM[k],ticks,COPY_TICKS_ALL,left,right);
      if(n<0 || n>6000){failures++;continue;}
      string path="ABUTRON_COPYTICKS_CONTINUOUS_V1_"+nonce+"_"+IntegerToString((long)TimeGMT()/3600)+".tsv";
      int f=FileOpen(path,FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
      if(f==INVALID_HANDLE){failures++;continue;}
      if(FileSize(f)==0)
      {
         FileWriteString(f,"ABUTRON_COPYTICKS_CONTINUOUS_V1\t"+nonce+"\t"+expected_login+"\tDeriv-Demo\tDEMO\n");
         FileWriteString(f,"symbol\ttime_msc\tbid\task\tlast\tflags\n");
      }
      else FileSeek(f,0,SEEK_END);
      ulong last=cursor[k];
      for(int i=0;i<n;i++)
      {
         MqlTick t=ticks[i];
         if(t.time_msc<=0 || (ulong)t.time_msc<left ||
            (ulong)t.time_msc>right || (ulong)t.time_msc<=last ||
            t.bid<=0 || t.ask<t.bid) {failures++;continue;}
         FileWriteString(f,SYM[k]+"\t"+IntegerToString((long)t.time_msc)+"\t"+
           DoubleToString(t.bid,10)+"\t"+DoubleToString(t.ask,10)+"\t"+
           DoubleToString(t.last,10)+"\t"+IntegerToString((long)t.flags)+"\n");
         last=(ulong)t.time_msc;good++;
      }
      FileFlush(f);FileClose(f);
      if(last>cursor[k])cursor[k]=last;
   }
   total_ticks+=good;
}
void ExportHistory()
{
   if(!HistorySelect(TimeCurrent()-45*86400,TimeCurrent()+120))
   {failures++;return;}
   int count=HistoryDealsTotal();
   if(count<0 || count>200000){failures++;return;}
   string path="ABUTRON_APEX_DEAL_HISTORY_V2_"+nonce+".tsv";
   int f=FileOpen(path,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(f==INVALID_HANDLE){failures++;return;}
   FileWriteString(f,"ABUTRON_APEX_DEAL_HISTORY_V2\n"+nonce+"\n"+expected_login+
      "\nDeriv-Demo\n"+IntegerToString((long)TimeGMT())+"\nDEMO\n"+
      "ticket\tposition_id\torder_id\ttime_utc\ttype\tentry\treason\tmagic\tsymbol\tvolume\tprice\tprofit\tcommission\tfee\tswap\n");
   int written=0;
   for(int i=0;i<count;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0)continue;
      long pos=(long)HistoryDealGetInteger(ticket,DEAL_POSITION_ID);
      long ord=(long)HistoryDealGetInteger(ticket,DEAL_ORDER);
      long clock=(long)HistoryDealGetInteger(ticket,DEAL_TIME);
      long typ=(long)HistoryDealGetInteger(ticket,DEAL_TYPE);
      long entry=(long)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      double vol=HistoryDealGetDouble(ticket,DEAL_VOLUME);
      if(pos<=0 || ord<=0 || clock<=0 || vol<=0 || !(typ==DEAL_TYPE_BUY || typ==DEAL_TYPE_SELL)
          || entry<0 || entry>3) continue;
      string sym=HistoryDealGetString(ticket,DEAL_SYMBOL);
      if(StringLen(sym)<1 || StringLen(sym)>100)continue;
      FileWriteString(f,StringFormat("%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%I64d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
          (long)ticket,pos,ord,clock,typ,entry,
          (long)HistoryDealGetInteger(ticket,DEAL_REASON),
          (long)HistoryDealGetInteger(ticket,DEAL_MAGIC),sym,DoubleToString(vol,8),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_PRICE),10),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_PROFIT),6),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_COMMISSION),6),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_FEE),6),
          DoubleToString(HistoryDealGetDouble(ticket,DEAL_SWAP),6)));
      written++;
   }
   FileFlush(f);FileClose(f);
   last_history=TimeGMT();
   last_deal_count=written;
}
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
   string outpath=dir+".tsv";
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
   if(written!=total || !FileMove(tmp,0,outpath,FILE_REWRITE))
   {FileDelete(tmp);failures++;return false;}
   full_history_rows=written;
   last_full_history=TimeGMT();
   return true;
}

void Status()
{
   string file="ABUTRON_SIDECAR_STATUS_V1_"+nonce+".txt";
   int f=FileOpen(file,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(f==INVALID_HANDLE)return;
   FileWriteString(f,"ABUTRON_SIDECAR_STATUS_V1\n"+nonce+"\n"+expected_login+
     "\nDeriv-Demo\nDEMO\n"+IntegerToString((long)TimeGMT())+
     "\n"+IntegerToString(cycles)+"\n"+IntegerToString(total_ticks)+
     "\n"+IntegerToString(last_deal_count)+"\n"+
     IntegerToString((long)last_history)+"\n"+IntegerToString(failures)+"\nNO_ORDER_FUNCTIONS\n");
   FileFlush(f);FileClose(f);
}
void OnTimer()
{
   // Safety is enforced by no-order bytecode and independent DEMO identity,
   // not by a terminal-wide UI flag that is inconsistent across MT5 builds.
   if(!BrokerOK())
   {if(verified)Print("ABUTRON_SIDECAR_BROKER_SESSION_LOST");verified=false;return;}
   verified=true;cycles++;
   CaptureTicks();
   if(last_history==0 || TimeGMT()-last_history>=120)ExportHistory();
   if(last_full_history==0 || TimeGMT()-last_full_history>=120)
      ExportNativeLifetimeHistory();
   Status();
}
