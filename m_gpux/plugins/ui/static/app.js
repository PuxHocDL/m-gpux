// Shell of the m-gpux console: token bootstrap, router, nav, scope, theme,
// auto-refresh, keyboard shortcuts and the command palette.
import { $, closeDrawer, empty, fmt, h, hasToken, installTooltips, prefs, saveToken, store } from "./core.js";
import { hydrateIcons, icon } from "./icons.js";
import { ROUTES, actions } from "./views.js";

const AUTO_REFRESH_MS = 30_000;
const view = $("#view");

// ─── Token bootstrap: the link printed by `m-gpux ui` carries #token=… ──

(function bootstrapToken() {
  const match = location.hash.match(/token=([A-Za-z0-9_-]+)/);
  if (match) {
    saveToken(match[1]);
    const page = (location.hash.match(/page=([\w-]+)/) || [])[1] || "overview";
    history.replaceState(null, "", `${location.pathname}#/${page}`);
  }
})();

function lockedScreen(reason) {
  view.replaceChildren(h("div", { class: "card", style: { maxWidth: "560px", margin: "10vh auto 0" } },
    empty({
      glyph: "key",
      title: reason || "Open the dashboard from its link",
      hint: "For your safety, this page only works through the private link `m-gpux ui` prints. Each start creates a new link.",
      code: "m-gpux ui",
    })));
}

// ─── Theme ───────────────────────────────────────────────────

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("#theme-toggle").replaceChildren(icon(theme === "dark" ? "sun" : "moon"));
  $("#theme-toggle").setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
}
const systemTheme = () => (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark");
applyTheme(prefs.get("theme", null) || systemTheme());
$("#theme-toggle").addEventListener("click", toggleTheme);
function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  prefs.set("theme", next);
  applyTheme(next);
}

// ─── Router & rendering ──────────────────────────────────────

function currentRoute() {
  const id = (location.hash.match(/^#\/([\w-]+)/) || [])[1];
  return ROUTES.find((r) => r.id === id) || ROUTES[0];
}

const ctx = { rerender: () => render() };

function render() {
  if (!hasToken()) return lockedScreen();
  const route = currentRoute();
  const active = document.activeElement;
  const focusKey = active?.dataset?.focusKey;
  const caret = focusKey ? [active.selectionStart, active.selectionEnd] : null;

  view.replaceChildren(...route.render(ctx).flat().filter((n) => n instanceof Node));

  if (focusKey) {
    const again = view.querySelector(`[data-focus-key="${focusKey}"]`);
    if (again) { again.focus(); try { again.setSelectionRange(...caret); } catch { /* not a text input */ } }
  }
  renderNav(route);
  renderCrumbs(route);
  renderScope();
  renderUpdated();
}

function renderNav(route) {
  const groups = [];
  for (const r of ROUTES) {
    let group = groups.find((g) => g.name === r.group);
    if (!group) groups.push((group = { name: r.group, items: [] }));
    group.items.push(r);
  }
  $("#nav").replaceChildren(...groups.map((g) => h("div", { class: "nav-group" },
    g.name && h("div", { class: "nav-label" }, g.name),
    g.items.map((r) => {
      const count = r.count?.();
      return h("a", { class: "nav-item", href: `#/${r.id}`, "aria-current": r === route ? "page" : undefined },
        icon(r.glyph), h("span", {}, r.label), count > 0 && h("span", { class: "nav-count" }, fmt.count(count)));
    }))));
}

function renderCrumbs(route) {
  $("#crumbs").replaceChildren(
    h("span", {}, store.scope || "All accounts"), h("span", { "aria-hidden": "true" }, "/"), h("strong", {}, route.label));
  document.title = `${route.label} · m-gpux console`;
}

function renderScope() {
  const select = $("#scope-select");
  const names = store.peek("accounts")?.data?.accounts?.map((a) => a.name) || (store.scope ? [store.scope] : []);
  const wanted = ["", ...names].join("\n");
  if (select.dataset.options !== wanted) {
    select.replaceChildren(h("option", { value: "" }, "All accounts"), ...names.map((n) => h("option", { value: n }, n)));
    select.dataset.options = wanted;
  }
  select.value = store.scope;
}

function renderUpdated() {
  const stamps = currentRoute().refresh.map((r) => store.peek(r)).filter((e) => e?.at).map((e) => e.at);
  const busy = currentRoute().refresh.some((r) => store.peek(r)?.pending);
  $("#refresh").classList.toggle("spinning", busy);
  $("#updated").textContent = busy ? "Refreshing…" : stamps.length ? `Updated ${fmt.ago(new Date(Math.min(...stamps)).toISOString())}` : "";
}

$("#scope-select").addEventListener("change", (e) => setScope(e.target.value));
function setScope(scope) {
  store.setScope(scope);
  for (const r of currentRoute().refresh) store.need(r);
}

function refresh() {
  for (const r of currentRoute().refresh) store.load(r, { refresh: true });
}
$("#refresh").addEventListener("click", refresh);

window.addEventListener("hashchange", () => {
  closeDrawer();
  $("#shell").classList.remove("nav-open");
  render();
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
});
store.subscribe(render);
document.addEventListener("mgpux:locked", () => lockedScreen("This link has expired — the dashboard was restarted"));

// Auto-refresh what the current page shows; the server caches for 15 s, so this stays cheap.
setInterval(() => {
  if (document.hidden || !hasToken()) return;
  for (const r of currentRoute().refresh) store.load(r);
}, AUTO_REFRESH_MS);
setInterval(renderUpdated, 5000);

// ─── Drawer, mobile nav ──────────────────────────────────────

$("#drawer-close").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", () => { closeDrawer(); $("#shell").classList.remove("nav-open"); $("#scrim").hidden = true; });
$("#menu-toggle").addEventListener("click", () => {
  $("#shell").classList.add("nav-open");
  $("#scrim").hidden = false;
});

// ─── Command palette ─────────────────────────────────────────

let paletteItems = [];
let paletteIndex = 0;

function commands() {
  const accounts = store.peek("accounts")?.data?.accounts || [];
  return [
    ...ROUTES.map((r) => ({ section: "Go to", label: r.label, glyph: r.glyph, hint: r.group || "", run: () => { location.hash = `#/${r.id}`; } })),
    { section: "Actions", label: "Refresh data", glyph: "refresh", hint: "R", run: refresh },
    { section: "Actions", label: "Add account", glyph: "plus", run: () => { location.hash = "#/accounts"; actions.addAccount(); } },
    { section: "Actions", label: "Set default budget", glyph: "wallet", run: () => actions.editBudget(null, store.peek("billing")?.data?.budgets?.["*"]) },
    { section: "Actions", label: "Toggle light / dark theme", glyph: "sun", run: toggleTheme },
    { section: "Scope", label: "All accounts", glyph: "layers", hint: store.scope ? "" : "current", run: () => setScope("") },
    ...accounts.map((a) => ({ section: "Scope", label: a.name, glyph: "user", hint: a.workspace || "", run: () => setScope(a.name) })),
  ];
}

function openPalette() {
  $("#palette").hidden = false;
  const input = $("#palette-input");
  input.value = "";
  drawPalette("");
  input.focus();
}

function closePalette() {
  $("#palette").hidden = true;
}

function drawPalette(query) {
  const q = query.trim().toLowerCase();
  paletteItems = commands().filter((c) => !q || `${c.section} ${c.label} ${c.hint}`.toLowerCase().includes(q));
  paletteIndex = Math.min(paletteIndex, Math.max(paletteItems.length - 1, 0));
  if (q) paletteIndex = 0;
  const list = $("#palette-list");
  const nodes = [];
  let section = null;
  paletteItems.forEach((c, i) => {
    if (c.section !== section) { section = c.section; nodes.push(h("li", { class: "palette-section", role: "presentation" }, section)); }
    nodes.push(h("li", {
      role: "option", "aria-selected": String(i === paletteIndex),
      onclick: () => runPalette(i), onmousemove: () => { if (paletteIndex !== i) { paletteIndex = i; drawPalette($("#palette-input").value); } },
    }, icon(c.glyph), h("span", {}, c.label), c.hint && h("span", { class: "hint" }, c.hint)));
  });
  list.replaceChildren(...(nodes.length ? nodes : [h("li", { class: "palette-section" }, "No matches")]));
  list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

function runPalette(i) {
  const item = paletteItems[i];
  closePalette();
  item?.run();
}

$("#open-palette").addEventListener("click", openPalette);
$("#palette").addEventListener("click", (e) => { if (e.target.id === "palette") closePalette(); });
$("#palette-input").addEventListener("input", (e) => drawPalette(e.target.value));
$("#palette-input").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const n = paletteItems.length;
    if (n) paletteIndex = (paletteIndex + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
    drawPalette(e.target.value);
  } else if (e.key === "Enter") {
    e.preventDefault();
    runPalette(paletteIndex);
  }
});

// ─── Keyboard ────────────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "") || $("#dialog").open;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    $("#palette").hidden ? openPalette() : closePalette();
  } else if (e.key === "Escape") {
    if (!$("#palette").hidden) closePalette();
    else closeDrawer();
  } else if (!typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
    if (e.key === "r") refresh();
    if (e.key === "/") { const search = view.querySelector(".search input"); if (search) { e.preventDefault(); search.focus(); } }
  }
});

// ─── Start ───────────────────────────────────────────────────

hydrateIcons();
installTooltips();
$("#runtime-addr").textContent = location.host;
if (!location.hash.startsWith("#/")) history.replaceState(null, "", location.pathname + "#/overview");
if (hasToken()) store.need("accounts");
render();
