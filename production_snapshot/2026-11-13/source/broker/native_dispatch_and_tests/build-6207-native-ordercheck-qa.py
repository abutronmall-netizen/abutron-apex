#!/usr/bin/python3
"""Stage an additive, no-send MQL5 exact order preflight for QA compilation only.
Does not replace installed EA; does not change service, CRM, or request files.
"""
from pathlib import Path
import hashlib
import os
import pwd

SRC=Path('/usr/local/lib/abutron-6207-v4/AbutronApexExistingDerivV4_6207.mq5')
QA=Path('/home/abutron_mt5_ui/.wine-abutron/drive_c/AbutronMT5Demo/MQL5/Experts/ABUTRON_APEX_EXACT_ORDER_CHECK_ONLY_QA_20261110')
NAME='AbutronApexExistingDerivV4_6207_ExactCheckQA.mq5'
marker='\nvoid OnTimer()\n{'
hook=' WriteApexExactOrderCheckNoSend();\n // LEGACY_V2_V3_CONSUMPTION_DISABLED'
original=SRC.read_text()
assert original.count(marker)==1 and original.count(' // LEGACY_V2_V3_CONSUMPTION_DISABLED')==1
assert '#define MAGIC 73113011' in original

fn=r'''
// === ABUTRON APEX 1.1 exact broker OrderCheck diagnostic; NEVER SENDS ===
// Separate from privileged execution requests. A positive OrderCheck does not
// authorize an order, change CRM effective_on, or count as broker execution ACK.
#define APEX11_CHECK_REQ "ABUTRON\\APEX11_EXACT_CHECK_ONLY.req"
#define APEX11_CHECK_MAGIC "ABUTRON_APEX11_EXACT_CHECK_NO_SEND_V1"
void WriteApexExactOrderCheckNoSend()
{
 if(!FileIsExist(APEX11_CHECK_REQ))return;
 int h=FileOpen(APEX11_CHECK_REQ,FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ,0,CP_UTF8);
 if(h==INVALID_HANDLE)return;
 string head=FileReadString(h),nonce=FileReadString(h);
 string login=FileReadString(h),server=FileReadString(h);
 string decision=FileReadString(h),key=FileReadString(h);
 string symbol=FileReadString(h),side=FileReadString(h);
 string volumeText=FileReadString(h),entryText=FileReadString(h);
 string stopText=FileReadString(h),takeText=FileReadString(h);
 string expiryText=FileReadString(h),purpose=FileReadString(h);
 bool exactEnd=FileIsEnding(h);
 FileClose(h);
 if(!IsHex64(key)||!IsHex64(decision)||!exactEnd)return;
 string consumed="ABUTRON\\execution-audit\\apex11-check-"+key+".consumed";
 string resultFile="ABUTRON\\execution-audit\\apex11-check-"+key+".txt";
 if(FileIsExist(consumed)||FileIsExist(resultFile))return;
 if(!FileMove(APEX11_CHECK_REQ,0,consumed,0))return;
 string status="DENY",reason="PRECHECK";
 bool checked=false;uint retcode=0;int lastErr=0;
 double stopUSD=0.0,targetUSD=0.0,marginUSD=0.0;
 double currentBid=0.0,currentAsk=0.0;
 double lots=StringToDouble(volumeText),entry=StringToDouble(entryText);
 double sl=StringToDouble(stopText),tp=StringToDouble(takeText);
 long expiry=(long)StringToInteger(expiryText);
 ENUM_ORDER_TYPE direction=side=="BUY"?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
 bool identity=head==APEX11_CHECK_MAGIC&&purpose=="CHECK_ONLY_NEVER_SEND"&&
    nonce==gNonce&&login==gLogin&&login=="32456207"&&server==gServer&&
    server=="Deriv-Demo"&&VerifiedDemoAccount()&&
    (side=="BUY"||side=="SELL")&&V4ApprovedSymbol(symbol)&&
    expiryText==IntegerToString(expiry)&&
    expiry>=(long)TimeGMT()&&expiry<=(long)TimeGMT()+12;
 if(!identity)reason="IDENTITY_OR_EXPIRY_FAILED";
 else if(!MathIsValidNumber(lots)||!MathIsValidNumber(entry)||!MathIsValidNumber(sl)||
         !MathIsValidNumber(tp)||lots<=0.0||entry<=0.0||sl<=0.0||tp<=0.0)
   reason="NUMBERS_INVALID";
 else if(!SymbolSelect(symbol,true))reason="SYMBOL_UNAVAILABLE";
 else
 {
   MqlTick tick={};
   if(!SymbolInfoTick(symbol,tick)||tick.time_msc<=0||
      tick.bid<=0.0||tick.ask<=0.0||tick.ask<tick.bid)
      reason="NO_AUTHENTIC_TICK";
   else
   {
      currentBid=tick.bid;currentAsk=tick.ask;
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      double minlots=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double maxlots=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      double ticksize=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
      long stops=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      long freeze=SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      double closePrice=side=="BUY"?tick.bid:tick.ask;
      double startPrice=side=="BUY"?tick.ask:tick.bid;
      double minStop=(double)MathMax(stops,freeze)*point;
      if(point<=0.0||step<=0.0||ticksize<=0.0||minlots<=0.0||
         lots<minlots||lots>maxlots||
         MathAbs((lots-minlots)/step-MathRound((lots-minlots)/step))>0.00001)
         reason="VOLUME_OR_SPEC_INVALID";
      else if(MathAbs(entry-startPrice)>point*15.0||
              MathAbs(entry/ticksize-MathRound(entry/ticksize))>0.00001)
         reason="EXACT_PROPOSAL_PRICE_MOVED";
      else if((side=="BUY"&&!(sl<closePrice&&entry<tp&&
                  closePrice-sl>=minStop&&tp-closePrice>=minStop))||
              (side=="SELL"&&!(tp<closePrice&&entry<sl&&
                  sl-closePrice>=minStop&&closePrice-tp>=minStop)))
         reason="INVALID_NATIVE_STOPS";
      else if(!OrderCalcProfit(direction,symbol,lots,entry,sl,stopUSD)||
              !OrderCalcProfit(direction,symbol,lots,entry,tp,targetUSD)||
              !OrderCalcMargin(direction,symbol,lots,entry,marginUSD)||
              stopUSD>=0.0||targetUSD<=0.0||marginUSD<0.0)
         reason="NATIVE_RISK_CALC_FAILED";
      else if(-stopUSD>AccountInfoDouble(ACCOUNT_EQUITY)*0.001*0.85||
              targetUSD/(-stopUSD)<1.5||
              marginUSD>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.10)
         reason="NATIVE_010_RISK_RR_MARGIN_DENIED";
      else
      {
         MqlTradeRequest req={};MqlTradeCheckResult c={};
         req.action=TRADE_ACTION_DEAL;
         req.symbol=symbol;req.volume=lots;req.type=direction;
         req.price=entry;req.sl=sl;req.tp=tp;req.magic=MAGIC;
         req.deviation=15;req.type_time=ORDER_TIME_GTC;
         req.comment="APEX11 DERIV DEMO";
         int fill=(int)SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
         if((fill & SYMBOL_FILLING_IOC)!=0)req.type_filling=ORDER_FILLING_IOC;
         else if((fill & SYMBOL_FILLING_FOK)!=0)req.type_filling=ORDER_FILLING_FOK;
         else req.type_filling=ORDER_FILLING_RETURN;
         ResetLastError();
         checked=OrderCheck(req,c);
         lastErr=GetLastError();retcode=c.retcode;
         if(!checked)reason="MT5_ORDERCHECK_CALL_FAILED";
         else if(c.retcode!=0&&c.retcode!=TRADE_RETCODE_DONE)
            reason="MT5_ORDERCHECK_BROKER_REJECTED";
         else {status="CHECK_PASS_NO_SEND";reason="BROKER_NATIVE_EXACT_CHECK_ONLY";}
      }
   }
 }
 string body="ABUTRON_APEX11_EXACT_CHECK_NATIVE_NO_SEND_V1\r\n"+
    gNonce+"\r\n"+gLogin+"\r\n"+gServer+"\r\n"+
    decision+"\r\n"+key+"\r\n"+symbol+"\r\n"+side+"\r\n"+
    volumeText+"\r\n"+entryText+"\r\n"+stopText+"\r\n"+takeText+"\r\n"+
    IntegerToString((long)TimeGMT())+"\r\n"+status+"\r\n"+reason+"\r\n"+
    (checked?"ORDER_CHECK_CALLED":"ORDER_CHECK_NOT_CALLED")+"\r\n"+
    IntegerToString((long)retcode)+"\r\n"+IntegerToString(lastErr)+"\r\n"+
    DoubleToString(stopUSD,8)+"\r\n"+DoubleToString(targetUSD,8)+"\r\n"+
    DoubleToString(marginUSD,8)+"\r\n"+DoubleToString(currentBid,8)+"\r\n"+
    DoubleToString(currentAsk,8)+"\r\n"+
    "NO_ORDER_SEND;NO_CRM_CHANGE;NO_BROKER_ACK\r\n";
 int out=FileOpen(resultFile,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
 if(out!=INVALID_HANDLE){FileWriteString(out,body);FileFlush(out);FileClose(out);}
 Print("ABUTRON_APEX11_EXACT_CHECK_NO_SEND id=",key," state=",status,
       " reason=",reason," retcode=",retcode," sent=FALSE");
}
// === END ABUTRON APEX 1.1 exact broker OrderCheck diagnostic ===
'''

candidate=original.replace(marker,'\n'+fn+marker)
candidate=candidate.replace(' // LEGACY_V2_V3_CONSUMPTION_DISABLED',hook)
# No additional broker order send calls in additive code.
assert fn.count('OrderCheck(')==1 and 'OrderSend(' not in fn
assert candidate.count('OrderSend(')==original.count('OrderSend(')
assert candidate.count('HandleV4Request();')==original.count('HandleV4Request();')
assert candidate.count('WriteApexExactOrderCheckNoSend();')==1
QA.mkdir(parents=True,exist_ok=True)
pw=pwd.getpwnam('abutron_mt5_ui');os.chown(QA,pw.pw_uid,pw.pw_gid)
p=QA/NAME
p.write_text(candidate)
os.chown(p,pw.pw_uid,pw.pw_gid);p.chmod(0o640)
print('QA_ONLY_SOURCE',str(p),'sha256',hashlib.sha256(p.read_bytes()).hexdigest(),'lines',len(candidate.splitlines()))
print('ORIGINAL_ORDERSEND_COUNT',original.count('OrderSend('),'QA_ORDERSEND_COUNT',candidate.count('OrderSend('))
