export const EXTENSION_HIGHLIGHTS = [
  "One-click private CLI setup with the matching v3 wheel bundled in the VSIX",
  "Create, open, pause, resume, sync and delete Sandbox dev boxes",
  "Profile-pinned launches, session discovery and safe workspace sync",
  "Works on macOS, Windows and Linux — finds Python and Modal even when VS Code starts from the Dock",
];

// Every contributed command, grouped by where it lives in the editor.
// Titles match package.json so the site and the Command Palette agree.
// `cli` is the equivalent terminal command, when there is one.
export const EXTENSION_SURFACES = [
  {
    id: "accounts",
    icon: "KeyRound",
    title: "Accounts",
    where: "Sidebar view",
    blurb: "Every Modal profile with its live budget or credit left; the active one is marked.",
    actions: [
      { title: "Add Account", cli: "m-gpux account add" },
      { title: "Switch Account", cli: "m-gpux account switch" },
      { title: "Remove Account", cli: "m-gpux account remove" },
      { title: "Refresh Accounts" },
    ],
  },
  {
    id: "sessions",
    icon: "Radar",
    title: "Active Sessions",
    where: "Sidebar view",
    blurb: "Hub, host, serve and preset launches with state, GPU, URL and inline actions.",
    actions: [
      { title: "Open Session URL", cli: "m-gpux sessions open" },
      { title: "Copy Session URL" },
      { title: "View Session Logs", cli: "m-gpux sessions logs" },
      { title: "Stop Session", cli: "m-gpux sessions stop" },
      { title: "Pull Workspace from Modal", cli: "m-gpux sessions pull" },
      { title: "Push Workspace to Modal" },
      { title: "Toggle Auto-Sync" },
      { title: "Remove Session from List", cli: "m-gpux sessions forget" },
      { title: "Discover Modal Apps" },
      { title: "Refresh Sessions" },
    ],
  },
  {
    id: "presets",
    icon: "Bookmark",
    title: "Presets",
    where: "Sidebar view",
    blurb: "Saved workloads shared with the CLI — click one to run it.",
    actions: [
      { title: "Create Preset", cli: "m-gpux preset create" },
      { title: "Run Preset", cli: "m-gpux preset run" },
      { title: "Delete Preset", cli: "m-gpux preset delete" },
      { title: "Refresh Presets" },
    ],
  },
  {
    id: "launch",
    icon: "Cpu",
    title: "Launch & Dev Box",
    where: "Quick Actions",
    blurb: "Guided wizards for GPU work and long-lived dev boxes.",
    actions: [
      { title: "Open GPU Hub", cli: "m-gpux hub" },
      { title: "Probe GPU Hardware", cli: "m-gpux load probe" },
      { title: "Create / Start Dev Box", cli: "m-gpux dev up" },
      { title: "Manage Dev Box", cli: "m-gpux dev list|code|ssh|pause|resume|sync|down" },
    ],
  },
  {
    id: "ship",
    icon: "Globe",
    title: "Host & Serve",
    where: "Quick Actions",
    blurb: "Put web apps and LLM endpoints behind a persistent Modal URL.",
    actions: [
      { title: "Host Web App (ASGI / WSGI / Static)", cli: "m-gpux host asgi|wsgi|static" },
      { title: "Deploy LLM Endpoint", cli: "m-gpux serve deploy" },
      { title: "Manage API Keys", cli: "m-gpux serve keys list|show|revoke" },
      { title: "Create API Key", cli: "m-gpux serve keys create" },
      { title: "Open Modal Apps Dashboard" },
    ],
  },
  {
    id: "compose",
    icon: "Container",
    title: "Compose",
    where: "Quick Actions",
    blurb: "Finds docker-compose.yml in the workspace and runs it in any mode.",
    actions: [
      { title: "Check docker-compose.yml", cli: "m-gpux compose check" },
      { title: "Deploy docker-compose to Modal", cli: "m-gpux compose up | vm up" },
      { title: "Compose Sandbox", cli: "m-gpux compose sandbox …" },
    ],
  },
  {
    id: "manage",
    icon: "Gauge",
    title: "Manage & Setup",
    where: "Quick Actions · Command Palette",
    blurb: "Billing, cleanup, and the environment the extension runs Modal with.",
    actions: [
      { title: "Show Billing Usage", cli: "m-gpux billing usage" },
      { title: "Open Billing Dashboard", cli: "m-gpux billing open" },
      { title: "Stop All Apps on Profile", cli: "m-gpux stop" },
      { title: "Show Info", cli: "m-gpux info" },
      { title: "Set Up / Update CLI" },
      { title: "Check Python Interpreter" },
    ],
  },
];

export const EXTENSION_SETTINGS = [
  { key: "mgpux.pythonPath", desc: "Python used to run Modal (auto-detected when empty)" },
  { key: "mgpux.cliPath", desc: "Use an existing m-gpux executable instead of the managed one" },
  { key: "mgpux.autoSync", desc: "Sync session workspaces automatically (off by default)" },
];
