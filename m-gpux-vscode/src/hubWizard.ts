import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { loadProfiles, switchProfile, getActiveProfile } from "./config";

// ---------------------------------------------------------------------------
// GPU catalogue (mirrors CLI)
// ---------------------------------------------------------------------------
interface GpuOption {
  id: string;
  label: string;
  description: string;
}

const AVAILABLE_GPUS: GpuOption[] = [
  { id: "T4", label: "T4", description: "Light inference / exploration (16 GB)" },
  { id: "L4", label: "L4", description: "Balance of cost / performance (24 GB)" },
  { id: "A10G", label: "A10G", description: "Training / inference (24 GB)" },
  { id: "L40S", label: "L40S", description: "Ada Lovelace, great for inference (48 GB)" },
  { id: "A100", label: "A100", description: "High performance (40 GB SXM)" },
  { id: "A100-40GB", label: "A100-40GB", description: "Ampere 40 GB variant" },
  { id: "A100-80GB", label: "A100-80GB", description: "Extreme performance (80 GB)" },
  { id: "RTX-PRO-6000", label: "RTX-PRO-6000", description: "Pro workstation GPU (48 GB)" },
  { id: "H100", label: "H100", description: "Hopper architecture (80 GB)" },
  { id: "H100!", label: "H100!", description: "H100 priority / reserved" },
  { id: "H200", label: "H200", description: "Next-gen Hopper HBM3e (141 GB)" },
  { id: "B200", label: "B200", description: "Blackwell — latest gen" },
  { id: "B200+", label: "B200+", description: "B200 priority / reserved" },
];

// ---------------------------------------------------------------------------
// Script templates (mirrors hub.py)
// ---------------------------------------------------------------------------
const METRICS_SNIPPET = `
import threading, subprocess, time, json, re

def _print_metrics():
    try:
        out = subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu","--format=csv,noheader,nounits"], text=True)
        for line in out.strip().split("\\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 7:
                print(f"[GPU] {parts[0]} | Driver {parts[1]} | VRAM {parts[3]}/{parts[2]} MB ({parts[4]} free) | Util {parts[5]}% | Temp {parts[6]}°C")
    except Exception as e:
        print(f"[metrics] GPU info unavailable: {e}")
    try:
        with open("/proc/meminfo") as f:
            mi = {k.strip(): v.strip() for line in f for k, v in [line.split(":") ]}
        total = int(mi["MemTotal"].split()[0]) / 1048576
        avail = int(mi["MemAvailable"].split()[0]) / 1048576
        print(f"[SYS] RAM {total - avail:.1f}/{total:.1f} GB used | {avail:.1f} GB free")
    except Exception:
        pass

def _monitor_metrics(interval=30):
    def _loop():
        while True:
            time.sleep(interval)
            try:
                out = subprocess.check_output(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw","--format=csv,noheader,nounits"], text=True)
                for line in out.strip().split("\\n"):
                    p = [x.strip() for x in line.split(",")]
                    if len(p) >= 5:
                        print(f"[monitor] GPU util {p[0]}% | VRAM {p[1]}/{p[2]} MB | Temp {p[3]}°C | Power {p[4]}W")
            except Exception:
                pass
            try:
                with open("/proc/loadavg") as f:
                    load = f.read().split()[:3]
                print(f"[monitor] CPU load avg: {' '.join(load)}")
            except Exception:
                pass
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
`;

const WEB_TERMINAL_BASHRC = String.raw`
export TERM=xterm-256color
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export EDITOR=nano
export HISTSIZE=50000
export HISTFILESIZE=100000
export HISTCONTROL=ignoreboth:erasedups
shopt -s histappend checkwinsize globstar 2>/dev/null
export PS1='\[\e[1;36m\]\w\[\e[0m\] \[\e[1;32m\]\$\[\e[0m\] '
alias ll='ls -lah --color=auto --group-directories-first'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias py='python'
alias gpus='nvidia-smi'
cd /workspace 2>/dev/null || true
if [ -z "$M_GPUX_WELCOMED" ] && [ -t 1 ]; then
  export M_GPUX_WELCOMED=1
  printf "\n\033[1mM-GPUX Web Terminal\033[0m\n"
  printf "Tools: ll, py, gpus, rg, fd, top. Run tmux manually if you want sessions.\n\n"
fi
`;

const WEB_TERMINAL_TMUX_CONF = String.raw`
set -g default-terminal "xterm-256color"
set -g mouse on
set -g history-limit 200000
set -g status off
setw -g mode-keys vi
set -sg escape-time 10
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g aggressive-resize on
bind | split-window -h -c "#{pane_current_path}"
bind - split-window -v -c "#{pane_current_path}"
`;

const STABLE_TTYD_FLAGS = [
  "-W",
  "-P", "120",
  "-t", "fontSize=14",
  "-t", "fontFamily=Cascadia Mono, Consolas, Menlo, monospace",
  "-t", "fontWeight=400",
  "-t", "fontWeightBold=700",
  "-t", "lineHeight=1.2",
  "-t", "letterSpacing=0",
  "-t", "cursorStyle=bar",
  "-t", "cursorBlink=true",
  "-t", "scrollback=10000",
  "-t", "scrollSensitivity=1",
  "-t", "rendererType=canvas",
  "-t", "customGlyphs=true",
  "-t", "rescaleOverlappingGlyphs=true",
  "-t", "drawBoldTextInBrightColors=false",
  "-t", "smoothScrollDuration=125",
  "-t", "fastScrollModifier=alt",
  "-t", "fastScrollSensitivity=10",
  "-t", "disableResizeOverlay=true",
  "-t", "macOptionIsMeta=true",
  "-t", "theme={\"background\":\"#1e1e2e\",\"foreground\":\"#cdd6f4\",\"cursor\":\"#f5e0dc\",\"cursorAccent\":\"#1e1e2e\",\"selectionBackground\":\"#585b70\",\"black\":\"#45475a\",\"red\":\"#f38ba8\",\"green\":\"#a6e3a1\",\"yellow\":\"#f9e2af\",\"blue\":\"#89b4fa\",\"magenta\":\"#f5c2e7\",\"cyan\":\"#94e2d5\",\"white\":\"#bac2de\",\"brightBlack\":\"#585b70\",\"brightRed\":\"#f38ba8\",\"brightGreen\":\"#a6e3a1\",\"brightYellow\":\"#f9e2af\",\"brightBlue\":\"#89b4fa\",\"brightMagenta\":\"#f5c2e7\",\"brightCyan\":\"#94e2d5\",\"brightWhite\":\"#a6adc8\"}",
  "-T", "xterm-256color",
];

function jupyterScript(gpu: string, localDir: string, pipSection: string, excludePatterns: string[]): string {
  return `import modal
import subprocess
import time

${METRICS_SNIPPET}

app = modal.App("m-gpux-jupyter")
image = modal.Image.debian_slim()${pipSection}.pip_install("jupyterlab").add_local_dir(
    "${localDir}", remote_path="/workspace", ignore=${JSON.stringify(excludePatterns)}
)

@app.function(image=image, gpu="${gpu}", timeout=86400)
def run_jupyter():
    _print_metrics()
    _monitor_metrics()
    jupyter_port = 8888
    with modal.forward(jupyter_port) as tunnel:
        print(f"\\n=======================================================")
        print(f"[JUPYTER READY] Connect via this URL: {tunnel.url}")
        print(f"  Workspace files mounted at: /workspace")
        print(f"=======================================================\\n")
        subprocess.Popen([
            "jupyter", "lab", "--no-browser", "--allow-root",
            "--ip=0.0.0.0", "--port", str(jupyter_port),
            "--NotebookApp.token=''", "--NotebookApp.password=''",
            "--ServerApp.disable_check_xsrf=True",
            "--ServerApp.allow_origin='*'",
            "--ServerApp.allow_remote_access=True",
            "--ServerApp.root_dir=/workspace",
        ])
        time.sleep(86400)
`;
}

function pythonScript(gpu: string, localDir: string, scriptName: string, pipSection: string, excludePatterns: string[]): string {
  return `import modal
import subprocess
import sys

${METRICS_SNIPPET}

app = modal.App("m-gpux-runner")
image = modal.Image.debian_slim()${pipSection}.add_local_dir(
    "${localDir}", remote_path="/workspace", ignore=${JSON.stringify(excludePatterns)}
)

@app.function(image=image, gpu="${gpu}", timeout=86400)
def run_script():
    _print_metrics()
    print("[EXECUTING] ${scriptName} on ${gpu}...")
    subprocess.run(
        [sys.executable, "/workspace/${scriptName}"],
        text=True,
        check=True,
    )
`;
}

function bashScript(gpu: string): string {
  return `import modal
import os
import subprocess

${METRICS_SNIPPET}

app = modal.App("m-gpux-shell")
image = modal.Image.debian_slim().apt_install("bash", "curl", "tmux").run_commands(
    "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64",
    "chmod +x /usr/local/bin/ttyd"
).pip_install("torch")

@app.function(image=image, gpu="${gpu}", timeout=86400)
def run_shell():
    _print_metrics()
    port = 8888
    env = {**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    os.makedirs("/workspace", exist_ok=True)
    with open("/root/.bashrc", "w", encoding="utf-8") as f:
        f.write(${JSON.stringify(WEB_TERMINAL_BASHRC)})
    with open("/root/.tmux.conf", "w", encoding="utf-8") as f:
        f.write(${JSON.stringify(WEB_TERMINAL_TMUX_CONF)})
    with modal.forward(port) as tunnel:
        print("\\n[WEB SHELL READY]")
        print("URL: " + tunnel.url)
        print("Workspace: /workspace   Mode: direct bash\\n")
        proc = subprocess.Popen(
            ["ttyd", *${JSON.stringify(STABLE_TTYD_FLAGS)}, "-p", str(port), "bash", "--login"],
            env=env,
        )
        proc.wait()
`;
}

function vllmScript(gpu: string, modelName: string): string {
  return `import modal
import subprocess

${METRICS_SNIPPET}

app = modal.App("m-gpux-vllm")

MODEL_NAME = "${modelName}"

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm", "transformers", "hf-transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache = modal.Volume.from_name("m-gpux-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

@app.function(
    image=vllm_image,
    gpu="${gpu}",
    timeout=24 * 60 * MINUTES,
    scaledown_window=5 * MINUTES,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
    },
)
@modal.concurrent(max_inputs=50)
@modal.web_server(port=8000, startup_timeout=10 * MINUTES)
def serve():
    _print_metrics()
    _monitor_metrics()
    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--served-model-name", MODEL_NAME, "llm",
        "--host", "0.0.0.0", "--port", "8000",
        "--enforce-eager", "--tensor-parallel-size", "1",
    ]
    print("Starting vLLM:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)
`;
}

function interactiveScript(gpu: string, localDir: string, scriptName: string, pipSection: string, excludePatterns: string[]): string {
  return `import modal
import subprocess
import os

${METRICS_SNIPPET}

app = modal.App("m-gpux-interactive")
image = modal.Image.debian_slim().apt_install("bash", "curl", "tmux").run_commands(
    "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64",
    "chmod +x /usr/local/bin/ttyd"
)${pipSection}.add_local_dir(
    "${localDir}", remote_path="/workspace", ignore=${JSON.stringify(excludePatterns)}
)

@app.function(image=image, gpu="${gpu}", timeout=86400)
def run_interactive():
    _print_metrics()
    port = 8888
    env = {**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    with open("/root/.bashrc", "w", encoding="utf-8") as f:
        f.write(${JSON.stringify(WEB_TERMINAL_BASHRC)})
    with open("/root/.tmux.conf", "w", encoding="utf-8") as f:
        f.write(${JSON.stringify(WEB_TERMINAL_TMUX_CONF)})
    with modal.forward(port) as tunnel:
        url = tunnel.url
        print("\\n[INTERACTIVE TERMINAL READY]")
        print("URL: " + url)
        print("Workspace: /workspace   Run: python ${scriptName}\\n")
        proc = subprocess.Popen(
            ["ttyd", *${JSON.stringify(STABLE_TTYD_FLAGS)}, "-p", str(port), "bash", "--login"],
            env=env,
        )
        proc.wait()
`;
}

// ---------------------------------------------------------------------------
// Wizard
// ---------------------------------------------------------------------------
export async function runHubWizard(): Promise<void> {
  // Step 0: Select profile
  const profiles = loadProfiles();
  if (profiles.length === 0) {
    const action = await vscode.window.showWarningMessage(
      "No Modal accounts configured.",
      "Add Account"
    );
    if (action === "Add Account") {
      vscode.commands.executeCommand("mgpux.addAccount");
    }
    return;
  }

  const profileItems: vscode.QuickPickItem[] = [
    {
      label: "$(sparkle) AUTO",
      description: "Smart pick — most credit remaining",
      detail: "Automatically selects the best profile",
    },
    ...profiles.map((p) => ({
      label: p.active ? `$(check) ${p.name}` : `$(person) ${p.name}`,
      description: p.active ? "Active" : "",
      detail: `Token: ${p.token_id.substring(0, 8)}...`,
    })),
  ];

  let selectedProfileName: string;

  if (profiles.length === 1) {
    selectedProfileName = profiles[0].name;
  } else {
    const profilePick = await vscode.window.showQuickPick(profileItems, {
      title: "M-GPUX Hub — Step 1/4: Select Workspace",
      placeHolder: "Choose a Modal profile or AUTO for smart selection",
    });
    if (!profilePick) { return; }

    if (profilePick.label.includes("AUTO")) {
      // For AUTO, just use the active profile (full balance check requires Modal SDK)
      const active = getActiveProfile();
      if (!active) {
        vscode.window.showErrorMessage("No active profile found.");
        return;
      }
      selectedProfileName = active.name;
      vscode.window.showInformationMessage(`Auto-selected profile: ${selectedProfileName}`);
    } else {
      selectedProfileName = profilePick.label.replace(/^\$\([^)]+\)\s*/, "");
    }
  }

  // Activate selected profile
  switchProfile(selectedProfileName);

  // Step 1: Select GPU
  const gpuPick = await vscode.window.showQuickPick(
    AVAILABLE_GPUS.map((g) => ({
      label: g.label,
      description: g.description,
      id: g.id,
    })),
    {
      title: "M-GPUX Hub — Step 2/4: Choose GPU",
      placeHolder: "Select an NVIDIA GPU accelerator",
    }
  );
  if (!gpuPick) { return; }
  const selectedGpu = gpuPick.label;

  // Step 2: Select action
  const actionPick = await vscode.window.showQuickPick(
    [
      {
        label: "$(notebook) Jupyter Lab",
        description: "Interactive notebook with auto-tunneling",
        action: "jupyter",
      },
      {
        label: "$(play) Run Python Script",
        description: "Upload workspace & execute a .py file",
        action: "python",
      },
      {
        label: "$(terminal) Bash Shell",
        description: "VS Code-like web terminal (direct bash)",
        action: "bash",
      },
      {
        label: "$(server) vLLM Inference Server",
        description: "OpenAI-compatible LLM API endpoint",
        action: "vllm",
      },
    ],
    {
      title: "M-GPUX Hub — Step 3/4: Choose Application",
      placeHolder: "What do you want to run on the GPU?",
    }
  );
  if (!actionPick) { return; }
  const action = (actionPick as any).action as string;

  // Get workspace directory
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceFolder && action !== "bash") {
    vscode.window.showErrorMessage("No workspace folder open. Please open a folder first.");
    return;
  }
  const localDir = (workspaceFolder ?? ".").replace(/\\/g, "/");

  // Default exclude patterns
  const defaultExcludes = [
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    ".mypy_cache", ".pytest_cache", "*.egg-info", ".tox",
  ];

  let scriptContent: string;
  let detach = false;

  switch (action) {
    case "jupyter": {
      const pipSection = await askPipSection(localDir);
      const excludes = await askExcludePatterns(defaultExcludes);
      if (!excludes) { return; }
      scriptContent = jupyterScript(selectedGpu, localDir, pipSection, excludes);
      detach = true;
      break;
    }
    case "python": {
      const pyFile = await pickPythonFile(localDir);
      if (!pyFile) { return; }
      const pipSection = await askPipSection(localDir);
      const excludes = await askExcludePatterns(defaultExcludes);
      if (!excludes) { return; }
      scriptContent = pythonScript(selectedGpu, localDir, pyFile, pipSection, excludes);
      break;
    }
    case "bash": {
      scriptContent = bashScript(selectedGpu);
      detach = true;
      break;
    }
    case "vllm": {
      const model = await pickVllmModel();
      if (!model) { return; }
      scriptContent = vllmScript(selectedGpu, model);
      detach = true;
      break;
    }
    default:
      return;
  }

  // Step 4: Show generated script and execute
  await showAndExecuteScript(scriptContent, selectedGpu, action, detach, localDir);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function askPipSection(localDir: string): Promise<string> {
  const reqPath = path.join(localDir, "requirements.txt");
  if (fs.existsSync(reqPath)) {
    const use = await vscode.window.showQuickPick(
      [
        { label: "$(check) Yes", description: "Install from requirements.txt", value: true },
        { label: "$(x) No", description: "Use default packages (torch, numpy, pandas)", value: false },
      ],
      { title: "Found requirements.txt — use it?" }
    );
    if (use && (use as any).value) {
      const escaped = reqPath.replace(/\\/g, "/");
      return `.pip_install_from_requirements("${escaped}")`;
    }
  }
  return '.pip_install(\n    "torch", "numpy", "pandas"\n)';
}

async function askExcludePatterns(defaults: string[]): Promise<string[] | undefined> {
  const input = await vscode.window.showInputBox({
    title: "Exclude patterns (comma-separated)",
    value: defaults.join(", "),
    prompt: "Glob patterns to exclude from upload to the container",
  });
  if (input === undefined) { return undefined; }
  return input.split(",").map((s) => s.trim()).filter(Boolean);
}

async function pickPythonFile(localDir: string): Promise<string | undefined> {
  const files: string[] = fs.readdirSync(localDir).filter((f: string) => f.endsWith(".py"));
  if (files.length === 0) {
    const manual = await vscode.window.showInputBox({
      title: "Enter Python script filename",
      placeHolder: "main.py",
    });
    return manual;
  }
  const pick = await vscode.window.showQuickPick(
    files.map((f: string) => ({ label: f })),
    {
      title: "Select Python script to run",
      placeHolder: "Choose a .py file from your workspace",
    }
  );
  return pick?.label;
}

async function pickVllmModel(): Promise<string | undefined> {
  const models = [
    { label: "Qwen/Qwen2.5-1.5B-Instruct", description: "Tiny 1.5B — T4/L4 friendly, fast" },
    { label: "Qwen/Qwen2.5-7B-Instruct", description: "7B — A10G/A100, good quality" },
    { label: "meta-llama/Llama-3.1-8B-Instruct", description: "Llama 8B — A10G/A100" },
    { label: "google/gemma-2-9b-it", description: "Gemma 9B — A10G/A100" },
    { label: "mistralai/Mistral-7B-Instruct-v0.3", description: "Mistral 7B — A10G/A100" },
  ];
  const pick = await vscode.window.showQuickPick(models, {
    title: "Select model to serve",
    placeHolder: "Choose an LLM model",
  });
  return pick?.label;
}

async function showAndExecuteScript(
  content: string,
  gpu: string,
  actionType: string,
  detach: boolean,
  localDir: string
): Promise<void> {
  const { spawn } = require("child_process");

  // Write temporary script
  const runnerPath = path.join(localDir, "modal_runner.py");
  fs.writeFileSync(runnerPath, content, "utf-8");

  // Open in editor for review
  const doc = await vscode.workspace.openTextDocument(runnerPath);
  await vscode.window.showTextDocument(doc, { preview: true });

  // Ask to execute
  const choice = await vscode.window.showInformationMessage(
    `Ready to launch ${actionType} on ${gpu}. Review the script, then choose an action.`,
    { modal: true },
    "Launch",
    "Cancel"
  );

  if (choice === "Cancel" || !choice) {
    vscode.window.showInformationMessage("Execution cancelled. modal_runner.py kept for manual use.");
    return;
  }

  // Create output channel for logs
  const outputChannel = vscode.window.createOutputChannel(`M-GPUX: ${actionType} (${gpu})`, "log");
  outputChannel.show(true);
  outputChannel.appendLine(`═══════════════════════════════════════════════`);
  outputChannel.appendLine(`  M-GPUX: Launching ${actionType} on ${gpu}`);
  outputChannel.appendLine(`  Profile: ${getActiveProfile()?.name ?? "default"}`);
  outputChannel.appendLine(`  Time: ${new Date().toLocaleString()}`);
  outputChannel.appendLine(`═══════════════════════════════════════════════\n`);

  // Activate profile first
  const selectedProfile = getActiveProfile();
  if (selectedProfile) {
    outputChannel.appendLine(`▸ Activating profile: ${selectedProfile.name}`);
    const activateResult = await runCommand("modal", ["profile", "activate", selectedProfile.name], localDir);
    if (activateResult.exitCode !== 0) {
      outputChannel.appendLine(`⚠ Profile activation warning: ${activateResult.stderr}`);
    } else {
      outputChannel.appendLine(`✓ Profile activated\n`);
    }
  }

  // Run modal with progress — use just filename with cwd to avoid space-in-path issues
  const useDetach = detach;
  const runnerFilename = path.basename(runnerPath);
  const args = useDetach
    ? ["run", "--detach", runnerFilename]
    : ["run", runnerFilename];

  outputChannel.appendLine(`▸ Running: modal ${args.join(" ")}`);
  outputChannel.appendLine(`  CWD: ${localDir}`);
  outputChannel.appendLine(`  Mode: ${useDetach ? "Detached (background)" : "Foreground"}\n`);

  // Show progress in notification
  vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `M-GPUX: Launching ${actionType} on ${gpu}...`,
      cancellable: true,
    },
    (progress, token) => {
      return new Promise<void>((resolve) => {
        const proc = spawn("modal", args, {
          cwd: localDir,
          shell: true,
          env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
        });

        let foundUrl = false;

        token.onCancellationRequested(() => {
          proc.kill();
          outputChannel.appendLine("\n⚠ Cancelled by user.");
          resolve();
        });

        proc.stdout.on("data", (data: Buffer) => {
          const text = data.toString();
          outputChannel.append(text);

          // Detect URLs in output
          const urlMatch = text.match(/https?:\/\/[^\s"']+/g);
          if (urlMatch && !foundUrl) {
            foundUrl = true;
            const url = urlMatch[0];

            progress.report({ message: "Ready! Opening..." });

            // Show persistent notification with URL
            vscode.window.showInformationMessage(
              `${actionType} is ready on ${gpu}!`,
              "Open in Browser",
              "Copy URL"
            ).then((action) => {
              if (action === "Open in Browser") {
                vscode.env.openExternal(vscode.Uri.parse(url));
              } else if (action === "Copy URL") {
                vscode.env.clipboard.writeText(url);
                vscode.window.showInformationMessage("URL copied to clipboard!");
              }
            });

            outputChannel.appendLine(`\n${"═".repeat(50)}`);
            outputChannel.appendLine(`  ✓ ${actionType} READY`);
            outputChannel.appendLine(`  URL: ${url}`);
            outputChannel.appendLine(`${"═".repeat(50)}\n`);
          }
        });

        proc.stderr.on("data", (data: Buffer) => {
          const text = data.toString();
          outputChannel.append(text);

          // Modal also prints URLs and status to stderr
          const urlMatch = text.match(/https?:\/\/[^\s"']+/g);
          if (urlMatch && !foundUrl) {
            foundUrl = true;
            const url = urlMatch[0];
            progress.report({ message: "Ready!" });

            vscode.window.showInformationMessage(
              `${actionType} is running on ${gpu}`,
              "Open Modal Dashboard"
            ).then((action) => {
              if (action === "Open Modal Dashboard") {
                vscode.env.openExternal(vscode.Uri.parse(url));
              }
            });
          }
        });

        proc.on("close", (code: number | null) => {
          if (code === 0) {
            outputChannel.appendLine(`\n✓ Process completed successfully.`);
            if (!foundUrl) {
              vscode.window.showInformationMessage(`${actionType} on ${gpu} completed.`);
            }
          } else if (code !== null) {
            outputChannel.appendLine(`\n✗ Process exited with code ${code}.`);
            vscode.window.showWarningMessage(
              `${actionType} exited with code ${code}. Check Output for details.`
            );
          }

          // Cleanup temp file
          try {
            if (fs.existsSync(runnerPath)) {
              fs.unlinkSync(runnerPath);
              outputChannel.appendLine(`  Cleaned up ${path.basename(runnerPath)}`);
            }
          } catch { /* ignore */ }

          resolve();
        });

        proc.on("error", (err: Error) => {
          outputChannel.appendLine(`\n✗ Failed to start: ${err.message}`);
          vscode.window.showErrorMessage(`Failed to run modal: ${err.message}`);
          resolve();
        });
      });
    }
  );
}

/** Helper: run a command and return stdout/stderr/exitCode */
function runCommand(cmd: string, args: string[], cwd: string): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const { spawn } = require("child_process");
  return new Promise((resolve) => {
    const proc = spawn(cmd, args, { cwd, shell: true, env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" } });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    proc.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });
    proc.on("close", (code: number | null) => {
      resolve({ stdout, stderr, exitCode: code ?? 1 });
    });
    proc.on("error", () => {
      resolve({ stdout, stderr, exitCode: 1 });
    });
  });
}
