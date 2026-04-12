import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax
import os
import json
import secrets
import subprocess
import time
import threading
from datetime import datetime
from m_gpux.commands._metrics_snippet import FUNCTIONS as _METRICS_FUNCTIONS
from m_gpux.commands.hub import _select_profile, _activate_profile, AVAILABLE_GPUS

app = typer.Typer(
    help="Deploy LLMs as OpenAI-compatible APIs with API key authentication.",
    short_help="LLM API Server",
    no_args_is_help=True,
)
console = Console()

# ─── Paths ────────────────────────────────────────────────────

KEYS_DIR = os.path.expanduser("~/.m-gpux")
KEYS_FILE = os.path.join(KEYS_DIR, "api_keys.json")

# ─── Key helpers ──────────────────────────────────────────────


def _load_keys():
    if not os.path.exists(KEYS_FILE):
        return []
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_keys(keys):
    os.makedirs(KEYS_DIR, exist_ok=True)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)


def _generate_key():
    return f"sk-mgpux-{secrets.token_hex(24)}"


def _get_active_keys():
    return [k["key"] for k in _load_keys() if k.get("active", True)]


# ─── Keys sub-commands ────────────────────────────────────────

keys_app = typer.Typer(help="Manage API keys for LLM endpoints.")
app.add_typer(keys_app, name="keys")


@keys_app.command("create")
def create_key(name: str = typer.Option(None, help="Label for this key")):
    """Generate a new API key."""
    if not name:
        name = Prompt.ask("Key name (e.g. 'dev', 'production', 'team-a')", default="default")
    keys = _load_keys()
    if any(k["name"] == name for k in keys):
        console.print(f"[red]Key '{name}' already exists. Use a different name.[/red]")
        raise typer.Exit(1)
    new_key = _generate_key()
    keys.append({
        "name": name,
        "key": new_key,
        "created": datetime.now().isoformat(),
        "active": True,
    })
    _save_keys(keys)
    console.print(Panel(
        f"[bold green]API Key Created[/bold green]\n\n"
        f"  Name:   [cyan]{name}[/cyan]\n"
        f"  Key:    [bold yellow]{new_key}[/bold yellow]\n\n"
        f"[dim]Save this key. View later with `m-gpux serve keys show {name}`.[/dim]",
        border_style="green",
    ))


@keys_app.command("list")
def list_keys():
    """List all API keys."""
    keys = _load_keys()
    if not keys:
        console.print("[yellow]No keys yet. Run: m-gpux serve keys create[/yellow]")
        return
    table = Table(title="M-GPUX API Keys")
    table.add_column("Name", style="cyan")
    table.add_column("Key", style="yellow")
    table.add_column("Created", style="dim")
    table.add_column("Status")
    for k in keys:
        masked = k["key"][:14] + "..." + k["key"][-4:]
        status = "[green]Active[/green]" if k.get("active", True) else "[red]Revoked[/red]"
        table.add_row(k["name"], masked, k.get("created", "")[:19], status)
    console.print(table)


@keys_app.command("show")
def show_key(name: str = typer.Argument(..., help="Key name")):
    """Show the full API key value."""
    for k in _load_keys():
        if k["name"] == name:
            console.print(f"\n  [cyan]{name}[/cyan]: [bold yellow]{k['key']}[/bold yellow]\n")
            return
    console.print(f"[red]Key '{name}' not found.[/red]")
    raise typer.Exit(1)


@keys_app.command("revoke")
def revoke_key(name: str = typer.Argument(..., help="Key name to revoke")):
    """Revoke an API key (redeploy required to take effect)."""
    keys = _load_keys()
    for k in keys:
        if k["name"] == name:
            k["active"] = False
            _save_keys(keys)
            console.print(f"[green]Key '{name}' revoked. Redeploy with `m-gpux serve deploy` to apply.[/green]")
            return
    console.print(f"[red]Key '{name}' not found.[/red]")
    raise typer.Exit(1)


# ─── Modal deployment template ───────────────────────────────
# Architecture:
#   - Auth proxy (FastAPI) on port 8000 — starts instantly, Modal sees it
#   - vLLM on port 8001 — loads model in background
#   - /health exempt from auth → Modal health probe always passes
#   - /v1/* requires Bearer token, proxies to vLLM

SERVE_TEMPLATE = '''import modal
import subprocess
import os
import sys

# __METRICS__

app = modal.App("m-gpux-llm-api")

MODEL_NAME = "{model_name}"
API_KEY = "{api_key}"

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm", "transformers", "hf-transfer", "httpx", "fastapi", "uvicorn")
    .env(ENV_DICT_PLACEHOLDER)
)

hf_cache = modal.Volume.from_name("m-gpux-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

PROXY_CODE = """
import httpx, json, os, asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response, JSONResponse
import uvicorn

API_KEY = os.environ["MGPUX_API_KEY"]
VLLM = "http://127.0.0.1:8001"
app = FastAPI()

@app.middleware("http")
async def auth(request, call_next):
    path = request.url.path
    if path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": {"message": "Missing API key. Use: Authorization: Bearer sk-mgpux-xxx", "type": "auth_error"}})
    if auth_header[7:] != API_KEY:
        return JSONResponse(status_code=403, content={"error": {"message": "Invalid API key", "type": "auth_error"}})
    return await call_next(request)

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(base_url=VLLM, timeout=3) as c:
            r = await c.get("/v1/models")
            return {"status": "ok", "vllm_ready": r.status_code == 200}
    except Exception:
        return {"status": "ok", "vllm_ready": False}

@app.api_route("/v1/{path:path}", methods=["GET","POST"])
async def proxy(request: Request, path: str):
    body = await request.body()
    headers = {k:v for k,v in request.headers.items() if k.lower() not in ("host","authorization","content-length")}
    is_stream = False
    if body:
        try: is_stream = json.loads(body).get("stream", False)
        except: pass
    try:
        if is_stream:
            async def gen():
                try:
                    async with httpx.AsyncClient(base_url=VLLM, timeout=httpx.Timeout(600.0)) as c:
                        async with c.stream(request.method, f"/v1/{path}", content=body, headers=headers) as r:
                            async for chunk in r.aiter_bytes(): yield chunk
                except Exception as e:
                    err = json.dumps({"error":{"message":str(e),"type":"server_error"}})
                    nl = chr(10)
                    yield f"data: {err}{nl}{nl}data: [DONE]{nl}{nl}".encode()
            return StreamingResponse(gen(), media_type="text/event-stream")
        async with httpx.AsyncClient(base_url=VLLM, timeout=httpx.Timeout(600.0)) as c:
            r = await c.request(request.method, f"/v1/{path}", content=body, headers=headers)
            return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type","application/json"))
    except (httpx.ConnectError, httpx.TimeoutException):
        return JSONResponse(status_code=503, content={"error":{"message":"Model is still loading. Try again in a minute.","type":"server_error"}})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
"""


@app.function(
    image=vllm_image,
    gpu="{gpu_type}",
    timeout=24 * 60 * MINUTES,
    scaledown_window=5 * MINUTES,
    min_containers={keep_warm},
    volumes=VOLUMES_PLACEHOLDER,
)
@modal.concurrent(max_inputs=50)
@modal.web_server(port=8000, startup_timeout=20 * MINUTES)
def serve():
    _print_metrics()
    _monitor_metrics()

    # Start vLLM on port 8001 (background)
    vllm_cmd = [
        "vllm", "serve", MODEL_NAME,
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", "8001",
        "--enforce-eager",
        "--tensor-parallel-size", "1",
        "--max-model-len", "{max_model_len}",
    ]
    print("[M-GPUX] Starting vLLM on :8001:", " ".join(vllm_cmd))
    subprocess.Popen(vllm_cmd)

    # Start auth proxy on port 8000 (Modal detects this immediately)
    os.environ["MGPUX_API_KEY"] = API_KEY
    with open("/tmp/_proxy.py", "w") as f:
        f.write(PROXY_CODE)
    print("[M-GPUX] Starting auth proxy on :8000")
    subprocess.Popen([sys.executable, "/tmp/_proxy.py"])
'''

# ─── Model presets ────────────────────────────────────────────

SERVE_MODELS = {
    "1":  ("Qwen/Qwen2.5-1.5B-Instruct",          "1.5B — T4/L4 friendly, fast",       "T4"),
    "2":  ("Qwen/Qwen2.5-7B-Instruct",             "7B — A10G/A100",                    "A10G"),
    "3":  ("Qwen/Qwen3-8B",                         "Qwen3 8B — A10G/A100",             "A10G"),
    "4":  ("Qwen/Qwen3.5-35B-A3B",                  "Qwen3.5 35B MoE — A100-80GB/H100", "A100-80GB"),
    "5":  ("meta-llama/Llama-3.1-8B-Instruct",      "Llama 3.1 8B — A10G/A100",         "A10G"),
    "6":  ("google/gemma-2-9b-it",                   "Gemma 2 9B — A10G/A100",           "A10G"),
    "7":  ("mistralai/Mistral-7B-Instruct-v0.3",    "Mistral 7B — A10G/A100",           "A10G"),
    "8":  ("Qwen/Qwen2.5-72B-Instruct-AWQ",        "72B AWQ quant — H100/A100-80GB",   "A100-80GB"),
    "9":  ("meta-llama/Llama-3.1-70B-Instruct",     "Llama 70B — H100/A100-80GB",       "H100"),
    "10": ("deepseek-ai/DeepSeek-V2-Lite-Chat",     "DeepSeek V2 Lite 16B — A100",      "A100"),
    "11": ("microsoft/Phi-3-medium-4k-instruct",    "Phi-3 Medium 14B — A10G/A100",     "A10G"),
}

# ─── Deploy command ───────────────────────────────────────────


@app.command("deploy")
def deploy():
    """Deploy an LLM as an OpenAI-compatible API with API key authentication."""

    console.print(Panel.fit(
        "[bold magenta]M-GPUX LLM API Server[/bold magenta]\n"
        "Deploy a GPU-accelerated LLM with OpenAI-compatible API + auth keys.\n"
        "Works as a drop-in replacement for OpenRouter / OpenAI.",
        border_style="cyan",
    ))

    # ── Step 0: Profile / workspace ──
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    # ── Step 1: Model ──
    console.print("\n[bold cyan]Step 1: Select Model[/bold cyan]")
    for k, (name, desc, _) in SERVE_MODELS.items():
        console.print(f"  [bold yellow]{k:>2}[/bold yellow]: {name:<45} {desc}")
    console.print(f"  [bold yellow] 0[/bold yellow]: {'(custom)':<45} Enter a HuggingFace model ID")

    model_choice = Prompt.ask("Select model", default="2")
    if model_choice == "0":
        selected_model = Prompt.ask("HuggingFace model ID (e.g. org/model-name)")
        recommended_gpu = "A100"
    elif model_choice in SERVE_MODELS:
        selected_model, _, recommended_gpu = SERVE_MODELS[model_choice]
    else:
        console.print("[red]Invalid choice.[/red]")
        raise typer.Exit(1)

    console.print(f"  [green]Model:[/green] [bold]{selected_model}[/bold]")

    # ── Step 2: GPU ──
    console.print(f"\n[bold cyan]Step 2: Choose GPU[/bold cyan]  [dim](recommended: {recommended_gpu})[/dim]")
    for k, (gpu, desc) in AVAILABLE_GPUS.items():
        marker = " [bold green]<- recommended[/bold green]" if gpu == recommended_gpu else ""
        console.print(f"  [bold yellow]{k:>2}[/bold yellow]: {gpu:<16} {desc}{marker}")

    default_gpu_key = "5"
    for k, (gpu, _) in AVAILABLE_GPUS.items():
        if gpu == recommended_gpu:
            default_gpu_key = k
            break

    gpu_choice = Prompt.ask("Select GPU", choices=list(AVAILABLE_GPUS.keys()), default=default_gpu_key)
    selected_gpu = AVAILABLE_GPUS[gpu_choice][0]
    console.print(f"  [green]GPU:[/green] [bold]{selected_gpu}[/bold]")

    # ── Step 3: Max context length ──
    console.print("\n[bold cyan]Step 3: Max Context Length[/bold cyan]")
    console.print("  [dim]Lower = faster startup + less VRAM. Increase for long inputs.[/dim]")
    max_model_len = Prompt.ask("Max model length (tokens)", default="4096")

    # ── Step 4: Keep warm ──
    console.print("\n[bold cyan]Step 4: Keep Warm[/bold cyan]")
    console.print("  [dim]1 = keeps 1 container always running (no cold start, but costs GPU $$).[/dim]")
    console.print("  [dim]0 = scales to zero when idle (cold start ~5 min, saves cost).[/dim]")
    keep_warm = Prompt.ask("Min containers", default="1")
    try:
        keep_warm_val = int(keep_warm)
    except ValueError:
        keep_warm_val = 0
    console.print(f"  [green]Keep warm:[/green] [bold]{keep_warm_val}[/bold]")

    # ── Step 5: API key ──
    console.print("\n[bold cyan]Step 5: API Key Setup[/bold cyan]")
    active_keys = _get_active_keys()
    if not active_keys:
        console.print("  [yellow]No API keys found. Creating one automatically...[/yellow]")
        new_key = _generate_key()
        keys = _load_keys()
        keys.append({
            "name": "default",
            "key": new_key,
            "created": datetime.now().isoformat(),
            "active": True,
        })
        _save_keys(keys)
        active_keys = [new_key]
        console.print(f"  [green]Created key:[/green] [bold yellow]{new_key}[/bold yellow]")
    else:
        console.print(f"  [green]{len(active_keys)} active key(s) available.[/green]")
        for k in _load_keys():
            if k.get("active", True):
                masked = k["key"][:14] + "..." + k["key"][-4:]
                console.print(f"    [dim]*[/dim] {k['name']}: [yellow]{masked}[/yellow]")

    first_key = active_keys[0]

    # ── Build script ──
    env_dict = '{"HF_HUB_ENABLE_HF_TRANSFER": "1"}'
    volumes_dict = (
        '{\n'
        '        "/root/.cache/huggingface": hf_cache,\n'
        '        "/root/.cache/vllm": vllm_cache,\n'
        '    }'
    )
    script = (SERVE_TEMPLATE
        .replace("{model_name}", selected_model)
        .replace("{gpu_type}", selected_gpu)
        .replace("{api_key}", first_key)
        .replace("{max_model_len}", max_model_len)
        .replace("{keep_warm}", str(keep_warm_val))
        .replace("ENV_DICT_PLACEHOLDER", env_dict)
        .replace("VOLUMES_PLACEHOLDER", volumes_dict))

    script = script.replace("# __METRICS__", _METRICS_FUNCTIONS)

    runner_file = "modal_runner.py"
    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(script)

    console.print(f"\n[cyan]Generated deployment script: {runner_file}[/cyan]")
    console.print(Syntax(script, "python", theme="monokai", line_numbers=True))

    # ── Config preview ──
    api_url = f"https://{selected_profile}--m-gpux-llm-api-serve.modal.run/v1"

    console.print(Panel(
        f"[bold]After deployment, use this configuration:[/bold]\n\n"
        f"  [green]agent:[/green]\n"
        f"    [green]model:[/green] {selected_model}\n"
        f"    [green]api_base:[/green] {api_url}\n"
        f"    [green]api_key:[/green] {first_key}\n"
        f"    [green]temperature:[/green] 0.0\n\n"
        f"[dim]The exact URL will be shown in the deploy output below.\n"
        f"If the workspace name differs, update api_base accordingly.[/dim]",
        title="YOUR LLM API CONFIG",
        border_style="magenta",
    ))

    console.print(Panel(
        f"[bold green]Configuration file `{runner_file}` has been created.[/bold green]\n\n"
        f"You can open this file in your IDE to:\n"
        f"  - Change the GPU type or timeout duration.\n"
        f"  - Adjust '--max-model-len' for context window.\n"
        f"  - Adjust '--tensor-parallel-size' for multi-GPU.\n\n"
        f"Your code is 100% transparent and editable.",
        title="WAITING FOR CONFIGURATION", expand=False, border_style="cyan",
    ))

    choice = Prompt.ask(
        "\n[bold cyan]Press [Enter] to deploy, or type 'cancel' to abort[/bold cyan]",
        default=""
    )
    if choice.strip().lower() == "cancel":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    console.print(f"\n[bold green]Deploying {selected_model} on {selected_gpu}...[/bold green]")
    console.print("[dim]First deploy may take 5-15 min (downloading model weights to cache).[/dim]")
    console.print("[dim]Subsequent cold starts will be faster (weights cached in Volume).[/dim]\n")

    try:
        subprocess.run(["modal", "deploy", runner_file])
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. The remote deployment may still be in progress.[/yellow]")
        return

    console.print(Panel(
        f"[bold green]Deployment complete![/bold green]\n\n"
        f"Check the output above for your endpoint URL (look for the web_server URL).\n\n"
        f"[bold]Your API key:[/bold] [bold yellow]{first_key}[/bold yellow]\n"
        f"[bold]Model name:[/bold]  {selected_model}\n\n"
        f"[bold cyan]Test with curl:[/bold cyan]\n"
        f'  curl <YOUR_URL>/v1/chat/completions \\\n'
        f'    -H "Authorization: Bearer {first_key}" \\\n'
        f'    -H "Content-Type: application/json" \\\n'
        f"    -d '{{\"model\": \"{selected_model}\", \"messages\": [{{\"role\": \"user\", \"content\": \"Hello!\"}}]}}'\n\n"
        f"[bold cyan]Python (openai client):[/bold cyan]\n"
        f'  from openai import OpenAI\n'
        f'  client = OpenAI(base_url="<YOUR_URL>/v1", api_key="{first_key}")\n'
        f'  resp = client.chat.completions.create(\n'
        f'      model="{selected_model}",\n'
        f'      messages=[{{"role": "user", "content": "Hello!"}}]\n'
        f'  )',
        title="DEPLOYMENT SUCCESS",
        border_style="green",
    ))

    del_choice = Prompt.ask(
        f"\n[bold cyan]Delete {runner_file}?[/bold cyan]",
        choices=["y", "n"],
        default="n",
    )
    if del_choice == "y":
        try:
            os.remove(runner_file)
            console.print("[dim]Cleaned up.[/dim]")
        except OSError:
            pass


# ─── Stop command ─────────────────────────────────────────────


@app.command("stop")
def stop():
    """Stop the deployed LLM API server."""
    console.print("[cyan]Stopping m-gpux-llm-api...[/cyan]")
    result = subprocess.run(
        ["modal", "app", "stop", "m-gpux-llm-api"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        console.print("[bold green]App stopped successfully.[/bold green]")
    else:
        err = result.stderr.strip()
        if "Could not find" in err:
            console.print("[yellow]No deployed app found (already stopped or never deployed).[/yellow]")
        else:
            console.print(f"[red]Error: {err}[/red]")


# ─── Warmup / ping command ────────────────────────────────────


def _warmup_worker(base_url: str, model_name: str):
    """Send a lightweight request to trigger cold start + model load."""
    import urllib.request

    # Phase 1: hit /v1/models to trigger cold start
    models_url = f"{base_url}/v1/models"
    console.print(f"  [dim]Hitting {models_url} ...[/dim]")
    start = time.time()
    try:
        r = urllib.request.urlopen(models_url, timeout=600)
        elapsed = time.time() - start
        console.print(f"  [green]Container ready in {elapsed:.1f}s[/green]")
    except Exception as e:
        console.print(f"  [red]Cold start failed: {e}[/red]")
        return

    # Phase 2: send a tiny completion to warm the engine
    console.print("  [dim]Sending warmup completion...[/dim]")
    data = json.dumps({
        "model": model_name,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        start = time.time()
        r = urllib.request.urlopen(req, timeout=120)
        elapsed = time.time() - start
        console.print(f"  [green]First inference done in {elapsed:.1f}s — server is hot![/green]")
    except Exception as e:
        console.print(f"  [yellow]Warmup completion failed: {e}[/yellow]")


@app.command("warmup")
def warmup(
    url: str = typer.Option(None, help="Full base URL (e.g. https://workspace--m-gpux-llm-api-serve.modal.run)"),
    model: str = typer.Option(None, help="Model name for warmup completion"),
):
    """Trigger cold start and warm up the vLLM engine so it's ready for requests."""
    if not url:
        # Try to guess from active profile
        profiles = _load_profiles_for_url()
        if profiles:
            url = profiles[0]
            console.print(f"  [dim]Auto-detected URL: {url}[/dim]")
        else:
            url = Prompt.ask("Enter your deployment base URL")

    url = url.rstrip("/")
    if not model:
        model = Prompt.ask("Model name", default="Qwen/Qwen3.5-35B-A3B")

    console.print(Panel.fit(
        f"[bold cyan]Warming up LLM API[/bold cyan]\n"
        f"URL: {url}\n"
        f"Model: {model}",
        border_style="cyan",
    ))

    _warmup_worker(url, model)


def _load_profiles_for_url():
    """Try to build endpoint URLs from known Modal profiles."""
    import tomlkit
    config_path = os.path.expanduser("~/.modal.toml")
    if not os.path.exists(config_path):
        return []
    try:
        result = subprocess.run(
            ["modal", "profile", "list", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import re
            # Parse workspace names from the table output
            lines = result.stdout.strip().split("\n")
            urls = []
            for line in lines:
                # Try to find workspace column from profile list
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2 and parts[0] not in ("Profile", ""):
                    workspace = parts[1] if len(parts) > 1 else parts[0]
                    urls.append(f"https://{workspace}--m-gpux-llm-api-serve.modal.run")
            return urls
    except Exception:
        pass
    return []
