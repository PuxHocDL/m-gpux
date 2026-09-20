export const DOC_TOPICS = [
  {
    id: "quickstart",
    icon: "Rocket",
    label: "Quick start",
    title: "From install to a live dev box",
    summary: "Install the CLI, connect a Modal profile and start a resumable Sandbox workspace in a few minutes.",
    time: "5 min",
    sections: [
      {
        title: "Install the toolchain",
        body: "m-gpux requires Python 3.10 or newer. Installing Modal alongside it gives the generated runners and deployment commands a compatible runtime.",
        code: "pip install -U m-gpux modal\nm-gpux info",
      },
      {
        title: "Connect your first profile",
        body: "Create an API token in Modal, then let the account wizard save it as a named profile in ~/.modal.toml.",
        code: "m-gpux account add\nm-gpux account list",
        steps: ["Choose a memorable profile name.", "Paste the Modal token ID and token secret.", "Confirm the profile is marked active."],
      },
      {
        title: "Start working",
        body: "A dev box uploads the current project to /workspace and gives you SSH, VS Code Remote and browser-shell access.",
        code: "m-gpux dev up --name studio\nm-gpux dev code studio",
      },
    ],
    tip: "Run `m-gpux dev pause studio` when you stop coding. The workspace is snapshotted and compute billing stops.",
  },
  {
    id: "profiles",
    icon: "Users",
    label: "Profiles",
    title: "Keep every Modal workspace in reach",
    summary: "Use named identities for personal, team and client workloads without manually swapping credentials.",
    time: "4 min",
    sections: [
      {
        title: "Manage identities",
        body: "Profiles are shared with the Modal CLI and the VS Code extension through ~/.modal.toml.",
        code: "m-gpux account list\nm-gpux account switch work\nm-gpux account remove old-profile",
      },
      {
        title: "Pin a command to one profile",
        body: "Interactive workflows remember the selected account. Automation can set MODAL_PROFILE or MGPUX_PROFILE for an isolated command.",
        code: "MODAL_PROFILE=work m-gpux billing usage --days 7",
      },
    ],
    tip: "Profile matching is case-insensitive in m-gpux v3, so `tool1` resolves safely to a configured `Tool1` profile.",
  },
  {
    id: "devboxes",
    icon: "Box",
    label: "Dev boxes",
    title: "A remote GPU workspace that can sleep",
    summary: "Create, enter, sync, pause and resume Modal Sandbox environments while keeping project state durable.",
    time: "8 min",
    sections: [
      {
        title: "Lifecycle",
        body: "Name the workspace once, then use the same name across SSH, VS Code and pause/resume commands.",
        code: "m-gpux dev up --name studio --hours 12\nm-gpux dev ssh studio\nm-gpux dev pause studio\nm-gpux dev resume studio",
      },
      {
        title: "Move files deliberately",
        body: "Push local changes before a remote run, or pull results into a chosen local directory.",
        code: "m-gpux dev sync push studio\nm-gpux dev sync pull studio --to ./results",
      },
      {
        title: "Release resources",
        body: "Pause preserves the workspace. Down removes the running dev box when you no longer need it.",
        code: "m-gpux dev list\nm-gpux dev down studio",
      },
    ],
    tip: "Use pause for normal daily shutdowns; use down only when the environment is no longer needed.",
  },
  {
    id: "compose",
    icon: "Layers3",
    label: "Compose",
    title: "Lift a Compose stack onto Modal",
    summary: "Analyze services locally, review the generated topology, then choose a container, VM or Sandbox deployment path.",
    time: "10 min",
    sections: [
      {
        title: "Analyze before provisioning",
        body: "The check command detects services, ports, commands, environment files and GPU reservations without creating cloud resources.",
        code: "m-gpux compose check\nm-gpux compose sandbox check\nm-gpux compose vm check",
      },
      {
        title: "Deploy and sync",
        body: "Use the default mode for common stacks, Sandbox mode for isolated services, or VM mode for heavier Docker behavior.",
        code: "m-gpux compose up\nm-gpux compose sandbox up\nm-gpux compose sync",
      },
    ],
    tip: "Keep docker-compose.yml as the source of truth and run `compose check` after structural changes.",
  },
  {
    id: "hosting",
    icon: "Globe2",
    label: "Web hosting",
    title: "Deploy an app with a persistent URL",
    summary: "Host ASGI, WSGI or static output with generated Modal code, rolling updates and scale-to-zero defaults.",
    time: "7 min",
    sections: [
      {
        title: "Choose the application type",
        body: "Point Python apps at module:variable entry points, or give static hosting a built asset directory.",
        code: "m-gpux host asgi --entry main:app\nm-gpux host wsgi --entry app:app\nm-gpux host static --dir ./dist",
      },
      {
        title: "Control deployment behavior",
        body: "Deploy mode keeps the URL available until the app is stopped. Rolling strategy replaces it without intentional downtime.",
        code: "m-gpux host static --dir ./dist --strategy rolling",
      },
    ],
    tip: "Choose auto-scale to 0 for documentation and landing pages; the first request after idle may have a short cold start.",
  },
  {
    id: "serving",
    icon: "Server",
    label: "Model serving",
    title: "Serve a model behind an OpenAI API",
    summary: "Deploy Hugging Face models with vLLM, bearer authentication, streaming, health checks and a live dashboard.",
    time: "12 min",
    sections: [
      {
        title: "Create a key and deploy",
        body: "The wizard selects the model, GPU, context length, concurrency and warm-container policy.",
        code: "m-gpux serve keys create --name production\nm-gpux serve deploy",
      },
      {
        title: "Observe and stop",
        body: "Use the dashboard for request, latency and token metrics. Stop the app when the endpoint is no longer needed.",
        code: "m-gpux serve dashboard\nm-gpux serve logs\nm-gpux serve stop",
      },
    ],
    tip: "A revoked local API key takes effect after the next deployment.",
  },
  {
    id: "extension",
    icon: "Blocks",
    label: "VS Code",
    title: "Operate Modal without leaving the editor",
    summary: "The extension manages accounts, dev boxes, sessions, Compose, hosting and billing through native VS Code surfaces.",
    time: "6 min",
    sections: [
      {
        title: "Install",
        body: "Install from Marketplace, open the M-GPUX activity view and run the setup action on first use.",
        code: "code --install-extension puxpux.m-gpux",
        steps: ["Open the M-GPUX sidebar.", "Choose Set Up / Update CLI.", "Add or select a Modal profile.", "Launch a workload from Quick Actions."],
      },
      {
        title: "No global m-gpux required",
        body: "The extension can create a private Python environment in extension storage and install its bundled, matching CLI wheel plus Modal.",
      },
    ],
    tip: "Set `mgpux.cliPath` only when you deliberately want the extension to use an existing executable.",
  },
  {
    id: "costs",
    icon: "WalletCards",
    label: "Costs & budgets",
    title: "Know the rate before compute starts",
    summary: "Inspect live prices, aggregate usage across profiles and enforce a monthly m-gpux spending ceiling.",
    time: "5 min",
    sections: [
      {
        title: "Inspect usage and rates",
        body: "Usage can be scoped to one account or aggregated across every configured profile.",
        code: "m-gpux billing rates --refresh\nm-gpux billing usage --days 7 --all --resources\nm-gpux billing summary --all",
      },
      {
        title: "Set guardrails",
        body: "Budget checks compare current-cycle usage against your local limit and can stop workloads when the limit is reached.",
        code: "m-gpux budget set 30 --account work\nm-gpux budget check --stop\nm-gpux budget watch --interval 600",
      },
    ],
    tip: "Price labels are estimates; `billing usage` and `billing summary` query account data for the actual cycle.",
  },
  {
    id: "sessions",
    icon: "History",
    label: "Sessions",
    title: "Find and recover every tracked workload",
    summary: "Open URLs, inspect logs, pull workspaces and stop Hub or dev sessions without losing profile context.",
    time: "4 min",
    sections: [
      {
        title: "Inspect and reopen",
        body: "Each detached session records its app, profile, workspace and current lifecycle state.",
        code: "m-gpux sessions list\nm-gpux sessions show sess-1234abcd\nm-gpux sessions open sess-1234abcd",
      },
      {
        title: "Recover and clean up",
        body: "Pull remote files before stopping a session when results have not yet been copied locally.",
        code: "m-gpux sessions pull sess-1234abcd --to ./recovered\nm-gpux sessions stop sess-1234abcd",
      },
    ],
    tip: "For historical logs, add `--no-follow --tail 500 --since 2h` to `sessions logs`.",
  },
];

export const DOC_REQUIREMENTS = [
  "Python 3.10+",
  "Modal 1.5.4+",
  "A Modal API token",
  "VS Code 1.85+ for the extension",
];
