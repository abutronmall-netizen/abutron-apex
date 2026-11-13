/* Broker-native execution evidence: independent from APEX research journals. */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const put = (id, value) => { const el = $(id); if (el) el.textContent = String(value); };
  const count = value => Number.isInteger(value) && value >= 0 ? String(value) : "—";
  function render(data) {
    if (data.schema !== "abutron.apex11.broker_evidence.readonly.v1" ||
        !Array.isArray(data.accounts)) throw Error("Unexpected evidence");
    const tbody = $("apex11BrokerRows");
    if (!tbody) return;
    tbody.replaceChildren();
    let current = 0, exposed = 0, overruns = 0;
    for (const a of data.accounts) {
      const fresh = a.status === "BROKER_SNAPSHOT_CURRENT" || a.status === "BROKER_HISTORY_CURRENT";
      if (fresh) {
        current++;
        exposed += Number.isInteger(a.open_positions) ? a.open_positions : 0;
        overruns += Number.isInteger(a.native_risk_budget_overruns) ? a.native_risk_budget_overruns : 0;
      }
      const row = document.createElement("tr");
      if (!fresh) row.className = "apex11-stale";
      const detail = a.status === "BROKER_HISTORY_CURRENT" ? "MT5 HISTORY · APEX attribution unverified"
        : a.status === "BROKER_SNAPSHOT_CURRENT" ? "NATIVE BROKER SNAPSHOT · signal attribution unverified"
        : a.status === "NO_CURRENT_LIVE_BROKER_PROOF" ? "NO LIVE BROKER PROOF"
        : "ACCOUNT BROKER PROOF UNAVAILABLE";
      const risk = a.native_risk_budget_overruns > 0
        ? "⚠ " + a.native_risk_budget_overruns + " BUDGET OVERRUN"
        : a.native_risk_budget_overruns === 0 ? "No flagged overrun · global risk unverified" : "Not assessed";
      const items = [
        a.broker + " " + a.environment + " ••••" + a.account_suffix,
        detail,
        count(a.open_positions),
        a.positions_with_stops === null ? "—" : count(a.positions_with_stops) + " / " + count(a.open_positions),
        count(a.broker_deals_in_export_window),
        risk,
        a.age_seconds === null ? "UNVERIFIED" : a.age_seconds + "s ago"
      ];
      for (const item of items) {
        const cell = document.createElement("td");
        cell.textContent = item;
        if (String(item).includes("BUDGET OVERRUN")) cell.className = "apex11-risk-alert";
        row.appendChild(cell);
      }
      tbody.appendChild(row);
    }
    put("apex11BrokerState",current + " / " + data.accounts.length + " FRESH SOURCES");
    put("apex11BrokerPositions",String(exposed));
    put("apex11BrokerRisk",overruns ? "⚠ " + overruns + " FLAGGED" : "NOT GLOBALLY VERIFIED");
    put("apex11BrokerChecked","Sources checked " + new Date(data.checked_at_utc).toLocaleString("en-GB", {timeZone:"UTC"}) + " UTC. Broker deals are historical, not new APEX orders.");
  }
  function unavailable() {
    put("apex11BrokerState","SOURCE UNAVAILABLE");
    put("apex11BrokerPositions","—");
    put("apex11BrokerRisk","UNVERIFIED");
    put("apex11BrokerChecked","Broker evidence could not be verified.");
    const tbody=$("apex11BrokerRows");
    if(tbody) {
      tbody.replaceChildren();
      const row=document.createElement("tr"),cell=document.createElement("td");
      cell.colSpan=7; cell.textContent="Account-bound broker evidence unavailable; research status does not establish execution.";
      row.appendChild(cell);tbody.appendChild(row);
    }
  }
  async function refresh(){
    if(document.hidden) return;
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),6000);
    try{
      const response=await fetch("/apex/api/apex11-broker-evidence", {credentials:"same-origin",cache:"no-store",signal:controller.signal});
      if(!response.ok) throw Error("HTTP "+response.status);
      render(await response.json());
    }catch(_){unavailable();}
    finally{clearTimeout(timer);}
  }
  refresh();
  setInterval(refresh,30000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
})();