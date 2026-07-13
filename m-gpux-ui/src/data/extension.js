// VS Code extension command palette — mirrors m-gpux-vscode v2.7.0 `contributes.commands`.
// `key` is the visible title; `id` is the real command id; `kbd` an illustrative keybinding.

export const PALETTE_COMMANDS = [
  { id: "mgpux.openHub", key: "m-gpux: Open GPU Hub", group: "Hub", icon: "Cpu" },
  { id: "mgpux.addAccount", key: "m-gpux: Add Account", group: "Accounts", icon: "KeyRound" },
  { id: "mgpux.switchAccount", key: "m-gpux: Switch Account", group: "Accounts", icon: "Users" },
  { id: "mgpux.serveDeploy", key: "m-gpux: Deploy LLM Endpoint", group: "Serve", icon: "Sparkles" },
  { id: "mgpux.hostApp", key: "m-gpux: Host Web App (ASGI / WSGI / Static)", group: "Hosting", icon: "Globe" },
  { id: "mgpux.composeUp", key: "m-gpux: Deploy docker-compose to Modal", group: "Compose", icon: "Container" },
  { id: "mgpux.billingUsage", key: "m-gpux: Show Billing Usage", group: "Billing", icon: "Gauge" },
  { id: "mgpux.loadProbe", key: "m-gpux: Probe GPU Hardware", group: "Ops", icon: "Activity" },
  { id: "mgpux.runPreset", key: "m-gpux: Run Preset", group: "Presets", icon: "Bookmark" },
  { id: "mgpux.openSession", key: "m-gpux: Open Session URL", group: "Sessions", icon: "ExternalLink" },
  { id: "mgpux.stopAll", key: "m-gpux: Stop All Apps on Profile", group: "Ops", icon: "Square" },
  { id: "mgpux.discoverApps", key: "m-gpux: Discover Modal Apps", group: "Compose", icon: "Radar" },
];

export const EXTENSION_HIGHLIGHTS = [
  "Mirrors the full Hub wizard — GPU, runtime & action — inside the editor",
  "Tree views for accounts, sessions and presets that refresh live",
  "Generate Modal scripts from the current workspace, no terminal required",
  "Open session URLs, copy links and tail logs from the sidebar",
];
