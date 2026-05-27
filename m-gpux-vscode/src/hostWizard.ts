// Mirrors the CLI's `m-gpux host {asgi,wsgi,static}` plugin — generates a
// modal_runner.py for ASGI/WSGI/static hosting and deploys (or runs) it.
import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { loadProfiles, switchProfile, getActiveProfile } from "./config";
import { launchModalScript } from "./sessionLauncher";

type HostKind = "asgi" | "wsgi" | "static";

const DEFAULT_EXCLUDES = [
  ".venv", "venv", "__pycache__", ".git", "node_modules",
  ".mypy_cache", ".pytest_cache", "*.egg-info", ".tox",
  "dist", "build",
];

const CPU_OPTIONS = [
  { label: "1 core / 512 MB",   spec: "cpu=1, memory=512",   compute: "CPU (1 core, 512 MB)" },
  { label: "2 cores / 1024 MB", spec: "cpu=2, memory=1024",  compute: "CPU (2 cores, 1024 MB)" },
  { label: "4 cores / 2048 MB", spec: "cpu=4, memory=2048",  compute: "CPU (4 cores, 2048 MB)" },
  { label: "8 cores / 4096 MB", spec: "cpu=8, memory=4096",  compute: "CPU (8 cores, 4096 MB)" },
];

const GPU_OPTIONS = [
  { label: "T4",   spec: 'gpu="T4"',   description: "16 GB — light inference" },
  { label: "L4",   spec: 'gpu="L4"',   description: "24 GB — balanced" },
  { label: "A10G", spec: 'gpu="A10G"', description: "24 GB — training" },
  { label: "A100", spec: 'gpu="A100"', description: "40 GB SXM" },
  { label: "H100", spec: 'gpu="H100"', description: "80 GB" },
];

function slugify(s: string): string {
  const safe = s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return safe.slice(0, 32) || "site";
}

function asgiTemplate(v: TemplateVars): string {
  return `import modal

app = modal.App("m-gpux-host-${v.slug}")
image = (
    modal.Image.debian_slim(python_version="${v.pythonVersion}")
    ${v.pipSection}
    .add_local_dir("${v.localDir}", remote_path="/app", ignore=${JSON.stringify(v.excludePatterns)})
)

@app.function(
    image=image,
    ${v.computeSpec},
    timeout=86400,
    scaledown_window=${v.scaledown},
    min_containers=${v.minContainers},
)
@modal.concurrent(max_inputs=${v.maxConcurrent})
@modal.asgi_app()
def web():
    import sys, importlib
    sys.path.insert(0, "/app")
    module_name, _, attr = "${v.entry}".partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "app")
`;
}

function wsgiTemplate(v: TemplateVars): string {
  return `import modal

app = modal.App("m-gpux-host-${v.slug}")
image = (
    modal.Image.debian_slim(python_version="${v.pythonVersion}")
    ${v.pipSection}
    .add_local_dir("${v.localDir}", remote_path="/app", ignore=${JSON.stringify(v.excludePatterns)})
)

@app.function(
    image=image,
    ${v.computeSpec},
    timeout=86400,
    scaledown_window=${v.scaledown},
    min_containers=${v.minContainers},
)
@modal.concurrent(max_inputs=${v.maxConcurrent})
@modal.wsgi_app()
def web():
    import sys, importlib
    sys.path.insert(0, "/app")
    module_name, _, attr = "${v.entry}".partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "app")
`;
}

function staticTemplate(v: TemplateVars): string {
  return `import modal
import subprocess

app = modal.App("m-gpux-host-${v.slug}")
image = (
    modal.Image.debian_slim(python_version="${v.pythonVersion}")
    .add_local_dir("${v.localDir}", remote_path="/site", ignore=${JSON.stringify(v.excludePatterns)})
)

PORT = 8000

@app.function(
    image=image,
    ${v.computeSpec},
    timeout=86400,
    scaledown_window=${v.scaledown},
    min_containers=${v.minContainers},
)
@modal.concurrent(max_inputs=${v.maxConcurrent})
@modal.web_server(port=PORT, startup_timeout=60)
def web():
    subprocess.Popen(
        ["python", "-m", "http.server", str(PORT), "--directory", "/site"],
    )
`;
}

interface TemplateVars {
  slug: string;
  entry: string;
  localDir: string;
  pythonVersion: string;
  pipSection: string;
  excludePatterns: string[];
  computeSpec: string;
  scaledown: number;
  minContainers: number;
  maxConcurrent: number;
}

export async function runHostWizard(): Promise<void> {
  const profiles = loadProfiles();
  if (profiles.length === 0) {
    const add = await vscode.window.showWarningMessage("No Modal accounts configured.", "Add Account");
    if (add === "Add Account") { vscode.commands.executeCommand("mgpux.addAccount"); }
    return;
  }

  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceFolder) {
    vscode.window.showErrorMessage("No workspace folder open. Open the folder containing your web app first.");
    return;
  }
  const localDir = workspaceFolder.replace(/\\/g, "/");

  // Step 1 — kind
  const kindPick = await vscode.window.showQuickPick(
    [
      { label: "$(server-environment) ASGI",   description: "FastAPI / Starlette / Quart — module:variable entry" },
      { label: "$(server) WSGI",               description: "Flask / Django — module:variable entry" },
      { label: "$(file-directory) Static site", description: "Serve a folder of HTML/JS/CSS" },
    ],
    { title: "M-GPUX Host — Step 1/5: Choose target", placeHolder: "What kind of web app are you hosting?" }
  );
  if (!kindPick) { return; }
  const kind: HostKind = kindPick.label.includes("ASGI")
    ? "asgi"
    : kindPick.label.includes("WSGI") ? "wsgi" : "static";

  // Step 2 — profile
  let selectedProfile = getActiveProfile()?.name;
  if (profiles.length > 1) {
    const pick = await vscode.window.showQuickPick(
      profiles.map((p) => ({ label: p.active ? `$(check) ${p.name}` : `$(person) ${p.name}`, profileName: p.name })),
      { title: "M-GPUX Host — Step 2/5: Select profile" }
    );
    if (!pick) { return; }
    selectedProfile = (pick as any).profileName;
  }
  if (!selectedProfile) {
    vscode.window.showErrorMessage("No active profile.");
    return;
  }
  switchProfile(selectedProfile);

  // Step 3 — name + entry
  const defaultName = path.basename(localDir);
  const appName = await vscode.window.showInputBox({
    title: "M-GPUX Host — Step 3/5: App name",
    value: defaultName,
    prompt: "Short name for the Modal app (used in the URL)",
  });
  if (!appName) { return; }

  let entry = "";
  if (kind !== "static") {
    const placeholder = kind === "asgi" ? "main:app" : "app:app";
    const inputEntry = await vscode.window.showInputBox({
      title: `M-GPUX Host — ${kind.toUpperCase()} entry`,
      placeHolder: placeholder,
      value: detectEntry(localDir, kind) ?? placeholder,
      prompt: `module:variable — e.g. \`${placeholder}\` for \`${kind === "asgi" ? "app = FastAPI()" : "app = Flask(__name__)"}\` in ${kind === "asgi" ? "main.py" : "app.py"}`,
      validateInput: (val) => /^[A-Za-z_][\w.]*:[A-Za-z_]\w*$/.test(val.trim())
        ? undefined
        : 'Use the form "module:variable", e.g. main:app',
    });
    if (!inputEntry) { return; }
    entry = inputEntry.trim();
  }

  // Step 4 — compute
  const computeTypePick = await vscode.window.showQuickPick(
    [
      { label: "$(circuit-board) CPU", description: "Recommended for typical web apps", value: "cpu" },
      { label: "$(symbol-misc) GPU",  description: "If your app needs CUDA",            value: "gpu" },
    ],
    { title: "M-GPUX Host — Step 4/5: Compute type" }
  );
  if (!computeTypePick) { return; }
  let computeSpec: string;
  let computeLabel: string;
  if ((computeTypePick as any).value === "cpu") {
    const cpuPick = await vscode.window.showQuickPick(CPU_OPTIONS, { title: "Select CPU" });
    if (!cpuPick) { return; }
    computeSpec = cpuPick.spec;
    computeLabel = cpuPick.compute;
  } else {
    const gpuPick = await vscode.window.showQuickPick(GPU_OPTIONS, { title: "Select GPU" });
    if (!gpuPick) { return; }
    computeSpec = gpuPick.spec;
    computeLabel = gpuPick.label;
  }

  // Step 5 — warm replicas + mode
  const warmPick = await vscode.window.showQuickPick(
    [
      { label: "$(zap) Auto-scale to 0",  description: "Cheapest. ~5–15s cold start when idle.", warm: 0 },
      { label: "$(flame) Keep 1 warm",    description: "No cold starts. Costs continuously.",     warm: 1 },
    ],
    { title: "M-GPUX Host — Warm replicas" }
  );
  if (!warmPick) { return; }
  const modePick = await vscode.window.showQuickPick(
    [
      { label: "$(rocket) Deploy",  description: "Persistent — URL stays live until you stop it", mode: "deploy" as const },
      { label: "$(play) Run",       description: "Ephemeral — runs until Ctrl+C, no public DNS",  mode: "run"    as const },
    ],
    { title: "M-GPUX Host — Mode" }
  );
  if (!modePick) { return; }

  const pipSection = await askPipSection(localDir);
  const excludeInput = await vscode.window.showInputBox({
    title: "Exclude patterns (comma-separated)",
    value: DEFAULT_EXCLUDES.join(", "),
    prompt: "Globs to exclude from upload",
  });
  if (excludeInput === undefined) { return; }
  const excludes = excludeInput.split(",").map((s) => s.trim()).filter(Boolean);

  const vars: TemplateVars = {
    slug: slugify(appName),
    entry,
    localDir,
    pythonVersion: "3.12",
    pipSection,
    excludePatterns: excludes,
    computeSpec,
    scaledown: 60,
    minContainers: warmPick.warm,
    maxConcurrent: 100,
  };
  const script = kind === "asgi" ? asgiTemplate(vars)
              : kind === "wsgi" ? wsgiTemplate(vars)
              : staticTemplate(vars);

  await launchModalScript({
    scriptContent: script,
    cwd: localDir,
    mode: modePick.mode,
    kind: `host-${kind}`,
    computeLabel,
    profile: selectedProfile,
  });
}

function detectEntry(localDir: string, kind: "asgi" | "wsgi"): string | undefined {
  // Best-effort guess so the user doesn't have to type from scratch.
  // We scan a handful of common filenames for `app = FastAPI()` / `app = Flask(...)`.
  const candidates = kind === "asgi"
    ? ["main.py", "app.py", "asgi.py", "server.py"]
    : ["app.py", "main.py", "wsgi.py", "server.py"];
  const needle = kind === "asgi" ? /(FastAPI|Starlette|Quart)/ : /Flask\s*\(/;
  for (const name of candidates) {
    const full = path.join(localDir, name);
    try {
      const src = fs.readFileSync(full, "utf-8");
      if (needle.test(src)) {
        const mod = name.replace(/\.py$/, "");
        return `${mod}:app`;
      }
    } catch { /* ignore */ }
  }
  return undefined;
}

async function askPipSection(localDir: string): Promise<string> {
  const reqPath = path.join(localDir, "requirements.txt");
  if (fs.existsSync(reqPath)) {
    const use = await vscode.window.showQuickPick(
      [
        { label: "$(check) Yes", description: "Install from requirements.txt", value: true },
        { label: "$(x) No",       description: "No extra packages",            value: false },
      ],
      { title: "Found requirements.txt — install it?" }
    );
    if (use && (use as any).value) {
      const escaped = reqPath.replace(/\\/g, "/");
      return `.pip_install_from_requirements("${escaped}")`;
    }
  }
  const extras = await vscode.window.showInputBox({
    title: "Pip packages (comma-separated, blank to skip)",
    value: "",
    placeHolder: "fastapi, uvicorn[standard], pydantic",
  });
  if (!extras || !extras.trim()) { return ""; }
  const pkgs = extras.split(",").map((s) => s.trim()).filter(Boolean);
  return ".pip_install(" + pkgs.map((p) => JSON.stringify(p)).join(", ") + ")";
}
