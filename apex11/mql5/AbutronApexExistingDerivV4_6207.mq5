#property strict
#property version "4.00"
#property description "ABUTRON APEX Deriv DEMO V2 plus fail-closed broker execution evidence"

// Attach to a DERIV DEMO MT5 chart in each isolated customer terminal.
// Default is OFF. An authorized customer/owner must explicitly enable it.
input bool EnableNativeDemoOrders = false;
input bool EnableAdaptiveEquityV2 = true; // Only for versioned native requests
input bool AdaptiveV2ReconcilerApproved = false; // OFF until native V2 lifecycle is verified
// Native V4 is inert until BOTH supervisor and EA revision checks are proven.
input bool EnableApex11V4DemoOrders = false;
// Previous V3 request path remains present but disabled by default for exclusive-writer handoff.
// The old V2/V3 writer is permanently disabled in this V4-only build.

#define DIR_BASE "ABUTRON\\"
#define DIR_RECEIPTS "ABUTRON\\receipts\\"
#define DIR_EVIDENCE "ABUTRON\\evidence\\"
#define DIR_AUDIT "ABUTRON\\execution-audit\\"
#define REQ "ABUTRON\\APEX_NATIVE_ORDER_V1.req"
#define CONSUMED "ABUTRON\\APEX_NATIVE_ORDER_V1.consumed"
#define V4_REQ "ABUTRON\\ABUTRON_APEX_V4.req"
#define V4_CONSUMED_DIR "ABUTRON\\execution-audit\\"
#define V4_MAGIC "APEX_NATIVE_ACCOUNT_BOUND_ORDER_V4"
#define MAGIC 73113011

string gNonce="",gLogin="",gServer="",gReady="";
int gConsecutiveFeedFailures=0;
#include "AdaptiveRiskProofV2.mqh"

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
 const string universe[]={"Volatility 10 Index.0","Volatility 25 Index.0","Volatility 50 Index.0",
 "Volatility 75 Index.0","Volatility 100 Index.0","Crash 150 Index.0","Crash 300 Index.0",
 "Crash 600 Index.0","Crash 1000 Index.0","Boom 150 Index.0","Boom 300 Index.0",
 "Boom 600 Index.0","Boom 1000 Index.0"};
 for(int i=0;i<ArraySize(universe);i++)if(sym==universe[i])return true;
 return false;
}

bool VerifiedDemoAccount()
{
 string firm=AccountInfoString(ACCOUNT_COMPANY);
 StringToLower(firm);
 return TerminalInfoInteger(TERMINAL_CONNECTED)!=0 &&
   AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
   StringFind(firm,"deriv")>=0 &&
   AccountInfoString(ACCOUNT_CURRENCY)=="USD" &&
   IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))==gLogin &&
   AccountInfoString(ACCOUNT_SERVER)==gServer && gServer=="Deriv-Demo";
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
    StringLen(owner)!=36||broker!="DERIV_BVI"||server!="Deriv-Demo"||
    mode!="DEMO"||status!="CONNECTED"||orders!="NO_ORDER_FUNCTIONS")return false;
 if(initial)
 {
    gNonce=nonce;
    gLogin=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
    gServer=AccountInfoString(ACCOUNT_SERVER);
 }
 return gNonce==nonce && gServer==server && VerifiedDemoAccount();
}


// A separate, nonce/account-bound capability proof from THIS existing EA.
// Only used by a guarded V2 router when all backend V2 checks are installed.
void WriteOptionCAdaptiveCapability()
{
 string name="ABUTRON_OPTIONC_DERIV_CAPABILITY_V2_"+gNonce+".txt";
 int h=FileOpen(name,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE)return;
 // Old V2/3 proof MUST NOT claim it can authorize new orders.
 int approved=0;
 string body="APEX_OPTIONC_ADAPTIVE_CAPABILITY_V2\r\n"+gNonce+"\r\n"+
    gLogin+"\r\n"+gServer+"\r\nDERIV\r\n"+
    IntegerToString((long)TimeGMT())+"\r\n"+IntegerToString(approved)+
    "\r\n0.10\r\n20\r\n";
 FileWriteString(h,body);FileFlush(h);FileClose(h);
}

void WriteReadiness()
{
 string base=gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\nDERIV_DEMO\r\n"+
  IntegerToString((long)TimeGMT())+"\r\n"+IntegerToString(OrdersTotal())+"\r\n"+
  IntegerToString(PositionsTotal())+"\r\n"+
  IntegerToString((long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))+"\r\n"+
  IntegerToString((long)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+"\r\n";
 int h=FileOpen(gReady,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h!=INVALID_HANDLE)
 {
  FileWriteString(h,"APEX_NATIVE_BRIDGE_READY_V2\r\n"+base+
                    IntegerToString((long)0)+"\r\n");
  FileFlush(h);FileClose(h);
 }
 // Distinct capability proof: only a multi-position-capable V2 EA writes this.
 // The original V2 and V1 readiness records remain backward compatible.
 string multi="ABUTRON_APEX_BRIDGE_READY_V3_"+gNonce+".txt";
 int mh=FileOpen(multi,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(mh!=INVALID_HANDLE)
 {
  FileWriteString(mh,"APEX_NATIVE_BRIDGE_READY_V3\r\n"+base+
    IntegerToString((long)0)+"\r\n");
  FileFlush(mh);FileClose(mh);
 }
 // Exact new policy marker; only the $50/$100 build emits this proof.
 // Used by the Python new-order gate; old V2 does not write this file.
 string usdproof="ABUTRON_APEX_V2_USD_50_100_"+gNonce+".txt";
 int ph=FileOpen(usdproof,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(ph!=INVALID_HANDLE)
 {
  FileWriteString(ph,"APEX_NATIVE_BRIDGE_USD_50_100_V1\r\n"+base+
    IntegerToString((long)0)+"\r\n");
  FileFlush(ph);FileClose(ph);
 }
 // Keep the existing production dashboard/preflight V1 reader compatible.
 string legacy="ABUTRON_APEX_BRIDGE_READY_V1_"+gNonce+".txt";
 h=FileOpen(legacy,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h!=INVALID_HANDLE)
 {
  FileWriteString(h,"APEX_NATIVE_BRIDGE_READY_V1\r\n"+base);
  FileFlush(h);FileClose(h);
 }
}

// A fresh account-bound marker lets the read-only auditor verify the exact
// instrumented EA is running before any model becomes eligible for an order.
void WriteExecutionAuditReady()
{
 if(!VerifiedDemoAccount())return;
 string file="ABUTRON_EXECUTION_AUDIT_V1_"+gNonce+".txt";
 int h=FileOpen(file,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE)return;
 string body="ABUTRON_EXECUTION_AUDIT_READY_V1\r\n"+gNonce+"\r\n"+
    gLogin+"\r\n"+gServer+"\r\n"+
    IntegerToString((long)TimeGMT())+"\r\n"+
    IntegerToString((long)EnableNativeDemoOrders)+"\r\n"+
    IntegerToString((long)EnableAdaptiveEquityV2)+"\r\n"+
    IntegerToString((long)AdaptiveV2ReconcilerApproved)+"\r\n";
 FileWriteString(h,body);FileFlush(h);FileClose(h);
}

// Authentic broker-native bid/ask sampling every two seconds on the same
// isolated DEMO terminal. These are sampled quotes, NOT all CopyTicks events.
void AuditSpreadPulse()
{
 if(!VerifiedDemoAccount())return;
 string symbols[3]={"Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0"};
 static long lastTimeMsc[3]={0,0,0};
 string day=TimeToString(TimeGMT(),TIME_DATE);
 StringReplace(day,".","");
 string name=DIR_AUDIT+"broker-spread-"+day+".tsv";
 for(int i=0;i<3;i++)
 {
   MqlTick tick;
   if(!SymbolInfoTick(symbols[i],tick)||tick.time_msc<=0||
      tick.time_msc<=lastTimeMsc[i]||tick.bid<=0||tick.ask<tick.bid)continue;
   double spreadBps=(tick.ask-tick.bid)*20000.0/(tick.ask+tick.bid);
   int h=FileOpen(name,FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ,0,CP_UTF8);
   if(h==INVALID_HANDLE)continue;
   FileSeek(h,0,SEEK_END);
   string line=IntegerToString((long)TimeGMT())+"\t"+
       IntegerToString((long)GetTickCount64())+"\t"+symbols[i]+"\t"+
       IntegerToString((long)tick.time_msc)+"\t"+
       DoubleToString(tick.bid,10)+"\t"+DoubleToString(tick.ask,10)+"\t"+
       DoubleToString(spreadBps,8)+"\r\n";
   uint written=FileWriteString(h,line);
   FileFlush(h);FileClose(h);
   if(written==StringLen(line))lastTimeMsc[i]=tick.time_msc;
 }
}

// Execution evidence, independent of native receipts and risk policy.
// Every file is account-bound and keyed by the immutable signal identifier.
// All audit failures before OrderSend block the order; no audit code sends orders.
bool AuditRequestBeforeSend(string key,string sym,string side,
                            const MqlTradeRequest &req,const MqlTick &tick)
{
 if(!IsHex64(key) || !VerifiedDemoAccount())return false;
 string name=DIR_AUDIT+key+".request.txt";
 if(FileIsExist(name))return false;
 int h=FileOpen(name,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE)return false;
 string body="ABUTRON_NATIVE_REQUEST_AUDIT_V1\r\n"+key+"\r\n"+gNonce+"\r\n"+
   gLogin+"\r\n"+gServer+"\r\n"+sym+"\r\n"+side+"\r\n"+
   DoubleToString(req.volume,8)+"\r\n"+DoubleToString(req.price,10)+"\r\n"+
   DoubleToString(req.sl,10)+"\r\n"+DoubleToString(req.tp,10)+"\r\n"+
   DoubleToString(tick.bid,10)+"\r\n"+DoubleToString(tick.ask,10)+"\r\n"+
   IntegerToString((long)tick.time_msc)+"\r\n"+
   IntegerToString((long)TimeGMT())+"\r\n"+
   IntegerToString((long)GetTickCount64())+"\r\n"+
   IntegerToString((long)req.type_filling)+"\r\n"+
   IntegerToString((long)req.deviation)+"\r\n";
 uint written=FileWriteString(h,body);
 FileFlush(h);FileClose(h);
 return written==StringLen(body) && FileIsExist(name);
}
// Capture raw OrderSend result with the actual native start time (UTC seconds
// + monotonic milliseconds); no quote-based substitute for true slippage.
void AuditSendResult(string key,bool sent,const MqlTradeResult &res,
                     datetime sendUtc,ulong sendMono)
{
 if(!IsHex64(key))return;
 string name=DIR_AUDIT+key+".result.txt";
 if(FileIsExist(name))return;
 int h=FileOpen(name,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE){Print("ABUTRON_AUDIT_RESPONSE_OPEN_FAILED ",GetLastError());return;}
 string body="ABUTRON_NATIVE_RESULT_AUDIT_V1\r\n"+key+"\r\n"+gNonce+"\r\n"+
   gLogin+"\r\n"+gServer+"\r\n"+
   IntegerToString((long)sendUtc)+"\r\n"+IntegerToString((long)sendMono)+"\r\n"+
   IntegerToString((long)TimeGMT())+"\r\n"+IntegerToString((long)GetTickCount64())+"\r\n"+
   IntegerToString((long)sent)+"\r\n"+IntegerToString((long)res.retcode)+"\r\n"+
   IntegerToString((long)res.request_id)+"\r\n"+
   IntegerToString((long)res.order)+"\r\n"+IntegerToString((long)res.deal)+"\r\n"+
   DoubleToString(res.price,10)+"\r\n"+
   DoubleToString(res.bid,10)+"\r\n"+
   DoubleToString(res.ask,10)+"\r\n";
 FileWriteString(h,body);FileFlush(h);FileClose(h);
}
// Written only after a *separate* broker history deal and matching open
// protected position are observed, not from a provisional EA acknowledgement.
void AuditBrokerProtection(string key,string sym,string side,long order,long deal,
                           long pos,double volume,double entry,double sl,double tp)
{
 if(!IsHex64(key)||pos<=0||sl<=0||tp<=0)return;
 string name=DIR_AUDIT+key+".protected.txt";
 if(FileIsExist(name))return;
 if(!HistoryDealSelect((ulong)deal))return;
 if(HistoryDealGetInteger((ulong)deal,DEAL_POSITION_ID)!=pos)return;
 double price=HistoryDealGetDouble((ulong)deal,DEAL_PRICE);
 long fillMsc=HistoryDealGetInteger((ulong)deal,DEAL_TIME_MSC);
 if(price<=0||fillMsc<=0)return;
 long orderSetupMsc=0,orderDoneMsc=0;
 if(HistoryOrderSelect((ulong)order))
 {
  orderSetupMsc=HistoryOrderGetInteger((ulong)order,ORDER_TIME_SETUP_MSC);
  orderDoneMsc=HistoryOrderGetInteger((ulong)order,ORDER_TIME_DONE_MSC);
 }
 int h=FileOpen(name,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE)return;
 string body="ABUTRON_NATIVE_PROTECTED_AUDIT_V1\r\n"+key+"\r\n"+gNonce+"\r\n"+
   gLogin+"\r\n"+gServer+"\r\n"+sym+"\r\n"+side+"\r\n"+
   IntegerToString(order)+"\r\n"+IntegerToString(deal)+"\r\n"+
   IntegerToString(pos)+"\r\n"+DoubleToString(volume,8)+"\r\n"+
   DoubleToString(price,10)+"\r\n"+IntegerToString(fillMsc)+"\r\n"+
   DoubleToString(entry,10)+"\r\n"+DoubleToString(sl,10)+"\r\n"+
   DoubleToString(tp,10)+"\r\n"+
   IntegerToString(orderSetupMsc)+"\r\n"+
   IntegerToString(orderDoneMsc)+"\r\n"+
   DoubleToString(HistoryDealGetDouble((ulong)deal,DEAL_COMMISSION),8)+"\r\n"+
   DoubleToString(HistoryDealGetDouble((ulong)deal,DEAL_FEE),8)+"\r\n"+
   DoubleToString(HistoryDealGetDouble((ulong)deal,DEAL_SWAP),8)+"\r\n"+
   IntegerToString((long)TimeGMT())+"\r\nOPEN_PROTECTED\r\n";
 FileWriteString(h,body);FileFlush(h);FileClose(h);
}

// Immutable receipt per signal. Never overwrites an earlier result.
void Receipt(string key,string status,string reason,long order=0,long deal=0)
{
 if(!IsHex64(key))return;
 string file=DIR_RECEIPTS+key+".txt";
 if(FileIsExist(file))return;
 int h=FileOpen(file,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(h==INVALID_HANDLE){Print("APEX_IMMUTABLE_RECEIPT_ERROR ",GetLastError());return;}
 string body="APEX_NATIVE_V2\r\n"+key+"\r\n"+status+"\r\n"+reason+"\r\n"+
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

// Native Option C V2: broker-equity budget <=0.10% per new position.
// Requires a trusted versioned request from the EXISTING single-writer router.
// The legacy fixed-$50/$100 path does not call this function.
bool NativeAdaptivePlan(string sym,bool buy,double bid,double ask,
                        double &vol,double &sl,double &tp,
                        double &stopRisk,double &targetCash)
{
 double equity=AccountInfoDouble(ACCOUNT_EQUITY);
 if(!MathIsValidNumber(equity)||equity<=0.0||OrdersTotal()!=0)return false;
 MqlRates bars[30];
 if(CopyRates(sym,PERIOD_M5,1,30,bars)!=30)return false;
 if(TimeCurrent()-(long)bars[29].time>630)return false;
 double recent=0.0,prior=0.0,low=1.0e99,high=0.0;
 for(int i=1;i<30;i++)
 {
  if(bars[i].high<=0.0||bars[i].low<=0.0||bars[i-1].close<=0.0 ||
     bars[i].high<bars[i].low)return false;
  double tr=MathMax(bars[i].high-bars[i].low,
          MathMax(MathAbs(bars[i].high-bars[i-1].close),
                  MathAbs(bars[i].low-bars[i-1].close)));
  if(i>=16&&i<=22)prior+=tr;
  if(i>=23)recent+=tr;
  if(i>=18){low=MathMin(low,bars[i].low);high=MathMax(high,bars[i].high);}
 }
 double atr=(prior+recent)/14.0,accel=recent/MathMax(prior,0.000000001);
 if(!MathIsValidNumber(atr)||atr<=0)return false;
 double entry=buy?ask:bid;
 double rawStop=buy?MathMin(low-0.35*atr,entry-1.2*atr):
                    MathMax(high+0.35*atr,entry+1.2*atr);
 double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
 if(tick<=0)tick=SymbolInfoDouble(sym,SYMBOL_POINT);
 if(!MathIsValidNumber(tick)||tick<=0)return false;
 int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
 sl=NormalizeDouble((buy?MathFloor(rawStop/tick+1e-9):
                         MathCeil(rawStop/tick-1e-9))*tick,digits);
 if(sl<=0||((buy&&sl>=entry)||(!buy&&sl<=entry)))return false;
 double distance=MathAbs(entry-sl);
 double rr=(accel>=1.6?1.5:(accel>=1.3?1.75:(accel<=.75?2.25:2.0)));
 tp=NormalizeDouble((buy?
     MathFloor((entry+rr*distance)/tick+1e-9):
     MathCeil((entry-rr*distance)/tick-1e-9))*tick,digits);
 if(tp<=0||((buy&&tp<=entry)||(!buy&&tp>=entry)))return false;
 // Spread and broker stop/freeze distances are enforced on the close-side.
 if(ask<bid || (ask-bid)/distance>0.15)return false;
 double point=SymbolInfoDouble(sym,SYMBOL_POINT);
 double minstop=MathMax((double)SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL),
                        (double)SymbolInfoInteger(sym,SYMBOL_TRADE_FREEZE_LEVEL))*point;
 if((buy&&(bid-sl<minstop||tp-bid<minstop))||
    (!buy&&(sl-ask<minstop||ask-tp<minstop)))return false;
 // Broker-native gross risk for every position on this account, all symbols.
 double existing=0.0;
 for(int k=0;k<PositionsTotal();k++)
 {
  ulong ticket=PositionGetTicket(k);
  if(ticket==0)return false;
  string name=PositionGetString(POSITION_SYMBOL);
  long type=PositionGetInteger(POSITION_TYPE);
  double qty=PositionGetDouble(POSITION_VOLUME);
  double opened=PositionGetDouble(POSITION_PRICE_OPEN);
  double stop=PositionGetDouble(POSITION_SL);
  double target=PositionGetDouble(POSITION_TP);
  if(qty<=0||opened<=0||stop<=0||target<=0||
     (type!=POSITION_TYPE_BUY&&type!=POSITION_TYPE_SELL)||
     !((type==POSITION_TYPE_BUY&&stop<opened&&opened<target)||
       (type==POSITION_TYPE_SELL&&target<opened&&opened<stop)))return false;
  double cash=0.0;
  if(!OrderCalcProfit(type==POSITION_TYPE_BUY?ORDER_TYPE_BUY:ORDER_TYPE_SELL,
                      name,qty,opened,stop,cash)||!MathIsValidNumber(cash))return false;
  existing+=MathMax(0.0,-cash);
 }
 double headroom=MathMax(0.0,equity*0.20-existing);
 double maxBudget=MathMin(equity*0.001,headroom);
 // 15% reservation for estimated fees and slippage. Gaps remain unbounded.
 double budget=.85*maxBudget;
 if(budget<=0||!MathIsValidNumber(budget))return false;
 double minv=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
 double maxv=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
 double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
 if(minv<=0||maxv<minv||step<=0)return false;
 ENUM_ORDER_TYPE direction=buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
 double minCash=0.0;
 if(!OrderCalcProfit(direction,sym,minv,entry,sl,minCash)||minCash>=0)return false;
 double rawLots=minv*budget/(-minCash);
 if(rawLots<minv)return false; // never force the minimum lot over risk.
 vol=NormalizeDouble(minv+MathFloor((rawLots-minv)/step+1e-9)*step,8);
 if(vol<minv||vol>maxv)return false;
 double projected=0.0,profit=0.0,margin=0.0;
 if(!OrderCalcProfit(direction,sym,vol,entry,sl,projected)||
    !OrderCalcProfit(direction,sym,vol,entry,tp,profit)||
    !OrderCalcMargin(direction,sym,vol,entry,margin))return false;
 stopRisk=-projected;targetCash=profit;
 if(stopRisk<=0||stopRisk>budget+0.005 ||
    targetCash/stopRisk<1.50 ||
    !MathIsValidNumber(margin)||margin<0||
    margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.10)return false;
 return true;
}

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
      !((MathAbs(-loss-50.0)<=2.0 && MathAbs(gain-100.0)<=2.0) ||
        (MathAbs(-loss-10.0)<=2.0 && MathAbs(gain-20.0)<=2.0) ||
        OptionCAnyVerifiedPosition(sym,buy?"BUY":"SELL",vol,entry,sl,tp)))
      return false;
 }
 return true;
}


// ==================== APEX 1.1.0 V4 NATIVE ADAPTER ====================
// This is the *existing* EA, preserving V3 adaptive risk and broker audit.
// DO NOT allow production V4 until a trusted root-owned, independently
// authenticated activation supervisor is present. Local permission flags,
// MQL5 input booleans or an EA-writable ON file are NOT authorization.
//
// The native V4 supervisor must atomically fence the CRM account revision,
// concurrent OFF acknowledgements, customer risk inventory and in-flight
// unknown orders. Merely checking an ON file before OrderSend has an OFF race.
// No safe supervisor protocol has yet been deployed; always fail closed.
bool V4RevisionAuthorized(string signalKey,long crmRevision)
{
 if(!IsHex64(signalKey)||crmRevision<1)return false;
 return false; // FAIL CLOSED until independent supervisor handshake exists.
}

// V4 only supports the five DERIV volatility symbols from the APEX M5 journal.
bool V4ApprovedSymbol(string sym)
{
 return sym=="Volatility 10 Index.0"||sym=="Volatility 25 Index.0"||
        sym=="Volatility 50 Index.0"||sym=="Volatility 75 Index.0"||
        sym=="Volatility 100 Index.0";
}

bool V4NativeNumbers(string volumeString,string stopString,string takeString,
                     double &volume,double &stop,double &take)
{
 volume=StringToDouble(volumeString);
 stop=StringToDouble(stopString);
 take=StringToDouble(takeString);
 return StringLen(volumeString)>0 && StringLen(stopString)>0 &&
        StringLen(takeString)>0 && MathIsValidNumber(volume) &&
        MathIsValidNumber(stop) && MathIsValidNumber(take) &&
        volume>0.0 && stop>0.0 && take>0.0;
}

// V4 request: protocol, nonce, signal ID, MT5 login, server, symbol,
// BUY/SELL, explicit broker lots, explicit SL, explicit TP,
// effective CRM revision, expiry UTC seconds, SEND_DEMO_ONLY.
// Never convert a V4 request into legacy V3 AUTO/STRUCTURE_M5.
void HandleV4Request()
{
 if(!FileIsExist(V4_REQ))return;
 int h=FileOpen(V4_REQ,FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ,0,CP_UTF8);
 if(h==INVALID_HANDLE)return;
 string version=FileReadString(h),nonce=FileReadString(h),key=FileReadString(h);
 string login=FileReadString(h),server=FileReadString(h),symbol=FileReadString(h);
 string side=FileReadString(h),lotsText=FileReadString(h);
 string slText=FileReadString(h),tpText=FileReadString(h);
 string revisionText=FileReadString(h),expiresText=FileReadString(h);
 string mode=FileReadString(h);
 bool exactFields=FileIsEnding(h);
 FileClose(h);
 if(!IsHex64(key)||!exactFields)return;
 // Never overwrite a consumed request or repeat an uncertain outcome.
 string archive=V4_CONSUMED_DIR+"apex11-v4-"+key+".consumed";
 if(FileIsExist(archive)||FileIsExist(DIR_RECEIPTS+key+".txt"))return;
 if(!FileMove(V4_REQ,0,archive,0))return;
 if(version!=V4_MAGIC||nonce!=gNonce||login!=gLogin||server!=gServer||
    side!="BUY"&&side!="SELL"||mode!="SEND_DEMO_ONLY"||
    !V4ApprovedSymbol(symbol)||!VerifiedDemoAccount()||
    !StringEndsWith(login,"6207"))
 {Receipt(key,"BLOCKED","V4_DEMO_ACCOUNT_OR_PROTOCOL_DENIED");return;}
 long revision=(long)StringToInteger(revisionText);
 if(revision<1||revisionText!=IntegerToString(revision))
 {Receipt(key,"BLOCKED","V4_CLIENT_ACTIVATION_REVISION_INVALID");return;}
 long expires=(long)StringToInteger(expiresText);
 if(expiresText!=IntegerToString(expires)||
    expires<(long)TimeGMT()||expires>(long)TimeGMT()+12)
 {Receipt(key,"BLOCKED","V4_SIGNAL_EXPIRED");return;}
 if(FileIsExist(REQ)||!EnableNativeDemoOrders||!EnableApex11V4DemoOrders||
    !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)||
    !MQLInfoInteger(MQL_TRADE_ALLOWED)||
    !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
 {Receipt(key,"BLOCKED","V4_EXECUTION_SWITCH_OR_LEGACY_PENDING");return;}
 if(!V4RevisionAuthorized(key,revision))
 {Receipt(key,"BLOCKED","V4_ROOT_ACTIVATION_SUPERVISOR_NOT_ATTESTED");return;}
 if(!PortfolioCanAdd(symbol)||!SymbolSelect(symbol,true))
 {Receipt(key,"BLOCKED","V4_PORTFOLIO_OR_SYMBOL_DENIED");return;}
 double volume=0.0,sl=0.0,tp=0.0;
 if(!V4NativeNumbers(lotsText,slText,tpText,volume,sl,tp))
 {Receipt(key,"BLOCKED","V4_INVALID_NATIVE_SIZE_OR_STOPS");return;}
 MqlTick tick;
 if(!SymbolInfoTick(symbol,tick)||tick.time_msc<=0||
    tick.ask<=0.0||tick.bid<=0.0||tick.bid>tick.ask)
 {Receipt(key,"BLOCKED","V4_AUTHENTIC_BROKER_TICK_MISSING");return;}
 bool buy=(side=="BUY");
 double entry=buy?tick.ask:tick.bid;
 double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
 double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
 double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
 if(minv<=0.0||maxv<minv||step<=0.0||volume<minv||volume>maxv||
    MathAbs((volume-minv)/step-MathRound((volume-minv)/step))>0.00001||
    (buy&&!(sl<entry&&entry<tp))||(!buy&&!(tp<entry&&entry<sl)))
 {Receipt(key,"BLOCKED","V4_VOLUME_STEP_OR_STOP_GEOMETRY");return;}
 double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
 double closeSide=buy?tick.bid:tick.ask;
 double minstop=MathMax((double)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL),
                        (double)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL))*point;
 if(point<=0.0||(buy&&(closeSide-sl<minstop||tp-closeSide<minstop))||
    (!buy&&(sl-closeSide<minstop||closeSide-tp<minstop)))
 {Receipt(key,"BLOCKED","V4_BROKER_STOP_OR_FREEZE_DISTANCE");return;}
 ENUM_ORDER_TYPE type=buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
 double stopPnl=0.0,targetPnl=0.0,margin=0.0;
 if(!OrderCalcProfit(type,symbol,volume,entry,sl,stopPnl)||
    !OrderCalcProfit(type,symbol,volume,entry,tp,targetPnl)||
    !OrderCalcMargin(type,symbol,volume,entry,margin)||
    !MathIsValidNumber(stopPnl)||!MathIsValidNumber(targetPnl)||
    !MathIsValidNumber(margin)||stopPnl>=0.0||targetPnl<=0.0||
    margin<0.0||margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.10)
 {Receipt(key,"BLOCKED","V4_BROKER_RISK_OR_MARGIN_INVALID");return;}
 double grossRisk=-stopPnl;
 double equity=AccountInfoDouble(ACCOUNT_EQUITY);
 if(equity<=0.0||grossRisk>equity*0.001*0.85||
    targetPnl/grossRisk<1.50)
 {Receipt(key,"BLOCKED","V4_PER_TRADE_RISK_OR_REWARD_DENIED");return;}
 MqlTradeRequest req={};MqlTradeResult result={};MqlTradeCheckResult checked={};
 req.action=TRADE_ACTION_DEAL;req.symbol=symbol;req.volume=volume;
 req.type=type;req.price=entry;req.sl=sl;req.tp=tp;req.magic=MAGIC;
 req.deviation=15;req.type_time=ORDER_TIME_GTC;
 req.comment="APEX11 DERIV DEMO";
 int fill=(int)SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
 if((fill & SYMBOL_FILLING_IOC)!=0)req.type_filling=ORDER_FILLING_IOC;
 else if((fill & SYMBOL_FILLING_FOK)!=0)req.type_filling=ORDER_FILLING_FOK;
 else req.type_filling=ORDER_FILLING_RETURN;
 ResetLastError();
 bool orderChecked=OrderCheck(req,checked);
 if(!orderChecked||(checked.retcode!=0&&checked.retcode!=TRADE_RETCODE_DONE))
 {Receipt(key,"BLOCKED","V4_ORDERCHECK_REJECTED_"+IntegerToString((long)checked.retcode));return;}
 if(!OptionCWriteIntent(key,symbol,side,equity,
       MathMin(equity*0.001,grossRisk+0.02),volume,entry,sl,tp))
 {Receipt(key,"BLOCKED","V4_RISK_INTENT_NOT_DURABLE");return;}
 if(!AuditRequestBeforeSend(key,symbol,side,req,tick))
 {Receipt(key,"BLOCKED","V4_ORDER_AUDIT_NOT_DURABLE");return;}
 // The trusted supervisor must fence OFF while an in-flight send is
 // unresolved; without such a service this guard always blocks.
 if(!V4RevisionAuthorized(key,revision))
 {Receipt(key,"BLOCKED","V4_AUTHORIZATION_EXPIRED_BEFORE_SEND");return;}
 datetime sentUtc=TimeGMT();ulong sentMono=GetTickCount64();
 bool sent=OrderSend(req,result); // EXACTLY ONE attempted send; no retries
 AuditSendResult(key,sent,result,sentUtc,sentMono);
 if(!sent||(result.retcode!=TRADE_RETCODE_DONE&&
           result.retcode!=TRADE_RETCODE_DONE_PARTIAL)||
    result.order<=0||result.deal<=0)
 {Receipt(key,"UNKNOWN","V4_BROKER_SEND_UNCERTAIN_"+IntegerToString((long)result.retcode),
          (long)result.order,(long)result.deal);return;}
 Receipt(key,"ACK","V4_BROKER_ACK_POSITION_STILL_UNVERIFIED",
         (long)result.order,(long)result.deal);
}

// Helper avoids relying on unavailable StringEndsWith in older MetaEditor.
bool StringEndsWith(string value,string suffix)
{
 int a=StringLen(value),b=StringLen(suffix);
 return a>=b && StringSubstr(value,a-b,b)==suffix;
}

// ================= END APEX V4 NATIVE ADAPTER ===================

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
 bool adaptive=(ver=="APEX_NATIVE_ADAPTIVE_ORDER_V3");
 if(((ver!="APEX_NATIVE_ORDER_V2")&&!adaptive)||(nonce!=gNonce)||(login!=gLogin)||(server!=gServer)||
    ((side!="BUY")&&(side!="SELL"))||(mode!="SEND_DEMO_ONLY")||(!ApprovedSymbol(sym))||(!VerifiedDemoAccount()))
 {Receipt(key,"BLOCKED","IDENTITY_OR_BROKER_DENIED");return;}
 long expire=(long)StringToInteger(expire_s);
 if(expire<(long)TimeGMT()||expire>(long)TimeGMT()+20)
 {Receipt(key,"BLOCKED","EXPIRED_SIGNAL");return;}
 if(!EnableNativeDemoOrders||!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)||
    !MQLInfoInteger(MQL_TRADE_ALLOWED)||!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
 {Receipt(key,"BLOCKED","ACCOUNT_OR_EA_AUTOTRADING_OFF");return;}
 if(adaptive&&(!EnableAdaptiveEquityV2||!AdaptiveV2ReconcilerApproved||
    lots_s!="AUTO"||sl_s!="0.10"||tp_s!="STRUCTURE_M5"))
 {Receipt(key,"BLOCKED","ADAPTIVE_V2_ACCOUNT_RECONCILER_OR_POLICY_NOT_READY");return;}
 if(!PortfolioCanAdd(sym))
 {Receipt(key,"BLOCKED","PORTFOLIO_SYMBOL_OR_RISK_CAPACITY_DENIED");return;}
 if(!SymbolSelect(sym,true))
 {Receipt(key,"BLOCKED","SYMBOL_NOT_AVAILABLE");return;}
 double vol=(adaptive?0.0:StringToDouble(lots_s));
 double minv=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN),maxv=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
 double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
 if((!adaptive&&(!MathIsValidNumber(vol)||vol<minv||vol>maxv))||step<=0||
    (!adaptive&&MathAbs((vol-minv)/step-MathRound((vol-minv)/step))>0.00001)||
    (!adaptive&&(MathAbs(StringToDouble(sl_s)-50.0)>0.001||
                 MathAbs(StringToDouble(tp_s)-100.0)>0.001)))
 {Receipt(key,"BLOCKED","INVALID_VOLUME_OR_USD_STOP_POLICY");return;}
 MqlTick tick;
 if(!SymbolInfoTick(sym,tick)||tick.ask<=0||tick.bid<=0)
 {Receipt(key,"BLOCKED","BROKER_TICK_NOT_AVAILABLE");return;}
 bool buy=(side=="BUY");
 double entry=(buy?tick.ask:tick.bid),sl=0.0,tp=0.0,loss=0.0,gain=0.0;
 if(adaptive?
    !NativeAdaptivePlan(sym,buy,tick.bid,tick.ask,vol,sl,tp,loss,gain):
    (!DollarPrice(sym,buy,vol,entry,50.0,false,sl,loss)||
     !DollarPrice(sym,buy,vol,entry,100.0,true,tp,gain)))
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
 req.deviation=15;req.type_time=ORDER_TIME_GTC;req.comment="APEX DEMO NATIVE";
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
 if(adaptive && !OptionCWriteIntent(key,sym,side,
       AccountInfoDouble(ACCOUNT_EQUITY),
       MathMin(AccountInfoDouble(ACCOUNT_EQUITY)*0.001,loss+0.02),
       vol,entry,sl,tp))
 {Receipt(key,"BLOCKED","ADAPTIVE_NATIVE_RISK_RECORD_NOT_DURABLE");return;}
 if(!AuditRequestBeforeSend(key,sym,side,req,tick))
 {Receipt(key,"BLOCKED","EXECUTION_AUDIT_REQUEST_NOT_DURABLE");return;}
 datetime auditSendUtc=TimeGMT();
 ulong auditSendMono=GetTickCount64();
 bool sent=OrderSend(req,res);
 AuditSendResult(key,sent,res,auditSendUtc,auditSendMono);
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
      if(geometry&&((MathAbs(loss-50.0)<=2.0&&MathAbs(gain-100.0)<=2.0)||
                   (MathAbs(loss-10.0)<=2.0&&MathAbs(gain-20.0)<=2.0)||
                   OptionCVerifyOpenPosition(key,sym,side,volume,entry,sl,tp,loss,gain)))
         state="OPEN_PROTECTED";
      else state="OPEN_UNPROTECTED";
   }
   else state="OPEN_UNPROTECTED";
   if(state=="OPEN_PROTECTED")
      AuditBrokerProtection(key,sym,side,order,deal,position_id,volume,entry,sl,tp);
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
 string text="APEX_BROKER_POSITION_V2\r\n"+key+"\r\n"+gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\n"+
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
    if(header!="APEX_NATIVE_V2"||kind!="ACK"||
       filename!=key+".txt"||!IsHex64(key)||
       nonce!=gNonce||login!=gLogin||server!=gServer)continue;
    UpdateEvidenceFor(key,(long)StringToInteger(order_s),(long)StringToInteger(deal_s));
 } while(FileFindNext(h,filename));
 FileFindClose(h);
}

int OnInit()
{
 if(!VerifiedNativeFeed(true))
 {Print("APEX_V2_FRESH_NATIVE_DERIV_DEMO_FEED_REQUIRED");return INIT_FAILED;}
 FolderCreate("ABUTRON");FolderCreate("ABUTRON\\receipts");FolderCreate("ABUTRON\\evidence");FolderCreate("ABUTRON\\execution-audit");
 gReady="ABUTRON_APEX_BRIDGE_READY_V2_"+gNonce+".txt";
 WriteReadiness();WriteExecutionAuditReady();EventSetTimer(2);
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
 WriteReadiness();WriteOptionCAdaptiveCapability();WriteExecutionAuditReady();UpdateEvidence();
 // LEGACY_V2_V3_CONSUMPTION_DISABLED: do not call HandleRequest().
 HandleV4Request();
 AuditSpreadPulse();
}
