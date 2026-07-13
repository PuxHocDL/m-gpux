// CLI command groups — mirrors `m-gpux --help` (v2.7.0) and the README reference.
// `icon` is a lucide-react component name resolved in the showcase.

export const COMMAND_GROUPS = [
  {
    id: "accounts",
    icon: "KeyRound",
    title: "Accounts",
    blurb: "Multi-profile Modal credentials in ~/.modal.toml — add, switch, audit.",
    commands: [
      { cmd: "m-gpux account add", desc: "Authenticate & save a Modal token profile" },
      { cmd: "m-gpux account list", desc: "List configured profiles & the active one" },
      { cmd: "m-gpux account switch <name>", desc: "Make a profile active" },
      { cmd: "m-gpux account remove <name>", desc: "Delete a profile (auto-promotes another)" },
    ],
  },
  {
    id: "hub",
    icon: "Cpu",
    title: "GPU Hub & Dev",
    blurb: "Guided launcher for Jupyter, script runs, browser shells and vLLM — any GPU, any runtime.",
    commands: [
      { cmd: "m-gpux hub", desc: "Pick GPU + runtime + action, then launch" },
      { cmd: "m-gpux dev", desc: "Persistent Modal dev container for this folder" },
      { cmd: "m-gpux sessions list", desc: "See running / tracked Hub & dev sessions" },
      { cmd: "m-gpux sessions open <id>", desc: "Reopen a generated app URL" },
    ],
  },
  {
    id: "presets",
    icon: "Bookmark",
    title: "Presets",
    blurb: "Save common workloads — GPU, runtime and action — then replay them hands-free.",
    commands: [
      { cmd: "m-gpux preset create", desc: "Capture the current workload as a preset" },
      { cmd: "m-gpux preset list", desc: "Browse saved presets" },
      { cmd: "m-gpux preset run <name>", desc: "Replay a preset on Modal" },
    ],
  },
  {
    id: "vision",
    icon: "Image",
    title: "Vision",
    blurb: "Image-classification from local folders: sample data, train, predict, export to ONNX / TorchScript.",
    commands: [
      { cmd: "m-gpux vision sample-data", desc: "Generate a tiny shapes dataset" },
      { cmd: "m-gpux vision train", desc: "Fine-tune a TorchVision backbone on a GPU" },
      { cmd: "m-gpux vision predict", desc: "Run inference on new images" },
    ],
  },
  {
    id: "host",
    icon: "Globe",
    title: "Web Hosting",
    blurb: "Persistent Modal URLs for FastAPI, Starlette, Flask, Django and static sites.",
    commands: [
      { cmd: "m-gpux host asgi --entry main:app", desc: "Host an ASGI app (FastAPI / Starlette)" },
      { cmd: "m-gpux host wsgi --entry app:app", desc: "Host a WSGI app (Flask / Django)" },
      { cmd: "m-gpux host static --dir ./site", desc: "Host a static folder" },
    ],
  },
  {
    id: "serve",
    icon: "Sparkles",
    title: "Model Serving",
    blurb: "OpenAI-compatible LLM endpoints with bearer auth, streaming, warmup, logs & a live dashboard.",
    commands: [
      { cmd: "m-gpux serve deploy", desc: "Deploy a HF model as an OpenAI-style API" },
      { cmd: "m-gpux serve dashboard", desc: "Open the live metrics dashboard" },
      { cmd: "m-gpux serve keys create", desc: "Mint a bearer API key" },
      { cmd: "m-gpux serve logs", desc: "Tail endpoint logs" },
    ],
  },
  {
    id: "compose",
    icon: "Container",
    title: "Docker Compose",
    blurb: "Analyze & deploy docker-compose on Modal — subprocess, VM and isolated Sandbox modes.",
    commands: [
      { cmd: "m-gpux compose check", desc: "Analyze services, ports, volumes & images" },
      { cmd: "m-gpux compose up", desc: "Deploy supported services to a Modal app" },
      { cmd: "m-gpux compose sandbox up", desc: "Run services as isolated Sandboxes" },
    ],
  },
  {
    id: "ops",
    icon: "Gauge",
    title: "Billing & Ops",
    blurb: "Cross-workspace spend, GPU probes, video generation and one-shot cleanup.",
    commands: [
      { cmd: "m-gpux billing usage --all", desc: "Total spend across every profile" },
      { cmd: "m-gpux load probe", desc: "Probe a GPU & print hardware metrics" },
      { cmd: "m-gpux video generate", desc: "Text-to-video with LTX" },
      { cmd: "m-gpux stop --all", desc: "Stop running apps & release GPUs" },
    ],
  },
];
