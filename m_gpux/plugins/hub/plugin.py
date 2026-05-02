import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
import base64
import hashlib
import subprocess
import os
import sys
import tomlkit
from typing import Optional
from m_gpux.core.metrics import FUNCTIONS as _METRICS_FUNCTIONS
from m_gpux.core.ui import arrow_select
from m_gpux.core.runner import execute_modal_temp_script

app = typer.Typer(no_args_is_help=True)
console = Console()

MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")


def _load_profiles():
    """Load all profiles from ~/.modal.toml and return list of (name, is_active) tuples."""
    if not os.path.exists(MODAL_CONFIG_PATH):
        return []
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    profiles = []
    for name in doc:
        is_active = doc[name].get("active", False)
        profiles.append((name, is_active))
    return profiles


def _select_profile() -> Optional[str]:
    """Show interactive profile/workspace picker. Returns selected profile name or None."""
    profiles = _load_profiles()
    if not profiles:
        console.print("[yellow]No Modal profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return None
    if len(profiles) == 1:
        name, _ = profiles[0]
        console.print(f"  Using profile: [bold cyan]{name}[/bold cyan]")
        return name

    console.print("\n[bold cyan]Step 0: Select Workspace / Profile[/bold cyan]")
    profile_options = [("AUTO", "Smart pick (most credit remaining)")]
    for name, is_active in profiles:
        marker = " (active)" if is_active else ""
        profile_options.append((name, f"Modal profile{marker}"))

    choice_idx = arrow_select(profile_options, title="Select Workspace", default=0)

    if choice_idx == 0:
        from m_gpux.core.profiles import get_best_profile
        console.print("  [cyan]Scanning all accounts for best balance...[/cyan]")
        best_name, best_remaining = get_best_profile()
        if best_name is None:
            console.print("[bold red]Could not determine best profile. Pick manually.[/bold red]")
            return None
        console.print(f"  [bold green]Auto-selected: {best_name} (${best_remaining:.2f} remaining)[/bold green]")
        return best_name

    selected_name, _ = profiles[choice_idx - 1]
    console.print(f"  Using profile: [bold cyan]{selected_name}[/bold cyan]")
    return selected_name


def _activate_profile(profile_name: str):
    """Activate the given profile via `modal profile activate`."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    result = subprocess.run(
        ["modal", "profile", "activate", profile_name],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        console.print(f"[bold red]Failed to activate profile '{profile_name}': {result.stderr.strip()}[/bold red]")

AVAILABLE_GPUS = {
    "1":  ("T4",            "Light inference/exploration (16GB)"),
    "2":  ("L4",            "Balance of cost/performance (24GB)"),
    "3":  ("A10G",          "Good alternative for training/inference (24GB)"),
    "4":  ("L40S",          "Ada Lovelace, great for inference (48GB)"),
    "5":  ("A100",          "High performance (40GB, default SXM)"),
    "6":  ("A100-40GB",     "Ampere 40GB variant"),
    "7":  ("A100-80GB",     "Extreme performance (80GB)"),
    "8":  ("RTX-PRO-6000",   "RTX PRO 6000 — pro workstation GPU (48GB)"),
    "9":  ("H100",          "Hopper architecture (80GB)"),
    "10": ("H100!",         "H100 priority/reserved — guaranteed availability"),
    "11": ("H200",          "Next-gen Hopper with HBM3e (141GB)"),
    "12": ("B200",          "Blackwell architecture — latest gen"),
    "13": ("B200+",         "B200 priority/reserved — guaranteed availability"),
}

AVAILABLE_CPUS = {
    "1":  (1,   512,    "1 core, 512 MB — minimal testing"),
    "2":  (2,   1024,   "2 cores, 1 GB — light models"),
    "3":  (4,   2048,   "4 cores, 2 GB — small models"),
    "4":  (8,   4096,   "8 cores, 4 GB — medium models"),
    "5":  (16,  8192,   "16 cores, 8 GB — larger models"),
    "6":  (32,  16384,  "32 cores, 16 GB — large models"),
    "7":  (64,  32768,  "64 cores, 32 GB — max performance"),
}

JUPYTER_SCRIPT = """
import modal
import os
import subprocess
import threading
import time

# __METRICS__

app = modal.App("m-gpux-jupyter")
workspace_volume = modal.Volume.from_name("{workspace_volume}", create_if_missing=True)
image = (
    modal.Image.debian_slim()
    {pip_section}
    .pip_install("jupyterlab>=4.2", "jupyter-server>=2.14", "ipywidgets")
    .add_local_dir("{local_dir}", remote_path="/workspace_seed", ignore={exclude_patterns})
)

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    subprocess.run(["cp", "-an", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

def _start_workspace_autocommit(interval=20):
    def _loop():
        while True:
            time.sleep(interval)
            try:
                workspace_volume.commit()
            except Exception as exc:
                print(f"[sync] workspace commit failed: {exc}", flush=True)
    threading.Thread(target=_loop, daemon=True).start()

@app.function(image=image, {compute_spec}, timeout=86400, volumes={"/workspace": workspace_volume})
def run_jupyter():
    _print_metrics()
    _prepare_workspace()
    _start_workspace_autocommit()
    # NOTE: background metrics monitor is intentionally disabled here.
    # It floods the tunnelled stdout every 30s which causes JupyterLab to
    # appear laggy. Re-enable manually if you need it.
    jupyter_port = 8888
    with modal.forward(jupyter_port) as tunnel:
        print("\\n=======================================================")
        print(f"[JUPYTER READY] {tunnel.url}")
        print("  Workspace mounted at: /workspace")
        print("  Sync volume: {workspace_volume} (auto-commit every ~20s)")
        print("  Pull later: modal volume get {workspace_volume} / ./m-gpux-workspace")
        print("=======================================================\\n", flush=True)
        proc = subprocess.Popen(
            [
                "jupyter", "lab",
                "--no-browser",
                "--allow-root",
                "--ip=0.0.0.0",
                "--port", str(jupyter_port),
                # Auth: token-less because the URL is already a private Modal tunnel.
                "--ServerApp.token=",
                "--ServerApp.password=",
                "--ServerApp.disable_check_xsrf=True",
                "--ServerApp.allow_origin=*",
                "--ServerApp.allow_remote_access=True",
                "--ServerApp.root_dir=/workspace",
                # Lag fixes: lift iopub data/msg rate limits so big stdout does
                # not get throttled, and stop polling for inactive shutdowns.
                "--ServerApp.iopub_data_rate_limit=1.0e10",
                "--ServerApp.iopub_msg_rate_limit=1.0e10",
                "--ServerApp.rate_limit_window=3.0",
                "--ServerApp.shutdown_no_activity_timeout=0",
                "--LabApp.collaborative=False",
            ],
            env={**os.environ, "JUPYTER_PLATFORM_DIRS": "1"},
        )
        proc.wait()
"""

WRAPPER_SCRIPT = """
import modal
import subprocess
import sys

# __METRICS__

app = modal.App("m-gpux-runner")

image = modal.Image.debian_slim(){pip_section}.add_local_dir(
    "{local_dir}", remote_path="/workspace", ignore={exclude_patterns}
)

@app.function(image=image, {compute_spec}, timeout=86400)
def run_script():
    _print_metrics()
    print("[EXECUTING] {script_name} on {compute_label}...")
    stdin_input = {stdin_input}
    subprocess.run(
        [sys.executable, "/workspace/{script_name}"],
        input=stdin_input,
        text=True if stdin_input is not None else False,
        check=True,
    )
"""

# Bash + optional tmux config used by both INTERACTIVE_SCRIPT and BASH_SCRIPT.
# IMPORTANT: this is written to disk INSIDE the container at runtime by the
# generated function (not via Image.run_commands) so we don't have to worry
# about Dockerfile heredoc parsing or CRLF line-endings in modal_runner.py.
#
# Stack: a VS Code-like direct Bash shell, plus optional tmux/fzf/bat/fd/rg/btop.
_BASHRC = r'''
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
# Debian ships bat as `batcat` and fd as `fdfind`.
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
# Keep this close to VS Code's integrated terminal: simple ASCII prompt, no
# powerline/emoji glyphs. This avoids browser/font width disagreements that
# can make cells look overwritten in ttyd.
export PS1='\[\e[1;36m\]\w\[\e[0m\] \[\e[1;32m\]\$\[\e[0m\] '

cd /workspace 2>/dev/null || true

# ---------- welcome banner (run once per shell) ----------
if [ -z "$M_GPUX_WELCOMED" ] && [ -t 1 ]; then
    export M_GPUX_WELCOMED=1
    _GREEN='\033[38;5;150m'; _DIM='\033[2m'; _BOLD='\033[1m'; _R='\033[0m'
    printf "\n${_BOLD}M-GPUX Web Terminal${_R}\n"
    if command -v nvidia-smi >/dev/null 2>&1; then
        _gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | sed 's/, / - /;s/$/ MiB/')
        [ -n "$_gpu" ] && printf "GPU: %s\n" "$_gpu"
    fi
    _cpu=$(grep -c ^processor /proc/cpuinfo 2>/dev/null)
    _mem=$(awk '/MemTotal/ {printf "%.1f GiB", $2/1024/1024}' /proc/meminfo 2>/dev/null)
    printf "CPU: %s cores   RAM: %s   WD: /workspace\n" "${_cpu:-?}" "${_mem:-?}"
    printf "${_DIM}Tools: ll, py, gpus, rg, fd, top. Run tmux manually if you want sessions.${_R}\n\n"
fi
'''

# Catppuccin Mocha-flavored Starship prompt config.
_STARSHIP_TOML = r'''
add_newline = false
format = """
[](#cba6f7)\
$os\
$username\
[](bg:#94e2d5 fg:#cba6f7)\
$directory\
[](fg:#94e2d5 bg:#fab387)\
$git_branch\
$git_status\
[](fg:#fab387 bg:#f38ba8)\
$python\
$nodejs\
$rust\
$golang\
[](fg:#f38ba8) \
"""

[username]
show_always = true
style_user = "bg:#cba6f7 fg:#1e1e2e bold"
style_root = "bg:#cba6f7 fg:#1e1e2e bold"
format = '[ $user ]($style)'

[directory]
style = "bg:#94e2d5 fg:#1e1e2e bold"
format = "[ $path ]($style)"
truncation_length = 3
truncation_symbol = "…/"
[directory.substitutions]
"workspace" = "📂 ws"

[git_branch]
symbol = "\uf418 "
style = "bg:#fab387 fg:#1e1e2e"
format = '[ $symbol$branch ]($style)'

[git_status]
style = "bg:#fab387 fg:#1e1e2e"
format = '[$all_status$ahead_behind ]($style)'

[python]
symbol = "\ue235 "
style = "bg:#f38ba8 fg:#1e1e2e"
format = '[ $symbol$version ]($style)'

[nodejs]
symbol = "\ue718 "
style = "bg:#f38ba8 fg:#1e1e2e"
format = '[ $symbol$version ]($style)'

[character]
success_symbol = "[\u276f](bold #a6e3a1)"
error_symbol = "[\u276f](bold #f38ba8)"
'''

# Catppuccin Mocha-flavored tmux config.
_TMUX_CONF = r'''
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
# Let mouse wheel scroll through tmux scrollback, not alternate screen
bind -n WheelUpPane   if-shell -F "#{alternate_on}" "send-keys -M" "select-pane -t=; copy-mode -e; send-keys -M"
bind -n WheelDownPane if-shell -F "#{alternate_on}" "send-keys -M" "select-pane -t=; send-keys -M"
# Scroll 3 lines at a time in copy-mode for smoother feel
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
'''

# ttyd web terminal: VS Code-like defaults tuned for clean repaints.
_TTYD_FLAGS = [
    "-W",                # writable
    "-P", "120",         # reduce websocket heartbeat churn while keeping reconnects healthy
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
    "-t", 'theme={"background":"#1e1e2e","foreground":"#cdd6f4","cursor":"#f5e0dc","cursorAccent":"#1e1e2e","selectionBackground":"#585b70","black":"#45475a","red":"#f38ba8","green":"#a6e3a1","yellow":"#f9e2af","blue":"#89b4fa","magenta":"#f5c2e7","cyan":"#94e2d5","white":"#bac2de","brightBlack":"#585b70","brightRed":"#f38ba8","brightGreen":"#a6e3a1","brightYellow":"#f9e2af","brightBlue":"#89b4fa","brightMagenta":"#f5c2e7","brightCyan":"#94e2d5","brightWhite":"#a6adc8"}',
    "-T", "xterm-256color",
]


def _b64(text: str) -> str:
    """Encode *text* to a base64 ASCII string suitable for embedding inside a
    generated Python source file. Used to ship the bashrc/tmux configs into
    the Modal container without worrying about line endings or escaping.
    """
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _workspace_volume_name(local_dir: str) -> str:
    """Return a stable Modal Volume name for the current local workspace."""
    root = os.path.abspath(local_dir)
    base = os.path.basename(root.rstrip("\\/")) or "workspace"
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in base)
    slug = "-".join(part for part in slug.split("-") if part)[:32] or "workspace"
    digest = hashlib.sha1(root.encode("utf-8")).hexdigest()[:10]
    return f"m-gpux-workspace-{slug}-{digest}"

INTERACTIVE_SCRIPT = """
import base64
import modal
import os
import subprocess
import threading
import time

# __METRICS__

app = modal.App("m-gpux-interactive")
workspace_volume = modal.Volume.from_name("{workspace_volume}", create_if_missing=True)
image = (
    modal.Image.debian_slim()
    .apt_install(
        "bash", "curl", "tmux", "nano", "vim", "git", "htop", "btop",
        "fzf", "ripgrep", "fd-find", "bat", "locales", "ca-certificates",
        "swig", "build-essential", "unzip",
    )
    .run_commands(
        "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && chmod +x /usr/local/bin/ttyd",
        "mkdir -p /root/.config",
    )
    {pip_section}
    .add_local_dir("{local_dir}", remote_path="/workspace_seed", ignore={exclude_patterns})
)

_BASHRC_B64 = "{bashrc_b64}"
_TMUX_B64 = "{tmux_b64}"
_STARSHIP_B64 = "{starship_b64}"

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    subprocess.run(["cp", "-an", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

def _start_workspace_autocommit(interval=20):
    def _loop():
        while True:
            time.sleep(interval)
            try:
                workspace_volume.commit()
            except Exception as exc:
                print(f"[sync] workspace commit failed: {exc}", flush=True)
    threading.Thread(target=_loop, daemon=True).start()

@app.function(image=image, {compute_spec}, timeout=86400, volumes={"/workspace": workspace_volume})
def run_interactive():
    _print_metrics()
    _prepare_workspace()
    _start_workspace_autocommit()
    os.makedirs("/root/.config", exist_ok=True)
    with open("/root/.bashrc", "wb") as f:
        f.write(base64.b64decode(_BASHRC_B64))
    with open("/root/.tmux.conf", "wb") as f:
        f.write(base64.b64decode(_TMUX_B64))
    with open("/root/.config/starship.toml", "wb") as f:
        f.write(base64.b64decode(_STARSHIP_B64))

    port = 8888
    env = {**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    with modal.forward(port) as tunnel:
        print("\\n[INTERACTIVE TERMINAL READY]")
        print("URL: " + tunnel.url)
        print("Workspace: /workspace   Run: python {script_name}")
        print("Sync volume: {workspace_volume} (auto-commit every ~20s)")
        print("Pull later: modal volume get {workspace_volume} / ./m-gpux-workspace\\n", flush=True)
        proc = subprocess.Popen(
            ["ttyd", *{ttyd_flags}, "-p", str(port), "bash", "--login"],
            env=env,
        )
        proc.wait()
"""

VLLM_SCRIPT = """
import modal
import subprocess

# __METRICS__

app = modal.App("m-gpux-vllm")

MODEL_NAME = "{model_name}"

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm", "transformers", "hf-transfer")
    .env({{"HF_HUB_ENABLE_HF_TRANSFER": "1"}})
)

hf_cache = modal.Volume.from_name("m-gpux-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

@app.function(
    image=vllm_image,
    {compute_spec},
    timeout=24 * 60 * MINUTES,
    scaledown_window=5 * MINUTES,
    volumes={{
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
    }},
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
        "--tensor-parallel-size", "1",
    ]
    print("Starting vLLM:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)
"""

BASH_SCRIPT = """
import base64
import modal
import os
import subprocess
import threading
import time

# __METRICS__

app = modal.App("m-gpux-shell")
workspace_volume = modal.Volume.from_name("{workspace_volume}", create_if_missing=True)
image = (
    modal.Image.debian_slim()
    .apt_install(
        "bash", "curl", "tmux", "nano", "vim", "git", "htop", "btop",
        "fzf", "ripgrep", "fd-find", "bat", "locales", "ca-certificates",
        "swig", "build-essential", "unzip",
    )
    .run_commands(
        "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && chmod +x /usr/local/bin/ttyd",
        "mkdir -p /root/.config",
    )
    {pip_section}
    .add_local_dir("{local_dir}", remote_path="/workspace_seed", ignore={exclude_patterns})
)

_BASHRC_B64 = "{bashrc_b64}"
_TMUX_B64 = "{tmux_b64}"
_STARSHIP_B64 = "{starship_b64}"

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    subprocess.run(["cp", "-an", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

def _start_workspace_autocommit(interval=20):
    def _loop():
        while True:
            time.sleep(interval)
            try:
                workspace_volume.commit()
            except Exception as exc:
                print(f"[sync] workspace commit failed: {exc}", flush=True)
    threading.Thread(target=_loop, daemon=True).start()

@app.function(image=image, {compute_spec}, timeout=86400, volumes={"/workspace": workspace_volume})
def run_shell():
    _print_metrics()
    _prepare_workspace()
    _start_workspace_autocommit()
    os.makedirs("/root/.config", exist_ok=True)
    with open("/root/.bashrc", "wb") as f:
        f.write(base64.b64decode(_BASHRC_B64))
    with open("/root/.tmux.conf", "wb") as f:
        f.write(base64.b64decode(_TMUX_B64))
    with open("/root/.config/starship.toml", "wb") as f:
        f.write(base64.b64decode(_STARSHIP_B64))

    port = 8888
    env = {**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    with modal.forward(port) as tunnel:
        print("\\n[WEB SHELL READY]")
        print("URL: " + tunnel.url)
        print("Workspace: /workspace   Mode: direct bash")
        print("Sync volume: {workspace_volume} (auto-commit every ~20s)")
        print("Pull later: modal volume get {workspace_volume} / ./m-gpux-workspace\\n", flush=True)
        proc = subprocess.Popen(
            ["ttyd", *{ttyd_flags}, "-p", str(port), "bash", "--login"],
            env=env,
        )
        proc.wait()
"""


def hub_main():
    """
    Launch the M-GPUX Interactive Provisioning Hub.
    
    This command initiates a wizard-like CLI interface that allows you to easily 
    select compute resources (GPU or CPU) and deploy your workloads entirely serverless.
    
    Features:
    - Jupyter Notebook instances with auto-tunneling
    - Automatic Workspace File Mounting for Python scripts
    - Web-based Bash Shells
    """
        
    console.print(Panel.fit("[bold magenta]m-gpux Compute Hub[/bold magenta]\n"
                            "Allocate powerful compute in seconds.", border_style="cyan"))

    # --- Step 0: Workspace / Profile selection ---
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)
    
    # --- Step 1: Compute Type ---
    console.print("\n[bold cyan]Step 1: Choose Compute Type[/bold cyan]")
    compute_type_options = [
        ("GPU", "GPU acceleration (recommended for ML/LLM workloads)"),
        ("CPU", "CPU-only (cheaper, good for light tasks or small models)"),
    ]
    compute_type_idx = arrow_select(compute_type_options, title="Compute Type", default=0)
    use_cpu = (compute_type_idx == 1)

    if use_cpu:
        console.print("\n[bold cyan]Step 1b: Choose CPU Configuration[/bold cyan]")
        console.print("  [dim]More cores = faster but costs more. Memory scales with cores.[/dim]")
        cpu_keys = list(AVAILABLE_CPUS.keys())
        cpu_options = []
        for k in cpu_keys:
            cores, mem, desc = AVAILABLE_CPUS[k]
            cpu_options.append((f"{cores} cores", desc))
        cpu_idx = arrow_select(cpu_options, title="Select CPU", default=3)
        selected_cores, selected_memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
        compute_spec = f'cpu={selected_cores}, memory={selected_memory}'
        compute_label = f"CPU ({selected_cores} cores, {selected_memory} MB)"
        console.print(f"\n[green]You selected: [bold]{compute_label}[/bold][/green]")
    else:
        console.print("\n[bold cyan]Step 1b: Choose GPU[/bold cyan]")
        gpu_options = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
        gpu_idx = arrow_select(gpu_options, title="Select GPU", default=1)
        selected_gpu = list(AVAILABLE_GPUS.values())[gpu_idx][0]
        compute_spec = f'gpu="{selected_gpu}"'
        compute_label = selected_gpu
        console.print(f"\n[green]You selected: [bold]{compute_label}[/bold][/green]")
    
    console.print("\n[bold cyan]Step 2: Choose Application[/bold cyan]")
    action_options = [
        ("Jupyter Notebook", "Interactive lab session"),
        ("Run Python Script", "Upload directory & execute"),
        ("Bash Shell", "VS Code-like direct web terminal"),
        ("vLLM Inference", "OpenAI-compatible API server"),
    ]
    action_idx = arrow_select(action_options, title="Select Action", default=0)
    action_choice = str(action_idx + 1)
    
    if action_choice == "1":
        # --- Environment Setup ---
        console.print("\n[bold cyan]Step 3: Environment Setup[/bold cyan]")
        pip_section = '.pip_install(\n    "torch", "numpy", "pandas"\n)'
        if os.path.exists("requirements.txt"):
            use_req = Prompt.ask(
                "[green]Found requirements.txt.[/green] Install dependencies from it?",
                choices=["y", "n"], default="y"
            )
            if use_req == "y":
                req_escaped = os.path.abspath("requirements.txt").replace("\\", "/")
                pip_section = f'.pip_install_from_requirements("{req_escaped}")'
        else:
            specify_req = Prompt.ask(
                "No requirements.txt found. Specify a custom path?",
                choices=["y", "n"], default="n"
            )
            if specify_req == "y":
                req_input = Prompt.ask("Enter path to requirements.txt")
                if os.path.exists(req_input):
                    req_escaped = os.path.abspath(req_input).replace("\\", "/")
                    pip_section = f'.pip_install_from_requirements("{req_escaped}")'
                else:
                    console.print(f"[bold red]File {req_input} not found. Using default packages.[/bold red]")

        # --- File upload config ---
        console.print("\n[bold cyan]Step 4: Configure File Upload[/bold cyan]")
        console.print("[dim]Files and directories in current workspace:[/dim]")
        entries = sorted(os.listdir("."))
        for entry in entries:
            if os.path.isdir(entry):
                console.print(f"  [bold blue]{entry}/[/bold blue]")
            else:
                size = os.path.getsize(entry)
                if size > 1024 * 1024:
                    size_str = f" ({size / (1024*1024):.1f} MB)"
                elif size > 1024:
                    size_str = f" ({size / 1024:.1f} KB)"
                else:
                    size_str = ""
                console.print(f"  {entry}{size_str}")

        default_excludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox"
        exclude_input = Prompt.ask(
            "\n[bold cyan]Comma-separated patterns to exclude from upload (glob supported)[/bold cyan]",
            default=default_excludes
        )
        exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]

        local_dir_escaped = os.path.abspath(".").replace("\\", "/")
        workspace_volume = _workspace_volume_name(".")
        script = (JUPYTER_SCRIPT
            .replace("{compute_spec}", compute_spec)
            .replace("{local_dir}", local_dir_escaped)
            .replace("{workspace_volume}", workspace_volume)
            .replace("{exclude_patterns}", repr(exclude_patterns))
            .replace("{pip_section}", pip_section))
        execute_modal_temp_script(script, f"Jupyter Lab on {compute_label}", detach=True)
        
    elif action_choice == "2":
        # Scan current dir for .py files
        files = [f for f in os.listdir(".") if f.endswith(".py")]
        script_path = Prompt.ask("Enter the filename of your Python script", default=files[0] if files else "main.py")
        if not os.path.exists(script_path):
            console.print(f"[bold red]File {script_path} does not exist![/bold red]")
            raise typer.Exit(1)
            
        with open(script_path, "r", encoding="utf-8") as rf:
            script_content = rf.read()
        console.print(f"[dim]Loaded {script_path} ({len(script_content)} chars).[/dim]")
        
        # --- Step 3: requirements.txt support ---
        console.print("\n[bold cyan]Step 3: Environment Setup[/bold cyan]")
        pip_section = '.pip_install(\n    "torch", "numpy", "pandas"\n)'
        if os.path.exists("requirements.txt"):
            use_req = Prompt.ask(
                "[green]Found requirements.txt.[/green] Install dependencies from it?",
                choices=["y", "n"], default="y"
            )
            if use_req == "y":
                req_escaped = os.path.abspath("requirements.txt").replace("\\", "/")
                pip_section = f'.pip_install_from_requirements("{req_escaped}")'
        else:
            specify_req = Prompt.ask(
                "No requirements.txt found. Specify a custom path?",
                choices=["y", "n"], default="n"
            )
            if specify_req == "y":
                req_input = Prompt.ask("Enter path to requirements.txt")
                if os.path.exists(req_input):
                    req_escaped = os.path.abspath(req_input).replace("\\", "/")
                    pip_section = f'.pip_install_from_requirements("{req_escaped}")'
                else:
                    console.print(f"[bold red]File {req_input} not found. Using default packages.[/bold red]")
        
        # --- Step 4: File upload selection ---
        console.print("\n[bold cyan]Step 4: Configure File Upload[/bold cyan]")
        console.print("[dim]Files and directories in current workspace:[/dim]")
        
        entries = sorted(os.listdir("."))
        for entry in entries:
            if os.path.isdir(entry):
                console.print(f"  [bold blue]{entry}/[/bold blue]")
            else:
                size = os.path.getsize(entry)
                if size > 1024 * 1024:
                    size_str = f" ({size / (1024*1024):.1f} MB)"
                elif size > 1024:
                    size_str = f" ({size / 1024:.1f} KB)"
                else:
                    size_str = ""
                console.print(f"  {entry}{size_str}")
        
        default_excludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox"
        exclude_input = Prompt.ask(
            "\n[bold cyan]Comma-separated patterns to exclude from upload (glob supported)[/bold cyan]",
            default=default_excludes
        )
        exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]
        
        # --- Step 5: Detect interactive input() calls ---
        import re as _re
        input_matches = _re.findall(r'input\s*\(', script_content)
        
        local_dir_escaped = os.path.abspath(".").replace("\\", "/")
        workspace_volume = _workspace_volume_name(".")
        base_script_name = os.path.basename(script_path)
        
        if input_matches:
            console.print(f"\n[bold yellow]Warning:[/bold yellow] Your script contains [bold]{len(input_matches)}[/bold] `input()` call(s).")
            console.print("[dim]Modal containers have no interactive stdin.[/dim]")
            console.print("\n[bold cyan]How would you like to handle this?[/bold cyan]")
            input_options = [
                ("Interactive terminal", "(recommended) opens a web terminal to run the script"),
                ("Pre-fill responses", "provide stdin answers in advance"),
                ("Run anyway", "script will crash on first input() call"),
            ]
            handle_idx = arrow_select(input_options, title="Handle input() calls", default=0)
            handle_choice = str(handle_idx + 1)
            
            if handle_choice == "1":
                script = (INTERACTIVE_SCRIPT
                    .replace("{compute_spec}", compute_spec)
                    .replace("{compute_label}", compute_label)
                    .replace("{local_dir}", local_dir_escaped)
                    .replace("{workspace_volume}", workspace_volume)
                    .replace("{script_name}", base_script_name)
                    .replace("{exclude_patterns}", repr(exclude_patterns))
                    .replace("{pip_section}", pip_section)
                    .replace("{bashrc_b64}", _b64(_BASHRC))
                    .replace("{tmux_b64}", _b64(_TMUX_CONF))
                    .replace("{starship_b64}", _b64(_STARSHIP_TOML))
                    .replace("{ttyd_flags}", repr(_TTYD_FLAGS)))
                execute_modal_temp_script(script, f"Interactive terminal for {script_path} on {compute_label}", detach=True)
                return
            elif handle_choice == "2":
                console.print(f"[dim]Enter {len(input_matches)} response(s), one per input() call. Press Enter after each.[/dim]")
                responses = []
                for i in range(len(input_matches)):
                    resp = Prompt.ask(f"  Response #{i+1}")
                    responses.append(resp)
                stdin_input_repr = repr("\n".join(responses) + "\n")
                script = (WRAPPER_SCRIPT
                    .replace("{compute_spec}", compute_spec)
                    .replace("{local_dir}", local_dir_escaped)
                    .replace("{script_name}", base_script_name)
                    .replace("{exclude_patterns}", repr(exclude_patterns))
                    .replace("{pip_section}", pip_section)
                    .replace("{stdin_input}", stdin_input_repr))
                execute_modal_temp_script(script, f"Script {script_path} on {compute_label}")
                return
            # else: handle_choice == "3", fall through to normal run
        
        script = (WRAPPER_SCRIPT
            .replace("{compute_spec}", compute_spec)
            .replace("{compute_label}", compute_label)
            .replace("{local_dir}", local_dir_escaped)
            .replace("{script_name}", base_script_name)
            .replace("{exclude_patterns}", repr(exclude_patterns))
            .replace("{pip_section}", pip_section)
            .replace("{stdin_input}", "None"))
        execute_modal_temp_script(script, f"Script {script_path} on {compute_label}")
        
    elif action_choice == "3":
        # --- Environment Setup ---
        console.print("\n[bold cyan]Step 3: Environment Setup[/bold cyan]")
        pip_section = '.pip_install(\n    "torch", "numpy", "pandas"\n)'
        if os.path.exists("requirements.txt"):
            use_req = Prompt.ask(
                "[green]Found requirements.txt.[/green] Install dependencies from it?",
                choices=["y", "n"], default="y"
            )
            if use_req == "y":
                req_escaped = os.path.abspath("requirements.txt").replace("\\", "/")
                pip_section = f'.pip_install_from_requirements("{req_escaped}")'
        else:
            specify_req = Prompt.ask(
                "No requirements.txt found. Specify a custom path?",
                choices=["y", "n"], default="n"
            )
            if specify_req == "y":
                req_input = Prompt.ask("Enter path to requirements.txt")
                if os.path.exists(req_input):
                    req_escaped = os.path.abspath(req_input).replace("\\", "/")
                    pip_section = f'.pip_install_from_requirements("{req_escaped}")'
                else:
                    console.print(f"[bold red]File {req_input} not found. Using default packages.[/bold red]")

        # --- File upload config ---
        console.print("\n[bold cyan]Step 4: Configure File Upload[/bold cyan]")
        console.print("[dim]Files and directories in current workspace:[/dim]")
        entries = sorted(os.listdir("."))
        for entry in entries:
            if os.path.isdir(entry):
                console.print(f"  [bold blue]{entry}/[/bold blue]")
            else:
                size = os.path.getsize(entry)
                if size > 1024 * 1024:
                    size_str = f" ({size / (1024*1024):.1f} MB)"
                elif size > 1024:
                    size_str = f" ({size / 1024:.1f} KB)"
                else:
                    size_str = ""
                console.print(f"  {entry}{size_str}")

        default_excludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox"
        exclude_input = Prompt.ask(
            "\n[bold cyan]Comma-separated patterns to exclude from upload (glob supported)[/bold cyan]",
            default=default_excludes
        )
        exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]

        local_dir_escaped = os.path.abspath(".").replace("\\", "/")
        workspace_volume = _workspace_volume_name(".")
        script = (BASH_SCRIPT
            .replace("{compute_spec}", compute_spec)
            .replace("{local_dir}", local_dir_escaped)
            .replace("{workspace_volume}", workspace_volume)
            .replace("{exclude_patterns}", repr(exclude_patterns))
            .replace("{pip_section}", pip_section)
            .replace("{bashrc_b64}", _b64(_BASHRC))
            .replace("{tmux_b64}", _b64(_TMUX_CONF))
            .replace("{starship_b64}", _b64(_STARSHIP_TOML))
            .replace("{ttyd_flags}", repr(_TTYD_FLAGS)))
        execute_modal_temp_script(script, f"Web Bash Shell on {compute_label}", detach=True)
        
    elif action_choice == "4":
        models = {
            "1": ("Qwen/Qwen2.5-1.5B-Instruct", "Tiny 1.5B — T4/L4 friendly, fast"),
            "2": ("Qwen/Qwen2.5-7B-Instruct", "7B — A10G/A100, good quality"),
            "3": ("meta-llama/Llama-3.1-8B-Instruct", "Llama 8B — A10G/A100"),
            "4": ("google/gemma-2-9b-it", "Gemma 9B — A10G/A100"),
            "5": ("mistralai/Mistral-7B-Instruct-v0.3", "Mistral 7B — A10G/A100"),
        }
        model_options = [(name, desc) for name, desc in models.values()]
        model_idx = arrow_select(model_options, title="Select model to serve", default=0)
        selected_model = list(models.values())[model_idx][0]
        
        script = (VLLM_SCRIPT
            .replace("{compute_spec}", compute_spec)
            .replace("{model_name}", selected_model))
        
        console.print(Panel(
            f"[bold]After deploying, you'll get an OpenAI-compatible URL like:[/bold]\n"
            f"  https://<workspace>--m-gpux-vllm-serve.modal.run\n\n"
            f"[bold cyan]To connect OpenClaw, add to ~/.openclaw/openclaw.json:[/bold cyan]\n"
            f'  {{\n'
            f'    "agent": {{\n'
            f'      "model": "openai-compatible/{selected_model}"\n'
            f'    }},\n'
            f'    "providers": {{\n'
            f'      "openai-compatible": {{\n'
            f'        "baseUrl": "https://<workspace>--m-gpux-vllm-serve.modal.run/v1"\n'
            f'      }}\n'
            f'    }}\n'
            f'  }}\n\n'
            f"[dim]Replace <workspace> with your Modal workspace name.[/dim]\n"
            f"[dim]Use `modal deploy modal_runner.py` instead of `modal run` for persistent serving.[/dim]",
            title="OPENCLAW INTEGRATION", border_style="magenta"
        ))
        
        deploy_options = [
            ("deploy", "Persistent deployment (recommended for serving)"),
            ("run", "One-time run (stops when terminal closes)"),
        ]
        deploy_idx = arrow_select(deploy_options, title="Deploy mode", default=0)
        deploy_mode = deploy_options[deploy_idx][0]
        
        if deploy_mode == "deploy":
            script = script.replace("# __METRICS__", _METRICS_FUNCTIONS)
            runner_file = "modal_runner.py"
            with open(runner_file, "w", encoding="utf-8") as f:
                f.write(script)
            console.print(f"[dim]Wrote {runner_file}. Edit it before deploying if needed (set MGPUX_VERBOSE=1 to print the source).[/dim]")
            if os.environ.get("MGPUX_VERBOSE", "").strip() in ("1", "true", "yes"):
                from rich.syntax import Syntax
                console.print(Syntax(script, "python", theme="monokai", line_numbers=True))

            choice = Prompt.ask("[bold cyan][Enter][/bold cyan] deploy  •  [bold cyan]c[/bold cyan] cancel", default="")
            if choice.strip().lower() in ("c", "cancel"):
                console.print("[yellow]Cancelled.[/yellow]")
                return
            
            console.print(f"[bold green]Deploying vLLM server with {selected_model} on {compute_label}...[/bold green]")
            try:
                subprocess.run(["modal", "deploy", runner_file])
                console.print("\n[green]vLLM deployed. When done, stop with:[/green] [bold yellow]m-gpux stop[/bold yellow]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
        else:
            execute_modal_temp_script(script, f"vLLM {selected_model} on {compute_label}")


# ─── Plugin registration ──────────────────────────────────────
from m_gpux.core.plugin import PluginBase as _PluginBase


class HubPlugin(_PluginBase):
    name = "hub"
    help = "Launch interactive UI to provision Python scripts, Terminals, or Jupyter on GPUs."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        root_app.command(
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )(hub_main)
