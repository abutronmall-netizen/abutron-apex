// ABUTRON Option C V2: native, nonce-bound entry-risk evidence for the
// EXISTING Deriv and FP Markets order-bridge EAs.
// No order sender here. Only the original bridge may call OrderSend.
// Include in both existing EAs AFTER gNonce/gLogin/gServer and DIR_BASE.
#ifndef __ABUTRON_ADAPTIVE_PROOF_V2__
#define __ABUTRON_ADAPTIVE_PROOF_V2__

bool OptionCFinitePositive(double value)
{
  return MathIsValidNumber(value) && value > 0.0;
}

// Durable BEFORE sending. If this cannot be written, BLOCK the new order.
// It intentionally never contains credentials or passwords.
bool OptionCWriteIntent(const string key,const string sym,const string side,
                        const double equity,const double budget,
                        const double lots,const double intended_entry,
                        const double stop,const double target)
{
  if(StringLen(key)!=64 || !OptionCFinitePositive(equity) ||
     !OptionCFinitePositive(budget) || budget>equity*0.03+0.00001 ||
     !OptionCFinitePositive(lots) || !OptionCFinitePositive(intended_entry) ||
     !OptionCFinitePositive(stop) || !OptionCFinitePositive(target))return false;
  FolderCreate(DIR_BASE+"optionc_v2");
  string file=DIR_BASE+"optionc_v2\\"+key+".txt";
  if(FileIsExist(file))return false; // UNKNOWN is never automatically retried
  int h=FileOpen(file,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
  if(h==INVALID_HANDLE)return false;
  string body="APEX_OPTIONC_NATIVE_RISK_INTENT_V2\r\n"+key+"\r\n"+
      gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\n"+
      sym+"\r\n"+side+"\r\n"+
      DoubleToString(equity,2)+"\r\n"+
      DoubleToString(budget,4)+"\r\n"+
      DoubleToString(lots,8)+"\r\n"+
      DoubleToString(intended_entry,10)+"\r\n"+
      DoubleToString(stop,10)+"\r\n"+
      DoubleToString(target,10)+"\r\n"+
      IntegerToString((long)TimeGMT())+"\r\n";
  FileWriteString(h,body);FileFlush(h);FileClose(h);
  return FileIsExist(file);
}

// Called ONLY from the existing EA's UpdateEvidenceFor(key,...), on a
// broker-visible position. This supports an adaptive position without
// mislabelling it a fixed-$50/$100 position. Still require independent
// broker-position and deal-history reconciliation on the Python side.
bool OptionCVerifyOpenPosition(const string key,const string sym,
                               const string side,const double vol,
                               const double entry,const double stop,
                               const double target,double &cashRisk,
                               double &cashTarget)
{
  string file=DIR_BASE+"optionc_v2\\"+key+".txt";
  if(!FileIsExist(file))return false;
  int h=FileOpen(file,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8);
  if(h==INVALID_HANDLE)return false;
  string protocol=FileReadString(h),id=FileReadString(h);
  string nonce=FileReadString(h),login=FileReadString(h),server=FileReadString(h);
  string savedSymbol=FileReadString(h),savedSide=FileReadString(h);
  double originalEquity=StringToDouble(FileReadString(h));
  double budget=StringToDouble(FileReadString(h));
  double originalLots=StringToDouble(FileReadString(h));
  double intendedEntry=StringToDouble(FileReadString(h));
  double originalStop=StringToDouble(FileReadString(h));
  double originalTarget=StringToDouble(FileReadString(h));
  long originalTime=(long)StringToInteger(FileReadString(h));
  FileClose(h);
  if(protocol!="APEX_OPTIONC_NATIVE_RISK_INTENT_V2" || id!=key ||
     nonce!=gNonce || login!=gLogin || server!=gServer ||
     sym!=savedSymbol || side!=savedSide ||
     !OptionCFinitePositive(originalEquity) ||
     !OptionCFinitePositive(budget) ||
     !OptionCFinitePositive(originalLots) ||
     !OptionCFinitePositive(originalStop) ||
     !OptionCFinitePositive(originalTarget) ||
     originalTime<=0 || originalTime>(long)TimeGMT()+5 ||
     budget>originalEquity*0.03+0.00001 ||
     MathAbs(vol-originalLots)>0.0000001 ||
     MathAbs(stop-originalStop)>0.0000001 ||
     MathAbs(target-originalTarget)>0.0000001)
    return false;
  if(!((side=="BUY" && stop<entry && entry<target) ||
       (side=="SELL" && target<entry && entry<stop)))return false;
  ENUM_ORDER_TYPE typ=(side=="BUY"?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
  double loss=0.0,reward=0.0;
  if(!OrderCalcProfit(typ,sym,vol,entry,stop,loss) ||
     !OrderCalcProfit(typ,sym,vol,entry,target,reward))return false;
  cashRisk=-loss;cashTarget=reward;
  return MathIsValidNumber(cashRisk) && MathIsValidNumber(cashTarget) &&
         cashRisk>0.0 && cashRisk<=budget+0.005 &&
         cashTarget>=1.5*cashRisk;
}
// Used inside the ORIGINAL PortfolioCanAdd to keep mixed legacy/V2 open
// positions accepted only when the broker-native V2 intent is verifiable.
bool OptionCAnyVerifiedPosition(const string sym,const string side,
                                const double volume,const double entry,
                                const double stop,const double target)
{
  string file="";
  long search=FileFindFirst(DIR_BASE+"optionc_v2\\*.txt",file);
  if(search==INVALID_HANDLE)return false;
  bool valid=false;
  int inspected=0;
  do
  {
    if(++inspected>250)break;
    int n=StringLen(file);
    if(n!=68 || StringSubstr(file,64)!=".txt")continue;
    string key=StringSubstr(file,0,64);
    double cashLoss=0.0,cashTarget=0.0;
    if(OptionCVerifyOpenPosition(key,sym,side,volume,entry,stop,target,
                                 cashLoss,cashTarget))
    { valid=true;break; }
  } while(FileFindNext(search,file));
  FileFindClose(search);
  return valid;
}
#endif
