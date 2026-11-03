// Core of the m-gpux console: DOM helper, API client, data store and UI components.
// Untrusted text (names, IDs, logs from Modal) is only ever set via textContent.
import { icon } from "./icons.js";

// ─── DOM ─────────────────────────────────────────────────────

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export const $ = (selector, root = document) => root.querySelector(selector);

// ─── Formatting ──────────────────────────────────────────────

export const fmt = {
  money(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    if (Math.abs(value) >= 10000) return "$" + new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
    return "$" + Number(value).toFixed(digits);
  },
  count(value) {
    return value === null || value === undefined ? "—" : new Intl.NumberFormat("en", { notation: value >= 10000 ? "compact" : "standard" }).format(value);
  },
  pct(value) {
    return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
  },
  date(iso) {
    const d = parseDate(iso);
    return d ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : iso || "—";
  },
  ago(iso) {
    const d = parseDate(iso);
    if (!d) return iso || "—";
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    if (s < 86400 * 14) return `${Math.round(s / 86400)}d ago`;
    return d.toLocaleDateString(undefined, { dateStyle: "medium" });
  },
};

function parseDate(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

// ─── Storage (per-viewer conveniences only; may be unavailable) ──

export const prefs = {
  get(key, fallback) {
    try { const v = localStorage.getItem("mgpux:" + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem("mgpux:" + key, JSON.stringify(value)); } catch { /* ignore */ }
  },
};

function readToken() {
  try { return sessionStorage.getItem("mgpux:token"); } catch { return window.__mgpuxToken || null; }
}

export function saveToken(token) {
  window.__mgpuxToken = token;
  try { sessionStorage.setItem("mgpux:token", token); } catch { /* keep in memory */ }
}

export function hasToken() {
  return Boolean(window.__mgpuxToken || readToken());
}

// ─── API ─────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { Authorization: `Bearer ${window.__mgpuxToken || readToken() || ""}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError("The m-gpux server is not reachable. Is `m-gpux ui` still running?", 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) document.dispatchEvent(new CustomEvent("mgpux:locked"));
    throw new ApiError(data.error || `HTTP ${response.status}`, response.status);
  }
  return data;
}

// ─── Store: one cached entry per resource+scope, refreshed in the background ──

const SCOPED = new Set(["apps", "containers", "sandboxes", "sessions"]);
const entries = new Map();
const listeners = new Set();

export const store = {
  scope: prefs.get("scope", ""),
  autoRefresh: prefs.get("autoRefresh", true),

  key(resource) {
    return SCOPED.has(resource) && this.scope ? `${resource}@${this.scope}` : resource;
  },
  /** Cached entry {data, error, at, pending}; starts a load when missing. */
  need(resource) {
    const key = this.key(resource);
    if (!entries.has(key)) this.load(resource);
    return entries.get(key);
  },
  peek(resource) {
    return entries.get(this.key(resource));
  },
  async load(resource, { refresh = false } = {}) {
    const key = this.key(resource);
    const entry = entries.get(key) || { data: null, error: null, at: 0, pending: null };
    entries.set(key, entry);
    if (entry.pending) return entry.pending;
    const params = new URLSearchParams();
    if (SCOPED.has(resource) && this.scope) params.set("profile", this.scope);
    if (refresh) params.set("refresh", "1");
    const query = params.toString();
    entry.pending = api(`/api/${resource}${query ? "?" + query : ""}`)
      .then((data) => { entry.data = data; entry.error = null; entry.at = Date.now(); })
      .catch((error) => { entry.error = error; entry.at = Date.now(); })
      .finally(() => { entry.pending = null; emit(); });
    emit();
    return entry.pending;
  },
  invalidate(...resources) {
    for (const key of [...entries.keys()]) {
      if (!resources.length || resources.some((r) => key === r || key.startsWith(r + "@"))) entries.delete(key);
    }
    emit();
  },
  setScope(scope) {
    this.scope = scope;
    prefs.set("scope", scope);
    emit();
  },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};

let emitQueued = false;
function emit() {
  if (emitQueued) return;
  emitQueued = true;
  queueMicrotask(() => { emitQueued = false; listeners.forEach((fn) => fn()); });
}

// ─── Status ──────────────────────────────────────────────────

const STATUS = {
  // tone: good | warning | serious | critical | idle (icon + label always accompany the color)
  deployed: ["good", "ok", "Deployed"],
  ephemeral: ["good", "play", "Running"],
  "ephemeral (detached)": ["good", "play", "Detached"],
  "initializing...": ["warning", "idle", "Starting"],
  "stopping...": ["warning", "idle", "Stopping"],
  stopped: ["idle", "idle", "Stopped"],
  disabled: ["idle", "idle", "Disabled"],
  running: ["good", "play", "Running"],
  succeeded: ["good", "ok", "Succeeded"],
  paused: ["idle", "pause", "Paused"],
  expired: ["serious", "alert", "Expired"],
  failed: ["critical", "error", "Failed"],
  error: ["critical", "error", "Unreachable"],
  cancelled: ["idle", "idle", "Cancelled"],
  orphaned: ["serious", "alert", "Account removed"],
  ended: ["idle", "idle", "Not running"],
  connected: ["good", "ok", "Connected"],
  unknown: ["warning", "alert", "No billing data"],
  queued: ["warning", "idle", "Queued"],
  login: ["warning", "key", "Not logged in"],
  relogin: ["serious", "key", "Login expired"],
};

export function statusPill(state, label) {
  const [tone, glyph, text] = STATUS[String(state || "").toLowerCase()] || ["idle", "idle", state || "Unknown"];
  return h("span", { class: `pill pill-${tone}` }, icon(glyph), label || text);
}

// ─── Components ──────────────────────────────────────────────

export function copyable(text, { display } = {}) {
  if (!text) return h("span", { class: "muted" }, "—");
  return h("button", {
    class: "copy", type: "button", title: "Copy", dataset: { tip: "Click to copy" },
    onclick: (event) => { event.stopPropagation(); copyText(text); },
  }, h("span", {}, display || text), icon("copy"));
}

export async function copyText(text, message = "Copied to clipboard") {
  try { await navigator.clipboard.writeText(text); toast(message); } catch { toast("Copy failed — select and copy manually", "error"); }
}

export function meter(used, cap, format = (v) => fmt.money(v)) {
  if (used === null || used === undefined || !cap) {
    return h("div", { class: "meter unknown", role: "img", "aria-label": "Usage unknown", dataset: { tip: "Usage unknown" } });
  }
  const ratio = used / cap;
  const tone = ratio >= 1 ? "over" : ratio >= 0.75 ? "warn" : "";
  const tip = `${format(used)} of ${format(cap)} used (${fmt.pct(ratio)})`;
  return h("div", { class: `meter ${tone}`, role: "img", "aria-label": tip, dataset: { tip } },
    h("span", { style: { width: `${Math.min(ratio, 1) * 100}%` } }));
}

export function card({ title, hint, actions, body, flush = false, className = "" }) {
  return h("section", { class: `card ${className}` },
    title && h("header", { class: "card-head" }, h("h2", {}, title), hint && h("span", { class: "hint" }, hint),
      actions && h("div", { class: "actions" }, actions)),
    h("div", { class: `card-body ${flush ? "flush" : ""}` }, body));
}

export function kpi({ label, glyph, value, sub, loading }) {
  return h("div", { class: "card kpi" },
    h("div", { class: "kpi-label" }, icon(glyph), label),
    loading ? h("div", { class: "skeleton sk-value" }) : h("div", { class: "kpi-value" }, value),
    h("div", { class: "kpi-sub" }, loading ? "" : sub || ""));
}

export function pageHead(title, description, actions) {
  return h("div", { class: "page-head" },
    h("div", {}, h("h1", {}, title), description && h("p", {}, description)),
    actions && h("div", { class: "actions" }, actions));
}

export function button(label, { glyph, kind = "", size = "", onClick, title, disabled } = {}) {
  return h("button", { class: `btn ${kind} ${size}`.trim(), type: "button", title, disabled, onclick: onClick },
    glyph && icon(glyph), label);
}

export function empty({ glyph = "idle", title, hint, code }) {
  return h("div", { class: "empty" }, icon(glyph), h("strong", {}, title), hint && h("div", {}, hint), code && h("code", {}, code));
}

export function skeletonRows(n = 4) {
  return h("div", {}, Array.from({ length: n }, (_, i) => h("div", { class: "skeleton sk-line", style: { width: `${88 - i * 9}%` } })));
}

/** A warning banner listing accounts that could not be reached. */
export function errorBanner(errors) {
  if (!errors || !errors.length) return null;
  return h("div", { class: "banner" }, icon("alert"),
    h("div", {}, h("strong", {}, `${errors.length} account${errors.length > 1 ? "s" : ""} could not be reached`),
      h("ul", {}, errors.map((e) => h("li", {}, h("strong", {}, e.profile), " — ", e.error)))));
}

export function failure(error, retry) {
  return h("div", { class: "banner error" }, icon("error"),
    h("div", {}, h("strong", {}, "Could not load this data"), h("div", { class: "dim" }, error.message),
      retry && h("div", { style: { marginTop: "8px" } }, button("Try again", { glyph: "refresh", size: "btn-sm", onClick: retry }))));
}

/**
 * columns: [{ label, render(row) -> Node|string, className }]
 * options: { onRow(row), empty: Node, key(row) }
 */
export function table(columns, rows, { onRow, empty: emptyNode } = {}) {
  if (!rows.length) return emptyNode || empty({ title: "Nothing here yet" });
  return h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {}, columns.map((c) => h("th", { class: c.className || "", scope: "col" }, c.label)))),
      h("tbody", {}, rows.map((row) => h("tr", {
        class: onRow ? "clickable" : "",
        tabindex: onRow ? "0" : undefined,
        onclick: onRow ? () => onRow(row) : undefined,
        onkeydown: onRow ? (e) => { if (e.key === "Enter") onRow(row); } : undefined,
      }, columns.map((c) => h("td", { class: c.className || "" }, c.render(row))))))));
}

export function segmented(options, value, onChange) {
  return h("div", { class: "segmented", role: "group" }, options.map((o) =>
    h("button", { type: "button", "aria-pressed": String(o.value === value), onclick: () => onChange(o.value) },
      o.label, o.count !== undefined && h("span", { class: "count" }, o.count))));
}

export function searchBox(placeholder, value, onInput, focusKey) {
  return h("label", { class: "search" }, icon("search"),
    h("input", { type: "search", placeholder, value, "aria-label": placeholder, dataset: { focusKey }, oninput: (e) => onInput(e.target.value) }));
}

export function matches(row, query, fields) {
  if (!query) return true;
  const q = query.toLowerCase();
  return fields.some((f) => String(row[f] ?? "").toLowerCase().includes(q));
}

// ─── Drawer ──────────────────────────────────────────────────

export function openDrawer({ kicker, title, body }) {
  $("#drawer-kicker").textContent = kicker || "";
  $("#drawer-title").textContent = title || "";
  const holder = $("#drawer-body");
  holder.replaceChildren(...[body].flat().filter(Boolean));
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").hidden = false;
  $("#drawer-close").focus();
}

export function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
}

export function kv(pairs) {
  return h("dl", { class: "kv" }, pairs.filter(([, v]) => v !== undefined).map(([k, v]) => [h("dt", {}, k), h("dd", {}, v ?? "—")]));
}

export function logView(lines) {
  if (!lines.length) return empty({ glyph: "logs", title: "No log lines", hint: "Nothing was logged in the requested window." });
  const pre = h("pre", { class: "logs" });
  for (const line of lines) {
    const match = line.match(/^(\S+T\S+|\d{4}-\d\d-\d\d[ T][\d:.]+\S*)\s(.*)$/);
    if (match) pre.append(h("span", { class: "ts" }, match[1] + " "), match[2] + "\n");
    else pre.append(line + "\n");
  }
  return pre;
}

// ─── Dialogs ─────────────────────────────────────────────────

export function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const dialog = $("#dialog");
    const form = h("form", { method: "dialog" },
      h("header", {}, h("h2", {}, title), message && h("p", {}, message)),
      h("footer", {},
        h("button", { class: "btn", value: "cancel", type: "submit" }, "Cancel"),
        h("button", { class: `btn ${danger ? "btn-danger solid" : "btn-primary"}`, value: "ok", type: "submit" }, confirmLabel)));
    dialog.replaceChildren(form);
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), { once: true });
    dialog.returnValue = "";
    dialog.showModal();
    form.querySelector('[value="ok"]').focus();
  });
}

/** fields: [{ name, label, type, placeholder, help, value, required, autocomplete, onPaste }] */
export function formDialog({ title, description, fields, submitLabel = "Save", onSubmit }) {
  return new Promise((resolve) => {
    const dialog = $("#dialog");
    const error = h("div", { class: "form-error", role: "alert" });
    const submit = h("button", { class: "btn btn-primary", type: "submit" }, submitLabel);
    const inputs = {};
    const form = h("form", {
      onsubmit: async (event) => {
        event.preventDefault();
        error.textContent = "";
        submit.disabled = true;
        submit.classList.add("spinning");
        try {
          const values = Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value]));
          const result = await onSubmit(values);
          dialog.close("ok");
          resolve(result ?? true);
        } catch (e) {
          error.textContent = e.message;
        } finally {
          submit.disabled = false;
          submit.classList.remove("spinning");
        }
      },
    },
      h("header", {}, h("h2", {}, title), description && h("p", {}, description)),
      h("div", { class: "fields" },
        fields.map((f) => {
          const id = `f-${f.name}`;
          const input = h("input", {
            id, name: f.name, type: f.type || "text", placeholder: f.placeholder, value: f.value ?? "",
            required: f.required, autocomplete: f.autocomplete || "off", spellcheck: "false", step: f.step, min: f.min,
          });
          if (f.onPaste) input.addEventListener("paste", (e) => f.onPaste(e, inputs));
          inputs[f.name] = input;
          return h("div", { class: "field" }, h("label", { for: id }, f.label), input, f.help && h("div", { class: "help" }, f.help));
        }),
        error),
      h("footer", {}, h("button", { class: "btn", type: "button", onclick: () => { dialog.close(); resolve(null); } }, "Cancel"), submit));
    dialog.replaceChildren(form);
    dialog.addEventListener("cancel", () => resolve(null), { once: true });
    dialog.showModal();
    form.querySelector("input")?.focus();
  });
}

// ─── Toasts & tooltips ───────────────────────────────────────

export function toast(message, kind = "ok") {
  const el = h("div", { class: `toast ${kind}`, role: kind === "error" ? "alert" : "status" }, icon(kind === "error" ? "error" : "ok"), h("div", {}, message));
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 3500);
}

/** Run an action with a busy button, a toast, and cache invalidation. */
export async function act(buttonEl, run, { success, invalidate = [] } = {}) {
  buttonEl?.classList.add("spinning");
  if (buttonEl) buttonEl.disabled = true;
  try {
    const result = await run();
    if (success) toast(typeof success === "function" ? success(result) : success);
    if (invalidate.length) store.invalidate(...invalidate);
    return result;
  } catch (e) {
    toast(e.message, "error");
    return null;
  } finally {
    buttonEl?.classList.remove("spinning");
    if (buttonEl) buttonEl.disabled = false;
  }
}

export function installTooltips() {
  const tip = $("#tooltip");
  const show = (target) => {
    tip.textContent = target.dataset.tip;
    tip.hidden = false;
    const r = target.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const left = Math.max(8, Math.min(window.innerWidth - t.width - 8, r.left + r.width / 2 - t.width / 2));
    const top = r.top - t.height - 8 < 8 ? r.bottom + 8 : r.top - t.height - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  };
  document.addEventListener("pointerover", (e) => { const t = e.target.closest?.("[data-tip]"); if (t) show(t); });
  document.addEventListener("pointerout", (e) => { if (e.target.closest?.("[data-tip]")) tip.hidden = true; });
  document.addEventListener("focusin", (e) => { const t = e.target.closest?.("[data-tip]"); if (t) show(t); });
  document.addEventListener("focusout", () => { tip.hidden = true; });
  window.addEventListener("scroll", () => { tip.hidden = true; }, true);
}
