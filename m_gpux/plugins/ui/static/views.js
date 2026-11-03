// Pages of the m-gpux console. Each view returns nodes built from the store;
// the shell re-renders the current view whenever data arrives.
import {
  act, api, button, card, closeDrawer, confirmDialog, copyText, copyable, empty, errorBanner, failure, fmt,
  formDialog, h, kpi, kv, logView, matches, meter, openDrawer, pageHead, searchBox, segmented, skeletonRows,
  statusPill, store, table, toast,
} from "./core.js";
import { icon } from "./icons.js";

const viewState = {};
const stateFor = (id, init) => (viewState[id] ??= init);

// ─── Shared helpers ──────────────────────────────────────────

/** Resolve a resource into {data} or a placeholder node (loading / error). */
function resolve(resource, pick, { lines = 4 } = {}) {
  const entry = store.need(resource);
  if (entry?.data) return { data: pick ? pick(entry.data) : entry.data, raw: entry.data };
  if (entry?.error) return { node: failure(entry.error, () => store.load(resource, { refresh: true })) };
  return { node: skeletonRows(lines) };
}

function scopedAccounts(rows) {
  return store.scope ? (rows || []).filter((a) => a.name === store.scope) : rows || [];
}

function workspaceOf(profile) {
  return store.peek("accounts")?.data?.accounts?.find((a) => a.name === profile)?.workspace;
}

function modalAppUrl(app) {
  const ws = workspaceOf(app.profile);
  if (!ws) return null;
  const base = `https://modal.com/apps/${encodeURIComponent(ws)}/main`;
  return app.state === "deployed" && app.name ? `${base}/deployed/${encodeURIComponent(app.name)}` : base;
}

const seg = (s) => encodeURIComponent(s);

function cliHint(command) {
  return h("button", { class: "copy", type: "button", dataset: { tip: "Copy command" }, onclick: () => copyText(command, "Command copied") },
    h("span", {}, "$ " + command), icon("copy"));
}

function accountCell(profile) {
  const ws = workspaceOf(profile);
  return h("div", {}, h("div", {}, profile || "—"), ws && h("div", { class: "cell-sub mono" }, ws));
}

function when(iso) {
  return iso ? h("span", { dataset: { tip: fmt.date(iso) } }, fmt.ago(iso)) : h("span", { class: "muted" }, "—");
}

// ─── Logs drawer ─────────────────────────────────────────────

async function showLogs({ kind, profile, id, title, cli }) {
  const body = h("div", { class: "stack" });
  const holder = h("div", {}, skeletonRows(8));
  const reload = button("Reload", { glyph: "refresh", size: "btn-sm" });
  const load = async () => {
    holder.replaceChildren(skeletonRows(8));
    try {
      const data = await api(`/api/${kind}/${seg(profile)}/${seg(id)}/logs?tail=300`);
      holder.replaceChildren(logView(data.lines));
    } catch (e) {
      holder.replaceChildren(failure(e, load));
    }
  };
  reload.addEventListener("click", load);
  body.append(h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } }, reload, cliHint(cli)), holder);
  openDrawer({ kicker: `${profile} · ${id}`, title: `Logs — ${title}`, body });
  load();
}

// ─── Overview ────────────────────────────────────────────────

function overview() {
  const acc = store.need("accounts");
  const apps = store.need("apps");
  const cons = store.need("containers");
  const sbx = store.need("sandboxes");
  const accounts = scopedAccounts(acc?.data?.accounts);
  const known = accounts.filter((a) => a.used !== null);
  const liveApps = (apps?.data?.apps || []).filter((a) => a.alive);
  const sum = (rows, key) => rows.reduce((t, r) => t + (r[key] || 0), 0);
  const unreachable = accounts.filter((a) => a.status === "error").length;
  const devBoxes = sbx?.data?.dev_boxes || [];

  const kpis = h("div", { class: "kpis" },
    kpi({ label: "Accounts", glyph: "accounts", loading: !acc?.data, value: fmt.count(accounts.length),
      sub: unreachable ? `${unreachable} unreachable` : `${known.length} with billing data` }),
    kpi({ label: "Credit left", glyph: "wallet", loading: !acc?.data, value: fmt.money(sum(known, "spendable")),
      sub: `of ${fmt.money(sum(known, "cap"), 0)} this month` }),
    kpi({ label: "Spent this month", glyph: "gauge", loading: !acc?.data, value: fmt.money(sum(known, "used")), sub: "metered usage" }),
    kpi({ label: "Live apps", glyph: "apps", loading: !apps?.data, value: fmt.count(liveApps.length),
      sub: `${liveApps.filter((a) => a.managed).length} launched by m-gpux` }),
    kpi({ label: "Containers", glyph: "containers", loading: !cons?.data, value: fmt.count(cons?.data?.containers?.length ?? 0), sub: "running now" }),
    kpi({ label: "Sandboxes", glyph: "sandboxes", loading: !sbx?.data, value: fmt.count(sbx?.data?.sandboxes?.length ?? 0),
      sub: `${devBoxes.length} dev box${devBoxes.length === 1 ? "" : "es"} tracked` }));

  const accountList = acc?.data
    ? accounts.length
      ? h("div", { class: "list" }, [...accounts].sort((a, b) => (b.spendable ?? -1) - (a.spendable ?? -1)).map((a) =>
        h("div", { class: "list-row account-row" },
          h("div", {},
            h("div", { class: "title" }, h("span", { class: "name" }, a.name), a.active && h("span", { class: "badge" }, "Active"),
              a.status === "error" && statusPill("error")),
            h("div", { class: "meta mono" }, a.workspace || "—")),
          h("div", { class: "meter-cell" }, meter(a.used, a.cap)),
          h("div", { class: "figure" }, fmt.money(a.spendable), h("small", {}, a.used === null ? "no data" : `${fmt.money(a.used)} used`)))))
      : empty({ glyph: "accounts", title: "No accounts", hint: "Add a Modal token to get started.", code: "m-gpux account add" })
    : acc?.error ? failure(acc.error) : skeletonRows(5);

  const appList = apps?.data
    ? liveApps.length
      ? h("div", { class: "list" }, liveApps.slice(0, 8).map((a) =>
        h("div", { class: "list-row" },
          h("div", {}, h("div", { class: "title" }, h("span", { class: "name" }, a.name || a.id), a.managed && h("span", { class: "badge neutral" }, "m-gpux")),
            h("div", { class: "meta" }, h("span", {}, a.profile), h("span", { class: "mono" }, a.id))),
          statusPill(a.state))))
      : empty({ glyph: "apps", title: "Nothing running", hint: "Live and deployed apps appear here.", code: "m-gpux hub" })
    : apps?.error ? failure(apps.error) : skeletonRows(4);

  const sessions = resolve("sessions", (d) => d.sessions.slice(0, 6), { lines: 3 });
  const recent = sessions.node || table([
    { label: "Session", render: (s) => h("div", { class: "cell-main" }, h("strong", {}, s.app_name || s.id)) },
    { label: "Account", render: (s) => s.profile || "—" },
    { label: "Compute", render: (s) => s.compute || "—" },
    { label: "State", render: (s) => statusPill(s.state) },
    { label: "Created", render: (s) => when(s.created_at) },
  ], sessions.data, { empty: empty({ glyph: "sessions", title: "No sessions yet", code: "m-gpux hub" }) });

  return [
    pageHead("Overview", store.scope ? `Account ${store.scope}` : "Every Modal account configured on this machine, at a glance."),
    errorBanner(apps?.data?.errors),
    kpis,
    h("div", { class: "grid-2" },
      card({ title: "Accounts", hint: "credit left this month", body: accountList, flush: true,
        actions: h("a", { class: "btn btn-ghost btn-sm", href: "#/accounts" }, "Manage", icon("arrow")) }),
      h("div", { class: "stack" },
        card({ title: "Live apps", hint: liveApps.length ? `${liveApps.length} running` : "", body: appList, flush: true,
          actions: h("a", { class: "btn btn-ghost btn-sm", href: "#/apps" }, "All apps", icon("arrow")) }))),
    card({ title: "Recent sessions", body: recent, flush: true,
      actions: h("a", { class: "btn btn-ghost btn-sm", href: "#/sessions" }, "All sessions", icon("arrow")) }),
  ];
}

// ─── Accounts ────────────────────────────────────────────────

const TOKEN_RE = /--token-id\s+(\S+)[\s\S]*?--token-secret\s+(\S+)/;
const PROFILE_RE = /--profile[=\s]+(\S+)/;

function addAccount() {
  const fillFromCommand = (event, inputs) => {
    const text = event.clipboardData?.getData("text") || "";
    const m = text.match(TOKEN_RE);
    if (!m) return;
    event.preventDefault();
    inputs.token_id.value = m[1];
    inputs.token_secret.value = m[2];
    const p = text.match(PROFILE_RE);
    if (p && !inputs.name.value) inputs.name.value = p[1].replace(/^["']|["']$/g, "");
  };
  formDialog({
    title: "Add a Modal account",
    description: "Create a token at modal.com/settings/tokens. It is verified with Modal before it is saved to ~/.modal.toml.",
    submitLabel: "Verify & add",
    fields: [
      { name: "name", label: "Account name", placeholder: "e.g. research", required: true, onPaste: fillFromCommand },
      { name: "token_id", label: "Token ID", placeholder: "ak-…", required: true, onPaste: fillFromCommand,
        help: "Tip: paste a full `modal token set …` command into any field to fill all three." },
      { name: "token_secret", label: "Token secret", type: "password", placeholder: "as-…", required: true, onPaste: fillFromCommand },
    ],
    onSubmit: (v) => api("/api/accounts", { method: "POST", body: v }),
  }).then((result) => {
    if (!result) return;
    store.invalidate("accounts");
    toast(`Added ${result.name} (workspace ${result.workspace})`);
  });
}

function editBudget(profile, current) {
  formDialog({
    title: profile ? `Budget for ${profile}` : "Default budget",
    description: profile
      ? "A monthly limit for this account. AUTO account selection and `budget check` respect it."
      : "Applies to every account without its own budget.",
    submitLabel: "Save budget",
    fields: [{ name: "limit", label: "Monthly limit (USD)", type: "number", step: "0.01", min: "0", value: current ?? "",
      placeholder: "30", help: "Leave empty to remove the budget." }],
    onSubmit: (v) => api("/api/budgets", { method: "PUT", body: { profile: profile || null, limit: v.limit === "" ? null : Number(v.limit) } }),
  }).then((ok) => { if (ok) { store.invalidate("accounts", "billing"); } });
}

async function activate(name, btn) {
  await act(btn, () => api(`/api/accounts/${seg(name)}/activate`, { method: "POST" }), { success: `${name} is now the active account`, invalidate: ["accounts"] });
}

async function removeAccount(name) {
  const ok = await confirmDialog({
    title: `Remove ${name}?`,
    message: "This deletes the profile and its token from ~/.modal.toml on this machine. Apps already running on Modal are not affected, and the token stays valid until you revoke it on modal.com.",
    confirmLabel: "Remove account", danger: true,
  });
  if (!ok) return;
  const removed = await act(null, () => api(`/api/accounts/${seg(name)}`, { method: "DELETE" }), { success: `Removed ${name}` });
  if (!removed) return;
  if (store.scope === name) store.setScope("");
  store.invalidate();
}

function accountDrawer(a) {
  openDrawer({
    kicker: "Account", title: a.name,
    body: [
      kv([
        ["Workspace", a.workspace ? copyable(a.workspace) : "—"],
        ["Status", statusPill(a.status === "ok" ? "connected" : a.status)],
        ["Active", a.active ? "Yes — `modal` commands use this account" : "No"],
        ["Spent this month", fmt.money(a.used)],
        ["Monthly cap", `${fmt.money(a.cap)}${a.budget === null ? " (free credit)" : " (budget)"}`],
        ["Left", fmt.money(a.spendable)],
        ["Error", a.error || undefined],
      ]),
      h("div", {}, meter(a.used, a.cap)),
      h("div", { class: "stack" }, cliHint(`m-gpux account switch "${a.name}"`), cliHint(`m-gpux billing usage --account "${a.name}"`)),
      a.workspace && h("a", { class: "btn", href: "https://modal.com/settings/usage", target: "_blank", rel: "noreferrer" }, icon("external"), "Open usage on modal.com"),
    ],
  });
}

function accountsView() {
  const { node, data } = resolve("accounts", (d) => d.accounts, { lines: 5 });
  const unreachable = (data || []).filter((a) => a.status === "error").map((a) => ({ profile: a.name, error: a.error }));
  const rows = data ? scopedAccounts(data) : [];
  return [
    pageHead("Accounts", "Modal profiles from ~/.modal.toml. Each has $30 of monthly credit unless you set a budget.", [
      button("Default budget", { glyph: "wallet", onClick: () => editBudget(null, store.peek("billing")?.data?.budgets?.["*"]) }),
      button("Add account", { glyph: "plus", kind: "btn-primary", onClick: addAccount }),
    ]),
    errorBanner(unreachable),
    card({
      title: "Profiles", hint: data ? `${rows.length} account${rows.length === 1 ? "" : "s"}` : "", flush: true,
      body: node || table([
        { label: "Account", render: (a) => h("div", { class: "cell-main" }, h("strong", {}, a.name), a.active && h("span", { class: "badge" }, "Active")) },
        { label: "Workspace", render: (a) => copyable(a.workspace) },
        { label: "Status", render: (a) => statusPill(a.status === "ok" ? "connected" : a.status) },
        { label: "Usage this month", render: (a) => h("div", { style: { minWidth: "150px" } }, meter(a.used, a.cap),
          h("div", { class: "cell-sub num", style: { marginTop: "5px" } }, a.used === null ? "unknown" : `${fmt.money(a.used)} of ${fmt.money(a.cap, 0)}`)) },
        { label: "Left", className: "num", render: (a) => fmt.money(a.spendable) },
        { label: "Budget", render: (a) => (a.budget === null ? h("span", { class: "muted" }, "Free credit") : fmt.money(a.budget)) },
        { label: "", className: "actions", render: (a) => [
          !a.active && h("button", { class: "btn btn-sm", type: "button", onclick: (e) => { e.stopPropagation(); activate(a.name, e.currentTarget); } }, "Make active"),
          h("button", { class: "btn btn-sm", type: "button", onclick: (e) => { e.stopPropagation(); editBudget(a.name, a.budget); } }, "Budget"),
          h("button", { class: "icon-btn btn-danger", type: "button", "aria-label": `Remove ${a.name}`, dataset: { tip: "Remove account" },
            onclick: (e) => { e.stopPropagation(); removeAccount(a.name); } }, icon("trash")),
        ] },
      ], rows, { onRow: accountDrawer, empty: empty({ glyph: "accounts", title: "No accounts yet", hint: "Add a Modal token to get started." }) }),
    }),
  ];
}

// ─── Apps ────────────────────────────────────────────────────

async function stopApp(a, btn) {
  const ok = await confirmDialog({
    title: `Stop ${a.name || a.id}?`,
    message: `Every container of this app on ${a.profile} is terminated and its GPUs are released. Deployed apps stop serving their URLs.`,
    confirmLabel: "Stop app", danger: true,
  });
  if (ok) await act(btn, () => api(`/api/apps/${seg(a.profile)}/${seg(a.id)}/stop`, { method: "POST" }),
    { success: `Stopped ${a.name || a.id}`, invalidate: ["apps", "containers"] });
}

function appsView(ctx) {
  const st = stateFor("apps", { filter: "live", query: "" });
  const { node, data, raw } = resolve("apps", (d) => d.apps, { lines: 6 });
  const all = data || [];
  const live = all.filter((a) => a.alive);
  const managed = all.filter((a) => a.managed && a.alive);
  const base = st.filter === "live" ? live : st.filter === "managed" ? managed : all;
  const rows = base.filter((a) => matches(a, st.query, ["name", "id", "profile", "state"]))
    .sort((a, b) => Number(b.alive) - Number(a.alive) || String(b.created_at).localeCompare(String(a.created_at)));
  const toolbar = h("div", { class: "toolbar" },
    segmented([
      { value: "live", label: "Live", count: live.length },
      { value: "managed", label: "m-gpux", count: managed.length },
      { value: "all", label: "All", count: all.length },
    ], st.filter, (v) => { st.filter = v; ctx.rerender(); }),
    searchBox("Filter by name, ID or account", st.query, (v) => { st.query = v; ctx.rerender(); }, "apps-q"));
  return [
    pageHead("Apps", "Modal apps across your accounts: deployed services, running and detached runs.", [
      h("a", { class: "btn", href: "#/containers" }, icon("containers"), "Containers"),
    ]),
    errorBanner(raw?.errors),
    card({
      title: "Apps", flush: true,
      body: node || [toolbar, table([
        { label: "App", render: (a) => h("div", {}, h("div", { class: "cell-main" }, h("strong", {}, a.name || "(unnamed)"),
          a.managed && h("span", { class: "badge neutral" }, "m-gpux")), h("div", { style: { marginTop: "2px" } }, copyable(a.id))) },
        { label: "Account", render: (a) => accountCell(a.profile) },
        { label: "State", render: (a) => statusPill(a.state) },
        { label: "Containers", className: "num", render: (a) => fmt.count(a.tasks) },
        { label: "Created", render: (a) => when(a.created_at) },
        { label: "", className: "actions", render: (a) => {
          const url = modalAppUrl(a);
          return [
            button("Logs", { glyph: "logs", size: "btn-sm", onClick: () => showLogs({ kind: "apps", profile: a.profile, id: a.id, title: a.name || a.id, cli: `modal app logs ${a.id} --follow` }) }),
            url && h("a", { class: "icon-btn", href: url, target: "_blank", rel: "noreferrer", "aria-label": "Open on modal.com", dataset: { tip: "Open on modal.com" } }, icon("external")),
            a.alive && h("button", { class: "btn btn-sm btn-danger", type: "button", onclick: (e) => stopApp(a, e.currentTarget) }, icon("stop"), "Stop"),
          ];
        } },
      ], rows, { empty: empty({ glyph: "apps", title: st.query ? "No matching apps" : st.filter === "all" ? "No apps" : "Nothing running",
        hint: st.query ? "Try a different filter." : "Launch a GPU session or deploy something.", code: st.query ? null : "m-gpux hub" }) })],
    }),
  ];
}

// ─── Containers ──────────────────────────────────────────────

async function stopContainer(c, btn) {
  const ok = await confirmDialog({
    title: "Stop this container?",
    message: `Container ${c.id} of ${c.app_name || c.app_id} gets SIGINT. For functions, its running inputs are rescheduled on other containers.`,
    confirmLabel: "Stop container", danger: true,
  });
  if (ok) await act(btn, () => api(`/api/containers/${seg(c.profile)}/${seg(c.id)}/stop`, { method: "POST" }),
    { success: "Container stopped", invalidate: ["containers", "apps"] });
}

function containersView(ctx) {
  const st = stateFor("containers", { query: "" });
  const { node, data, raw } = resolve("containers", (d) => d.containers, { lines: 5 });
  const rows = (data || []).filter((c) => matches(c, st.query, ["id", "app_name", "app_id", "profile"]));
  return [
    pageHead("Containers", "Every container running right now: functions, web endpoints and sandboxes. Each one is billing."),
    errorBanner(raw?.errors),
    card({
      title: "Running containers", hint: data ? `${data.length} running` : "", flush: true,
      body: node || [
        h("div", { class: "toolbar" }, searchBox("Filter by container, app or account", st.query, (v) => { st.query = v; ctx.rerender(); }, "containers-q")),
        table([
          { label: "Container", render: (c) => copyable(c.id) },
          { label: "App", render: (c) => h("div", {}, h("strong", {}, c.app_name || "—"), h("div", { class: "cell-sub mono" }, c.app_id)) },
          { label: "Account", render: (c) => accountCell(c.profile) },
          { label: "Started", render: (c) => (c.started_at ? when(c.started_at) : statusPill("initializing...", "Pending")) },
          { label: "", className: "actions", render: (c) => [
            button("Logs", { glyph: "logs", size: "btn-sm", onClick: () => showLogs({ kind: "containers", profile: c.profile, id: c.id, title: c.app_name || c.id, cli: `modal container logs ${c.id} --follow` }) }),
            h("button", { class: "btn btn-sm btn-danger", type: "button", onclick: (e) => stopContainer(c, e.currentTarget) }, icon("stop"), "Stop"),
          ] },
        ], rows, { empty: empty({ glyph: "containers", title: st.query ? "No matching containers" : "No containers running", hint: st.query ? "" : "Nothing is billing right now." }) }),
      ],
    }),
  ];
}

// ─── Sandboxes & dev boxes ───────────────────────────────────

async function terminateSandbox(s, btn) {
  const ok = await confirmDialog({
    title: "Terminate this sandbox?",
    message: s.dev_box
      ? `This is dev box “${s.dev_box}”. Unsaved work is lost — use \`m-gpux dev pause ${s.dev_box}\` to snapshot it instead.`
      : `Sandbox ${s.id} on ${s.profile} is terminated immediately.`,
    confirmLabel: "Terminate", danger: true,
  });
  if (ok) await act(btn, () => api(`/api/sandboxes/${seg(s.profile)}/${seg(s.id)}/terminate`, { method: "POST" }),
    { success: "Sandbox terminated", invalidate: ["sandboxes", "containers"] });
}

function devBoxTile(b) {
  return h("div", { class: "card tile" },
    h("div", { class: "tile-head" }, icon("terminal"), h("strong", {}, b.name), statusPill(b.state)),
    kv([["Compute", b.compute], ["Account", b.profile || "—"], ["Folder", b.local_dir ? h("span", { class: "mono" }, b.local_dir) : "—"],
      ["Snapshot", b.has_snapshot ? "Saved" : "None"], ["Started", b.started_at ? when(b.started_at) : "—"]]),
    h("div", { class: "stack", style: { gap: "6px" } },
      b.state === "running" ? [cliHint(`m-gpux dev code ${b.name}`), cliHint(`m-gpux dev pause ${b.name}`)]
        : [cliHint(`m-gpux dev resume ${b.name}`)]));
}

function sandboxesView() {
  const { node, raw } = resolve("sandboxes", null, { lines: 4 });
  const sandboxes = raw?.sandboxes || [];
  const boxes = raw?.dev_boxes || [];
  return [
    pageHead("Sandboxes", "Dev boxes managed by m-gpux, and every running Modal Sandbox on your accounts."),
    errorBanner(raw?.errors),
    card({
      title: "Dev boxes", hint: raw ? `${boxes.length} tracked on this machine` : "", flush: !node && !boxes.length,
      body: node || (boxes.length ? h("div", { class: "tiles" }, boxes.map(devBoxTile))
        : empty({ glyph: "terminal", title: "No dev boxes", hint: "A GPU box for the current folder, with SSH and pause/resume.", code: "m-gpux dev up" })),
    }),
    card({
      title: "Running sandboxes", hint: raw ? `${sandboxes.length} running` : "", flush: true,
      body: node ? skeletonRows(3) : table([
        { label: "Sandbox", render: (s) => copyable(s.id) },
        { label: "Account", render: (s) => accountCell(s.profile) },
        { label: "Dev box", render: (s) => (s.dev_box ? h("span", { class: "badge" }, s.dev_box) : h("span", { class: "muted" }, "—")) },
        { label: "", className: "actions", render: (s) => h("button", { class: "btn btn-sm btn-danger", type: "button", onclick: (e) => terminateSandbox(s, e.currentTarget) }, icon("power"), "Terminate") },
      ], sandboxes, { empty: empty({ glyph: "sandboxes", title: "No sandboxes running" }) }),
    }),
  ];
}

// ─── Sessions ────────────────────────────────────────────────

async function forgetSession(s) {
  const ok = await confirmDialog({ title: `Forget ${s.id}?`, message: "Removes it from the local list only. The Modal app is not stopped.", confirmLabel: "Forget" });
  if (ok) await act(null, () => api(`/api/sessions/${seg(s.id)}`, { method: "DELETE" }), { success: "Session forgotten", invalidate: ["sessions"] });
}

function sessionDrawer(s) {
  const note = {
    orphaned: "Recorded as running, but its account is no longer in ~/.modal.toml. Forget it to tidy the list.",
    ended: "Recorded as running, but no live app with this name exists on its account now.",
  }[s.state];
  openDrawer({
    kicker: s.id, title: s.app_name || s.description || s.id,
    body: [
      note && h("div", { class: "banner" }, icon("alert"), h("div", {}, note)),
      kv([["State", statusPill(s.state)], ["Kind", s.kind || "—"], ["Account", s.profile || "—"], ["Compute", s.compute || "—"],
        ["Python", s.python_version || "—"], ["Preset", s.preset || "—"], ["Description", s.description || "—"],
        ["Created", fmt.date(s.created_at)], ["Updated", fmt.date(s.updated_at)]]),
      h("div", { class: "stack", style: { gap: "6px" } },
        cliHint(`m-gpux sessions logs ${s.id}`), cliHint(`m-gpux sessions open ${s.id}`), cliHint(`m-gpux sessions stop ${s.id}`)),
      h("div", {}, button("Forget session", { glyph: "trash", kind: "btn-danger", onClick: () => { closeDrawer(); forgetSession(s); } })),
    ],
  });
}

function sessionsView(ctx) {
  const st = stateFor("sessions", { filter: "all", query: "" });
  const { node, data } = resolve("sessions", (d) => d.sessions, { lines: 6 });
  const all = data || [];
  const running = all.filter((s) => s.state === "running");
  const stale = all.filter((s) => s.state === "orphaned" || s.state === "ended");
  const groups = { all, running, stale, stopped: all.filter((s) => !running.includes(s) && !stale.includes(s)) };
  const base = groups[st.filter] || all;
  const rows = base.filter((s) => matches(s, st.query, ["id", "app_name", "profile", "compute", "kind", "description"]));
  return [
    pageHead("Sessions", "Hub, dev and deploy launches tracked by m-gpux on this machine."),
    card({
      title: "Sessions", flush: true,
      body: node || [
        h("div", { class: "toolbar" },
          segmented([{ value: "all", label: "All", count: all.length }, { value: "running", label: "Running", count: running.length },
            { value: "stale", label: "Needs cleanup", count: stale.length }, { value: "stopped", label: "Stopped", count: groups.stopped.length }],
          st.filter, (v) => { st.filter = v; ctx.rerender(); }),
          searchBox("Filter sessions", st.query, (v) => { st.query = v; ctx.rerender(); }, "sessions-q")),
        table([
          { label: "Session", render: (s) => h("div", {}, h("strong", {}, s.app_name || s.description || "—"), h("div", { class: "cell-sub mono" }, s.id)) },
          { label: "Kind", render: (s) => (s.kind ? h("span", { class: "chip" }, s.kind) : "—") },
          { label: "Account", render: (s) => s.profile || "—" },
          { label: "Compute", render: (s) => s.compute || "—" },
          { label: "Python", render: (s) => s.python_version || "—" },
          { label: "State", render: (s) => statusPill(s.state) },
          { label: "Created", render: (s) => when(s.created_at) },
        ], rows, { onRow: sessionDrawer, empty: empty({ glyph: "sessions", title: "No sessions", code: st.query ? null : "m-gpux hub" }) }),
      ],
    }),
  ];
}

// ─── Endpoints ───────────────────────────────────────────────

function endpointsView() {
  const { node, raw } = resolve("endpoints", null, { lines: 4 });
  if (node) return [pageHead("Endpoints", "Long-running services deployed by m-gpux."), node];
  const serve = raw.serve;
  const gw = raw.gateway;
  const serveCard = card({
    title: "LLM API", hint: "m-gpux serve",
    body: serve
      ? h("div", { class: "stack" }, kv([["URL", copyable(serve.url)], ...Object.entries(serve).filter(([k]) => !["url", "updated_at"].includes(k))
        .map(([k, v]) => [k.replace(/_/g, " "), String(v)]), ["Updated", fmt.date(serve.updated_at)]]),
        h("div", { class: "stack", style: { gap: "6px" } }, cliHint("m-gpux serve dashboard"), cliHint("m-gpux serve warmup")))
      : empty({ glyph: "bolt", title: "No LLM endpoint", hint: "An OpenAI-compatible API on vLLM, with API keys.", code: "m-gpux serve deploy" }),
  });
  const counts = gw?.job_counts || {};
  const gatewayCard = card({
    title: "Compute gateway", hint: "m-gpux gateway",
    body: gw
      ? h("div", { class: "stack" },
        kv([["URL", copyable(gw.url)], ["App", gw.app_name], ["Account", gw.profile],
          ["Tasks", h("div", { class: "chips" }, (gw.tasks || []).map((t) => h("span", { class: "chip" }, t)))],
          ["Jobs", Object.keys(counts).length ? h("div", { class: "chips" }, Object.entries(counts).map(([k, v]) => statusPill(k, `${v} ${k}`))) : "none yet"],
          ["Updated", fmt.date(gw.updated_at)]]),
        h("a", { class: "btn", href: `${gw.url}/docs`, target: "_blank", rel: "noreferrer" }, icon("external"), "API docs"))
      : empty({ glyph: "endpoints", title: "No gateway deployed", hint: "Expose declared CPU/GPU tasks as an authenticated job API.", code: "m-gpux gateway init" }),
  });
  return [
    pageHead("Endpoints", "Long-running services deployed by m-gpux. API keys are never shown here."),
    h("div", { class: "grid-2 even" }, serveCard, gatewayCard),
    gw?.recent_jobs?.length > 0 && card({
      title: "Recent gateway jobs", flush: true,
      body: table([
        { label: "Job", render: (j) => copyable(j.id) },
        { label: "Task", render: (j) => h("span", { class: "chip" }, j.task || "—") },
        { label: "Status", render: (j) => statusPill(j.status) },
        { label: "Submitted", render: (j) => when(j.submitted_at) },
        { label: "Finished", render: (j) => when(j.finished_at) },
      ], gw.recent_jobs),
    }),
  ];
}

// ─── Library ─────────────────────────────────────────────────

function libraryView() {
  const { node, raw } = resolve("library", null, { lines: 4 });
  return [
    pageHead("Presets & images", "Saved workloads you can replay, and prebuilt images for fast starts."),
    card({
      title: "Presets", hint: raw ? `${raw.presets.length} saved` : "", flush: true,
      body: node || table([
        { label: "Preset", render: (p) => h("strong", {}, p.name) },
        { label: "Action", render: (p) => (p.action ? h("span", { class: "chip" }, p.action) : "—") },
        { label: "Compute", render: (p) => p.compute_label || "—" },
        { label: "Account", render: (p) => p.profile || "AUTO" },
        { label: "Python", render: (p) => p.python_version || "—" },
        { label: "Updated", render: (p) => when(p.updated_at || p.created_at) },
        { label: "", className: "actions", render: (p) => cliHint(`m-gpux preset run ${p.name}`) },
      ], raw.presets, { empty: empty({ glyph: "library", title: "No presets", hint: "Save a Hub configuration to replay it in one command.", code: "m-gpux preset create" }) }),
    }),
    card({
      title: "Images", hint: raw ? `${raw.images.length} published` : "", flush: true,
      body: node ? skeletonRows(2) : table([
        { label: "Image", render: (i) => h("strong", { class: "mono" }, i.name) },
        { label: "Accounts", render: (i) => h("div", { class: "chips" }, (i.profiles || []).map((p) => h("span", { class: "chip" }, p))) },
        { label: "Python", render: (i) => i.python_version || i.python || "—" },
        { label: "Updated", render: (i) => when(i.updated_at || i.created_at) },
      ], raw.images, { empty: empty({ glyph: "library", title: "No published images", hint: "Bake dependencies once for near-instant starts.", code: "m-gpux image build torch" }) }),
    }),
  ];
}

// ─── Usage & pricing ─────────────────────────────────────────

/** Ranked horizontal bars: one hue, sorted, value printed at the end of each row. */
function rankedBars(rows, { value, label, format, tip }) {
  const max = Math.max(...rows.map(value), 0) || 1;
  return h("div", { class: "bars", role: "list" }, rows.map((r) => {
    const v = value(r);
    const text = tip(r);
    return h("div", { class: "bar-row", role: "listitem", tabindex: "0", "aria-label": text, dataset: { tip: text } },
      h("span", { class: "bar-label" }, label(r)),
      h("span", { class: "bar-track" }, h("span", { class: "bar-fill", style: { width: `${(v / max) * 100}%` } })),
      h("span", { class: "bar-value" }, format(v)));
  }));
}

function billingView() {
  const acc = resolve("accounts", (d) => d.accounts, { lines: 4 });
  const bill = resolve("billing", null, { lines: 6 });
  const spend = acc.data ? scopedAccounts(acc.data).filter((a) => a.used !== null).sort((a, b) => b.used - a.used) : [];
  const age = bill.raw?.rates_age_seconds;
  const budgets = bill.raw?.budgets || {};
  return [
    pageHead("Usage & pricing", "Metered spend this calendar month, your budgets, and what each GPU costs per hour.", [
      button("Default budget", { glyph: "wallet", onClick: () => editBudget(null, budgets["*"]) }),
      h("a", { class: "btn", href: "https://modal.com/settings/usage", target: "_blank", rel: "noreferrer" }, icon("external"), "modal.com usage"),
    ]),
    h("div", { class: "grid-2 even" },
      card({
        title: "Spend this month", hint: "by account",
        body: acc.node || (spend.length && !spend.some((a) => a.used >= 0.005)
          ? empty({ glyph: "gauge", title: "No spend yet this month", hint: `All ${spend.length} accounts are at ${fmt.money(0)} of their credit.` })
          : spend.length ? rankedBars(spend, {
          value: (a) => a.used, label: (a) => a.name, format: (v) => fmt.money(v),
          tip: (a) => `${a.name}: ${fmt.money(a.used)} of ${fmt.money(a.cap)} (${fmt.pct(a.used / a.cap)})`,
        }) : empty({ glyph: "gauge", title: "No billing data", hint: "Billing needs a workspace owner token." })),
      }),
      card({
        title: "Budgets", hint: budgets["*"] !== undefined ? `default ${fmt.money(budgets["*"])}` : "default: free credit",
        flush: true,
        body: acc.node || table([
          { label: "Account", render: (a) => h("strong", {}, a.name) },
          { label: "Cap", className: "num", render: (a) => fmt.money(a.cap, 0) },
          { label: "Source", render: (a) => (a.budget === null ? h("span", { class: "muted" }, "Free credit") : budgets[a.name] !== undefined ? "Own budget" : "Default budget") },
          { label: "", className: "actions", render: (a) => button("Edit", { size: "btn-sm", onClick: () => editBudget(a.name, budgets[a.name]) }) },
        ], scopedAccounts(acc.data)),
      })),
    card({
      title: "GPU prices", hint: age === null || age === undefined ? "built-in snapshot" : `live rates, fetched ${fmt.ago(new Date(Date.now() - age * 1000).toISOString())}`,
      body: bill.node || h("div", { class: "stack" },
        rankedBars([...bill.raw.gpu_rates].sort((a, b) => b.hourly - a.hourly), {
          value: (r) => r.hourly, label: (r) => r.gpu.replace(/_/g, "-"), format: (v) => `${fmt.money(v)}/h`,
          tip: (r) => `${r.gpu.replace(/_/g, "-")}: ${fmt.money(r.hourly)} per GPU-hour`,
        }),
        h("div", { style: { display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" } },
          h("span", { class: "muted" }, `CPU ${fmt.money(bill.raw.cpu_hour, 4)} per core-hour · memory ${fmt.money(bill.raw.mem_gib_hour, 4)} per GiB-hour`),
          h("span", { style: { marginLeft: "auto" } }, cliHint("m-gpux billing rates --refresh")))),
    }),
  ];
}

// ─── Kaggle ──────────────────────────────────────────────────

const hours = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)} h`);

function notInstalled(name, command) {
  return card({ title: `${name} CLI not found`, body: empty({ glyph: "alert", title: `Install the ${name} CLI`, hint: "Then refresh this page.", code: command }) });
}

function kaggleView() {
  const { node, raw } = resolve("kaggle", null, { lines: 6 });
  const head = pageHead("Kaggle", "Accounts in ~/.kaggle/zoo.json: weekly accelerator hours, running kernels and free GPU slots.", [
    cliHint("m-gpux kaggle push <folder> --as auto --wait"),
  ]);
  if (node) return [head, node];
  if (!raw.installed) return [head, notInstalled("Kaggle", "pip install kaggle")];
  const rows = raw.accounts;
  const ok = rows.filter((r) => !r.error);
  const gpu = (r) => r.quota?.gpu;
  const left = ok.reduce((t, r) => t + (gpu(r)?.remaining || 0), 0);
  const total = ok.reduce((t, r) => t + (gpu(r)?.total || 0), 0);
  const live = ok.flatMap((r) => (r.live || []).map((k) => ({ ...k, account: r.name })));
  const freeSlots = ok.reduce((t, r) => t + Math.max(0, raw.gpu_slots - (r.live || []).length), 0);
  const resets = ok.map((r) => gpu(r)?.refresh_at).filter(Boolean).sort()[0];
  return [
    head,
    errorBanner(rows.filter((r) => r.error).map((r) => ({ profile: r.name, error: r.error }))),
    h("div", { class: "kpis" },
      kpi({ label: "Accounts", glyph: "accounts", value: fmt.count(rows.length), sub: `${ok.length} reachable` }),
      kpi({ label: "GPU hours left", glyph: "gauge", value: hours(left), sub: `of ${hours(total)} this week` }),
      kpi({ label: "Free GPU slots", glyph: "bolt", value: fmt.count(freeSlots), sub: `${raw.gpu_slots} per account` }),
      kpi({ label: "Live kernels", glyph: "play", value: fmt.count(live.length), sub: "running or queued" }),
      kpi({ label: "AUTO would use", glyph: "user", value: raw.auto || "—", sub: resets ? `quota resets ${fmt.date(resets)}` : "" })),
    card({
      title: "Accounts", hint: raw.zoo_path, flush: true,
      body: table([
        { label: "Account", render: (r) => h("div", {}, h("div", { class: "cell-main" }, h("strong", {}, r.name), r.default && h("span", { class: "badge neutral" }, "machine"),
          r.name === raw.auto && h("span", { class: "badge" }, "AUTO")), r.team && h("div", { class: "cell-sub" }, r.team)) },
        { label: "Status", render: (r) => statusPill(r.error ? "error" : "connected") },
        { label: "GPU this week", render: (r) => gpu(r) ? h("div", { style: { minWidth: "150px" } }, meter(gpu(r).used, gpu(r).total, hours),
          h("div", { class: "cell-sub num", style: { marginTop: "5px" } }, `${hours(gpu(r).remaining)} left of ${hours(gpu(r).total)}`)) : "—" },
        { label: "TPU left", className: "num", render: (r) => hours(r.quota?.tpu?.remaining) },
        { label: "GPU slots", render: (r) => r.error ? "—" : `${Math.max(0, raw.gpu_slots - (r.live || []).length)} free / ${raw.gpu_slots}` },
        { label: "Live kernels", render: (r) => (r.live || []).length
          ? h("div", { class: "chips" }, r.live.map((k) => h("span", { class: "chip", dataset: { tip: k.state } }, k.ref.split("/")[1])))
          : h("span", { class: "muted" }, "none") },
        { label: "Note", render: (r) => h("span", { class: "muted", dataset: r.note ? { tip: r.note } : undefined }, r.note ? (r.note.length > 40 ? r.note.slice(0, 39) + "…" : r.note) : "") },
      ], rows, { empty: empty({ glyph: "accounts", title: "No Kaggle accounts", code: "m-gpux kaggle add <KGAT_token>" }) }),
    }),
    card({
      title: "Running & queued kernels", hint: live.length ? `${live.length} live` : "", flush: true,
      body: table([
        { label: "Kernel", render: (k) => h("a", { href: `https://www.kaggle.com/code/${k.ref}`, target: "_blank", rel: "noreferrer", class: "mono" }, k.ref) },
        { label: "Account", render: (k) => k.account },
        { label: "State", render: (k) => statusPill(k.state.toLowerCase()) },
        { label: "", className: "actions", render: (k) => cliHint(`m-gpux kaggle watch ${k.ref} --as ${k.account}`) },
      ], live, { empty: empty({ glyph: "play", title: "No kernels running", hint: "Kernels run in the last 14 hours that are still running or queued show up here." }) }),
    }),
  ];
}

// ─── Colab ───────────────────────────────────────────────────

async function stopRuntime(account, session, btn) {
  const ok = await confirmDialog({
    title: `Stop runtime ${session}?`, message: `The Colab VM on account ${account} is released; files on it are lost.`,
    confirmLabel: "Stop runtime", danger: true,
  });
  if (ok) await act(btn, () => api(`/api/colab/${seg(account)}/sessions/${seg(session)}/stop`, { method: "POST" }),
    { success: `Stopped ${session}`, invalidate: ["colab"] });
}

function colabView() {
  const { node, raw } = resolve("colab", null, { lines: 4 });
  const head = pageHead("Colab", "Google accounts used through google-colab-cli: compute units, burn rate and live runtimes.", [
    cliHint("m-gpux colab run train.py --gpu A100 --as auto"),
  ]);
  if (node) return [head, node];
  if (!raw.installed) return [head, notInstalled("Colab", "uv tool install google-colab-cli")];
  const rows = raw.accounts;
  const live = rows.filter((r) => r.usage);
  const units = live.reduce((t, r) => t + r.usage.balance, 0);
  const rate = live.reduce((t, r) => t + r.usage.rate, 0);
  const runtimes = rows.flatMap((r) => r.sessions.map((s) => ({ ...s, account: r.name })));
  const loginState = (r) => (!r.logged_in ? "login" : r.error && /expired|login/.test(r.error) ? "relogin" : r.error ? "error" : "connected");
  return [
    head,
    h("div", { class: "kpis" },
      kpi({ label: "Accounts", glyph: "accounts", value: fmt.count(rows.length), sub: `${live.length} ready` }),
      kpi({ label: "Compute units", glyph: "wallet", value: units.toFixed(2), sub: "left across accounts" }),
      kpi({ label: "Burn rate", glyph: "gauge", value: `${rate.toFixed(2)}/h`, sub: rate ? `≈ ${(units / rate).toFixed(0)} h at this rate` : "nothing running" }),
      kpi({ label: "Runtimes", glyph: "sandboxes", value: fmt.count(runtimes.length), sub: "live VMs" }),
      kpi({ label: "AUTO would use", glyph: "user", value: raw.auto || "—", sub: "most units left" })),
    card({
      title: "Google accounts", flush: true,
      body: table([
        { label: "Account", render: (r) => h("div", {}, h("div", { class: "cell-main" }, h("strong", {}, r.name), r.name === raw.auto && h("span", { class: "badge" }, "AUTO")),
          h("div", { class: "cell-sub mono" }, r.home)) },
        { label: "Login", render: (r) => statusPill(loginState(r)) },
        { label: "Compute units", className: "num", render: (r) => (r.usage ? r.usage.balance.toFixed(2) : "—") },
        { label: "Rate", className: "num", render: (r) => (r.usage ? `${r.usage.rate.toFixed(2)}/h` : "—") },
        { label: "Runtimes", className: "num", render: (r) => (r.usage ? fmt.count(r.sessions.length) : "—") },
        { label: "", className: "actions", render: (r) => (loginState(r) === "connected" ? null : cliHint(`m-gpux colab login ${r.name}`)) },
      ], rows),
    }),
    card({
      title: "Live runtimes", hint: runtimes.length ? `${runtimes.length} running` : "", flush: true,
      body: table([
        { label: "Runtime", render: (s) => h("strong", {}, s.name || "(no local name)") },
        { label: "Account", render: (s) => s.account },
        { label: "Hardware", render: (s) => h("span", { class: "chip" }, s.hardware) },
        { label: "Shape", render: (s) => s.shape },
        { label: "", className: "actions", render: (s) => s.name
          ? h("button", { class: "btn btn-sm btn-danger", type: "button", onclick: (e) => stopRuntime(s.account, s.name, e.currentTarget) }, icon("stop"), "Stop")
          : null },
      ], runtimes, { empty: empty({ glyph: "sandboxes", title: "No runtimes", hint: "Start one on the account with the most units left.", code: "m-gpux colab new -s trainer --gpu A100" }) }),
    }),
  ];
}

// ─── Volumes ─────────────────────────────────────────────────

function bytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
}

const quoteArg = (s) => (/[\s"']/.test(s) ? `"${s}"` : s);

function browseVolume(v, path = "/") {
  const listing = h("div", {}, skeletonRows(6));
  const parts = path.split("/").filter(Boolean);
  const crumbs = h("div", { class: "chips" },
    h("button", { class: "chip", type: "button", onclick: () => browseVolume(v, "/") }, v.name),
    parts.map((part, i) => [h("span", { class: "muted" }, "/"),
      h("button", { class: "chip", type: "button", onclick: () => browseVolume(v, "/" + parts.slice(0, i + 1).join("/")) }, part)]));
  openDrawer({
    kicker: `${v.profile} · volume`, title: v.name,
    body: [crumbs, listing, h("div", { class: "stack", style: { gap: "6px" } },
      cliHint(`m-gpux volume get ${v.name} ${path} ./${v.name} --account ${quoteArg(v.profile)}`),
      cliHint(`m-gpux volume du ${v.name} --account ${quoteArg(v.profile)}`))],
  });
  api(`/api/volumes/${seg(v.profile)}/${seg(v.name)}/files?path=${encodeURIComponent(path)}`).then((res) => {
    const name = (e) => e.path.replace(/\/$/, "").split("/").pop();
    listing.replaceChildren(table([
      { label: "Name", render: (e) => h("div", { class: "cell-main" }, icon(e.dir ? "folder" : "file"), h("span", { class: e.dir ? "" : "mono" }, name(e) + (e.dir ? "/" : ""))) },
      { label: "Size", className: "num", render: (e) => (e.dir ? "" : bytes(e.size)) },
      { label: "Modified", render: (e) => (e.mtime ? when(new Date(e.mtime * 1000).toISOString()) : "—") },
    ], res.entries, {
      onRow: (e) => { if (e.dir) browseVolume(v, "/" + e.path.replace(/^\/|\/$/g, "")); },
      empty: empty({ glyph: "folder", title: "Empty folder" }),
    }));
  }).catch((err) => listing.replaceChildren(failure(err, () => browseVolume(v, path))));
}

function volumesView(ctx) {
  const st = stateFor("volumes", { query: "" });
  const { node, raw } = resolve("volumes", null, { lines: 6 });
  const all = raw?.volumes || [];
  const rows = all.filter((v) => matches(v, st.query, ["name", "profile"]));
  const accounts = new Set(all.map((v) => v.profile));
  const cache = all.filter((v) => v.name === "m-gpux-hf-cache").length;
  return [
    pageHead("Volumes", "Persistent storage on every account: workspaces, run outputs, model caches. Click one to browse it.", [
      cliHint("m-gpux volume list --all"),
    ]),
    errorBanner(raw?.errors),
    h("div", { class: "kpis" },
      kpi({ label: "Volumes", glyph: "volumes", value: raw ? fmt.count(all.length) : "…", sub: `on ${accounts.size} account(s)` }),
      kpi({ label: "Run outputs", glyph: "runs", value: raw ? fmt.count(all.filter((v) => /-outputs$/.test(v.name)).length) : "…", sub: "from m-gpux up / sweep" }),
      kpi({ label: "Shared HF cache", glyph: "layers", value: raw ? `${cache}/${accounts.size}` : "…", sub: "accounts with m-gpux-hf-cache" })),
    card({
      title: "Volumes", flush: true,
      body: node || [
        h("div", { class: "toolbar" }, searchBox("Filter volumes", st.query, (v) => { st.query = v; ctx.rerender(); }, "volumes-q")),
        table([
          { label: "Volume", render: (v) => h("div", { class: "cell-main" }, icon("volumes"), h("strong", { class: "mono" }, v.name),
            v.name === "m-gpux-hf-cache" && h("span", { class: "badge" }, "HF cache"), /-outputs$/.test(v.name) && h("span", { class: "badge neutral" }, "outputs")) },
          { label: "Account", render: (v) => accountCell(v.profile) },
          { label: "", className: "actions", render: () => h("span", { class: "muted" }, "Browse →") },
        ], rows, { onRow: (v) => browseVolume(v), empty: empty({ glyph: "volumes", title: "No volumes", hint: "Upload data once, mount it in any task.", code: "m-gpux volume put my-data ./data" }) }),
      ],
    }),
  ];
}

// ─── Runs ────────────────────────────────────────────────────

const costText = (v) => (v === null || v === undefined ? "—" : v > 0 && v < 0.001 ? "<$0.001" : fmt.money(v, v < 1 ? 3 : 2));

const runState = (r) => ({ done: "succeeded", failed: "failed", running: "running", cancelled: "cancelled" }[r.status] || r.status);

function metricsText(result) {
  if (!result || typeof result !== "object") return "";
  return Object.entries(result).slice(0, 4).map(([k, v]) => `${k}=${typeof v === "number" ? +v.toPrecision(4) : v}`).join(", ");
}

const paramsText = (p) => Object.entries(p || {}).map(([k, v]) => `${k}=${v}`).join(", ") || "—";

function runDrawer(r) {
  const account = r.account && r.account !== "env" ? ` --account ${quoteArg(r.account)}` : "";
  openDrawer({
    kicker: `${r.kind} · ${r.id}`, title: `${r.project}/${r.task}`,
    body: [
      kv([["Status", statusPill(runState(r))], ["Jobs", `${r.ok}/${r.jobs} succeeded`], ["Compute", r.gpu || "—"], ["Account", r.account || "—"],
        ["Compute time", `${Math.round(r.compute_seconds || 0)} s`], ["Estimated cost", costText(r.cost_estimate)],
        ["Started", fmt.date(r.started_at)], ["Finished", fmt.date(r.finished_at)]]),
      r.best && h("div", { class: "banner" }, icon("ok"), h("div", {}, h("strong", {}, "Best: "), `${paramsText(r.best.params)} → ${metricsText(r.best.result)}`)),
      table([
        { label: "#", className: "num", render: (x) => String(x.index ?? "") },
        { label: "Params", render: (x) => h("span", { class: "mono" }, paramsText(x.params)) },
        { label: "Exit", render: (x) => statusPill(x.exit_code === 0 ? "succeeded" : "failed", String(x.exit_code)) },
        { label: "Time", className: "num", render: (x) => `${x.seconds ?? "?"} s` },
        { label: r.metric ? `Result (${r.metric})` : "Result", render: (x) => h("span", { class: "mono" }, metricsText(x.result) || "—") },
      ], r.results, { empty: empty({ glyph: "runs", title: "No results recorded" }) }),
      h("div", { class: "stack", style: { gap: "6px" } },
        cliHint(`m-gpux runs show ${r.id}`),
        r.output_volume && cliHint(`m-gpux volume get ${r.output_volume} /${r.id} ./outputs${account}`)),
    ],
  });
}

function runsView(ctx) {
  const st = stateFor("runs", { filter: "all" });
  const { node, raw } = resolve("runs", null, { lines: 5 });
  const all = raw?.runs || [];
  const groups = { all, sweep: all.filter((r) => r.kind === "sweep"), up: all.filter((r) => r.kind !== "sweep"), failed: all.filter((r) => r.status === "failed") };
  const rows = groups[st.filter] || all;
  const cost = all.reduce((t, r) => t + (r.cost_estimate || 0), 0);
  const seconds = all.reduce((t, r) => t + (r.compute_seconds || 0), 0);
  const finished = all.filter((r) => r.status === "done" || r.status === "failed");
  return [
    pageHead("Runs", "Results of m-gpux up, sweep and run: per-job exit codes, timings, reported metrics and cost.", [
      cliHint("m-gpux sweep train --grid lr=1e-4,3e-4"),
    ]),
    h("div", { class: "kpis" },
      kpi({ label: "Runs", glyph: "runs", value: raw ? fmt.count(all.length) : "…", sub: `${groups.sweep.length} sweeps` }),
      kpi({ label: "Success rate", glyph: "ok", value: finished.length ? fmt.pct(finished.filter((r) => r.status === "done").length / finished.length) : "—", sub: `${finished.length} finished` }),
      kpi({ label: "Compute", glyph: "gauge", value: raw ? `${(seconds / 3600).toFixed(2)} h` : "…", sub: "across all jobs" }),
      kpi({ label: "Estimated cost", glyph: "wallet", value: raw ? costText(cost) : "…", sub: "from cached rates" })),
    card({
      title: "Runs", flush: true,
      body: node || [
        h("div", { class: "toolbar" }, segmented([
          { value: "all", label: "All", count: all.length }, { value: "sweep", label: "Sweeps", count: groups.sweep.length },
          { value: "up", label: "Single", count: groups.up.length }, { value: "failed", label: "Failed", count: groups.failed.length },
        ], st.filter, (v) => { st.filter = v; ctx.rerender(); })),
        table([
          { label: "Run", render: (r) => h("div", {}, h("strong", {}, `${r.project}/${r.task}`), h("div", { class: "cell-sub mono" }, r.id)) },
          { label: "Kind", render: (r) => h("span", { class: "chip" }, r.kind) },
          { label: "Status", render: (r) => statusPill(runState(r)) },
          { label: "Jobs", className: "num", render: (r) => `${r.ok}/${r.jobs}` },
          { label: "Compute", render: (r) => r.gpu || "—" },
          { label: "Best", render: (r) => (r.best ? h("span", { class: "mono" }, metricsText(r.best.result)) : h("span", { class: "muted" }, "—")) },
          { label: "Cost", className: "num", render: (r) => costText(r.cost_estimate) },
          { label: "Started", render: (r) => when(r.started_at) },
        ], rows, { onRow: runDrawer, empty: empty({ glyph: "runs", title: "No runs yet", hint: "Declare tasks in mgpux.toml, then run or sweep them.", code: "m-gpux init" }) }),
      ],
    }),
  ];
}

// ─── Sync & alerts ───────────────────────────────────────────

function coverage(rows, profiles, has, label) {
  const tick = (ok) => (ok ? h("span", { class: "pill pill-good" }, icon("check"), "yes") : h("span", { class: "muted" }, "—"));
  return h("div", { class: "table-wrap" }, h("table", { class: "table" },
    h("thead", {}, h("tr", {}, h("th", { scope: "col" }, label), profiles.map((p) => h("th", { scope: "col" }, p)))),
    h("tbody", {}, rows.map((row) => h("tr", {}, h("td", {}, h("strong", { class: "mono" }, row.name)),
      profiles.map((p) => h("td", {}, tick(has(row, p)))))))));
}

async function testAlerts(btn) {
  await act(btn, async () => {
    const res = await api("/api/notify/test", { method: "POST" });
    if (!res.results.length) throw new Error("No channel is configured");
    const bad = res.results.filter((r) => !r.ok);
    if (bad.length) throw new Error(`Failed: ${bad.map((r) => `${r.channel} (${r.error})`).join(", ")}`);
  }, { success: "Test notification sent" });
}

function syncView() {
  const secrets = resolve("secrets", null, { lines: 4 });
  const library = resolve("library", null, { lines: 2 });
  const alerts = resolve("notify", null, { lines: 2 });
  const profiles = secrets.raw?.profiles || [];
  const rows = secrets.raw?.secrets || [];
  const missing = rows.reduce((t, s) => t + profiles.length - s.present.length, 0);
  const channels = alerts.raw?.channels || [];
  return [
    pageHead("Sync & alerts", "Keep Secrets and images on every workspace, and get pinged when runs finish or credit runs low."),
    errorBanner(secrets.raw?.errors),
    card({
      title: "Secrets per workspace", hint: secrets.raw ? (missing ? `${missing} missing` : "in sync") : "", flush: true,
      actions: [cliHint("m-gpux secrets sync hf HF_TOKEN --to all")],
      body: secrets.node || (rows.length
        ? coverage(rows, profiles, (s, p) => s.present.includes(p), "Secret")
        : empty({ glyph: "key", title: "No Secrets yet", hint: "Values come from your environment or a .env file and are never shown here.", code: "m-gpux secrets sync hf HF_TOKEN --to all" })),
    }),
    card({
      title: "Images per workspace", hint: "as recorded by m-gpux", flush: true,
      actions: [cliHint("m-gpux image status")],
      body: library.node || ((library.raw.images || []).length && profiles.length
        ? coverage(library.raw.images, profiles, (i, p) => (i.profiles || []).includes(p), "Image")
        : empty({ glyph: "library", title: "No published images", code: "m-gpux image build torch --pip torch --all" })),
    }),
    card({
      title: "Notifications", hint: channels.length ? `${channels.length} channel(s)` : "",
      actions: channels.length ? [button("Send test", { glyph: "bell", size: "btn-sm", onClick: (e) => testAlerts(e.currentTarget) })] : [],
      flush: channels.length > 0,
      body: alerts.node || (channels.length
        ? table([
          { label: "Channel", render: (c) => h("div", { class: "cell-main" }, icon("bell"), h("strong", {}, c.name)) },
          { label: "Type", render: (c) => h("span", { class: "chip" }, c.type) },
          { label: "Target", render: (c) => h("span", { class: "mono muted" }, c.target) },
          { label: "Events", render: (c) => h("div", { class: "chips" }, c.events.map((e) => h("span", { class: "chip" }, e === "*" ? "all events" : e))) },
        ], channels)
        : empty({ glyph: "bell", title: "No notification channels", hint: "Discord, Slack, Telegram, ntfy or any webhook; then run m-gpux notify watch.", code: "m-gpux notify add discord" })),
    }),
  ];
}

// ─── Route table ─────────────────────────────────────────────

const aliveApps = () => store.peek("apps")?.data?.apps?.filter((a) => a.alive).length;

export const ROUTES = [
  { id: "overview", label: "Overview", glyph: "overview", group: null, refresh: ["accounts", "apps", "containers", "sandboxes", "sessions"], render: overview },
  { id: "accounts", label: "Accounts", glyph: "accounts", group: "Workspaces", refresh: ["accounts", "billing"], render: accountsView,
    count: () => store.peek("accounts")?.data?.accounts?.length },
  { id: "apps", label: "Apps", glyph: "apps", group: "Compute", refresh: ["apps", "accounts"], render: appsView, count: aliveApps },
  { id: "containers", label: "Containers", glyph: "containers", group: "Compute", refresh: ["containers", "accounts"], render: containersView,
    count: () => store.peek("containers")?.data?.containers?.length },
  { id: "sandboxes", label: "Sandboxes", glyph: "sandboxes", group: "Compute", refresh: ["sandboxes", "accounts"], render: sandboxesView,
    count: () => store.peek("sandboxes")?.data?.sandboxes?.length },
  { id: "sessions", label: "Sessions", glyph: "sessions", group: "Workloads", refresh: ["sessions"], render: sessionsView,
    count: () => store.peek("sessions")?.data?.sessions?.filter((s) => s.state === "running").length },
  { id: "endpoints", label: "Endpoints", glyph: "endpoints", group: "Workloads", refresh: ["endpoints"], render: endpointsView },
  { id: "runs", label: "Runs", glyph: "runs", group: "Workloads", refresh: ["runs"], render: runsView,
    count: () => store.peek("runs")?.data?.runs?.filter((r) => r.status === "running").length },
  { id: "library", label: "Presets & images", glyph: "library", group: "Workloads", refresh: ["library"], render: libraryView },
  { id: "volumes", label: "Volumes", glyph: "volumes", group: "Storage & sync", refresh: ["volumes"], render: volumesView,
    count: () => store.peek("volumes")?.data?.volumes?.length },
  { id: "sync", label: "Sync & alerts", glyph: "sync", group: "Storage & sync", refresh: ["secrets", "library", "notify"], render: syncView },
  { id: "billing", label: "Usage & pricing", glyph: "billing", group: "Cost", refresh: ["accounts", "billing"], render: billingView },
  { id: "kaggle", label: "Kaggle", glyph: "gauge", group: "Other clouds", refresh: ["kaggle"], render: kaggleView,
    count: () => store.peek("kaggle")?.data?.accounts?.reduce((t, r) => t + (r.live || []).length, 0) },
  { id: "colab", label: "Colab", glyph: "bolt", group: "Other clouds", refresh: ["colab"], render: colabView,
    count: () => store.peek("colab")?.data?.accounts?.reduce((t, r) => t + r.sessions.length, 0) },
];

export const actions = { addAccount, editBudget };
