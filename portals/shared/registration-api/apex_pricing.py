"""Authoritative APEX fixed monthly ZAR list prices. Amounts are in cents."""
CURRENCY="ZAR"
INTERVAL="monthly"
PRICES={"Starter":100000,"Professional":200000,"Enterprise":300000}
SEATS={"Starter":1,"Professional":2,"Enterprise":3}
FUNDING_DISCLOSURE='ABUTRON license fees cover software access and included broker-account seats ONLY. No trading capital, account equity or broker deposits are included. For LIVE trading, deposit your own funds directly with your approved broker (Deriv, IC Markets or FP Markets). APEX does not receive or hold your broker trading deposit. DEMO balances are virtual.'
def quote(plan):
    if not isinstance(plan,str) or plan not in PRICES:
        raise ValueError("Select a valid Starter, Professional or Enterprise plan.")
    return {"plan":plan,"currency":CURRENCY,"amount_minor":PRICES[plan],
            "billing_interval":INTERVAL,"included_broker_accounts":SEATS[plan],
            "includes_trading_equity":False,"requires_separate_broker_deposit_for_live":True,
            "funding_disclosure":FUNDING_DISCLOSURE}
def catalog():
    return [quote(plan) for plan in PRICES]
