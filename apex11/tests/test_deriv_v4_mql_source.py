"""Offline static fail-closed V4 MQ5 acceptance smoke tests.

These tests DO NOT compile the MQL5 source, prove that an EX5 matches it,
or validate a broker trade. Compile and broker attestation are separate gates.
"""
from pathlib import Path
import re

EA = Path(__file__).resolve().parents[1] / "mql5" / "AbutronApexExistingDerivV4_6207.mq5"
PORT = Path(__file__).resolve().parents[1] / "abutron_replacement" / "native_v4_file_port.py"


def source():
    s = EA.read_text(encoding="utf-8")
    assert 40000 < len(s) < 70000
    return s


def test_mql5_original_risk_broker_evidence_preserved():
    s=source()
    for marker in (
        '#include "AdaptiveRiskProofV2.mqh"',
        'bool NativeAdaptivePlan(', 'bool PortfolioCanAdd(',
        'bool VerifiedNativeFeed(', 'bool VerifiedDemoAccount(',
        'bool AuditRequestBeforeSend(', 'void AuditSendResult(',
        'void AuditBrokerProtection(', 'bool OrderCheck(req,check);',
        'void UpdateEvidenceFor(', 'void UpdateEvidence()',
        'OptionCVerifyOpenPosition(', 'OptionCWriteIntent(',
        'OrderCalcProfit(', 'OrderCalcMargin(', 'OrderSend(req,res)',
    ):
        assert marker in s,marker


def test_v4_native_disabled_default_and_v3_dispatch_stays_opt_in():
    s=source()
    assert "input bool EnableNativeDemoOrders = false;" in s
    assert "input bool EnableApex11V4DemoOrders = false;" in s
    assert "input bool EnableLegacyNativeRequests = false;" in s
    assert "if(EnableLegacyNativeRequests)HandleRequest();" in s
    assert "HandleV4Request();" in s
    assert "V4_ROOT_ACTIVATION_SUPERVISOR_NOT_ATTESTED" in s
    assert "V4_AUTHORIZATION_EXPIRED_BEFORE_SEND" in s
    gate=s.split("bool V4RevisionAuthorized(",1)[1].split("// V4 only supports",1)[0]
    assert "return false;" in gate
    assert "return true;" not in gate


def test_v4_has_separate_file_and_explicit_risk_and_client_revision():
    s=source()
    p=PORT.read_text()
    assert '#define V4_REQ "ABUTRON\\\\ABUTRON_APEX_V4.req"' in s
    assert "V4_MAGIC" in s and "APEX_NATIVE_ACCOUNT_BOUND_ORDER_V4" in s
    assert 'V4_REQUEST_NAME="ABUTRON_APEX_V4.req"' in p
    assert 'V4_PROTOCOL="APEX_NATIVE_ACCOUNT_BOUND_ORDER_V4"' in p
    assert "revisionText=FileReadString(h)" in s
    assert "lotsText=FileReadString(h)" in s
    assert "slText=FileReadString(h)" in s and "tpText=FileReadString(h)" in s
    assert "FileIsEnding(h)" in s
    assert "FileMove(V4_REQ,0,archive,0)" in s
    assert "FileIsExist(REQ)" in s
    assert "V4_NATIVE" in s
    assert "0.001*0.85" in s
    assert "V4_PER_TRADE_RISK_OR_REWARD_DENIED" in s
    assert "V4ApprovedSymbol(" in s


def test_v4_single_attempt_and_no_ack_as_broker_position():
    s=source()
    handler=s.split("void HandleV4Request()",1)[1].split(
        "// Helper avoids",1)[0]
    assert handler.count("OrderSend(req,result)") == 1
    assert handler.index("FileMove(V4_REQ,0,archive,0)") < handler.index("OrderSend(req,result)")
    assert handler.index("V4RevisionAuthorized(key,revision)") < handler.index(
        "OrderSend(req,result)")
    assert handler.count("V4RevisionAuthorized(key,revision)") == 2
    assert handler.index("bool orderChecked=OrderCheck(req,checked)") < handler.index(
        "OrderSend(req,result)")
    assert handler.index("OptionCWriteIntent(") < handler.index(
        "OrderSend(req,result)")
    assert handler.index("AuditRequestBeforeSend(") < handler.index(
        "OrderSend(req,result)")
    assert handler.index("V4_AUTHORIZATION_EXPIRED_BEFORE_SEND") < handler.index(
        "OrderSend(req,result)")
    assert "BROKER_ACK_POSITION_STILL_UNVERIFIED" in handler
    assert 'Receipt(key,"UNKNOWN"' in handler
    assert "SEND_DEMO_ONLY" in handler
    assert "V4_APPROVED_LIVE" not in handler


def test_v4_fail_closed_capability_is_not_faked_or_production_autoarmed():
    s=source()
    assert "WriteV4Capability()" not in s
    assert "APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4" not in s
    assert "EnableApex11V4DemoOrders = true" not in s
    assert "EnableLegacyNativeRequests = true" not in s
    assert "LIVE" not in s.split("void HandleV4Request()",1)[1].split(
        "// Helper avoids",1)[0].replace("SEND_DEMO_ONLY","")


def test_source_not_malformed_by_patch_markers():
    s=source()
    assert s.count("#property version") == 1
    assert s.count("void HandleRequest()") == 1
    assert s.count("void HandleV4Request()") == 1
    assert s.count("void OnTimer()") == 1
    assert s.count("// ==================== APEX 1.1.0 V4 NATIVE ADAPTER") == 1
    assert s.count("#define REQ ") == 1
    assert s.count("#define V4_REQ ") == 1
