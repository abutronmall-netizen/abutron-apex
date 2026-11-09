/* Abutron V7 additive MT5 account setup UI, v1. Public UI only.
 * Does not handle credentials, broker auth, network writes, orders, or data storage.
 * Do not remove the read-only banner or enable credential submission.
 * Intended for safe display on the existing live Trading accounts page.
 */
(() => {
  "use strict";
  const BROKERS = Object.freeze({
    IC_MARKETS: Object.freeze({
      label: "IC Markets",
      servers: Object.freeze(["ICMarketsSC-Demo", "ICMarketsSC-MT5-3"])
    }),
    FP_MARKETS: Object.freeze({
      label: "FP Markets",
      servers: Object.freeze(["FPMarketsSC-Demo Server", "FPMarketsSC-Live"])
    }),
    DERIV_BVI: Object.freeze({
      label: "Deriv (BVI) Ltd.",
      servers: Object.freeze(["Deriv-Demo", "DerivBVI-Server-02"])
    })
  });
  const ELEMENT_ID = "abutron-mt5-account-setup-v1";

  function element(tag, attributes = {}, text = "") {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (name === "className") node.className = value;
      else if (name === "htmlFor") node.htmlFor = value;
      else node.setAttribute(name, value);
    }
    if (text) node.textContent = text;
    return node;
  }

  function makeField(name, id, child) {
    const label = element("label", {className: "abutron-mt5-label", htmlFor: id}, name);
    label.appendChild(child);
    return label;
  }

  function selectedOption(select, text, value) {
    const o = element("option", {value}, text);
    select.appendChild(o);
  }

  function build() {
    const box = element("section", {id: ELEMENT_ID, className: "abutron-mt5-setup", "aria-label": "Add MetaTrader 5 account"});
    box.appendChild(element("p", {className: "abutron-mt5-kicker"}, "META TRADER 5 ACCOUNTS"));
    box.appendChild(element("h3", {}, "Add trading account"));
    box.appendChild(element("p", {className: "abutron-mt5-help"},
      "Choose your MT5 broker and server. Demo servers are selected automatically. Your credentials are not collected or saved while broker linking remains locked."));

    const form = element("form", {className: "abutron-mt5-form", autocomplete: "off"});
    form.addEventListener("submit", event => event.preventDefault());
    const firstRow = element("div", {className: "abutron-mt5-row"});
    const broker = element("select", {id: "abutron-mt5-broker", name: "broker", "aria-label": "MT5 broker"});
    for (const [key, item] of Object.entries(BROKERS)) selectedOption(broker, item.label, key);
    const server = element("select", {id: "abutron-mt5-server", name: "server", "aria-label": "MT5 broker server"});

    const secondRow = element("div", {className: "abutron-mt5-row"});
    const login = element("input", {
      type: "text", id: "abutron-mt5-login", name: "username", inputmode: "numeric",
      autocomplete: "off", maxlength: "20", pattern: "[0-9]{3,20}",
      placeholder: "Your MT5 account number"
    });
    const password = element("input", {
      type: "password", id: "abutron-mt5-password", name: "password",
      placeholder: "Locked until secure broker linking is available",
      disabled: "disabled", autocomplete: "new-password"
    });
    const message = element("p", {className: "abutron-mt5-lock-note", role: "status"},
      "Secure MT5 password entry, Add account and Disconnect account are unavailable until an encrypted vault and genuine broker verification are certified. Your account is not connected.");
    const button = element("button", {type: "submit", className: "abutron-mt5-submit", disabled: "disabled"}, "Add trading account");
    const footer = element("p", {className: "abutron-mt5-helper"},
      "Server choices are customer-requested names, not evidence of a broker connection. LIVE servers never authorize trading. Existing positions are unaffected.");

    function populateServers() {
      const selectedBroker = BROKERS[broker.value];
      if (!selectedBroker) return;
      server.replaceChildren();
      for (const entry of selectedBroker.servers) {
        selectedOption(server, entry + (entry.toLowerCase().includes("demo") ? " · DEMO" : " · LIVE"), entry);
      }
      server.selectedIndex = 0;
      login.value = "";
      password.value = "";
    }
    broker.addEventListener("change", populateServers);
    server.addEventListener("change", () => {
      password.value = "";
      const demo = server.value.toLowerCase().includes("demo");
      message.textContent = demo
        ? "Secure MT5 password entry, Add account and Disconnect account are unavailable until an encrypted vault and genuine broker verification are certified. Your account is not connected."
        : "LIVE server selected. Credential collection and trading are locked. LIVE requires separate independent authorization.";
    });
    firstRow.append(makeField("Broker", broker.id, broker), makeField("Server", server.id, server));
    secondRow.append(makeField("Username (MT5 login)", login.id, login), makeField("Password", password.id, password));
    form.append(firstRow, secondRow, message, button, footer);
    box.appendChild(form);
    populateServers();
    return box;
  }

  let scanning = false;
  function mount() {
    if (scanning) return;
    scanning = true;
    try {
      // Restrict to the authenticated Trading Accounts panel, never login/admin.
      const root = document.querySelector("main.main");
      if (!root) return;
      const sections = root.querySelectorAll("section.panel");
      for (const section of sections) {
        const title = section.querySelector("h2");
        if (title && title.textContent.trim() === "Linked trading accounts") {
          if (!section.querySelector("#" + ELEMENT_ID)) {
            const table = section.querySelector(".table-wrap");
            const ui = build();
            if (table) section.insertBefore(ui, table);
            else section.appendChild(ui);
          }
          break;
        }
      }
    } finally {
      scanning = false;
    }
  }

  function start() {
    mount();
    const observer = new MutationObserver(() => mount());
    observer.observe(document.getElementById("root") || document.body, {childList: true, subtree: true});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
