import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as crypto from "crypto";
import { loadProfiles, switchProfile, getActiveProfile, fetchFunctionWebUrl } from "./config";
import { sessionStore, newSessionId, SessionKind, sessionLogPath, appendSessionLog } from "./sessionStore";
import { extractWebEndpoint } from "./modalCli";
import { startLiveSync } from "./liveSync";

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

const PYTHON_VERSIONS = [
  { label: "3.12", description: "Default, broadly compatible" },
  { label: "3.11", description: "Stable for older ML packages" },
  { label: "3.10", description: "Minimum supported by m-gpux" },
  { label: "3.13", description: "Newer runtime, package support may vary" },
  { label: "3.14", description: "Latest runtime, package support may vary" },
  { label: "Custom", description: "Type a Modal-supported Python version" },
];

// Turn user-facing exclude names into patterns Modal actually honours at every
// depth.
//
// Image.add_local_dir(ignore=[...]) uses dockerignore-style matching, which
// anchors a bare name to the root: "node_modules" excludes "./node_modules"
// but NOT "m-gpux-vscode/node_modules". That silently shipped every nested
// node_modules/.venv/__pycache__ into the workspace volume — in one real case
// 8,153 files / 144 MB, of which only ~213 files / 2 MB were actual work.
// Prefixing each name with a globstar matches at any depth (and still matches
// the root).
export function toRecursiveIgnore(patterns: string[]): string[] {
  const out = new Set<string>();
  for (const raw of patterns) {
    // Strip a leading "./" and any trailing slash — but never leading dots,
    // or dotfile excludes like ".venv" / ".git" would become "venv" / "git".
    const p = raw.trim().replace(/^(?:\.\/)+/, "").replace(/\/+$/, "");
    if (!p) { continue; }
    out.add(p.startsWith("**/") ? p : `**/${p}`);
  }
  return Array.from(out);
}

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

// `$` helper: TypeScript template literals interpret `${...}` as interpolation.
// Use `${D}{foo}` to emit a literal `${foo}` into the bashrc (for bash parameter expansion).
const D = "$";

const WEB_TERMINAL_BASHRC = String.raw`
# ---------- env ----------
export TERM=xterm-256color
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export EDITOR=nano
export HISTSIZE=50000
export HISTFILESIZE=100000
export HISTCONTROL=ignoreboth:erasedups
shopt -s histappend checkwinsize globstar 2>/dev/null

# ---------- color ----------
export CLICOLOR=1
export LESS="-R"
export GREP_COLORS="mt=01;38;5;214"

# ---------- aliases ----------
alias ll='ls -lah --color=auto --group-directories-first'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias gpus='nvidia-smi'
alias g='git'
alias gs='git status'
alias gl='git log --oneline --graph --decorate -20'
alias py='python'
alias ipy='ipython'
alias venv='python -m venv .venv && source .venv/bin/activate'
command -v batcat >/dev/null && alias cat='batcat --paging=never --style=plain' && alias bat='batcat'
command -v fdfind >/dev/null && alias fd='fdfind'
command -v btop  >/dev/null && alias top='btop'
alias df='df -h'
alias du='du -h'
alias free='free -h'
alias mkdir='mkdir -pv'

# ---------- fzf ----------
[ -f /usr/share/doc/fzf/examples/key-bindings.bash ] && source /usr/share/doc/fzf/examples/key-bindings.bash
[ -f /usr/share/doc/fzf/examples/completion.bash ]   && source /usr/share/doc/fzf/examples/completion.bash
export FZF_DEFAULT_OPTS="--height 40% --layout=reverse --border --color=bg+:#313244,bg:#1e1e2e,spinner:#f5e0dc,hl:#f38ba8,fg:#cdd6f4,header:#f38ba8,info:#cba6f7,pointer:#f5e0dc,marker:#f5e0dc,fg+:#cdd6f4,prompt:#cba6f7,hl+:#f38ba8"
command -v fdfind >/dev/null && export FZF_DEFAULT_COMMAND='fdfind --type f --hidden --exclude .git'

# ---------- prompt ----------
export PS1='\[\e[1;36m\]\w\[\e[0m\] \[\e[1;32m\]\$\[\e[0m\] '

cd /workspace 2>/dev/null || true

# ---------- welcome banner ----------
if [ -z "$M_GPUX_WELCOMED" ] && [ -t 1 ]; then
    export M_GPUX_WELCOMED=1
    _GREEN='\033[38;5;150m'; _DIM='\033[2m'; _BOLD='\033[1m'; _R='\033[0m'
    printf "\n${D}{_BOLD}M-GPUX Web Terminal${D}{_R}\n"
    if command -v nvidia-smi >/dev/null 2>&1; then
        _gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | sed 's/, / - /;s/$/ MiB/')
        [ -n "$_gpu" ] && printf "GPU: %s\n" "$_gpu"
    fi
    _cpu=$(grep -c ^processor /proc/cpuinfo 2>/dev/null)
    _mem=$(awk '/MemTotal/ {printf "%.1f GiB", $2/1024/1024}' /proc/meminfo 2>/dev/null)
    printf "CPU: %s cores   RAM: %s   WD: /workspace\n" "${D}{_cpu:-?}" "${D}{_mem:-?}"
    printf "${D}{_DIM}Tools: ll, py, gpus, rg, fd, top.  Inside tmux 'main' — Ctrl+B then D detaches; close & reopen URL to reattach.${D}{_R}\n\n"
fi
`;

const WEB_TERMINAL_TMUX_CONF = String.raw`
set -g default-terminal "xterm-256color"
set -ga terminal-overrides ",xterm-256color:Tc"
set -as terminal-features ",xterm-256color:RGB"
set -g mouse on
set -g history-limit 200000
set -g status off
setw -g mode-keys vi
set -sg escape-time 0
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g focus-events on

# --- Smooth scrolling ---
bind -n WheelUpPane   if-shell -F "#{alternate_on}" "send-keys -M" "select-pane -t=; copy-mode -e; send-keys -M"
bind -n WheelDownPane if-shell -F "#{alternate_on}" "send-keys -M" "select-pane -t=; send-keys -M"
bind -T copy-mode-vi WheelUpPane   send-keys -X -N 3 scroll-up
bind -T copy-mode-vi WheelDownPane send-keys -X -N 3 scroll-down

# nicer splits
bind | split-window -h -c "#{pane_current_path}"
bind - split-window -v -c "#{pane_current_path}"
bind r source-file ~/.tmux.conf \; display "reloaded"

# --- Catppuccin Mocha ---
set -g status-position bottom
set -g status-justify left
set -g status-style "bg=#1e1e2e fg=#cdd6f4"
set -g status-left-length 60
set -g status-right-length 120
set -g status-left "#[bg=#cba6f7,fg=#1e1e2e,bold] m-gpux #[bg=#313244,fg=#cba6f7] #S #[bg=#1e1e2e,fg=#313244] "
set -g status-right "#[fg=#313244]#[bg=#313244,fg=#fab387] #(awk '{printf \"%.2f\", $1}' /proc/loadavg) #[bg=#313244,fg=#a6e3a1]#[bg=#a6e3a1,fg=#1e1e2e,bold] %H:%M "
setw -g window-status-format "#[fg=#6c7086] #I:#W "
setw -g window-status-current-format "#[bg=#cba6f7,fg=#1e1e2e,bold] #I:#W #[bg=#1e1e2e,fg=#cba6f7]"
set -g pane-border-style "fg=#313244"
set -g pane-active-border-style "fg=#cba6f7"
set -g message-style "bg=#cba6f7,fg=#1e1e2e,bold"
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

// ---------------------------------------------------------------------------
// Container-side workspace sync
// ---------------------------------------------------------------------------
// The container used to commit() + reload() the volume every 5 seconds. On a
// real workspace that re-uploads multi-GB checkpoints over and over, which is
// slow and mostly pointless. Nothing syncs on a timer any more -- the user
// decides when, from inside the session:
//   - `msync`      push /workspace -> volume (in a notebook cell: !msync)
//   - `msync pull` pull volume -> /workspace (after a push from the extension)
// Modal still commits the volume once when the container exits.
export function syncHelperBlock(workspaceVolume: string): string {
  return `def _install_sync_helper():
    helper = """#!/usr/bin/env python3
import sys
import modal

vol = modal.Volume.from_name("${workspaceVolume}")
mode = (sys.argv[1:] or ["push"])[0]
if mode in ("pull", "down"):
    vol.reload()
    print("[sync] volume -> /workspace")
else:
    vol.commit()
    print("[sync] /workspace -> volume")
"""
    with open("/usr/local/bin/msync", "w") as f:
        f.write(helper)
    os.chmod("/usr/local/bin/msync", 0o755)
    print("[sync] manual sync only: run 'msync' to push, 'msync pull' to pull", flush=True)
`;
}

function jupyterScript(computeSpec: string, pythonVersion: string, localDir: string, pipSection: string, excludePatterns: string[], minContainers: number, scaledownWindow: string): string {
  const workspaceVolume = workspaceVolumeName(localDir);
  return `import modal
import subprocess
import time
import os
import threading

${METRICS_SNIPPET}

app = modal.App("m-gpux-jupyter")
workspace_volume = modal.Volume.from_name("${workspaceVolume}", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="${pythonVersion}")
    ${pipSection}
    .pip_install(
        "jupyterlab>=4.2",
        "jupyter-server>=2.14",
        "ipywidgets",
        # Real-time collaboration keeps notebook + cell outputs in a CRDT
        # Y.Doc on the server. Reconnecting from a new browser tab resyncs
        # the live state (including in-progress cell output) instead of
        # loading a stale snapshot from disk.
        "jupyter-collaboration>=3.0",
    )
    .add_local_dir("${localDir}", remote_path="/workspace_seed", ignore=${JSON.stringify(toRecursiveIgnore(excludePatterns))})
)

MINUTE = 60
HOUR = 60 * MINUTE

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    # Local files should win on every launch, while remote-only outputs remain.
    subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

${syncHelperBlock(workspaceVolume)}
@app.function(
    image=image,
    ${computeSpec},
    timeout=24 * HOUR,
    scaledown_window=${scaledownWindow},
    min_containers=${minContainers},
    max_containers=1,
    volumes={"/workspace": workspace_volume},
)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=8888, startup_timeout=10 * MINUTE)
def serve():
    _print_metrics()
    _prepare_workspace()
    _install_sync_helper()
    subprocess.Popen(
        [
            "jupyter", "lab",
            "--no-browser",
            "--allow-root",
            "--ip=0.0.0.0",
            "--port", "8888",
            "--ServerApp.token=",
            "--ServerApp.password=",
            "--ServerApp.disable_check_xsrf=True",
            "--ServerApp.allow_origin=*",
            "--ServerApp.allow_remote_access=True",
            "--ServerApp.root_dir=/workspace",
            "--ServerApp.iopub_data_rate_limit=1.0e10",
            "--ServerApp.iopub_msg_rate_limit=1.0e10",
            "--ServerApp.rate_limit_window=3.0",
            "--ServerApp.shutdown_no_activity_timeout=0",
            # Collaborative mode is enabled by installing jupyter-collaboration —
            # we just don't disable it. The flag below would be the kill-switch.
            # "--LabApp.collaborative=False",
        ],
        env={**os.environ, "JUPYTER_PLATFORM_DIRS": "1"},
    )
`;
}

function pythonScript(computeSpec: string, computeLabel: string, pythonVersion: string, localDir: string, scriptName: string, pipSection: string, excludePatterns: string[]): string {
  return `import modal
import subprocess
import sys

${METRICS_SNIPPET}

app = modal.App("m-gpux-runner")
image = modal.Image.debian_slim(python_version="${pythonVersion}")${pipSection}.add_local_dir(
    "${localDir}", remote_path="/workspace", ignore=${JSON.stringify(toRecursiveIgnore(excludePatterns))}
)

@app.function(image=image, ${computeSpec}, timeout=86400)
def run_script():
    _print_metrics()
    print("[EXECUTING] ${scriptName} on ${computeLabel}...")
    subprocess.run(
        [sys.executable, "/workspace/${scriptName}"],
        text=True,
        check=True,
    )
`;
}

function bashScript(computeSpec: string, pythonVersion: string, localDir: string, excludePatterns: string[]): string {
  const workspaceVolume = workspaceVolumeName(localDir);
  return `import modal
import os
import subprocess
import threading
import time

${METRICS_SNIPPET}

app = modal.App("m-gpux-shell")
workspace_volume = modal.Volume.from_name("${workspaceVolume}", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="${pythonVersion}")
    .apt_install(
        "bash", "curl", "tmux", "nano", "vim", "git", "htop", "btop",
        "fzf", "ripgrep", "fd-find", "bat", "locales", "ca-certificates",
        "swig", "build-essential", "unzip",
    )
    .run_commands(
        "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && chmod +x /usr/local/bin/ttyd",
        "mkdir -p /root/.config",
    )
    .add_local_dir("${localDir}", remote_path="/workspace_seed", ignore=${JSON.stringify(toRecursiveIgnore(excludePatterns))})
)

MINUTE = 60
HOUR = 60 * MINUTE

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    # Local files should win on every launch, while remote-only outputs remain.
    subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

${syncHelperBlock(workspaceVolume)}
@app.function(
    image=image,
    ${computeSpec},
    timeout=24 * HOUR,
    scaledown_window=60 * MINUTE,
    max_containers=1,
    volumes={"/workspace": workspace_volume},
)
@modal.concurrent(max_inputs=50)
@modal.web_server(port=8888, startup_timeout=5 * MINUTE)
def serve():
    _print_metrics()
    _prepare_workspace()
    _install_sync_helper()
    env = {**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    with open("/root/.bashrc", "w", encoding="utf-8") as f:
        f.write(${JSON.stringify(WEB_TERMINAL_BASHRC)})
    with open("/root/.tmux.conf", "w", encoding="utf-8") as f:
        f.write(${JSON.stringify(WEB_TERMINAL_TMUX_CONF)})
    subprocess.Popen(
        ["ttyd", *${JSON.stringify(STABLE_TTYD_FLAGS)}, "-p", "8888", "bash", "-lc", "tmux new-session -A -s main"],
        env=env,
    )
`;
}

function vllmScript(computeSpec: string, pythonVersion: string, modelName: string, tensorParallel: number): string {
  return `import modal
import subprocess

${METRICS_SNIPPET}

app = modal.App("m-gpux-vllm")

MODEL_NAME = "${modelName}"

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="${pythonVersion}")
    .entrypoint([])
    .pip_install("vllm", "transformers", "hf-transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache = modal.Volume.from_name("m-gpux-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

@app.function(
    image=vllm_image,
    ${computeSpec},
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
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", "8000",
        "--enforce-eager",
        "--tensor-parallel-size", "${tensorParallel}",
    ]
    print("Starting vLLM:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)
`;
}

function interactiveScript(computeSpec: string, pythonVersion: string, localDir: string, scriptName: string, pipSection: string, excludePatterns: string[]): string {
  const workspaceVolume = workspaceVolumeName(localDir);
  return `import modal
import subprocess
import os
import threading
import time

${METRICS_SNIPPET}

app = modal.App("m-gpux-interactive")
workspace_volume = modal.Volume.from_name("${workspaceVolume}", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="${pythonVersion}")
    .apt_install(
        "bash", "curl", "tmux", "nano", "vim", "git", "htop", "btop",
        "fzf", "ripgrep", "fd-find", "bat", "locales", "ca-certificates",
        "swig", "build-essential", "unzip",
    )
    .run_commands(
        "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && chmod +x /usr/local/bin/ttyd",
        "mkdir -p /root/.config",
    )
    ${pipSection}
    .add_local_dir("${localDir}", remote_path="/workspace_seed", ignore=${JSON.stringify(toRecursiveIgnore(excludePatterns))})
)

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    # Local files should win on every launch, while remote-only outputs remain.
    subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

${syncHelperBlock(workspaceVolume)}
@app.function(image=image, ${computeSpec}, timeout=86400, volumes={"/workspace": workspace_volume})
def run_interactive():
    _print_metrics()
    _prepare_workspace()
    _install_sync_helper()
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
        print("Workspace: /workspace   Run: python ${scriptName}")
        print("Session: tmux 'main' (close & reopen URL to reattach running jobs)")
        print("Sync volume: ${workspaceVolume} (auto-commit every ~20s)")
        print("Pull later: modal volume get ${workspaceVolume} / ./m-gpux-workspace\\n")
        proc = subprocess.Popen(
            ["ttyd", *${JSON.stringify(STABLE_TTYD_FLAGS)}, "-p", str(port), "bash", "-lc", "tmux new-session -A -s main"],
            env=env,
        )
        proc.wait()
`;
}

function workspaceVolumeName(localDir: string): string {
  const normalized = path.resolve(localDir);
  const base = path.basename(normalized) || "workspace";
  const slug = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32) || "workspace";
  const digest = crypto.createHash("sha1").update(normalized).digest("hex").slice(0, 10);
  return `m-gpux-workspace-${slug}-${digest}`;
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
      title: "M-GPUX Hub — Step 1/5: Select Workspace",
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

  // Step 2: Choose action FIRST so we know whether GPU is required (vLLM).
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
        description: "OpenAI-compatible LLM API endpoint (GPU only)",
        action: "vllm",
      },
    ],
    {
      title: "M-GPUX Hub — Step 2/5: Choose Application",
      placeHolder: "What do you want to run?",
    }
  );
  if (!actionPick) { return; }
  const action = (actionPick as any).action as string;

  // Step 3: Compute type — vLLM is GPU-only, everything else can run on CPU.
  let computeSpec: string;
  let computeLabel: string;
  let gpuCount = 1; // GPUs per container; >1 enables tensor parallelism / large models.
  if (action === "vllm") {
    const gpuPick = await pickGpu("M-GPUX Hub — Step 3/5: Choose GPU");
    if (!gpuPick) { return; }
    const count = await pickGpuCount();
    if (count === undefined) { return; }
    gpuCount = count;
    computeSpec = gpuCount > 1 ? `gpu="${gpuPick}:${gpuCount}"` : `gpu="${gpuPick}"`;
    computeLabel = gpuCount > 1 ? `${gpuPick} x${gpuCount}` : gpuPick;
  } else {
    const typePick = await vscode.window.showQuickPick(
      [
        { label: "$(symbol-misc) GPU",      description: "NVIDIA accelerator (T4 / L4 / A100 / H100 …)", value: "gpu" as const },
        { label: "$(circuit-board) CPU",    description: "CPU-only — much cheaper for non-GPU workloads", value: "cpu" as const },
      ],
      { title: "M-GPUX Hub — Step 3/5: Choose Compute Type" }
    );
    if (!typePick) { return; }
    if ((typePick as any).value === "cpu") {
      const cpuPick = await pickCpu();
      if (!cpuPick) { return; }
      computeSpec = cpuPick.spec;
      computeLabel = cpuPick.label;
    } else {
      const gpuPick = await pickGpu("M-GPUX Hub — Choose GPU");
      if (!gpuPick) { return; }
      const count = await pickGpuCount();
      if (count === undefined) { return; }
      gpuCount = count;
      computeSpec = gpuCount > 1 ? `gpu="${gpuPick}:${gpuCount}"` : `gpu="${gpuPick}"`;
      computeLabel = gpuCount > 1 ? `${gpuPick} x${gpuCount}` : gpuPick;
    }
  }
  const selectedGpu = computeLabel;

  // Step 3: Select Python version
  const pythonVersion = await pickPythonVersion();
  if (!pythonVersion) { return; }

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
  // "deploy" = persistent web service (modal deploy). "run" = foreground job.
  let mode: "deploy" | "run" = "run";

  switch (action) {
    case "jupyter": {
      const pipSection = await askPipSection(localDir);
      const excludes = await askExcludePatterns(defaultExcludes);
      if (!excludes) { return; }
      const persistence = await pickJupyterPersistence();
      if (!persistence) { return; }
      scriptContent = jupyterScript(computeSpec, pythonVersion, localDir, pipSection, excludes, persistence.minContainers, persistence.scaledownWindow);
      mode = "deploy";
      break;
    }
    case "python": {
      const pyFile = await pickPythonFile(localDir);
      if (!pyFile) { return; }
      const pipSection = await askPipSection(localDir);
      const excludes = await askExcludePatterns(defaultExcludes);
      if (!excludes) { return; }
      scriptContent = pythonScript(computeSpec, computeLabel, pythonVersion, localDir, pyFile, pipSection, excludes);
      mode = "run";
      break;
    }
    case "bash": {
      const excludes = await askExcludePatterns(defaultExcludes);
      if (!excludes) { return; }
      scriptContent = bashScript(computeSpec, pythonVersion, localDir, excludes);
      mode = "deploy";
      break;
    }
    case "vllm": {
      const model = await pickVllmModel();
      if (!model) { return; }
      // computeSpec is guaranteed GPU-shape here (e.g. gpu="H100:2"); reuse it
      // directly and run vLLM with tensor parallelism across the chosen GPUs.
      scriptContent = vllmScript(computeSpec, pythonVersion, model, gpuCount);
      mode = "deploy";
      break;
    }
    default:
      return;
  }

  // Step 5: Show generated script and execute. Jupyter / bash / interactive
  // mount a workspace volume — those get bidirectional live sync. python is
  // a one-shot run with `add_local_dir` and vllm has no user workspace, so
  // we pass undefined and the launcher skips sync setup.
  const wantsSync = action === "jupyter" || action === "bash";
  const volumeForSync = wantsSync ? workspaceVolumeName(localDir) : undefined;
  await showAndExecuteScript(scriptContent, selectedGpu, action, mode, localDir, volumeForSync);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const AVAILABLE_CPUS = [
  { label: "CPU 1c / 0.5GB",  cores: 1,  memory: 512,   description: "Smallest — quick scripts" },
  { label: "CPU 2c / 1GB",    cores: 2,  memory: 1024,  description: "Light tasks" },
  { label: "CPU 4c / 2GB",    cores: 4,  memory: 2048,  description: "Balanced default" },
  { label: "CPU 8c / 4GB",    cores: 8,  memory: 4096,  description: "Bigger workloads" },
  { label: "CPU 16c / 8GB",   cores: 16, memory: 8192,  description: "Heavier preprocessing" },
  { label: "CPU 32c / 16GB",  cores: 32, memory: 16384, description: "Max single-container" },
];

async function pickGpu(title: string): Promise<string | undefined> {
  const pick = await vscode.window.showQuickPick(
    AVAILABLE_GPUS.map((g) => ({ label: g.label, description: g.description, id: g.id })),
    { title, placeHolder: "Select an NVIDIA GPU accelerator" }
  );
  return pick?.label;
}

async function pickGpuCount(): Promise<number | undefined> {
  // Modal pins multiple GPUs to one container via `gpu="<type>:<count>"`.
  const input = await vscode.window.showInputBox({
    title: "M-GPUX Hub — Number of GPUs",
    value: "1",
    prompt: "How many GPUs to attach to the container? (1–8). Multiple GPUs enable tensor parallelism / larger models.",
    validateInput: (value) => {
      const n = Number(value.trim());
      return Number.isInteger(n) && n >= 1 && n <= 8
        ? undefined
        : "Enter a whole number between 1 and 8";
    },
  });
  if (input === undefined) { return undefined; }
  return Number(input.trim());
}

async function pickJupyterPersistence(): Promise<{ minContainers: number; scaledownWindow: string; label: string } | undefined> {
  // Keep-warm pins one container so a long-running kernel survives browser
  // disconnects; idle modes scale to zero after a quiet period to save cost.
  const pick = await vscode.window.showQuickPick(
    [
      { label: "$(pin) Keep-warm (always on)", description: "Pin one container — long jobs survive disconnects. Costs run until you stop.", min: 1, win: "60 * MINUTE", id: "keep-warm" },
      { label: "$(clock) Idle 1 hour", description: "Scale to zero after 1h with no activity (balanced).", min: 0, win: "60 * MINUTE", id: "idle-1h" },
      { label: "$(watch) Idle 15 minutes", description: "Scale to zero quickly when idle (cheapest).", min: 0, win: "15 * MINUTE", id: "idle-15m" },
    ],
    {
      title: "M-GPUX Hub — Notebook Session Persistence",
      placeHolder: "How long should the kernel stay alive when no browser is connected?",
    }
  );
  if (!pick) { return undefined; }
  return { minContainers: (pick as any).min, scaledownWindow: (pick as any).win, label: (pick as any).id };
}

async function pickCpu(): Promise<{ spec: string; label: string } | undefined> {
  const pick = await vscode.window.showQuickPick(
    AVAILABLE_CPUS.map((c) => ({ label: c.label, description: c.description, cores: c.cores, memory: c.memory })),
    { title: "M-GPUX Hub — Select CPU", placeHolder: "Cores / memory" }
  );
  if (!pick) { return undefined; }
  return { spec: `cpu=${pick.cores}, memory=${pick.memory}`, label: pick.label };
}

async function pickPythonVersion(): Promise<string | undefined> {
  const pick = await vscode.window.showQuickPick(PYTHON_VERSIONS, {
    title: "M-GPUX Hub — Step 4/5: Choose Python Version",
    placeHolder: "Select the Python runtime for the Modal image",
  });
  if (!pick) { return undefined; }
  if (pick.label !== "Custom") {
    return pick.label;
  }

  const custom = await vscode.window.showInputBox({
    title: "Custom Python version",
    value: "3.12",
    prompt: "Enter a Modal-supported Python version, for example 3.12 or 3.13",
    validateInput: (value) => /^\d+\.\d+$/.test(value.trim())
      ? undefined
      : "Use a version like 3.12 or 3.13",
  });
  return custom?.trim();
}

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
  mode: "deploy" | "run",
  localDir: string,
  workspaceVolume?: string
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

  const activeProfile = getActiveProfile();
  const profileName = activeProfile?.name ?? "default";

  // Output channel is silent — it is only revealed via "View Logs" on the session node.
  const outputChannel = vscode.window.createOutputChannel(`M-GPUX: ${actionType} (${gpu})`, "log");
  outputChannel.appendLine(`═══════════════════════════════════════════════`);
  outputChannel.appendLine(`  M-GPUX: Launching ${actionType} on ${gpu}`);
  outputChannel.appendLine(`  Profile: ${profileName}`);
  outputChannel.appendLine(`  Time: ${new Date().toLocaleString()}`);
  outputChannel.appendLine(`═══════════════════════════════════════════════\n`);

  // Activate profile first (silent — log to channel only)
  if (profileName !== "default") {
    outputChannel.appendLine(`▸ Activating profile: ${profileName}`);
    const activateResult = await runCommand("modal", ["profile", "activate", profileName], localDir);
    if (activateResult.exitCode !== 0) {
      outputChannel.appendLine(`⚠ Profile activation warning: ${activateResult.stderr}`);
    } else {
      outputChannel.appendLine(`✓ Profile activated\n`);
    }
  }

  const runnerFilename = path.basename(runnerPath);
  const args = mode === "deploy"
    ? ["deploy", runnerFilename]
    : ["run", runnerFilename];

  outputChannel.appendLine(`▸ Running: modal ${args.join(" ")}`);
  outputChannel.appendLine(`  CWD: ${localDir}`);
  outputChannel.appendLine(`  Mode: ${mode === "deploy" ? "Persistent web service" : "One-shot run"}\n`);

  // Register session in store BEFORE spawn so the sidebar shows "starting"
  const sessionId = newSessionId();
  const kind = (actionType as SessionKind);
  const logPath = sessionLogPath(sessionId);
  // Truncate any stale log from a prior id collision (extremely unlikely)
  try { fs.writeFileSync(logPath, ""); } catch { /* ignore */ }

  // For deploys, key the session on the App name straight from the script
  // (e.g. modal.App("m-gpux-jupyter")). `modal app list` reports that name as
  // the app's "Description", which is exactly what discovery reconciles
  // against — so we don't have to rely on scraping a dashboard URL out of
  // stdout (whose format the server controls and may not match our regex).
  const deployAppId = mode === "deploy" ? extractWebEndpoint(content)?.appName : undefined;

  const session = {
    id: sessionId,
    kind,
    gpu,
    profile: profileName,
    status: "starting" as const,
    startedAt: Date.now(),
    output: outputChannel,
    cwd: localDir,
    detached: mode === "deploy",
    logPath,
    workspaceVolume,
    appId: deployAppId,
  };
  sessionStore.add(session);

  // Start bidirectional sync if this action mounts a workspace volume.
  // We start before spawning modal so the initial push happens while the
  // container is still building its image.
  const driver = startLiveSync({
    volumeName: workspaceVolume,
    workspaceDir: localDir,
    profile: activeProfile,
    output: outputChannel,
  });
  if (driver) { sessionStore.update(sessionId, { liveSync: driver }); }

  // Reveal the sidebar so the user sees the new session
  vscode.commands.executeCommand("mgpux.sessionsView.focus").then(undefined, () => {/* ignore */});

  // For `modal deploy` the local CLI exits quickly once the deployment is
  // accepted, and the remote app lives independently — we don't need
  // `detached: true` (which spawns a visible console window on Windows even
  // with windowsHide). For `modal run` we let the local process die with
  // VS Code: the user explicitly chose foreground mode.
  const isWin = process.platform === "win32";
  const proc = spawn("modal", args, {
    cwd: localDir,
    shell: isWin,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
  });

  sessionStore.update(sessionId, { proc });

  // ---- output handlers ----
  let buffer = "";
  let gotAccessUrl = false;
  let gotAppMeta = false;

  const handleChunk = (text: string) => {
    outputChannel.append(text);
    const s = sessionStore.get(sessionId);
    if (s) { appendSessionLog(s, text); }
    buffer += text;
    if (buffer.length > 16000) {
      buffer = buffer.slice(-8000);
    }

    if (!gotAppMeta) {
      // `modal run` output: ✓ Initialized. View run at https://modal.com/apps/<ws>/main/ap-XXXXX
      // `modal deploy` output: View Deployment: https://modal.com/apps/<ws>/main/deployed/<name>
      const runMatch = buffer.match(/https?:\/\/modal\.com\/apps\/[^\s"']*\/(ap-[A-Za-z0-9]+)/);
      if (runMatch) {
        gotAppMeta = true;
        sessionStore.update(sessionId, {
          appId: runMatch[1],
          dashboardUrl: runMatch[0],
        });
      } else {
        const deployMatch = buffer.match(/https?:\/\/modal\.com\/apps\/[^\s"']*\/deployed\/([A-Za-z0-9_-]+)/);
        if (deployMatch) {
          gotAppMeta = true;
          // For deployed apps, use the app NAME as the identifier — `modal app stop` accepts both.
          sessionStore.update(sessionId, {
            appId: deployMatch[1],
            dashboardUrl: deployMatch[0],
          });
        }
      }
    }

    if (!gotAccessUrl) {
      // Public access URLs: *.modal.run (deployed web_server) or *.modal.host (modal.forward).
      const m = buffer.match(/https?:\/\/[^\s"']*modal\.(?:host|run)[^\s"']*/);
      if (m) {
        gotAccessUrl = true;
        const url = m[0];
        sessionStore.update(sessionId, {
          status: "ready",
          accessUrl: url,
        });
        // One-shot toast so the URL is not buried in the output channel.
        vscode.window.showInformationMessage(
          `${actionType} ready on ${gpu}: ${url}`,
          "Open in Browser",
          "Copy URL"
        ).then((choice) => {
          if (choice === "Open in Browser") {
            vscode.env.openExternal(vscode.Uri.parse(url));
          } else if (choice === "Copy URL") {
            vscode.env.clipboard.writeText(url);
            vscode.window.showInformationMessage("URL copied.");
          }
        });
      }
    }
  };

  proc.stdout.on("data", (d: Buffer) => handleChunk(d.toString()));
  proc.stderr.on("data", (d: Buffer) => handleChunk(d.toString()));

  proc.on("close", (code: number | null) => {
    const s = sessionStore.get(sessionId);
    if (!s) { return; }
    if (code === 0) {
      outputChannel.appendLine(`\n✓ Local process completed (code 0).`);
      // `modal deploy` exits 0 as soon as the app is accepted — the remote
      // service keeps running independently of the local CLI process, so a
      // clean exit means "deployed", regardless of whether we managed to
      // scrape an access URL out of stdout (recent `modal` CLI versions no
      // longer print the function's web URL during deploy, only the
      // dashboard link — see `gotAppMeta` above). `modal run` (python) exiting
      // 0 means the one-shot job genuinely finished.
      const stillUp = mode === "deploy";
      sessionStore.update(sessionId, {
        status: stillUp ? "ready" : "stopped",
        proc: undefined,
      });
      if (!stillUp) {
        try { s.liveSync?.dispose(); } catch { /* ignore */ }
        sessionStore.update(sessionId, { liveSync: undefined });
      } else if (!gotAccessUrl) {
        // Best-effort: fetch the real web URL via the SDK since it wasn't in
        // the CLI output. Non-blocking — the session is already "ready".
        const endpoint = extractWebEndpoint(content);
        if (endpoint && activeProfile?.token_id && activeProfile?.token_secret) {
          fetchFunctionWebUrl(activeProfile.token_id, activeProfile.token_secret, endpoint.appName, endpoint.functionName)
            .then((url) => {
              if (url && sessionStore.get(sessionId)) {
                sessionStore.update(sessionId, { accessUrl: url });
                outputChannel.appendLine(`\n✓ Resolved access URL: ${url}`);
              }
            })
            .catch(() => { /* best-effort */ });
        }
      }
    } else if (s.status === "stopping") {
      outputChannel.appendLine(`\n• Local process exited after stop (code ${code}).`);
      sessionStore.update(sessionId, { status: "stopped", proc: undefined });
      try { s.liveSync?.dispose(); } catch { /* ignore */ }
      sessionStore.update(sessionId, { liveSync: undefined });
    } else {
      outputChannel.appendLine(`\n✗ Process exited with code ${code}.`);
      sessionStore.update(sessionId, { status: "failed", proc: undefined });
      try { s.liveSync?.dispose(); } catch { /* ignore */ }
      sessionStore.update(sessionId, { liveSync: undefined });
      vscode.window.showWarningMessage(
        `M-GPUX: ${actionType} on ${gpu} exited with code ${code}. Right-click the session → View Logs.`
      );
    }

    // Cleanup temp file
    try {
      if (fs.existsSync(runnerPath)) {
        fs.unlinkSync(runnerPath);
      }
    } catch { /* ignore */ }
  });

  proc.on("error", (err: Error) => {
    outputChannel.appendLine(`\n✗ Failed to start: ${err.message}`);
    sessionStore.update(sessionId, { status: "failed", proc: undefined });
    vscode.window.showErrorMessage(`M-GPUX: failed to run modal: ${err.message}`);
  });
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
