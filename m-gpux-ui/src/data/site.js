export const STATS = [
  { value: 12, suffix: "", label: "Command groups", hint: "accounts → hub → serve" },
  { value: 30, suffix: "+", label: "VS Code actions", hint: "the Hub, in your editor" },
  { value: 6, suffix: "", label: "Python runtimes", hint: "3.10 → 3.14 + custom" },
  { value: 0, suffix: "→∞", label: "Scale to zero", hint: "pay only when busy" },
];

export const FEATURES = [
  {
    icon: "Cpu",
    title: "Interactive GPU Hub",
    body: "Pick a GPU or CPU, a Python runtime and an action — Jupyter, a script, a browser bash shell or vLLM — and m-gpux writes & launches the Modal app for you.",
  },
  {
    icon: "Sparkles",
    title: "OpenAI-compatible serving",
    body: "Deploy any Hugging Face model behind a streaming, bearer-auth API with warmup, logs, API keys and a live metrics dashboard.",
  },
  {
    icon: "Globe",
    title: "One-command web hosting",
    body: "Give FastAPI, Flask, Django or a static folder a persistent Modal URL. Auto-detected deps, file upload and scale-to-zero out of the box.",
  },
  {
    icon: "Container",
    title: "Docker Compose on Modal",
    body: "Analyze services, ports and volumes, then deploy via subprocess, VM or isolated Sandbox modes — Triton-aware and BuildKit-friendly.",
  },
  {
    icon: "Bookmark",
    title: "Presets & sessions",
    body: "Save any workload as a preset and replay it in one command. Every Hub and dev session is tracked so you can reopen, tail logs, pull files or stop it later.",
  },
  {
    icon: "Gauge",
    title: "Spend you can see",
    body: "Multi-profile accounts, session tracking, GPU probes and cross-workspace billing reports so cloud cost never surprises you.",
  },
];

export const RUNTIMES = ["3.10", "3.11", "3.12", "3.13", "3.14", "custom"];

export const GPUS = ["T4", "L4", "A10", "L40S", "A100", "H100", "H200", "B200", "B300", "CPU"];
