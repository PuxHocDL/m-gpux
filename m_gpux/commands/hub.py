import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax
import subprocess
import os
import sys

app = typer.Typer(no_args_is_help=True)
console = Console()

AVAILABLE_GPUS = {
    "1": ("T4", "Light inference/exploration"),
    "2": ("L4", "Balance of cost/performance (24GB)"),
    "3": ("A10G", "Good alternative for training/inference (24GB)"),
    "4": ("A100", "High performance (40GB)"),
    "5": ("A100-80GB", "Extreme performance (80GB)"),
    "6": ("H100", "Top tier hopper architecture (80GB)"),
}

JUPYTER_SCRIPT = """
import modal
import subprocess
import time

app = modal.App("m-gpux-jupyter")
image = modal.Image.debian_slim().pip_install("jupyterlab")

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_jupyter():
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

app = modal.App("m-gpux-runner")
image = modal.Image.debian_slim().pip_install(
    "torch", "numpy", "pandas" 
).add_local_dir("{local_dir}", remote_path="/workspace")

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_script():
    print(f"[EXECUTING] {script_name} on {gpu_type}...")
    subprocess.run([sys.executable, "/workspace/{script_name}"], check=True)
"""

BASH_SCRIPT = """
import modal
import subprocess
import time

app = modal.App("m-gpux-shell")
image = modal.Image.debian_slim().apt_install("ttyd", "bash", "curl").pip_install("torch")

@app.function(image=image, gpu="{gpu_type}", timeout=86400)
def run_shell():
    port = 8888
    with modal.forward(port) as tunnel:
        print(f"\\n=======================================================")
        print(f"[WEB SHELL READY] Open this terminal link in your browser: {tunnel.url}")
        print(f"=======================================================\\n")
        subprocess.Popen(["ttyd", "-p", str(port), "bash"])
        time.sleep(86400)
"""


def execute_modal_temp_script(content: str, description: str):
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
        
    console.print(f"[bold green]Starting {description}... Please wait...[/bold green]")
    
    try:
        subprocess.run(["modal", "run", runner_file])
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Execution of {description} interrupted.[/yellow]")
        
    del_choice = Prompt.ask(f"\n[bold cyan]Do you want to delete {runner_file}?[/bold cyan]", choices=["y", "n"], default="y")
    if del_choice.lower() == "y":
        try:
            os.remove(runner_file)
            console.print("[gray]Temporary runner file cleaned up.[/gray]")
        except OSError:
            pass


def hub_main():
    """Launch the interactive GPU Hub to start a Notebook or Shell."""
        
    console.print(Panel.fit("[bold magenta]m-gpux GPU Hub[/bold magenta]\n"
                            "Allocate a powerful GPU in seconds.", border_style="cyan"))
    
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
        "3": "Bash Shell (Interactive Web Terminal)"
    }
    for k, v in actions.items():
        console.print(f"  [bold yellow]{k}[/bold yellow]: {v}")
        
    action_choice = Prompt.ask("Select Action", choices=["1", "2", "3"], default="1")
    
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
            
        console.print(f"\\n[cyan]Preview of your script to run ({script_path}):[/cyan]")
        console.print(Syntax(script_content, "python", theme="monokai", line_numbers=True))
        
        local_dir_escaped = os.path.abspath(".").replace("\\\\", "/")
        script = WRAPPER_SCRIPT.replace("{gpu_type}", selected_gpu).replace("{local_dir}", local_dir_escaped).replace("{script_name}", os.path.basename(script_path))
        execute_modal_temp_script(script, f"Script {script_path} on {selected_gpu}")
        
    elif action_choice == "3":
        script = BASH_SCRIPT.replace("{gpu_type}", selected_gpu)
        execute_modal_temp_script(script, f"Web Bash Shell on {selected_gpu}")
