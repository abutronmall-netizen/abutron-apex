from pathlib import Path
src=Path("/opt/apex/runtime/apex_demo_usd_profile_v1.py")
dst=Path("/opt/apex/runtime/apex_multi_usd_planner_v3.py")
if dst.exists():raise SystemExit("Destination exists, manual review required")
s=src.read_text()
old='''    used=float(current_loss(account))
    if not math.isfinite(used) or not 0<cap_usd<=140:
        raise Blocked("USD_CAP_OR_ACCOUNT_LOSS_INVALID")
    # 30% buffer admits room for broker costs/slippage without claiming a
    # guaranteed outcome. A $100 SL with 30% buffer needs at least $130 headroom.
    buffered=round(risk_gross*BUFFER+0.005,4)
    if buffered>cap_usd-used:
        raise Blocked("PROFILE_USD_STOP_EXCEEDS_REMAINING_CAP")
'''
new='''    if cap_usd is not None:
        raise Blocked("ACCOUNT_WIDE_CAP_NOT_SUPPORTED_IN_MULTI_V3")
    # Independent profile USD stop exists on EVERY order.
    # Buffer is an informational estimate only; no account-wide dollar cap.
    buffered=round(risk_gross*BUFFER+0.005,4)
'''
assert s.count(old)==1
s=s.replace(old,new)
s=s.replace('from apex_demo_mt5_executor import Blocked, BUFFER, MAGIC, current_loss',
            'from apex_demo_mt5_executor import Blocked, BUFFER, MAGIC')
s=s.replace('def plan_usd_request(account,candidate,market_rows,profile,cap_usd):',
            'def plan_usd_request(account,candidate,market_rows,profile,cap_usd=None):')
s=s.replace('"account_loss_used_usd":round(used,2),\n                        "remaining_allowance_usd":round(cap_usd-used,2),',
            '"account_loss_cap_usd":None,')
s=s.replace('Any unrepresentable quote, unsupported lot, minimum broker stop, or $140 daily\nrisk budget violation MUST block entry; never silently resize or widen protection.',
            'Unrepresentable quotes, unsupported lots and broker minimum stops MUST\nblock entry. Each trade has its own USD SL and TP; no account-wide loss cap.')
s=s.replace('    # Protect against minimum broker stops on both sides, including quote size.',
            '    # Protect against minimum broker stops on both sides, including quote size.')
compile(s,str(dst),'exec')
dst.write_text(s)
dst.chmod(0o644)
print("CREATED",dst, "source intact",src)
