// ABUTRON FP Markets account history - read-only indicator, never submits orders.
// MQL5 broker API evidence: PositionsTotal, OrdersTotal, HistorySelect, HistoryDealsTotal.
// USD LIVE 86076364 nonce/owner/server/login bound; no order APIs.
#property strict
#property copyright "ABUTRON"
#property version "1.20"
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots 0
string FP_H_NONCE="",FP_H_OWNER="",FP_H_SERVER="",FP_H_LOGIN="",FP_H_MODE="";
bool FP_H_READY=false;
const int MAX_DEALS=10000;
const int MAX_POSITIONS=500;
const int MAX_ORDERS=500;
bool IsHex32(const string value){
 if(StringLen(value)!=32)return false;
 for(int i=0;i<32;i++){
  ushort x=StringGetCharacter(value,i);
  if(!((x>=48 && x<=57)||(x>=97 && x<=102)))return false;
 }
 return true;
}
bool IsDigits(const string v){
 if(StringLen(v)<4 || StringLen(v)>20)return false;
 for(int i=0;i<StringLen(v);i++){
  ushort x=StringGetCharacter(v,i);
  if(x<48 || x>57)return false;
 }
 return true;
}
bool AccountVerified(){
 string company=AccountInfoString(ACCOUNT_COMPANY);
 StringToLower(company);
 return TerminalInfoInteger(TERMINAL_CONNECTED) &&
   AccountInfoInteger(ACCOUNT_LOGIN)==86076364 &&
    AccountInfoInteger(ACCOUNT_LOGIN)==StringToInteger(FP_H_LOGIN) &&
   AccountInfoString(ACCOUNT_SERVER)==FP_H_SERVER &&
   AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL &&
   AccountInfoString(ACCOUNT_CURRENCY)=="USD" &&
   (StringFind(company,"fp markets")>=0 || StringFind(company,"fpmarkets")>=0 ||
    company=="first prudential markets limited");
}
string Money(const double x){return MathIsValidNumber(x)?DoubleToString(x,6):"nan";}
string SafeText(string v){
 StringReplace(v,"\t"," ");StringReplace(v,"\r"," ");StringReplace(v,"\n"," ");
 return StringSubstr(v,0,80);
}
string Int(const long n){return IntegerToString(n);}
void ExportHistory(){
 if(!FP_H_READY || !AccountVerified())return;
 // History window must advance on market-closed days; TimeCurrent is last-tick time.
 // TimeTradeServer is local-clock-estimated; fail closed unless native offset is bounded.
 datetime native_utc=TimeGMT();
 datetime last_tick=TimeCurrent();
 datetime now=TimeTradeServer();
 long offset=(long)(now-native_utc);
 if(native_utc<=0 || now<=0 || last_tick<=0 || now<last_tick ||
    MathAbs((double)(offset-7200))>30.0){
  Print("FP_HISTORY_BROKER_CLOCK_OFFSET_UNVERIFIED");return;
 }
 datetime from=now-(datetime)(90*86400);
 if(!HistorySelect(from,now+60)){
  Print("FP_HISTORY_BROKER_HISTORYSELECT_FAILED");
  return;
 }
 int pcount=PositionsTotal(),ocount=OrdersTotal(),dcount=HistoryDealsTotal();
 if(pcount<0 || pcount>MAX_POSITIONS || ocount<0 || ocount>MAX_ORDERS ||
    dcount<0 || dcount>MAX_DEALS){
  Print("FP_HISTORY_BROKER_LIMIT_EXCEEDED");
  return;
 }
 string file="ABUTRON_FP_ACCOUNT_HISTORY_V1_"+FP_H_NONCE+".txt";
 string staging=file+".tmp";
 int f=FileOpen(staging,FILE_WRITE|FILE_TXT|FILE_ANSI);
 if(f==INVALID_HANDLE){Print("FP_HISTORY_WRITE_FAILED");return;}
 long utc=(long)TimeGMT();
 long server_offset=(long)(TimeTradeServer()-TimeGMT());
 FileWriteString(f,"ABUTRON_FP_ACCOUNT_HISTORY_V1\n"+FP_H_NONCE+"\n"+FP_H_OWNER+"\n"+
   FP_H_SERVER+"\n"+FP_H_LOGIN+"\n"+FP_H_MODE+"\n"+
   Int(utc)+"\n"+Int(server_offset)+"\nUSD\n"+
   Money(AccountInfoDouble(ACCOUNT_BALANCE))+"\n"+
   Money(AccountInfoDouble(ACCOUNT_EQUITY))+"\n"+
   Money(AccountInfoDouble(ACCOUNT_MARGIN))+"\n"+
   Money(AccountInfoDouble(ACCOUNT_MARGIN_FREE))+"\n"+
   Money(AccountInfoDouble(ACCOUNT_PROFIT))+"\n"+
   Int(pcount)+"\n"+Int(ocount)+"\n"+Int(dcount)+"\n"+
   Int((long)from)+"\n"+Int((long)now+60)+"\n"+
   "BROKER_NATIVE_NO_ORDER_FUNCTIONS\n");
 int np=0,no=0,nd=0;
 for(int i=0;i<pcount && !IsStopped();i++){
  if(!AccountVerified())break;
  ulong ticket=PositionGetTicket(i);
  if(ticket==0)continue;
  int type=(int)PositionGetInteger(POSITION_TYPE);
  FileWriteString(f,"P\t"+Int((long)ticket)+"\t"+
   SafeText(PositionGetString(POSITION_SYMBOL))+"\t"+Int(type)+"\t"+
   Money(PositionGetDouble(POSITION_VOLUME))+"\t"+
   Money(PositionGetDouble(POSITION_PRICE_OPEN))+"\t"+
   Money(PositionGetDouble(POSITION_PRICE_CURRENT))+"\t"+
   Money(PositionGetDouble(POSITION_SL))+"\t"+
   Money(PositionGetDouble(POSITION_TP))+"\t"+
   Money(PositionGetDouble(POSITION_PROFIT))+"\t"+
   Money(PositionGetDouble(POSITION_SWAP))+"\t"+
   Int(PositionGetInteger(POSITION_TIME))+"\t"+
   Int(PositionGetInteger(POSITION_TIME_UPDATE))+"\n");
  np++;
 }
 for(int i=0;i<ocount && !IsStopped();i++){
  if(!AccountVerified())break;
  ulong ticket=OrderGetTicket(i);
  if(ticket==0)continue;
  FileWriteString(f,"O\t"+Int((long)ticket)+"\t"+
    SafeText(OrderGetString(ORDER_SYMBOL))+"\t"+
    Int(OrderGetInteger(ORDER_TYPE))+"\t"+
    Int(OrderGetInteger(ORDER_STATE))+"\t"+
    Money(OrderGetDouble(ORDER_VOLUME_INITIAL))+"\t"+
    Money(OrderGetDouble(ORDER_VOLUME_CURRENT))+"\t"+
    Money(OrderGetDouble(ORDER_PRICE_OPEN))+"\t"+
    Money(OrderGetDouble(ORDER_SL))+"\t"+
    Money(OrderGetDouble(ORDER_TP))+"\t"+
    Int(OrderGetInteger(ORDER_TIME_SETUP))+"\n");
  no++;
 }
 for(int i=0;i<dcount && !IsStopped();i++){
  if(!AccountVerified())break;
  ulong ticket=HistoryDealGetTicket(i);
  if(ticket==0)continue;
  FileWriteString(f,"D\t"+Int((long)ticket)+"\t"+
    Int(HistoryDealGetInteger(ticket,DEAL_ORDER))+"\t"+
    Int(HistoryDealGetInteger(ticket,DEAL_POSITION_ID))+"\t"+
    Int(HistoryDealGetInteger(ticket,DEAL_TIME))+"\t"+
    Int(HistoryDealGetInteger(ticket,DEAL_TYPE))+"\t"+
    Int(HistoryDealGetInteger(ticket,DEAL_ENTRY))+"\t"+
    Int(HistoryDealGetInteger(ticket,DEAL_REASON))+"\t"+
    SafeText(HistoryDealGetString(ticket,DEAL_SYMBOL))+"\t"+
    Money(HistoryDealGetDouble(ticket,DEAL_VOLUME))+"\t"+
    Money(HistoryDealGetDouble(ticket,DEAL_PRICE))+"\t"+
    Money(HistoryDealGetDouble(ticket,DEAL_PROFIT))+"\t"+
    Money(HistoryDealGetDouble(ticket,DEAL_COMMISSION))+"\t"+
    Money(HistoryDealGetDouble(ticket,DEAL_FEE))+"\t"+
    Money(HistoryDealGetDouble(ticket,DEAL_SWAP))+"\n");
  nd++;
 }
 if(np!=pcount || no!=ocount || nd!=dcount || !AccountVerified()){
  FileClose(f);FileDelete(staging);
  Print("FP_HISTORY_BROKER_SNAPSHOT_CHANGED_OR_UNVERIFIED");
  return;
 }
 FileWriteString(f,"END\t"+Int(np)+"\t"+Int(no)+"\t"+Int(nd)+"\n");
 FileFlush(f);FileClose(f);
 if(!FileMove(staging,0,file,FILE_REWRITE)){
  Print("FP_HISTORY_ATOMIC_PUBLISH_FAILED code=",GetLastError());
  FileDelete(staging);
  return;
 }
 Print("FP_HISTORY_NATIVE_READONLY_EXPORTED positions=",np,
   " orders=",no," deals=",nd," window_days=90");
}
int OnInit(){
 int f=FileOpen("ABUTRON_FP_HISTORY_REQUEST_V1.txt",FILE_READ|FILE_TXT|FILE_ANSI);
 if(f==INVALID_HANDLE){Print("FP_HISTORY_REQUEST_MISSING");return INIT_FAILED;}
 string schema=FileReadString(f);
 FP_H_NONCE=FileReadString(f);
 FP_H_OWNER=FileReadString(f);
 string broker=FileReadString(f);
 FP_H_SERVER=FileReadString(f);
 FP_H_LOGIN=FileReadString(f);
 FP_H_MODE=FileReadString(f);
 bool trailing=!FileIsEnding(f);FileClose(f);
 if(schema!="ABUTRON_FP_HISTORY_REQUEST_V1" || !IsHex32(FP_H_NONCE) ||
    StringLen(FP_H_OWNER)!=36 || broker!="FP_MARKETS" ||
    FP_H_SERVER!="FPMarketsSC-Live" || FP_H_MODE!="LIVE" ||
    !IsDigits(FP_H_LOGIN) || trailing || FP_H_LOGIN!="86076364"){
  Print("FP_HISTORY_ACCOUNT_REQUEST_REJECTED");
  return INIT_FAILED;
 }
 if(!EventSetTimer(20))return INIT_FAILED;
 // Await genuine broker authorization without failing indicator initialization.
 if(AccountVerified()){
  FP_H_READY=true;
  ExportHistory();
  Print("FP6364_HISTORY_NATIVE_READONLY_BOUND");
 } else Print("FP6364_HISTORY_AWAITING_BROKER_SESSION");
 return INIT_SUCCEEDED;
}
int OnCalculate(const int rates_total,const int prev_calculated,
 const datetime &time[],const double &open[],const double &high[],
 const double &low[],const double &close[],const long &tick_volume[],
 const long &volume[],const int &spread[]){
 return rates_total;
}
void OnTimer(){if(!FP_H_READY){if(!AccountVerified())return;FP_H_READY=true;Print("FP6364_HISTORY_NATIVE_READONLY_BOUND");}ExportHistory();}
void OnDeinit(const int reason){
 EventKillTimer();Print("FP_HISTORY_STOP reason=",reason);
}
