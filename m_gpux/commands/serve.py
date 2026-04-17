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
    .pip_install("vllm", "transformers", "hf-transfer", "httpx", "fastapi", "uvicorn[standard]")
    .env(ENV_DICT_PLACEHOLDER)
)

hf_cache = modal.Volume.from_name("m-gpux-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

PROXY_CODE = """
import httpx, json, os, asyncio, time as _time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response, JSONResponse
import uvicorn

API_KEY = os.environ["MGPUX_API_KEY"]
VLLM = "http://127.0.0.1:8001"

pool_limits = httpx.Limits(max_connections=300, max_keepalive_connections=150, keepalive_expiry=120)
timeout = httpx.Timeout(900.0, connect=15.0)
http_client = None

# ── In-flight request tracking for backpressure ──
import threading
_inflight = 0
_inflight_lock = threading.Lock()
MAX_INFLIGHT = 150  # reject new requests beyond this to avoid silent hangs

# ── Retry config ──
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1.0, 2.0, 4.0]  # seconds between retries

# ── Metrics tracking ──
_stats = {
    "start_time": _time.time(),
    "total_requests": 0,
    "total_success": 0,
    "total_errors_4xx": 0,
    "total_errors_5xx": 0,
    "total_retries": 0,
    "total_tokens_prompt": 0,
    "total_tokens_completion": 0,
    "latency_sum": 0.0,
    "latency_count": 0,
    "latency_min": float("inf"),
    "latency_max": 0.0,
    "latency_recent": [],       # last 50 latencies for p50/p95
    "peak_inflight": 0,
    "rejected_429": 0,
}
_stats_lock = threading.Lock()

def _record_request(latency, status_code, prompt_tokens=0, completion_tokens=0, retries=0):
    with _stats_lock:
        _stats["total_requests"] += 1
        if 200 <= status_code < 400:
            _stats["total_success"] += 1
        elif 400 <= status_code < 500:
            _stats["total_errors_4xx"] += 1
        else:
            _stats["total_errors_5xx"] += 1
        _stats["total_retries"] += retries
        _stats["total_tokens_prompt"] += prompt_tokens
        _stats["total_tokens_completion"] += completion_tokens
        if latency > 0:
            _stats["latency_sum"] += latency
            _stats["latency_count"] += 1
            if latency < _stats["latency_min"]:
                _stats["latency_min"] = latency
            if latency > _stats["latency_max"]:
                _stats["latency_max"] = latency
            _stats["latency_recent"].append(latency)
            if len(_stats["latency_recent"]) > 50:
                _stats["latency_recent"] = _stats["latency_recent"][-50:]
        if _inflight > _stats["peak_inflight"]:
            _stats["peak_inflight"] = _inflight

@asynccontextmanager
async def lifespan(app):
    global http_client
    http_client = httpx.AsyncClient(base_url=VLLM, limits=pool_limits, timeout=timeout)
    yield
    await http_client.aclose()

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def auth(request, call_next):
    path = request.url.path
    if path in ("/health", "/", "/docs", "/openapi.json", "/stats"):
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
        r = await http_client.get("/v1/models", timeout=3)
        vllm_ready = r.status_code == 200
    except Exception:
        vllm_ready = False
    resp = {"status": "ok" if vllm_ready else "loading", "vllm_ready": vllm_ready, "inflight_requests": _inflight}
    return JSONResponse(content=resp, status_code=200)

@app.get("/stats")
async def stats():
    import subprocess as _sp
    with _stats_lock:
        s = dict(_stats)
        recent = sorted(s["latency_recent"]) if s["latency_recent"] else []
    uptime = _time.time() - s["start_time"]
    avg_latency = s["latency_sum"] / s["latency_count"] if s["latency_count"] else 0
    p50 = recent[len(recent)//2] if recent else 0
    p95 = recent[int(len(recent)*0.95)] if recent else 0
    p99 = recent[int(len(recent)*0.99)] if recent else 0
    rps = s["total_requests"] / uptime if uptime > 0 else 0
    # Try to get vLLM model info
    vllm_info = {}
    try:
        r = await http_client.get("/v1/models", timeout=3)
        if r.status_code == 200:
            vllm_info = r.json()
    except Exception:
        pass
    # ── GPU metrics via nvidia-smi ──
    gpus = []
    try:
        r = _sp.run(["nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,"
            "utilization.memory,temperature.gpu,power.draw,power.limit",
            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for i, line in enumerate(r.stdout.strip().splitlines()):
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 9:
                    gpus.append({
                        "index": i,
                        "name": p[0],
                        "vram_total_mib": int(float(p[1])),
                        "vram_used_mib": int(float(p[2])),
                        "vram_free_mib": int(float(p[3])),
                        "gpu_util_pct": int(float(p[4])),
                        "mem_util_pct": int(float(p[5])),
                        "temperature_c": int(float(p[6])),
                        "power_draw_w": round(float(p[7]), 1),
                        "power_limit_w": round(float(p[8]), 1),
                    })
    except Exception:
        pass
    # ── CPU metrics ──
    cpu_info = {}
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            cpu_info["load_1m"] = float(parts[0])
            cpu_info["load_5m"] = float(parts[1])
            cpu_info["load_15m"] = float(parts[2])
    except Exception:
        pass
    try:
        with open("/proc/cpuinfo") as f:
            ci = f.read()
        cpu_info["cores"] = ci.count("processor" + chr(9) + ":")
        for ln in ci.splitlines():
            if ln.startswith("model name"):
                cpu_info["model"] = ln.split(":", 1)[1].strip()
                break
    except Exception:
        pass
    # ── RAM metrics ──
    ram_info = {}
    try:
        with open("/proc/meminfo") as f:
            mi = {}
            for ln in f:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    mi[k.strip()] = v.strip()
        total_kb = int(mi.get("MemTotal", "0 kB").split()[0])
        avail_kb = int(mi.get("MemAvailable", "0 kB").split()[0])
        ram_info["total_mb"] = round(total_kb / 1024)
        ram_info["used_mb"] = round((total_kb - avail_kb) / 1024)
        ram_info["available_mb"] = round(avail_kb / 1024)
        ram_info["used_pct"] = round((total_kb - avail_kb) / total_kb * 100, 1) if total_kb else 0
    except Exception:
        pass
    # ── Disk metrics ──
    disk_info = {}
    try:
        st = os.statvfs("/")
        total_b = st.f_blocks * st.f_frsize
        free_b = st.f_bavail * st.f_frsize
        used_b = total_b - free_b
        disk_info["total_gb"] = round(total_b / (1024**3), 1)
        disk_info["used_gb"] = round(used_b / (1024**3), 1)
        disk_info["free_gb"] = round(free_b / (1024**3), 1)
        disk_info["used_pct"] = round(used_b / total_b * 100, 1) if total_b else 0
    except Exception:
        pass
    return {
        "uptime_seconds": round(uptime, 1),
        "inflight_requests": _inflight,
        "peak_inflight": s["peak_inflight"],
        "max_inflight_limit": MAX_INFLIGHT,
        "total_requests": s["total_requests"],
        "total_success": s["total_success"],
        "total_errors_4xx": s["total_errors_4xx"],
        "total_errors_5xx": s["total_errors_5xx"],
        "total_retries": s["total_retries"],
        "rejected_429": s["rejected_429"],
        "requests_per_second": round(rps, 2),
        "latency_avg_ms": round(avg_latency * 1000, 1),
        "latency_min_ms": round(s["latency_min"] * 1000, 1) if s["latency_min"] != float("inf") else 0,
        "latency_max_ms": round(s["latency_max"] * 1000, 1),
        "latency_p50_ms": round(p50 * 1000, 1),
        "latency_p95_ms": round(p95 * 1000, 1),
        "latency_p99_ms": round(p99 * 1000, 1),
        "tokens_prompt_total": s["total_tokens_prompt"],
        "tokens_completion_total": s["total_tokens_completion"],
        "vllm_models": vllm_info,
        "gpus": gpus,
        "cpu": cpu_info,
        "ram": ram_info,
        "disk": disk_info,
    }

async def _proxy_with_retry(method, url, content, headers, is_stream):
    last_exc = None
    retries_used = 0
    for attempt in range(RETRY_ATTEMPTS):
        try:
            if is_stream:
                # Client wants streaming — pass through with error handling
                async def stream_response():
                    try:
                        async with http_client.stream(method, url, content=content, headers=headers) as r:
                            async for chunk in r.aiter_bytes():
                                yield chunk
                    except Exception as stream_exc:
                        # Yield a proper SSE error so client gets notified instead of
                        # Modal seeing a truncated response (TransferEncodingError)
                        err_payload = json.dumps({"error": {"message": f"Stream interrupted: {stream_exc}", "type": "server_error"}})
                        NL = chr(10)
                        yield f"data: {err_payload}{NL}{NL}data: [DONE]{NL}{NL}".encode()
                return StreamingResponse(stream_response(), media_type="text/event-stream"), 200, retries_used

            # ── Internal streaming for non-stream requests ──
            # Stream from vLLM internally to keep connection alive during long inference,
            # collect all chunks, then return as a normal response.
            collected = bytearray()
            status_code = 200
            content_type = "application/json"
            async with http_client.stream(method, url, content=content, headers=headers) as r:
                status_code = r.status_code
                content_type = r.headers.get("content-type", "application/json")
                async for chunk in r.aiter_bytes():
                    collected.extend(chunk)

            # Extract token usage from collected response
            prompt_tok = 0
            comp_tok = 0
            if content_type.startswith("application/json"):
                try:
                    rj = json.loads(collected)
                    usage = rj.get("usage", {})
                    prompt_tok = usage.get("prompt_tokens", 0)
                    comp_tok = usage.get("completion_tokens", 0)
                except Exception:
                    pass
            resp = Response(
                content=bytes(collected),
                status_code=status_code,
                media_type=content_type,
            )
            return resp, status_code, retries_used, prompt_tok, comp_tok
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError) as exc:
            last_exc = exc
            retries_used += 1
            if attempt < RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
                continue
        except httpx.PoolTimeout as exc:
            resp = JSONResponse(status_code=429, content={"error": {"message": f"Server overloaded ({_inflight} requests in flight). Retry after a few seconds.", "type": "rate_limit_error"}, "retry_after": 5})
            return resp, 429, retries_used, 0, 0
        except Exception as exc:
            resp = JSONResponse(status_code=502, content={"error": {"message": f"Backend error: {exc}", "type": "server_error"}})
            return resp, 502, retries_used, 0, 0
    resp = JSONResponse(status_code=503, content={"error": {"message": f"vLLM not responding after {RETRY_ATTEMPTS} attempts. Model may still be loading.", "type": "server_error"}, "retry_after": 30})
    return resp, 503, retries_used, 0, 0

@app.api_route("/v1/{path:path}", methods=["GET","POST"])
async def proxy(request: Request, path: str):
    global _inflight
    # ── Backpressure: reject early if overloaded ──
    with _inflight_lock:
        if _inflight >= MAX_INFLIGHT:
            with _stats_lock:
                _stats["rejected_429"] += 1
            _record_request(0, 429)
            return JSONResponse(status_code=429, content={"error": {"message": f"Too many concurrent requests ({_inflight}/{MAX_INFLIGHT}). Please retry.", "type": "rate_limit_error"}, "retry_after": 5})
        _inflight += 1
    t0 = _time.time()
    try:
        body = await request.body()
        headers = {k:v for k,v in request.headers.items() if k.lower() not in ("host","authorization","content-length")}
        is_stream = False
        if body:
            try: is_stream = json.loads(body).get("stream", False)
            except: pass
        result = await _proxy_with_retry(request.method, f"/v1/{path}", body, headers, is_stream)
        latency = _time.time() - t0
        if is_stream:
            resp, status, retries = result[0], result[1], result[2]
            _record_request(latency, status, retries=retries)
            return resp
        resp, status, retries, ptok, ctok = result
        _record_request(latency, status, prompt_tokens=ptok, completion_tokens=ctok, retries=retries)
        return resp
    finally:
        with _inflight_lock:
            _inflight -= 1

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info",
                backlog=2048, limit_concurrency=300, limit_max_requests=None,
                timeout_keep_alive=120)
"""


@app.function(
    image=vllm_image,
    gpu="{gpu_type}",
    timeout=24 * 60 * MINUTES,
    scaledown_window=5 * MINUTES,
    min_containers={keep_warm},
    volumes=VOLUMES_PLACEHOLDER,
)
@modal.concurrent(max_inputs=200)
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
        "--tensor-parallel-size", "{tensor_parallel}",
        "--max-model-len", "{max_model_len}",
        "--gpu-memory-utilization", "{gpu_mem_util}",
        "--enable-prefix-caching",
        "--max-num-seqs", "{max_num_seqs}",
        "--enable-chunked-prefill",
    ]
    print("[M-GPUX] Starting vLLM on :8001:", " ".join(vllm_cmd))
    subprocess.Popen(vllm_cmd)

    # Start auth proxy on port 8000 (Modal detects this immediately)
    os.environ["MGPUX_API_KEY"] = API_KEY
    with open("/tmp/_proxy.py", "w") as f:
        f.write(PROXY_CODE)
    print("[M-GPUX] Starting auth proxy on :8000")

    import threading, time as _time
    def _watch_proxy():
        while True:
            proc = subprocess.Popen([sys.executable, "/tmp/_proxy.py"])
            print(f"[M-GPUX] Proxy started (pid={proc.pid})")
            proc.wait()
            print(f"[M-GPUX] Proxy exited with code {proc.returncode}, restarting in 1s...")
            _time.sleep(1)
    threading.Thread(target=_watch_proxy, daemon=True).start()
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

    # ── Step 3.5: vLLM Engine Hyperparameters ──
    console.print("\n[bold cyan]Step 3.5: vLLM Engine Tuning[/bold cyan]  [dim](press Enter for defaults)[/dim]")

    console.print("  [dim]gpu-memory-utilization: fraction of GPU VRAM for KV cache (lower = safer, higher = more throughput)[/dim]")
    gpu_mem_util = Prompt.ask("  GPU memory utilization", default="0.92")
    try:
        gpu_mem_val = float(gpu_mem_util)
        if not (0.1 <= gpu_mem_val <= 0.99):
            console.print("  [yellow]Value out of range, using 0.92[/yellow]")
            gpu_mem_util = "0.92"
    except ValueError:
        gpu_mem_util = "0.92"

    console.print("  [dim]max-num-seqs: max concurrent sequences in the engine (higher = more throughput but more VRAM)[/dim]")
    max_num_seqs = Prompt.ask("  Max concurrent sequences", default="128")

    console.print("  [dim]tensor-parallel-size: number of GPUs for tensor parallelism (1 for single GPU)[/dim]")
    tensor_parallel = Prompt.ask("  Tensor parallel size", default="1")

    console.print("  [dim]Sampling defaults (applied when client does NOT send these per-request):[/dim]")
    console.print("  [dim]  top-k: limits token choices to top K candidates (-1 = disabled, 50 = common)[/dim]")
    console.print("  [dim]  top-p: nucleus sampling probability (0.9-1.0)[/dim]")
    console.print("  [dim]  Note: clients can always override these per-request in the JSON body.[/dim]")

    console.print(f"\n  [green]Engine config:[/green] mem={gpu_mem_util}, seqs={max_num_seqs}, tp={tensor_parallel}")

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
        .replace("{gpu_mem_util}", gpu_mem_util)
        .replace("{max_num_seqs}", max_num_seqs)
        .replace("{tensor_parallel}", tensor_parallel)
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

    # ── Auto-stream logs so user can see vLLM loading status ──
    console.print(Panel(
        "[bold cyan]Streaming server logs...[/bold cyan]\n"
        "You can monitor vLLM startup here. Press [bold yellow]Ctrl+C[/bold yellow] to stop watching.",
        border_style="cyan",
    ))
    try:
        subprocess.run(["modal", "app", "logs", "m-gpux-llm-api"])
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching logs.[/dim]")


# ─── Logs command ─────────────────────────────────────────────


@app.command("logs")
def logs():
    """Stream live logs from the deployed LLM API server."""
    console.print(Panel.fit(
        "[bold cyan]Streaming logs from m-gpux-llm-api[/bold cyan]\n"
        "[dim]Press Ctrl+C to stop.[/dim]",
        border_style="cyan",
    ))
    try:
        subprocess.run(["modal", "app", "logs", "m-gpux-llm-api"])
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    except FileNotFoundError:
        console.print("[red]Modal CLI not found. Install with: pip install modal[/red]")


# ─── Dashboard command ────────────────────────────────────────


def _fetch_stats(base_url: str):
    """Fetch /stats and /health from the proxy. Returns (stats_dict, health_dict, error_str)."""
    import urllib.request
    stats = None
    health = None
    error = None
    # Fetch /stats
    try:
        r = urllib.request.urlopen(f"{base_url}/stats", timeout=5)
        stats = json.loads(r.read().decode())
    except Exception as e:
        error = str(e)
    # Fetch /health
    try:
        r = urllib.request.urlopen(f"{base_url}/health", timeout=5)
        health = json.loads(r.read().decode())
    except Exception:
        if not error:
            error = "Cannot reach /health"
    return stats, health, error


def _fmt_uptime(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _build_dashboard(stats: dict, health: dict, error: str, base_url: str) -> Panel:
    """Build a Rich Panel dashboard from stats data."""
    from rich.text import Text
    from rich.table import Table as RichTable

    if error and not stats:
        return Panel(
            f"[bold red]Cannot connect to server[/bold red]\n\n"
            f"  URL: {base_url}\n"
            f"  Error: {error}\n\n"
            f"[dim]Make sure your LLM API is deployed and the URL is correct.\n"
            f"Deploy with: m-gpux serve deploy[/dim]",
            title="[bold red] M-GPUX DASHBOARD — OFFLINE [/bold red]",
            border_style="red",
            padding=(1, 2),
        )

    def _bar(pct, width=25, filled_char="█", empty_char="░"):
        """Render a colored progress bar string."""
        pct = max(0, min(100, pct))
        fill = int(pct / 100 * width)
        if pct >= 90:
            color = "red"
        elif pct >= 70:
            color = "yellow"
        elif pct >= 40:
            color = "green"
        else:
            color = "cyan"
        return f"[{color}]{filled_char * fill}[/{color}][dim]{empty_char * (width - fill)}[/dim] [{color}]{pct:5.1f}%[/{color}]"

    def _temp_bar(temp_c, width=15):
        """Temperature bar: blue < 50, green < 70, yellow < 85, red >= 85."""
        pct = min(temp_c / 100 * 100, 100)
        fill = int(pct / 100 * width)
        if temp_c >= 85:
            color = "red"
        elif temp_c >= 70:
            color = "yellow"
        elif temp_c >= 50:
            color = "green"
        else:
            color = "cyan"
        return f"[{color}]{'▓' * fill}[/{color}][dim]{'░' * (width - fill)}[/dim] [{color}]{temp_c}°C[/{color}]"

    def _latency_bar(ms, max_ms=10000, width=20):
        """Latency bar scaled to max_ms."""
        pct = min(ms / max_ms * 100, 100) if max_ms > 0 else 0
        fill = int(pct / 100 * width)
        if ms >= 5000:
            color = "red"
        elif ms >= 2000:
            color = "yellow"
        elif ms >= 500:
            color = "green"
        else:
            color = "cyan"
        return f"[{color}]{'▇' * fill}[/{color}][dim]{'·' * (width - fill)}[/dim] [{color}]{ms:,.0f}ms[/{color}]"

    # ── Health status ──
    vllm_ready = health.get("vllm_ready", False) if health else False
    if vllm_ready:
        status_icon = "[bold green]● ONLINE[/bold green]"
        status_color = "green"
    else:
        status_icon = "[bold yellow]◐ LOADING[/bold yellow]"
        status_color = "yellow"

    uptime = _fmt_uptime(stats.get("uptime_seconds", 0))
    inflight = stats.get("inflight_requests", 0)
    peak = stats.get("peak_inflight", 0)
    limit = stats.get("max_inflight_limit", 150)

    # ── Model info ──
    model_name = "—"
    vllm_models = stats.get("vllm_models", {})
    if vllm_models and "data" in vllm_models:
        models_list = vllm_models["data"]
        if models_list:
            model_name = models_list[0].get("id", "—")

    # ── Request counters ──
    total = stats.get("total_requests", 0)
    success = stats.get("total_success", 0)
    err_4xx = stats.get("total_errors_4xx", 0)
    err_5xx = stats.get("total_errors_5xx", 0)
    retries = stats.get("total_retries", 0)
    rejected = stats.get("rejected_429", 0)
    rps = stats.get("requests_per_second", 0)
    success_rate = (success / total * 100) if total > 0 else 100.0

    # ── Latency ──
    avg_ms = stats.get("latency_avg_ms", 0)
    min_ms = stats.get("latency_min_ms", 0)
    max_ms = stats.get("latency_max_ms", 0)
    p50 = stats.get("latency_p50_ms", 0)
    p95 = stats.get("latency_p95_ms", 0)
    p99 = stats.get("latency_p99_ms", 0)
    lat_scale = max(max_ms, 1000)  # scale bars to the max observed, min 1000ms

    # ── Tokens ──
    tok_prompt = stats.get("tokens_prompt_total", 0)
    tok_comp = stats.get("tokens_completion_total", 0)
    tok_total = tok_prompt + tok_comp

    # ── GPU data ──
    gpus = stats.get("gpus", [])
    cpu = stats.get("cpu", {})
    ram = stats.get("ram", {})
    disk = stats.get("disk", {})

    lines = []

    # ━━ HEADER ━━
    lines.append(f"  {status_icon}  │  Uptime: [bold]{uptime}[/bold]  │  Model: [cyan]{model_name}[/cyan]  │  [bold]{rps:.1f}[/bold] req/s")
    lines.append(f"  {'━' * 72}")

    # ━━ GPU SECTION ━━
    if gpus:
        lines.append("")
        lines.append(f"  [bold magenta]🔲 GPU[/bold magenta]")
        for g in gpus:
            vram_total = g.get("vram_total_mib", 1)
            vram_used = g.get("vram_used_mib", 0)
            vram_pct = vram_used / vram_total * 100 if vram_total else 0
            gpu_util = g.get("gpu_util_pct", 0)
            mem_util = g.get("mem_util_pct", 0)
            temp = g.get("temperature_c", 0)
            pwr_draw = g.get("power_draw_w", 0)
            pwr_limit = g.get("power_limit_w", 1)
            pwr_pct = pwr_draw / pwr_limit * 100 if pwr_limit else 0
            gpu_name = g.get("name", "GPU")

            lines.append(f"  [bold]{gpu_name}[/bold] (GPU {g.get('index', 0)})")
            lines.append(f"    VRAM     {_bar(vram_pct)}  [dim]{vram_used:,} / {vram_total:,} MiB[/dim]")
            lines.append(f"    Compute  {_bar(gpu_util)}")
            lines.append(f"    Mem BW   {_bar(mem_util)}")
            lines.append(f"    Temp     {_temp_bar(temp)}")
            lines.append(f"    Power    {_bar(pwr_pct, width=15)}  [dim]{pwr_draw:.0f} / {pwr_limit:.0f} W[/dim]")
    else:
        lines.append("")
        lines.append(f"  [bold magenta]🔲 GPU[/bold magenta]  [dim](no data — container may be cold)[/dim]")

    # ━━ CPU / RAM / DISK ━━
    lines.append("")
    lines.append(f"  [bold blue]💻 System[/bold blue]")
    if cpu:
        cpu_model = cpu.get("model", "—")
        cores = cpu.get("cores", "?")
        load_1m = cpu.get("load_1m", 0)
        load_pct = load_1m / max(int(cores) if str(cores).isdigit() else 1, 1) * 100
        lines.append(f"    CPU      {_bar(min(load_pct, 100))}  [dim]{cpu_model} ({cores} cores) load: {load_1m:.1f}[/dim]")
    else:
        lines.append(f"    CPU      [dim](no data)[/dim]")

    if ram:
        ram_pct = ram.get("used_pct", 0)
        ram_used = ram.get("used_mb", 0)
        ram_total = ram.get("total_mb", 0)
        lines.append(f"    RAM      {_bar(ram_pct)}  [dim]{ram_used:,} / {ram_total:,} MB[/dim]")
    else:
        lines.append(f"    RAM      [dim](no data)[/dim]")

    if disk:
        disk_pct = disk.get("used_pct", 0)
        disk_used = disk.get("used_gb", 0)
        disk_total = disk.get("total_gb", 0)
        lines.append(f"    Disk     {_bar(disk_pct)}  [dim]{disk_used:.1f} / {disk_total:.1f} GB[/dim]")
    else:
        lines.append(f"    Disk     [dim](no data)[/dim]")

    # ━━ TRAFFIC ━━
    lines.append("")
    lines.append(f"  [bold green]📡 Traffic[/bold green]")
    inflight_pct = inflight / max(limit, 1) * 100
    lines.append(f"    Active   {_bar(inflight_pct)}  [bold]{inflight}[/bold] / {limit}  (peak: {peak})")
    sr_color = "green" if success_rate >= 99 else ("yellow" if success_rate >= 95 else "red")
    lines.append(f"    Success  {_bar(success_rate, width=25, filled_char='▓')}  [dim]{success:,} / {total:,}[/dim]")
    lines.append(f"    Errors   4xx: [yellow]{err_4xx:,}[/yellow]  │  5xx: [red]{err_5xx:,}[/red]  │  429 rejected: [red]{rejected:,}[/red]  │  retries: [yellow]{retries:,}[/yellow]")

    # ━━ LATENCY ━━
    lines.append("")
    lines.append(f"  [bold yellow]⏱ Latency[/bold yellow]  [dim](scale: 0 — {lat_scale:,.0f}ms)[/dim]")
    lines.append(f"    Avg      {_latency_bar(avg_ms, lat_scale)}")
    lines.append(f"    P50      {_latency_bar(p50, lat_scale)}")
    lines.append(f"    P95      {_latency_bar(p95, lat_scale)}")
    lines.append(f"    P99      {_latency_bar(p99, lat_scale)}")
    lines.append(f"    Min      {_latency_bar(min_ms, lat_scale)}")
    lines.append(f"    Max      {_latency_bar(max_ms, lat_scale)}")

    # ━━ TOKENS ━━
    lines.append("")
    lines.append(f"  [bold cyan]🔤 Tokens[/bold cyan]")
    if tok_total > 0:
        prompt_pct = tok_prompt / tok_total * 100
        lines.append(f"    Prompt   {_bar(prompt_pct, width=20, filled_char='▪', empty_char='·')}  [cyan]{tok_prompt:,}[/cyan]")
        lines.append(f"    Complet  {_bar(100 - prompt_pct, width=20, filled_char='▪', empty_char='·')}  [cyan]{tok_comp:,}[/cyan]")
        lines.append(f"    Total    [bold]{tok_total:,}[/bold]")
    else:
        lines.append(f"    [dim]No tokens processed yet[/dim]")

    lines.append("")
    lines.append(f"  [dim]{'━' * 72}[/dim]")
    lines.append(f"  [dim]Polling {base_url}/stats • Ctrl+C to exit[/dim]")

    content = "\n".join(lines)
    now_str = datetime.now().strftime("%H:%M:%S")
    return Panel(
        content,
        title=f"[bold cyan] ⚡ M-GPUX LLM Dashboard [/bold cyan]  [dim]{now_str}[/dim]",
        border_style=status_color,
        padding=(1, 0),
    )


@app.command("dashboard")
def dashboard(
    url: str = typer.Option(None, "--url", "-u", help="Base URL of the deployed API"),
    interval: float = typer.Option(3.0, "--interval", "-i", help="Refresh interval in seconds"),
):
    """Live terminal dashboard showing LLM API metrics, latency, and traffic."""
    from rich.live import Live

    if not url:
        profiles = _load_profiles_for_url()
        if profiles:
            url = profiles[0]
            console.print(f"  [dim]Auto-detected URL: {url}[/dim]")
        else:
            url = Prompt.ask("Enter your deployment base URL")

    url = url.rstrip("/")
    console.print(f"[cyan]Starting dashboard for {url} (refresh every {interval}s)...[/cyan]\n")

    try:
        with Live(console=console, refresh_per_second=1, screen=False) as live:
            while True:
                stats, health, error = _fetch_stats(url)
                panel = _build_dashboard(stats, health, error, url)
                live.update(panel)
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped.[/dim]")


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
