export const STATS = [
  { value: 14, suffix: "", label: "Command groups", hint: "one coherent control surface" },
  { value: 37, suffix: "", label: "VS Code actions", hint: "the CLI, translated to UI" },
  { value: 3, suffix: "", label: "Compute modes", hint: "GPU · CPU · Sandbox" },
  { value: 0, suffix: "", label: "Idle compute", hint: "pause, snapshot, scale down" },
];

export const FEATURES = [
  {
    icon: "Cpu",
    eyebrow: "launch",
    title: "A guided GPU Hub",
    body: "Pick compute, runtime and workload. m-gpux writes the Modal app, launches it, captures the URL and tracks the session.",
    metric: "14 GPU targets",
    visual: "hub",
    wide: true,
  },
  {
    icon: "Box",
    eyebrow: "develop",
    title: "Dev boxes that can sleep",
    body: "SSH or open VS Code Remote, snapshot the whole filesystem, stop compute billing and resume exactly where you left off.",
    metric: "pause → resume",
    visual: "lifecycle",
  },
  {
    icon: "PanelLeft",
    eyebrow: "editor",
    title: "VS Code, zero CLI setup",
    body: "The extension carries a matching CLI wheel and can install it into a private environment on first use.",
    metric: "37 actions",
    visual: "managed",
  },
  {
    icon: "Container",
    eyebrow: "orchestrate",
    title: "Compose, mapped to Modal",
    body: "Analyze ports, images, volumes and dependencies, then run as a shared app, VM, or isolated Sandboxes.",
    metric: "3 deploy modes",
    visual: "compose",
    wide: true,
  },
  {
    icon: "Sparkles",
    eyebrow: "serve",
    title: "Ship models and web apps",
    body: "Host ASGI, WSGI or static apps, and deploy authenticated OpenAI-compatible endpoints with streaming and metrics.",
    metric: "one persistent URL",
    visual: "serve",
  },
  {
    icon: "Gauge",
    eyebrow: "govern",
    title: "Profiles, budgets, visibility",
    body: "Pin every process to the right profile, aggregate billing, set monthly budgets and stop workloads without losing context.",
    metric: "multi-profile",
    visual: "billing",
  },
];

export const RUNTIMES = ["3.10", "3.11", "3.12", "3.13", "3.14", "custom"];

export const GPUS = ["T4", "L4", "A10", "L40S", "A100", "H100", "H200", "B200", "B300", "CPU"];
