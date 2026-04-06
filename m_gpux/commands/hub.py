import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax
import subprocess
import os
import sys
import tomlkit
from typing import Optional
from m_gpux.commands._metrics_snippet import FUNCTIONS as _METRICS_FUNCTIONS

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
    console.print(f"  [bold yellow]0[/bold yellow]: [bold magenta]AUTO[/bold magenta] — Smart pick (most credit remaining)")
    for idx, (name, is_active) in enumerate(profiles, 1):
        marker = " [bold green](active)[/bold green]" if is_active else ""
        console.print(f"  [bold yellow]{idx}[/bold yellow]: {name}{marker}")

    default_idx = "0"
    valid_choices = [str(i) for i in range(0, len(profiles) + 1)]
    choice = Prompt.ask(
        "Select profile (0=auto)",
        choices=valid_choices,
        default=default_idx,
    )

    if choice == "0":
        from m_gpux.commands.account import get_best_profile
        console.print("  [cyan]Scanning all accounts for best balance...[/cyan]")
        best_name, best_remaining = get_best_profile()
        if best_name is None:
            console.print("[bold red]Could not determine best profile. Pick manually.[/bold red]")
            return None
        console.print(f"  [bold green]Auto-selected: {best_name} (${best_remaining:.2f} remaining)[/bold green]")
        return best_name

    selected_name, _ = profiles[int(choice) - 1]
    console.print(f"  Using profile: [bold cyan]{selected_name}[/bold cyan]")
    return selected_name


def _activate_profile(profile_name: str):
    """Activate the given profile via `modal profile activate`."""
    result = subprocess.run(
        ["modal", "profile", "activate", profile_name],
        capture_output=True, text=True,
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

JUPYTER_SCRIPT = """
import modal
import subprocess
import time

# __METRICS__

app = modal.App("m-gpux-jupyter")
image = modal.Image.debian_slim().pip_install("jupyterlab")

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_jupyter():
    _print_metrics()
    _monitor_metrics()
    jupyter_port = 8888
    with modal.forward(jupyter_port) as tunnel:
        print(f"\\n=======================================================")
        print(f"[JUPYTER READY] Connect via this URL: {tunnel.url}")
        print(f"=======================================================\\n")
        
        subprocess.Popen(
            [
                "jupyter",
                "lab",
                "--no-browser",
                "--allow-root",
                "--ip=0.0.0.0",
                "--port",
                str(jupyter_port),
                "--NotebookApp.token=''",
                "--NotebookApp.password=''",
                "--ServerApp.disable_check_xsrf=True",
                "--ServerApp.allow_origin='*'",
                "--ServerApp.allow_remote_access=True",
            ]
        )
        time.sleep(86400)
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

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_script():
    _print_metrics()
    print("[EXECUTING] {script_name} on {gpu_type}...")
    stdin_input = {stdin_input}
    subprocess.run(
        [sys.executable, "/workspace/{script_name}"],
        input=stdin_input,
        text=True if stdin_input is not None else False,
        check=True,
    )
"""

INTERACTIVE_SCRIPT = """
import modal
import subprocess
import time
import os

# __METRICS__

app = modal.App("m-gpux-interactive")
image = modal.Image.debian_slim().apt_install("bash", "curl", "tmux").run_commands(
    "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64",
    "chmod +x /usr/local/bin/ttyd"
){pip_section}.add_local_dir(
    "{local_dir}", remote_path="/workspace", ignore={exclude_patterns}
)

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_interactive():
    _print_metrics()
    _monitor_metrics()
    port = 8888
    # Start a tmux session so work survives browser disconnects
    subprocess.run(["tmux", "new-session", "-d", "-s", "main", "-c", "/workspace"])
    with modal.forward(port) as tunnel:
        url = tunnel.url
        print(f"\\n===========================================================")
        print(f"  INTERACTIVE TERMINAL — DETACHED MODE")
        print(f"  GPU: {gpu_type}")
        print(f"  URL: " + url)
        print(f"")
        print(f"  Your workspace is at /workspace")
        print(f"  Script: python {script_name}")
        print(f"")
        print(f"  The terminal runs inside tmux. If you close the browser,")
        print(f"  just reopen the URL — your session is still alive.")
        print(f"  Container stays running even if you Ctrl+C locally.")
        print(f"===========================================================")
        # ttyd connects to the tmux session; reconnects auto-reattach
        subprocess.Popen(["ttyd", "-W", "-p", str(port), "tmux", "attach-session", "-t", "main"])
        time.sleep(86400)
"""

VLLM_SCRIPT = """
import modal
import subprocess

# __METRICS__

app = modal.App("m-gpux-vllm")

MODEL_NAME = "{model_name}"

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm", "transformers", "hf-transfer")
    .env({{"HF_HUB_ENABLE_HF_TRANSFER": "1"}})
)

hf_cache = modal.Volume.from_name("m-gpux-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

@app.function(
    image=vllm_image,
    gpu="{gpu_type}",
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
        "--served-model-name", MODEL_NAME, "llm",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--enforce-eager",
        "--tensor-parallel-size", "1",
    ]
    print("Starting vLLM:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)
"""

BASH_SCRIPT = """
import modal
import subprocess
import time

# __METRICS__

app = modal.App("m-gpux-shell")
image = modal.Image.debian_slim().apt_install("bash", "curl").run_commands(
    "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64",
    "chmod +x /usr/local/bin/ttyd"
).pip_install("torch")

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_shell():
    _print_metrics()
    _monitor_metrics()
    port = 8888
    with modal.forward(port) as tunnel:
        print(f"\\n=======================================================")
        print(f"[WEB SHELL READY] Open this terminal link in your browser: {tunnel.url}")
        print(f"=======================================================\\n")
        subprocess.Popen(["ttyd", "-p", str(port), "bash"])
        time.sleep(86400)
"""


def execute_modal_temp_script(content: str, description: str, detach: bool = False):
    content = content.replace("# __METRICS__", _METRICS_FUNCTIONS)
    runner_file = "modal_runner.py"
    
    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    console.print(f"\n[cyan]Preview of Generated Configuration ({runner_file}):[/cyan]")
    console.print(Syntax(content, "python", theme="monokai", line_numbers=True))
        
    console.print(Panel(
        f"[bold green]Configuration file `{runner_file}` has been created.[/bold green]\n\n"
        f"You can open this file in your IDE to:\n"
        f"  - Change the GPU type (e.g. gpu='A100') or timeout duration.\n"
        f"  - Add pip dependencies to `.pip_install()` (e.g., `transformers`).\n"
        f"  - Modify environment variables or function parameters.\n\n"
        f"Your code is 100% transparent and editable.", 
        title="WAITING FOR CONFIGURATION", expand=False, border_style="cyan"
    ))
    
    choice = Prompt.ask("\n[bold cyan]Press [Enter] to execute, or type 'cancel' to abort[/bold cyan]", default="")
    
    if choice.strip().lower() == "cancel":
        console.print("[yellow]Execution cancelled.[/yellow]")
        return
    
    cmd = ["modal", "run", runner_file]
    if detach:
        cmd.insert(2, "--detach")
        
    console.print(f"[bold green]Starting {description}... Please wait...[/bold green]")
    if detach:
        console.print(Panel(
            "[bold cyan]Running in detached mode.[/bold cyan]\n\n"
            "The container keeps running even if you close this terminal or lose connection.\n"
            "Reopen the URL in your browser to reconnect to your session.\n\n"
            "To stop the container: [bold yellow]modal app stop[/bold yellow] from Modal dashboard\n"
            "or press Ctrl+C here (the remote container will keep running for ~5 min grace period).",
            border_style="green", title="DETACHED MODE"
        ))
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        if detach:
            console.print(f"\n[green]Disconnected locally. The remote container is still running.[/green]")
            console.print(f"[dim]Reopen the tunnel URL in your browser to reconnect.[/dim]")
        else:
            console.print(f"\n[yellow]Execution of {description} interrupted.[/yellow]")
        
    del_choice = Prompt.ask(f"\n[bold cyan]Do you want to delete {runner_file}?[/bold cyan]", choices=["y", "n"], default="y")
    if del_choice.lower() == "y":
        try:
            os.remove(runner_file)
            console.print("[gray]Temporary runner file cleaned up.[/gray]")
        except OSError:
            pass


@app.command()
def hub_main():
    """
    Launch the M-GPUX Interactive Provisioning Hub.
    
    This command initiates a wizard-like CLI interface that allows you to easily 
    select an Nvidia GPU accelerator (e.g. T4, L4, A100) and deploy your workloads
    entirely serverless.
    
    Features:
    - Jupyter Notebook instances with auto-tunneling
    - Automatic Workspace File Mounting for Python scripts
    - Web-based Bash Shells
    """
        
    console.print(Panel.fit("[bold magenta]m-gpux GPU Hub[/bold magenta]\n"
                            "Allocate a powerful GPU in seconds.", border_style="cyan"))

    # --- Step 0: Workspace / Profile selection ---
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)
    
    console.print("\n[bold cyan]Step 1: Choose your GPU[/bold cyan]")
    for k, v in AVAILABLE_GPUS.items():
        console.print(f"  [bold yellow]{k}[/bold yellow]: {v[0]:<10} - {v[1]}")
        
    gpu_choice = Prompt.ask("Select GPU", choices=list(AVAILABLE_GPUS.keys()), default="2")
    selected_gpu = AVAILABLE_GPUS[gpu_choice][0]
    
    console.print(f"\n[green]You selected: [bold]{selected_gpu}[/bold][/green]")
    
    console.print("\n[bold cyan]Step 2: Choose Application[/bold cyan]")
    actions = {
        "1": "Jupyter Notebook (Interactive)",
        "2": "Run a Python Script (Uploads directory automatically)",
        "3": "Bash Shell (Interactive Web Terminal)",
        "4": "vLLM Inference Server (OpenAI-compatible API)"
    }
    for k, v in actions.items():
        console.print(f"  [bold yellow]{k}[/bold yellow]: {v}")
        
    action_choice = Prompt.ask("Select Action", choices=["1", "2", "3", "4"], default="1")
    
    if action_choice == "1":
        script = JUPYTER_SCRIPT.replace("{gpu_type}", selected_gpu)
        execute_modal_temp_script(script, f"Jupyter Lab on {selected_gpu}")
        
    elif action_choice == "2":
        # Scan current dir for .py files
        files = [f for f in os.listdir(".") if f.endswith(".py")]
        script_path = Prompt.ask("Enter the filename of your Python script", default=files[0] if files else "main.py")
        if not os.path.exists(script_path):
            console.print(f"[bold red]File {script_path} does not exist![/bold red]")
            raise typer.Exit(1)
            
        with open(script_path, "r", encoding="utf-8") as rf:
            script_content = rf.read()
            
        console.print(f"\n[cyan]Preview of your script to run ({script_path}):[/cyan]")
        console.print(Syntax(script_content, "python", theme="monokai", line_numbers=True))
        
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
        base_script_name = os.path.basename(script_path)
        
        if input_matches:
            console.print(f"\n[bold yellow]Warning:[/bold yellow] Your script contains [bold]{len(input_matches)}[/bold] `input()` call(s).")
            console.print("[dim]Modal containers have no interactive stdin.[/dim]")
            console.print("\n[bold cyan]How would you like to handle this?[/bold cyan]")
            console.print("  [bold yellow]1[/bold yellow]: [bold green]Interactive terminal[/bold green] [dim](recommended)[/dim] — opens a web terminal where you run the script yourself")
            console.print("  [bold yellow]2[/bold yellow]: Pre-fill responses — provide stdin answers in advance")
            console.print("  [bold yellow]3[/bold yellow]: Run anyway — script will crash on first input() call")
            
            handle_choice = Prompt.ask("Select", choices=["1", "2", "3"], default="1")
            
            if handle_choice == "1":
                script = (INTERACTIVE_SCRIPT
                    .replace("{gpu_type}", selected_gpu)
                    .replace("{local_dir}", local_dir_escaped)
                    .replace("{script_name}", base_script_name)
                    .replace("{exclude_patterns}", repr(exclude_patterns))
                    .replace("{pip_section}", pip_section))
                execute_modal_temp_script(script, f"Interactive terminal for {script_path} on {selected_gpu}", detach=True)
                return
            elif handle_choice == "2":
                console.print(f"[dim]Enter {len(input_matches)} response(s), one per input() call. Press Enter after each.[/dim]")
                responses = []
                for i in range(len(input_matches)):
                    resp = Prompt.ask(f"  Response #{i+1}")
                    responses.append(resp)
                stdin_input_repr = repr("\n".join(responses) + "\n")
                script = (WRAPPER_SCRIPT
                    .replace("{gpu_type}", selected_gpu)
                    .replace("{local_dir}", local_dir_escaped)
                    .replace("{script_name}", base_script_name)
                    .replace("{exclude_patterns}", repr(exclude_patterns))
                    .replace("{pip_section}", pip_section)
                    .replace("{stdin_input}", stdin_input_repr))
                execute_modal_temp_script(script, f"Script {script_path} on {selected_gpu}")
                return
            # else: handle_choice == "3", fall through to normal run
        
        script = (WRAPPER_SCRIPT
            .replace("{gpu_type}", selected_gpu)
            .replace("{local_dir}", local_dir_escaped)
            .replace("{script_name}", base_script_name)
            .replace("{exclude_patterns}", repr(exclude_patterns))
            .replace("{pip_section}", pip_section)
            .replace("{stdin_input}", "None"))
        execute_modal_temp_script(script, f"Script {script_path} on {selected_gpu}")
        
    elif action_choice == "3":
        script = BASH_SCRIPT.replace("{gpu_type}", selected_gpu)
        execute_modal_temp_script(script, f"Web Bash Shell on {selected_gpu}")
        
    elif action_choice == "4":
        console.print("\n[bold cyan]Select a model to serve:[/bold cyan]")
        models = {
            "1": ("Qwen/Qwen2.5-1.5B-Instruct", "Tiny 1.5B — T4/L4 friendly, fast"),
            "2": ("Qwen/Qwen2.5-7B-Instruct", "7B — A10G/A100, good quality"),
            "3": ("meta-llama/Llama-3.1-8B-Instruct", "Llama 8B — A10G/A100"),
            "4": ("google/gemma-2-9b-it", "Gemma 9B — A10G/A100"),
            "5": ("mistralai/Mistral-7B-Instruct-v0.3", "Mistral 7B — A10G/A100"),
        }
        for k, (name, desc) in models.items():
            console.print(f"  [bold yellow]{k}[/bold yellow]: {name:<45} {desc}")
        
        model_choice = Prompt.ask("Select model", choices=list(models.keys()), default="1")
        selected_model = models[model_choice][0]
        
        script = (VLLM_SCRIPT
            .replace("{gpu_type}", selected_gpu)
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
        
        deploy_mode = Prompt.ask(
            "Deploy mode",
            choices=["run", "deploy"],
            default="deploy"
        )
        
        if deploy_mode == "deploy":
            script = script.replace("# __METRICS__", _METRICS_FUNCTIONS)
            runner_file = "modal_runner.py"
            with open(runner_file, "w", encoding="utf-8") as f:
                f.write(script)
            console.print(f"\n[cyan]Preview of Generated Configuration ({runner_file}):[/cyan]")
            console.print(Syntax(script, "python", theme="monokai", line_numbers=True))
            
            choice = Prompt.ask("\n[bold cyan]Press [Enter] to deploy, or type 'cancel' to abort[/bold cyan]", default="")
            if choice.strip().lower() == "cancel":
                console.print("[yellow]Cancelled.[/yellow]")
                return
            
            console.print(f"[bold green]Deploying vLLM server with {selected_model} on {selected_gpu}...[/bold green]")
            try:
                subprocess.run(["modal", "deploy", runner_file])
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
        else:
            execute_modal_temp_script(script, f"vLLM {selected_model} on {selected_gpu}")
