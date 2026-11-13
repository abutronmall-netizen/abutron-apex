#property strict
#property version "1.00"
#property description "ABUTRON APEX account-bound FP Markets DEMO one-shot native order bridge"

// Attach to an FP Markets DEMO MT5 chart in each isolated customer terminal.
// Default is OFF. An authorized customer/owner must explicitly enable it.
input bool EnableNativeDemoOrders = false;

#define DIR_BASE "ABUTRON_FP\\"
#define DIR_RECEIPTS "ABUTRON_FP\\receipts\\"
#define DIR_EVIDENCE "ABUTRON_FP\\evidence\\"
#define REQ "ABUTRON_FP\\APEX_FP_NATIVE_ORDER_V1.req"
#define CONSUMED "ABUTRON_FP\\APEX_FP_NATIVE_ORDER_V1.consumed"
#define MAGIC 73113051

string gNonce="",gLogin="",gServer="",gReady="";
int gConsecutiveFeedFailures=0;

bool IsHex64(string s)
{
 if(StringLen(s)!=64)return false;
 for(int i=0;i<64;i++)
 {
  ushort ch=StringGetCharacter(s,i);
  if(!((ch>=48&&ch<=57)||(ch>=97&&ch<=102)))return false;
 }
 return true;
}

bool ApprovedSymbol(string sym)
{
 const string universe[]={"XAUUSD.r","BTCUSD","EURUSD","GBPUSD","USDJPY","AUDUSD","US100","US30","US500","GER40","XTIUSD","USDCHF","NZDUSD"};
 for(int i=0;i<ArraySize(universe);i++)if(sym==universe[i])return true;
 return false;
}

bool VerifiedDemoAccount()
{
 string firm=AccountInfoString(ACCOUNT_COMPANY);
 StringToLower(firm);
 return TerminalInfoInteger(TERMINAL_CONNECTED)!=0 &&
   AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
   (StringFind(firm,"fp markets")>=0 || StringFind(firm,"fpmarkets")>=0 || firm=="first prudential markets limited") &&
   AccountInfoString(ACCOUNT_CURRENCY)=="USD" &&
   IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))==gLogin &&
   AccountInfoString(ACCOUNT_SERVER)==gServer && gServer=="FPMarketsSC-Demo";
}

bool VerifiedNativeFeed(bool initial)
{
 string file="",extra="";
 long h=FileFindFirst("ABUTRON_SESSION_HEARTBEAT_V1_*.txt",file);
 if(h==INVALID_HANDLE)return false;
 bool duplicate=FileFindNext(h,extra);
 FileFindClose(h);
 if(duplicate)return false;
 long modified=FileGetInteger(file,FILE_MODIFY_DATE);
 if(modified<=0 || MathAbs((double)((long)TimeGMT()-modified))>20.0)return false;
 int f=FileOpen(file,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(f==INVALID_HANDLE)return false;
 string header=FileReadString(f),nonce=FileReadString(f);
 string owner=FileReadString(f),broker=FileReadString(f);
 string server=FileReadString(f),mode=FileReadString(f);
 string status=FileReadString(f),orders=FileReadString(f);
 FileClose(f);
 if(header!="ABUTRON_MT5_NATIVE_HEARTBEAT_V1"||StringLen(nonce)!=32||
    file!="ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt"||
    StringLen(owner)!=36||broker!="FP_MARKETS"||server!="FPMarketsSC-Demo"||
    mode!="DEMO"||status!="CONNECTED"||orders!="NO_ORDER_FUNCTIONS")return false;
 if(initial)
 {
    gNonce=nonce;
    gLogin=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
    gServer=AccountInfoString(ACCOUNT_SERVER);
 }
 return gNonce==nonce && gServer==server && VerifiedDemoAccount();
}

void WriteReadiness()
{
 string base=gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\nFP_DEMO\r\n"+
  IntegerToString((long)TimeGMT())+"\r\n"+IntegerToString(OrdersTotal())+"\r\n"+
  IntegerToString(PositionsTotal())+"\r\n"+
  IntegerToString((long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))+"\r\n"+
  IntegerToString((long)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+"\r\n";
 int h=FileOpen(gReady,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h!=INVALID_HANDLE)
 {
  FileWriteString(h,"FP_NATIVE_BRIDGE_READY_V2\r\n"+base+
                    IntegerToString((long)EnableNativeDemoOrders)+"\r\n");
  FileFlush(h);FileClose(h);
 }
 // Distinct capability proof: only a multi-position-capable V2 EA writes this.
 // FP-only capability proof; not accepted by any FP Markets service.
 string multi="ABUTRON_FP_BRIDGE_READY_V3_"+gNonce+".txt";
 int mh=FileOpen(multi,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(mh!=INVALID_HANDLE)
 {
  FileWriteString(mh,"FP_NATIVE_BRIDGE_READY_V3\r\n"+base+
    IntegerToString((long)EnableNativeDemoOrders)+"\r\n");
  FileFlush(mh);FileClose(mh);
 }
 // Exact new policy marker; only the $50/$100 build emits this proof.
 // Used by the Python new-order gate; old V2 does not write this file.
 string usdproof="ABUTRON_FP_BRIDGE_USD_50_100_"+gNonce+".txt";
 int ph=FileOpen(usdproof,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(ph!=INVALID_HANDLE)
 {
  FileWriteString(ph,"FP_NATIVE_BRIDGE_USD_50_100_V1\r\n"+base+
    IntegerToString((long)EnableNativeDemoOrders)+"\r\n");
  FileFlush(ph);FileClose(ph);
 }
 // FP-only diagnostic compatibility proof.
 string legacy="ABUTRON_FP_BRIDGE_READY_V1_"+gNonce+".txt";
 h=FileOpen(legacy,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h!=INVALID_HANDLE)
 {
  FileWriteString(h,"FP_NATIVE_BRIDGE_READY_V1\r\n"+base);
  FileFlush(h);FileClose(h);
 }
}

// Immutable receipt per signal. Never overwrites an earlier result.
void Receipt(string key,string status,string reason,long order=0,long deal=0)
{
 if(!IsHex64(key))return;
 string file=DIR_RECEIPTS+key+".txt";
 if(FileIsExist(file))return;
 int h=FileOpen(file,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE){Print("APEX_IMMUTABLE_RECEIPT_ERROR ",GetLastError());return;}
 string body="APEX_FP_NATIVE_V1\r\n"+key+"\r\n"+status+"\r\n"+reason+"\r\n"+
   IntegerToString(order)+"\r\n"+IntegerToString(deal)+"\r\n"+
   IntegerToString((long)TimeGMT())+"\r\n"+gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\n";
 FileWriteString(h,body);FileFlush(h);FileClose(h);
}

bool DollarPrice(string sym,bool buy,double vol,double entry,double dollars,bool target,double &level,double &gross)
{
 if(vol<=0||entry<=0||dollars<=0)return false;
 ENUM_ORDER_TYPE side=(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
 int direction=(buy?1:-1)*(target?1:-1);
 double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
 if(tick<=0)tick=SymbolInfoDouble(sym,SYMBOL_POINT);
 if(tick<=0)return false;
 double lo=0.0,hi=tick,cash=0.0;
 bool reached=false;
 for(int i=0;i<65;i++)
 {
    double price=entry+direction*hi;
    if(price<=tick||!OrderCalcProfit(side,sym,vol,entry,price,cash))return false;
    if((target?cash:-cash)>=dollars){reached=true;break;}
    hi*=2.0;
 }
 if(!reached)return false;
 for(int j=0;j<55;j++)
 {
    double mid=(lo+hi)/2.0;
    if(!OrderCalcProfit(side,sym,vol,entry,entry+direction*mid,cash))return false;
    if((target?cash:-cash)>=dollars)hi=mid;
    else lo=mid;
 }
 double raw=entry+direction*hi;
 double ticks=(direction>0?MathCeil(raw/tick-1.0e-8):MathFloor(raw/tick+1.0e-8));
 level=NormalizeDouble(ticks*tick,(int)SymbolInfoInteger(sym,SYMBOL_DIGITS));
 if(level<=0||((direction>0)&&(level<=entry))||((direction<0)&&(level>=entry)))return false;
 if(!OrderCalcProfit(side,sym,vol,entry,level,cash))return false;
 gross=(target?cash:-cash);
 return MathIsValidNumber(gross)&&gross>0&&MathAbs(gross-dollars)<=2.0;
}

// Multi-symbol DEMO portfolio: maximum 13 positions, one protected APEX
// position per approved symbol. Broker pending orders always block new entry.
// Every existing position must be APEX-owned and have USD broker-native stops.
bool PortfolioCanAdd(string next_symbol)
{
 if(OrdersTotal()!=0 || PositionsTotal()>=13)return false;
 string seen[13];
 int used=0;
 for(int i=0;i<PositionsTotal();i++)
 {
   ulong ticket=PositionGetTicket(i);
   if(ticket==0)return false;
   string sym=PositionGetString(POSITION_SYMBOL);
   if(!ApprovedSymbol(sym)||sym==next_symbol ||
      PositionGetInteger(POSITION_MAGIC)!=MAGIC ||
      used>=13)return false;
   for(int j=0;j<used;j++)if(seen[j]==sym)return false;
   seen[used++]=sym;
   double vol=PositionGetDouble(POSITION_VOLUME);
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   double sl=PositionGetDouble(POSITION_SL);
   double tp=PositionGetDouble(POSITION_TP);
   long side=PositionGetInteger(POSITION_TYPE);
   bool buy=side==POSITION_TYPE_BUY;
   double loss=0.0,gain=0.0;
   if(vol<=0||entry<=0||sl<=0||tp<=0 ||
      !((buy&&sl<entry&&entry<tp)||(!buy&&tp<entry&&entry<sl)) ||
      !OrderCalcProfit(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL,sym,vol,entry,sl,loss) ||
      !OrderCalcProfit(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL,sym,vol,entry,tp,gain) ||
      !(MathAbs(-loss-50.0)<=2.0 && MathAbs(gain-100.0)<=2.0))
      return false;
 }
 return true;
}

// Single in-flight request; no retry on ambiguous broker results.
void HandleRequest()
{
 if(!FileIsExist(REQ))return;
 int h=FileOpen(REQ,FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ,0,CP_UTF8);
 if(h==INVALID_HANDLE)return;
 string ver=FileReadString(h),nonce=FileReadString(h),key=FileReadString(h);
 string login=FileReadString(h),server=FileReadString(h),sym=FileReadString(h),side=FileReadString(h);
 string lots_s=FileReadString(h),sl_s=FileReadString(h),tp_s=FileReadString(h);
 string expire_s=FileReadString(h),mode=FileReadString(h);
 FileClose(h);
 // Crash-safe consume BEFORE any broker send. No automatic replay on restart.
 if(!FileMove(REQ,0,CONSUMED,FILE_REWRITE))return;
 if(!IsHex64(key))return;
 if(FileIsExist(DIR_RECEIPTS+key+".txt"))return;
 if((ver!="APEX_FP_NATIVE_ORDER_V1")||(nonce!=gNonce)||(login!=gLogin)||(server!=gServer)||
    ((side!="BUY")&&(side!="SELL"))||(mode!="SEND_DEMO_ONLY")||(!ApprovedSymbol(sym))||(!VerifiedDemoAccount()))
 {Receipt(key,"BLOCKED","IDENTITY_OR_BROKER_DENIED");return;}
 long expire=(long)StringToInteger(expire_s);
 if(expire<(long)TimeGMT()||expire>(long)TimeGMT()+20)
 {Receipt(key,"BLOCKED","EXPIRED_SIGNAL");return;}
 if(!EnableNativeDemoOrders||!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)||
    !MQLInfoInteger(MQL_TRADE_ALLOWED)||!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
 {Receipt(key,"BLOCKED","ACCOUNT_OR_EA_AUTOTRADING_OFF");return;}
 if(!PortfolioCanAdd(sym))
 {Receipt(key,"BLOCKED","PORTFOLIO_SYMBOL_OR_RISK_CAPACITY_DENIED");return;}
 if(!SymbolSelect(sym,true))
 {Receipt(key,"BLOCKED","SYMBOL_NOT_AVAILABLE");return;}
 double vol=StringToDouble(lots_s);
 double minv=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN),maxv=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
 double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
 if(!MathIsValidNumber(vol)||vol<minv||vol>maxv||step<=0||
    MathAbs((vol-minv)/step-MathRound((vol-minv)/step))>0.00001||
    MathAbs(StringToDouble(sl_s)-50.0)>0.001||MathAbs(StringToDouble(tp_s)-100.0)>0.001)
 {Receipt(key,"BLOCKED","INVALID_VOLUME_OR_USD_STOP_POLICY");return;}
 MqlTick tick;
 if(!SymbolInfoTick(sym,tick)||tick.ask<=0||tick.bid<=0)
 {Receipt(key,"BLOCKED","BROKER_TICK_NOT_AVAILABLE");return;}
 bool buy=(side=="BUY");
 double entry=(buy?tick.ask:tick.bid),sl=0.0,tp=0.0,loss=0.0,gain=0.0;
 if(!DollarPrice(sym,buy,vol,entry,50.0,false,sl,loss)||
    !DollarPrice(sym,buy,vol,entry,100.0,true,tp,gain))
 {Receipt(key,"BLOCKED","NATIVE_USD_STOP_CALCULATION_FAILED");return;}
 double minstop=(double)SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*SymbolInfoDouble(sym,SYMBOL_POINT);
 // Protective levels are evaluated relative to the broker CLOSE-side quote.
 // BUY closes at Bid; SELL closes at Ask. Entry-side checks can misclassify stops.
 if((buy&&(tick.bid-sl<minstop||tp-tick.bid<minstop))||
    (!buy&&(sl-tick.ask<minstop||tick.ask-tp<minstop)))
 {Receipt(key,"BLOCKED","BROKER_STOP_DISTANCE");return;}
 ENUM_ORDER_TYPE typ=(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
 double margin=0.0;
 if(!OrderCalcMargin(typ,sym,vol,entry,margin)||margin<0||
    margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.10)
 {Receipt(key,"BLOCKED","ACCOUNT_MARGIN_GUARD");return;}
 MqlTradeRequest req={};MqlTradeResult res={};MqlTradeCheckResult check={};
 req.action=TRADE_ACTION_DEAL;req.symbol=sym;req.volume=vol;req.type=typ;
 req.price=entry;req.sl=sl;req.tp=tp;req.magic=MAGIC;
 req.deviation=15;req.type_time=ORDER_TIME_GTC;req.comment="ABUTRON FP DEMO";
 int fill=(int)SymbolInfoInteger(sym,SYMBOL_FILLING_MODE);
 if((fill & SYMBOL_FILLING_IOC)!=0)req.type_filling=ORDER_FILLING_IOC;
 else if((fill & SYMBOL_FILLING_FOK)!=0)req.type_filling=ORDER_FILLING_FOK;
 else req.type_filling=ORDER_FILLING_RETURN;
 // MQL5 OrderCheck() documents successful checking with retcode=0.
 // TRADE_RETCODE_DONE may also occur. Never pass a false OrderCheck().
 ResetLastError();
 bool checked=OrderCheck(req,check);
 if(!checked||(check.retcode!=0&&check.retcode!=TRADE_RETCODE_DONE))
 {Receipt(key,"BLOCKED","BROKER_ORDERCHECK_REJECTED_"+IntegerToString((long)check.retcode));return;}
 // Exactly one broker send attempt. Partial or ambiguous response is UNKNOWN.
 bool sent=OrderSend(req,res);
 if(!sent||(res.retcode!=TRADE_RETCODE_DONE&&res.retcode!=TRADE_RETCODE_DONE_PARTIAL)||
    res.order<=0||res.deal<=0)
 {Receipt(key,"UNKNOWN","BROKER_SEND_UNCERTAIN_"+IntegerToString((long)res.retcode),
           (long)res.order,(long)res.deal);return;}
 Receipt(key,"ACK","BROKER_ORDER_ACK_POSITION_STILL_UNVERIFIED",(long)res.order,(long)res.deal);
}

// Verify broker position and actual native SL/TP after accepted OrderSend.
// The immutable receipt is not mistaken for a position or verified closure.
void UpdateEvidenceFor(string key,long order,long deal)
{
 if(order<=0||deal<=0||!IsHex64(key))return;
 datetime from=TimeCurrent()-30*86400;
 if(!HistorySelect(from,TimeCurrent()+60)||!HistoryDealSelect((ulong)deal))return;
 if(HistoryDealGetInteger((ulong)deal,DEAL_MAGIC)!=MAGIC)return;
 string sym=HistoryDealGetString((ulong)deal,DEAL_SYMBOL);
 long direction=HistoryDealGetInteger((ulong)deal,DEAL_TYPE);
 string side=direction==DEAL_TYPE_BUY?"BUY":direction==DEAL_TYPE_SELL?"SELL":"";
 if(!ApprovedSymbol(sym)||side=="")return;
 long position_id=HistoryDealGetInteger((ulong)deal,DEAL_POSITION_ID);
 if(position_id<=0)return;
 string state="NOT_YET_VISIBLE";
 double volume=0,entry=0,sl=0,tp=0,loss=0,gain=0;
 bool found=false;
 for(int i=0;i<PositionsTotal();i++)
 {
   ulong ticket=PositionGetTicket(i);
   if(ticket==0||PositionGetInteger(POSITION_IDENTIFIER)!=position_id)continue;
   if(PositionGetString(POSITION_SYMBOL)!=sym||PositionGetInteger(POSITION_MAGIC)!=MAGIC)continue;
   found=true;
   volume=PositionGetDouble(POSITION_VOLUME);entry=PositionGetDouble(POSITION_PRICE_OPEN);
   sl=PositionGetDouble(POSITION_SL);tp=PositionGetDouble(POSITION_TP);
   if(sl>0&&tp>0&&OrderCalcProfit(side=="BUY"?ORDER_TYPE_BUY:ORDER_TYPE_SELL,sym,volume,entry,sl,loss)&&
      OrderCalcProfit(side=="BUY"?ORDER_TYPE_BUY:ORDER_TYPE_SELL,sym,volume,entry,tp,gain))
   {
      loss=-loss;
      bool geometry=((side=="BUY")?(sl<entry&&entry<tp):(tp<entry&&entry<sl));
      if(geometry&&(MathAbs(loss-50.0)<=2.0&&MathAbs(gain-100.0)<=2.0))
         state="OPEN_PROTECTED";
      else state="OPEN_UNPROTECTED";
   }
   else state="OPEN_UNPROTECTED";
   break;
 }
 long exit_deal=0;
 if(!found)
 {
   if(!HistorySelect(from,TimeCurrent()+60))return;
   for(int i=HistoryDealsTotal()-1;i>=0;i--)
   {
     ulong t=HistoryDealGetTicket(i);
     if(t==0||HistoryDealGetInteger(t,DEAL_POSITION_ID)!=position_id)continue;
     long entry_type=HistoryDealGetInteger(t,DEAL_ENTRY);
     if(entry_type==DEAL_ENTRY_OUT||entry_type==DEAL_ENTRY_OUT_BY)
     {exit_deal=(long)t;state="CLOSED_BROKER_VERIFIED";break;}
   }
 }
 string filename=DIR_EVIDENCE+key+".txt";
 if(state=="NOT_YET_VISIBLE"&&FileIsExist(filename))return;
 int f=FileOpen(filename,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(f==INVALID_HANDLE)return;
 string text="APEX_FP_BROKER_POSITION_V1\r\n"+key+"\r\n"+gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\n"+
    sym+"\r\n"+side+"\r\n"+IntegerToString(order)+"\r\n"+IntegerToString(deal)+"\r\n"+
    IntegerToString(position_id)+"\r\n"+DoubleToString(volume,8)+"\r\n"+
    DoubleToString(entry,10)+"\r\n"+DoubleToString(sl,10)+"\r\n"+
    DoubleToString(tp,10)+"\r\n"+DoubleToString(loss,3)+"\r\n"+
    DoubleToString(gain,3)+"\r\n"+state+"\r\n"+IntegerToString((long)TimeGMT())+"\r\n"+
    IntegerToString(exit_deal)+"\r\n";
 FileWriteString(f,text);FileFlush(f);FileClose(f);
}

// Refresh all protected positions and closures, not just the last order.
// Each receipt is immutable, account-bound, and checked against broker history.
void UpdateEvidence()
{
 string filename="";
 long h=FileFindFirst(DIR_RECEIPTS+"*.txt",filename);
 if(h==INVALID_HANDLE)return;
 int scanned=0;
 do
 {
    if(++scanned>250)break;
    int f=FileOpen(DIR_RECEIPTS+filename,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8);
    if(f==INVALID_HANDLE)continue;
    string header=FileReadString(f),key=FileReadString(f),kind=FileReadString(f);
    string reason=FileReadString(f),order_s=FileReadString(f),deal_s=FileReadString(f);
    string timestamp=FileReadString(f),nonce=FileReadString(f);
    string login=FileReadString(f),server=FileReadString(f);
    FileClose(f);
    if(header!="APEX_FP_NATIVE_V1"||kind!="ACK"||
       filename!=key+".txt"||!IsHex64(key)||
       nonce!=gNonce||login!=gLogin||server!=gServer)continue;
    UpdateEvidenceFor(key,(long)StringToInteger(order_s),(long)StringToInteger(deal_s));
 } while(FileFindNext(h,filename));
 FileFindClose(h);
}

int OnInit()
{
 if(!VerifiedNativeFeed(true))
 {Print("APEX_V2_FRESH_NATIVE_FP_DEMO_FEED_REQUIRED");return INIT_FAILED;}
 FolderCreate("ABUTRON_FP");FolderCreate("ABUTRON_FP\\receipts");FolderCreate("ABUTRON_FP\\evidence");
 gReady="ABUTRON_FP_BRIDGE_READY_V2_"+gNonce+".txt";
 WriteReadiness();EventSetTimer(2);
 Print("APEX_V2_BRIDGE_READY; automatic order submission input is ",EnableNativeDemoOrders);
 return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){EventKillTimer();}
void OnTimer()
{
 // Do not treat a partially written heartbeat as a permanent disconnect.
 // While any read/identity proof fails, DO NOT publish a fresh readiness proof,
 // accept an order request, or certify a broker position. Fail closed.
 if(!VerifiedNativeFeed(false))
 {
   gConsecutiveFeedFailures++;
   if(gConsecutiveFeedFailures==1)
      Print("APEX_V2_BROKER_FEED_TEMPORARILY_UNVERIFIED; orders paused");
   if(gConsecutiveFeedFailures==30)
      Print("APEX_V2_BROKER_FEED_UNVERIFIED_60_SECONDS; orders stay paused until verified recovery");
   return;
 }
 if(gConsecutiveFeedFailures>0)
    Print("APEX_V2_BROKER_FEED_RECOVERED_AFTER_",gConsecutiveFeedFailures,"_CHECKS");
 gConsecutiveFeedFailures=0;
 WriteReadiness();UpdateEvidence();HandleRequest();
}
