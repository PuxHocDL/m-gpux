// M-GPUX sidebar overview. Renders the snapshot posted by homeView.ts and
// sends every click back as an mgpux.* command; no logic of its own.
(function () {
  const vscode = acquireVsCodeApi();
  const root = document.getElementById("root");
  const ui = Object.assign({ toolsOpen: false, allSessions: false }, vscode.getState() || {});
  let state = null;

  // Stroke icons on a 24×24 grid, shared style with the web dashboard.
  const ICONS = {
    logo: '<path d="M9 22V10.5l7 6.5 7-6.5V22" transform="translate(-4 -4)"/>',
    refresh: '<path d="M20.5 11A8.5 8.5 0 0 0 5.6 6.4L3.5 8.5"/><path d="M3.5 3.5v5h5"/><path d="M3.5 13a8.5 8.5 0 0 0 14.9 4.6l2.1-2.1"/><path d="M20.5 20.5v-5h-5"/>',
    swap: '<path d="M4 8h14l-3.5-3.5"/><path d="M20 16H6l3.5 3.5"/>',
    rocket: '<path d="M14.5 4.5c2.5-1.2 4.6-1.4 5.5-1.5-.1.9-.3 3-1.5 5.5L13 14l-3-3z"/><path d="M10 11 6.5 10 4 12.5l4 1"/><path d="m13 14 1 3.5-2.5 2.5-1-4"/><path d="M6 16.5c-1.5.5-2.2 2-2.5 3.5 1.5-.3 3-1 3.5-2.5"/>',
    vm: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="m8.5 8.5 2 1.5-2 1.5"/>',
    server: '<rect x="3.5" y="3.5" width="17" height="7" rx="2"/><rect x="3.5" y="13.5" width="17" height="7" rx="2"/><path d="M7.5 7h.01M7.5 17h.01"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.4 2.6 3.6 5.6 3.6 9s-1.2 6.4-3.6 9c-2.4-2.6-3.6-5.6-3.6-9S9.6 5.6 12 3z"/>',
    package: '<path d="M12 2.8 20.5 7.5v9L12 21.2 3.5 16.5v-9z"/><path d="M3.8 7.6 12 12.2l8.2-4.6"/><path d="M12 12.2v9"/>',
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    notebook: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 3v18M12 8h4M12 12h4"/>',
    terminal: '<rect x="2.5" y="4" width="19" height="16" rx="2.5"/><path d="m6.5 9.5 3 2.5-3 2.5"/><path d="M12 15h5"/>',
    play: '<path d="m8 5.5 11 6.5-11 6.5z"/>',
    external: '<path d="M14 3.5h6.5V10"/><path d="M20.5 3.5 11 13"/><path d="M18.5 14v4.5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2H10"/>',
    logs: '<path d="M14.5 2.5H6.5a2 2 0 0 0-2 2v15a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-12z"/><path d="M14.5 2.5v5h5"/><path d="M8.5 13h7M8.5 17h5"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    trash: '<path d="M3.5 6h17"/><path d="M8.5 6V4.5A1.5 1.5 0 0 1 10 3h4a1.5 1.5 0 0 1 1.5 1.5V6"/><path d="M5.5 6l1 13.5A1.5 1.5 0 0 0 8 21h8a1.5 1.5 0 0 0 1.5-1.5l1-13.5"/>',
    down: '<path d="M12 4v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M4.5 19.5h15"/>',
    up: '<path d="M12 15V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M4.5 19.5h15"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/>',
    shield: '<path d="M12 3 4.5 6v5.5c0 4.5 3.2 8.2 7.5 9.5 4.3-1.3 7.5-5 7.5-9.5V6z"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9.5h18M3 14.5h18M9.5 9.5V20"/>',
    layers: '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/>',
    key: '<circle cx="8" cy="15" r="4.5"/><path d="m11.2 11.8 9.3-9.3M17 6l3 3M14.5 8.5l2 2"/>',
    gateway: '<path d="M4 7h10M4 17h10"/><circle cx="17" cy="7" r="3"/><circle cx="17" cy="17" r="3"/><path d="M4 12h16"/>',
    cloud: '<path d="M7 18.5a4.5 4.5 0 0 1-.6-9 6 6 0 0 1 11.5 1.5 3.8 3.8 0 0 1-.4 7.5z"/>',
    pulse: '<path d="M3 12h4l2.5-6 5 12 2.5-6h4"/>',
    remote: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="m10 8-2 2 2 2M14 8l2 2-2 2"/>',
    power: '<path d="M12 2.5v9"/><path d="M6.3 5.8a8.5 8.5 0 1 0 11.4 0"/>',
    wallet: '<path d="M3.5 7.5v10a2 2 0 0 0 2 2h14v-12h-14a2 2 0 0 1 0-4h12v4"/><circle cx="16" cy="13.5" r="1.2"/>',
    command: '<path d="M9 6.5A2.5 2.5 0 1 0 6.5 9H9zM9 9h6v6H9zM15 6.5V9h2.5A2.5 2.5 0 1 0 15 6.5zM9 17.5V15H6.5A2.5 2.5 0 1 0 9 17.5zM15 15v2.5a2.5 2.5 0 1 0 2.5-2.5z"/>',
    chevron: '<path d="m9 6 6 6-6 6"/>',
    tools: '<path d="M14.5 6.5a4 4 0 0 0 5 5L12 19a2.1 2.1 0 0 1-3-3z"/><path d="M14.5 6.5 17 4l3 3-2.5 2.5"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
    bolt: '<path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12z"/>',
  };

  const KIND_ICON = { jupyter: "notebook", python: "play", bash: "terminal", vllm: "server",
    "host-asgi": "globe", "host-wsgi": "globe", "host-static": "globe" };
  const STATUS_LABEL = { starting: "starting", ready: "running", idle: "idle", stopping: "stopping",
    stopped: "stopped", failed: "failed" };
  const ACTIVE = new Set(["starting", "ready", "idle", "stopping"]);

  const LAUNCH = [
    ["GPU Hub", "rocket", "mgpux.openHub", "Jupyter, scripts, web bash or vLLM on any GPU", true],
    ["Dev Box", "vm", "mgpux.devUp", "GPU sandbox with SSH and snapshots"],
    ["Serve LLM", "server", "mgpux.serveDeploy", "OpenAI-compatible endpoint from a HF model"],
    ["Host App", "globe", "mgpux.hostApp", "Deploy ASGI / WSGI / static sites"],
    ["Compose", "package", "mgpux.composeUp", "docker-compose services on Modal"],
    ["Dashboard", "dashboard", "mgpux.openDashboard", "Full web console in your browser"],
  ];
  const TOOLS = [
    ["Manage dev box", "Open, pause, resume, sync or delete", "remote", "mgpux.devManage"],
    ["LLM endpoints", "Warm up, logs, restart, stop", "server", "mgpux.manageServe"],
    ["API keys", "Create and revoke serve keys", "key", "mgpux.serveKeysList"],
    ["Compute gateway", "Async API for CPU/GPU jobs", "gateway", "mgpux.manageGateway"],
    ["Compose sandbox", "Isolated sandboxes per service", "layers", "mgpux.composeSandbox"],
    ["Budgets", "Monthly limits per account", "shield", "mgpux.manageBudgets"],
    ["Billing reports", "Usage table, cycle summary, GPU rates", "table", "mgpux.billingReports"],
    ["Images", "Build and publish prebuilt images", "package", "mgpux.manageImages"],
    ["Kaggle & Colab", "Quota, kernels and runtimes", "cloud", "mgpux.otherClouds"],
    ["Probe hardware", "GPU, CPU and RAM metrics", "pulse", "mgpux.loadProbe"],
    ["CLI menu", "Every m-gpux command", "command", "mgpux.openCliMenu"],
    ["Stop all apps", "On the active account", "power", "mgpux.stopAll", true],
  ];

  // ── tiny DOM helpers (text always via textContent) ──────────
  function icon(name, cls) {
    const span = document.createElement("span");
    span.className = "ic" + (cls ? " " + cls : "");
    span.setAttribute("aria-hidden", "true");
    span.innerHTML = '<svg viewBox="0 0 24 24">' + (ICONS[name] || "") + "</svg>";
    return span;
  }
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "on") for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
      // CSSOM, not a style attribute: the webview CSP has no 'unsafe-inline'.
      else if (k === "style") el.style.cssText = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const run = (command, arg) => vscode.postMessage({ type: "run", command, arg });
  const save = () => vscode.setState(ui);
  const money = (n) => "$" + (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2));
  function age(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    if (m < 60) return m + "m";
    const hr = Math.floor(m / 60);
    if (hr < 48) return hr + "h " + (m % 60) + "m";
    return Math.floor(hr / 24) + "d";
  }
  function meter(used, limit, small) {
    const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
    const tone = pct >= 90 ? " bad" : pct >= 70 ? " warn" : "";
    return h("div", { class: "meter" + tone + (small ? " meter-sm" : ""), role: "meter",
      "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": pct.toFixed(0) },
      h("i", { style: "width:" + pct.toFixed(1) + "%" }));
  }
  function iconBtn(name, label, onClick, cls) {
    return h("button", { class: "icon-btn" + (cls ? " " + cls : ""), title: label, "aria-label": label,
      on: { click: (e) => { e.stopPropagation(); onClick(); } } }, icon(name, "ic-sm"));
  }
  function sectionHead(title, count, ...actions) {
    return h("div", { class: "section-head" }, h("h2", {}, title),
      count ? h("span", { class: "count" }, count) : null, h("span", { class: "spacer" }), actions);
  }

  // ── sections ────────────────────────────────────────────────
  function header() {
    const busy = state.busy || state.loading;
    return h("header", { class: "head" },
      h("span", { class: "logo", "aria-hidden": "true" }, icon("logo")),
      h("span", { class: "brand" }, "M-GPUX"),
      h("span", { class: "ver" }, "v" + state.version),
      h("span", { class: "spacer" }),
      h("button", { class: "icon-btn", title: "Refresh billing and sessions", "aria-label": "Refresh",
        disabled: busy, on: { click: () => vscode.postMessage({ type: "refresh" }) } },
        icon("refresh", "ic-sm" + (busy ? " spin" : ""))));
  }

  function hero() {
    const active = state.accounts.find((a) => a.active);
    if (!active) {
      return h("section", { class: "empty" }, icon("user"),
        h("div", {}, "Connect a Modal account to start launching GPUs."),
        h("button", { class: "btn", on: { click: () => run("mgpux.addAccount") } }, icon("plus", "ic-sm"), "Add account"));
    }
    let body;
    if (active.used !== null) {
      const pct = active.limit > 0 ? Math.min(100, (active.used / active.limit) * 100) : 0;
      body = [
        h("div", { class: "money" }, h("b", {}, money(active.remaining)),
          h("span", {}, "left of " + money(active.limit) + (active.budget ? " budget" : " credit"))),
        meter(active.used, active.limit),
        h("div", { class: "hero-foot" }, h("span", {}, money(active.used) + " used this month"),
          h("span", {}, pct.toFixed(0) + "%")),
      ];
    } else if (state.loading) {
      body = [h("div", { class: "skeleton", style: "height:24px;width:55%;margin-top:12px" }),
        h("div", { class: "skeleton", style: "height:6px;margin-top:10px" })];
    } else {
      body = [h("div", { class: "hero-foot", style: "margin-top:10px" },
        h("span", {}, "Billing unavailable"),
        h("a", { on: { click: () => run("mgpux.checkPython") } }, "Check Python"))];
    }
    return h("section", { class: "hero" },
      h("div", { class: "hero-top" },
        h("span", { class: "avatar", "aria-hidden": "true" }, active.name.slice(0, 2)),
        h("div", { class: "hero-name" }, h("div", { class: "kicker" }, "Active account"), h("strong", { title: active.name }, active.name)),
        h("button", { class: "chip-btn", title: "Switch Modal account", on: { click: () => run("mgpux.switchAccount") } },
          icon("swap", "ic-sm"), "Switch")),
      body);
  }

  function stats() {
    const live = state.sessions.filter((s) => s.status === "ready" || s.status === "starting").length;
    const known = state.accounts.filter((a) => a.used !== null);
    const spent = known.reduce((t, a) => t + a.used, 0);
    const left = known.reduce((t, a) => t + a.remaining, 0);
    const blank = known.length ? null : state.loading ? "…" : "—";
    return h("section", { class: "stats" },
      h("div", { class: "stat" + (live ? " live" : "") }, h("b", {}, live), h("span", {}, "Running")),
      h("div", { class: "stat", title: "Spent this month across " + known.length + " account(s)" },
        h("b", {}, blank || money(spent)), h("span", {}, "Spent")),
      h("div", { class: "stat", title: "Credit or budget left across all accounts" },
        h("b", {}, blank || money(left)), h("span", {}, "Left")));
  }

  function launch() {
    return h("section", { class: "section" }, sectionHead("Launch"),
      h("div", { class: "tiles" }, LAUNCH.map(([label, ic, cmd, tip, primary]) =>
        h("button", { class: "tile" + (primary ? " primary" : ""), title: tip, on: { click: () => run(cmd) } },
          icon(ic), h("span", {}, label)))));
  }

  function sessionCard(s) {
    const live = ACTIVE.has(s.status);
    const since = Date.now() - s.startedAt;
    const actions = [];
    if (s.hasUrl) actions.push(iconBtn("external", "Open in browser", () => run("mgpux.openSession", s.id)));
    actions.push(iconBtn("logs", "View logs", () => run("mgpux.viewSessionLogs", s.id)));
    if (s.hasVolume) {
      actions.push(iconBtn("down", "Pull workspace from Modal", () => run("mgpux.syncSession", s.id)));
      actions.push(iconBtn("up", "Push workspace to Modal", () => run("mgpux.pushSession", s.id)));
    }
    actions.push(h("span", { class: "spacer" }));
    actions.push(live
      ? iconBtn("stop", "Stop session", () => run("mgpux.stopSession", s.id), "danger")
      : iconBtn("trash", "Remove from list", () => run("mgpux.removeSession", s.id), "danger"));
    return h("article", { class: "session st-" + s.status + (live ? "" : " ended") },
      h("div", { class: "s-top" },
        h("span", { class: "s-kind" }, icon(KIND_ICON[s.kind] || "bolt")),
        h("div", { class: "s-title" },
          h("strong", {}, s.kind, h("span", { class: "gpu" }, s.gpu)),
          h("div", { class: "s-meta", title: s.appId || "" },
            s.profile, " · ", h("span", { "data-since": s.startedAt }, age(since)),
            s.restored ? " · restored" : "")),
        h("span", { class: "pill" + (s.status === "starting" || s.status === "stopping" ? " pulse" : "") },
          STATUS_LABEL[s.status] || s.status)),
      h("div", { class: "s-actions" }, actions));
  }

  function sessions() {
    const all = state.sessions;
    const live = all.filter((s) => ACTIVE.has(s.status));
    const ended = all.filter((s) => !ACTIVE.has(s.status));
    const head = sectionHead("Sessions", live.length || null,
      iconBtn("search", "Discover m-gpux apps running on Modal", () => run("mgpux.discoverApps")));
    if (!all.length) {
      return h("section", { class: "section" }, head,
        h("div", { class: "empty" }, icon("rocket"), h("div", {}, "No sessions yet."),
          h("button", { class: "btn", on: { click: () => run("mgpux.openHub") } }, "Open GPU Hub")));
    }
    const shown = ui.allSessions ? live.concat(ended) : live.concat(ended.slice(0, live.length ? 0 : 2));
    const hidden = all.length - shown.length;
    return h("section", { class: "section" }, head,
      h("div", { class: "list" }, shown.map(sessionCard)),
      hidden > 0 || ui.allSessions && ended.length
        ? h("button", { class: "more", on: { click: () => { ui.allSessions = !ui.allSessions; save(); render(); } } },
          ui.allSessions ? "Hide ended sessions" : "Show " + hidden + " ended session" + (hidden === 1 ? "" : "s"))
        : null);
  }

  function accounts() {
    if (!state.accounts.length) return null;
    const rows = state.accounts.map((a) =>
      h("button", { class: "acct" + (a.active ? " active" : ""), title: a.active ? "Active account" : "Switch to " + a.name,
        on: { click: () => { if (!a.active) run("mgpux.switchAccount", a.name); } } },
        h("span", { class: "radio", "aria-hidden": "true" }),
        h("div", { class: "acct-name" }, h("div", {}, a.name),
          a.used !== null ? meter(a.used, a.limit, true)
            : state.loading ? h("div", { class: "skeleton", style: "height:4px;margin-top:5px" }) : null),
        h("span", { class: "acct-amt" }, a.used !== null ? [h("b", {}, money(a.remaining)), " left"] : state.loading ? "" : "—")));
    return h("section", { class: "section" },
      sectionHead("Accounts", state.accounts.length,
        iconBtn("wallet", "Budgets", () => run("mgpux.manageBudgets")),
        iconBtn("plus", "Add account", () => run("mgpux.addAccount"))),
      h("div", { class: "list", style: "gap:2px" }, rows));
  }

  function presets() {
    const chips = state.presets.map((p) =>
      h("button", { class: "chip", title: "Run preset " + p.name + (p.compute ? " (" + p.compute + ")" : ""),
        on: { click: () => run("mgpux.runPreset", p.name) } },
        icon(p.action === "jupyter" ? "notebook" : "terminal", "ic-sm"), p.name,
        p.compute ? h("small", {}, p.compute) : null));
    chips.push(h("button", { class: "chip ghost", on: { click: () => run("mgpux.createPreset") } }, icon("plus", "ic-sm"), "New preset"));
    return h("section", { class: "section" }, sectionHead("Presets", state.presets.length || null), h("div", { class: "chips" }, chips));
  }

  function tools() {
    const details = h("details", { class: "tools section", open: ui.toolsOpen },
      h("summary", { class: "section-head" }, icon("chevron", "ic-sm chev"), h("h2", {}, "More tools")),
      h("div", { class: "tool-list" }, TOOLS.map(([title, sub, ic, cmd, danger]) =>
        h("button", { class: "tool" + (danger ? " danger" : ""), on: { click: () => run(cmd) } },
          icon(ic), h("div", {}, h("strong", {}, title), h("small", {}, sub))))));
    details.addEventListener("toggle", () => { ui.toolsOpen = details.open; save(); });
    return details;
  }

  function footer() {
    return h("footer", { class: "foot" },
      h("button", { class: "switch" + (state.autoSync ? " on" : ""), role: "switch", "aria-checked": String(state.autoSync),
        title: "Continuously sync the workspace with running sessions", on: { click: () => run("mgpux.toggleAutoSync") } },
        h("span", { class: "track" }), "Auto-sync"),
      h("span", { class: "spacer" }),
      iconBtn("tools", "Set up / update the m-gpux CLI", () => run("mgpux.setupCli")),
      iconBtn("external", "Modal usage page", () => run("mgpux.openBillingDashboard")));
  }

  function render() {
    if (!state) return;
    const scroll = window.scrollY;
    const parts = [header(), hero(), stats(), launch(), sessions(), accounts(), presets(), tools(), footer()];
    root.replaceChildren(...parts.filter(Boolean));
    root.setAttribute("aria-busy", String(!!(state.busy || state.loading)));
    window.scrollTo(0, scroll);
  }

  // Keep "12m" ages live without re-rendering the whole view.
  setInterval(() => {
    for (const el of document.querySelectorAll("[data-since]")) {
      el.textContent = age(Date.now() - Number(el.getAttribute("data-since")));
    }
  }, 15000);

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (msg && msg.type === "state") { state = msg.state; render(); }
  });
  vscode.postMessage({ type: "ready" });
})();
