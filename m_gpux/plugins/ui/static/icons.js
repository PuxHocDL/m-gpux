// Stroke icons on a 24×24 grid (drawn for m-gpux; no external icon font).
const PATHS = {
  overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  accounts: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18.5 14.5A6.5 6.5 0 0 1 21.5 20"/>',
  apps: '<path d="M12 2.8 20.5 7.5v9L12 21.2 3.5 16.5v-9z"/><path d="M3.8 7.6 12 12.2l8.2-4.6"/><path d="M12 12.2v9"/>',
  containers: '<rect x="4" y="4" width="16" height="16" rx="2.5"/><rect x="8.5" y="8.5" width="7" height="7" rx="1"/><path d="M9 1.5V4M15 1.5V4M9 20v2.5M15 20v2.5M1.5 9H4M1.5 15H4M20 9h2.5M20 15h2.5"/>',
  sandboxes: '<rect x="2.5" y="4" width="19" height="16" rx="2.5"/><path d="m6.5 9.5 3 2.5-3 2.5"/><path d="M12 15h5"/>',
  sessions: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  endpoints: '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M3 12h18"/><path d="M12 3c2.4 2.6 3.6 5.6 3.6 9s-1.2 6.4-3.6 9c-2.4-2.6-3.6-5.6-3.6-9S9.6 5.6 12 3z"/>',
  library: '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/>',
  billing: '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 10h19"/><path d="M6.5 15h4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/>',
  refresh: '<path d="M20.5 11A8.5 8.5 0 0 0 5.6 6.4L3.5 8.5"/><path d="M3.5 3.5v5h5"/><path d="M3.5 13a8.5 8.5 0 0 0 14.9 4.6l2.1-2.1"/><path d="M20.5 20.5v-5h-5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a6.8 6.8 0 0 0 11 11z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3.5 6h17"/><path d="M8.5 6V4.5A1.5 1.5 0 0 1 10 3h4a1.5 1.5 0 0 1 1.5 1.5V6"/><path d="M5.5 6l1 13.5A1.5 1.5 0 0 0 8 21h8a1.5 1.5 0 0 0 1.5-1.5l1-13.5"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2.5"/>',
  logs: '<path d="M14.5 2.5H6.5a2 2 0 0 0-2 2v15a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-12z"/><path d="M14.5 2.5v5h5"/><path d="M8.5 13h7M8.5 17h5"/>',
  external: '<path d="M14 3.5h6.5V10"/><path d="M20.5 3.5 11 13"/><path d="M18.5 14v4.5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2H10"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5V5.5a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/>',
  check: '<path d="m4.5 12.5 5 5 10-11"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  menu: '<path d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17"/>',
  layers: '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12 9 4.5 9-4.5"/>',
  alert: '<path d="M10.3 3.9 2.4 17.6A2 2 0 0 0 4.1 20.6h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
  ok: '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.8 2.8L16.5 9.5"/>',
  error: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16h.01"/>',
  pause: '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
  idle: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
  play: '<circle cx="12" cy="12" r="9"/><path d="m10 8.5 5.5 3.5-5.5 3.5z"/>',
  bolt: '<path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12z"/>',
  wallet: '<path d="M3.5 7.5v10a2 2 0 0 0 2 2h14v-12h-14a2 2 0 0 1 0-4h12v4"/><circle cx="16" cy="13.5" r="1.2"/>',
  gauge: '<path d="M4.2 18.5a9 9 0 1 1 15.6 0"/><path d="m12 13.5 4-5"/><circle cx="12" cy="13.5" r="1.3"/>',
  power: '<path d="M12 2.5v9"/><path d="M6.3 5.8a8.5 8.5 0 1 0 11.4 0"/>',
  key: '<circle cx="8" cy="15" r="4.5"/><path d="m11.2 11.8 9.3-9.3M17 6l3 3M14.5 8.5l2 2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  command: '<path d="M9 6.5A2.5 2.5 0 1 0 6.5 9H9zM9 9h6v6H9zM15 6.5V9h2.5A2.5 2.5 0 1 0 15 6.5zM9 17.5V15H6.5A2.5 2.5 0 1 0 9 17.5zM15 15v2.5a2.5 2.5 0 1 0 2.5-2.5z"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  terminal: '<path d="m5 7.5 4.5 4.5L5 16.5"/><path d="M12 17h7"/>',
};

export function icon(name, className = "icon") {
  const span = document.createElement("span");
  span.className = className;
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = `<svg viewBox="0 0 24 24">${PATHS[name] || PATHS.idle}</svg>`;
  return span;
}

/** Fill every static <span data-icon="…"> placeholder in the page shell. */
export function hydrateIcons(root = document) {
  for (const el of root.querySelectorAll("[data-icon]")) {
    el.replaceWith(icon(el.dataset.icon, el.className || "icon"));
  }
}
