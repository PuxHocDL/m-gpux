# Architecture

This page explains how m-gpux works internally — from CLI structure to the LLM API server proxy layer.

## Project Structure

```
m_gpux/
├── __init__.py              # Package version
├── main.py                  # CLI entrypoint, command registration, welcome screen, top-level stop
└── commands/
    ├── __init__.py
    ├── account.py           # Profile CRUD (add/list/switch/remove)
    ├── billing.py           # Usage aggregation and billing dashboard links
    ├── hub.py               # Interactive GPU runtime launcher (Jupyter/script/shell)
    ├── serve.py             # LLM API deployment, auth proxy, API key management
    ├── load.py              # Live GPU hardware metrics probe
    └── _metrics_snippet.py  # GPU metrics code injected into generated Modal scripts
```

## How it works

### CLI Framework

m-gpux is built on [Typer](https://typer.tiangolo.com/) with [Rich](https://rich.readthedocs.io/) for terminal output. The entrypoint is `m_gpux.main:app`, registered as the `m-gpux` console script in `pyproject.toml`.

Each command module (`account`, `billing`, `hub`, `serve`, `load`) defines its own `typer.Typer()` app, which is attached to the main app via `app.add_typer()`.

### Profile Management

Profiles are stored in `~/.modal.toml` using the [tomlkit](https://github.com/sdispater/tomlkit) library. Each section represents a profile:

```toml
[personal]
token_id = "ak-..."
token_secret = "as-..."

[work]
token_id = "ak-..."
token_secret = "as-..."
```

When switching profiles, m-gpux calls `modal profile activate <name>` to set the active profile for subsequent Modal CLI commands.

### Script Generation (Hub & Serve)

Both `hub` and `serve deploy` follow the same pattern:

1. **Collect parameters** via interactive prompts (GPU, action, model, etc.)
2. **Generate a Python script** (`modal_runner.py`) from a template with string substitution
3. **Show the script** for review (syntax-highlighted with Rich)
4. **Execute** via `modal run` (hub) or `modal deploy` (serve)

The generated script is fully transparent — users can edit it before execution.

---

## LLM API Server Architecture

The `serve deploy` command creates a unique two-process architecture inside a single Modal container:

```
┌─────────────────────────────────────────────────────────────┐
│                    Modal Container (GPU)                     │
│                                                             │
│  ┌──────────────────────┐    ┌───────────────────────────┐  │
│  │   Auth Proxy (8000)  │───▶│    vLLM Backend (8001)    │  │
│  │   FastAPI + uvicorn  │    │    OpenAI-compatible API  │  │
│  │                      │    │                           │  │
│  │  • Bearer token auth │    │  • /v1/chat/completions   │  │
│  │  • 401/403 responses │    │  • /v1/models             │  │
│  │  • Streaming proxy   │    │  • /v1/completions        │  │
│  │  • /health endpoint  │    │  • Model loading/serving  │  │
│  └──────────────────────┘    └───────────────────────────┘  │
│           ▲                                                  │
│           │ Port 8000 (Modal web_server)                     │
└───────────┼─────────────────────────────────────────────────┘
            │
     ┌──────┴──────┐
     │   Internet  │
     │   Clients   │
     └─────────────┘
```

### Why two processes?

Modal's `@modal.web_server(port=8000)` requires a server to be listening on the specified port quickly (startup timeout). vLLM takes several minutes to load large models. By starting FastAPI first (instant) and vLLM second (background), the container passes Modal's health probe immediately.

### Auth Flow

```
Client Request
    │
    ▼
┌─ Auth Middleware ──────────────────────────────────┐
│  1. Is path /health, /, /docs, /openapi.json,     │
│     /stats?                                        │
│     → YES: Pass through (no auth)                  │
│     → NO: Check Authorization header               │
│                                                    │
│  2. No "Bearer" prefix?                            │
│     → 401 {"error": "Missing API key..."}          │
│                                                    │
│  3. Key doesn't match?                             │
│     → 403 {"error": "Invalid API key"}             │
│                                                    │
│  4. Too many concurrent requests (>150)?           │
│     → 429 {"error": "Too many concurrent..."}      │
│                                                    │
│  5. Valid key + capacity available                  │
│     → Proxy to vLLM on localhost:8001 (with retry) │
└────────────────────────────────────────────────────┘
```

### Proxy Resilience

The auth proxy includes several features to prevent request loss under load:

| Feature | Details |
|---|---|
| **Retry with backoff** | 3 attempts with 1s→2s→4s delays on `ConnectError`, `TimeoutException`, `RemoteProtocolError`, `ReadError` |
| **Backpressure (429)** | Tracks in-flight requests; rejects with 429 when >150 concurrent |
| **Internal streaming** | Non-stream requests use `httpx.stream()` internally to collect chunks — keeps connection alive during long inference (prevents timeout on 5+ min completions) |
| **Stream error recovery** | Streaming responses catch mid-stream errors and yield a proper SSE error event instead of leaving truncated responses (prevents `TransferEncodingError`) |
| **Metrics tracking** | Every request's latency, status, token usage tracked for `/stats` and `dashboard` |

### Streaming

For streaming requests (`"stream": true`), the proxy uses `httpx.AsyncClient.stream()` to forward vLLM's SSE chunks directly to the client in real-time. This means:

- Time-to-first-token (TTFT) is the same as hitting vLLM directly
- No buffering — chunks are yielded as they arrive
- `text/event-stream` content type is preserved

### Model Caching

Two Modal Volumes persist model weights across deployments and cold starts:

| Volume | Mount Path | Contents |
|---|---|---|
| `m-gpux-hf-cache` | `/root/.cache/huggingface` | HuggingFace model downloads |
| `m-gpux-vllm-cache` | `/root/.cache/vllm` | vLLM compiled model artifacts |

First deploy: downloads weights from HuggingFace (5-15 min for large models).
Subsequent deploys: weights are already cached (cold start ~1-3 min).

### Container Lifecycle

| Setting | Behavior |
|---|---|
| `min_containers=0` | Scale to zero when idle. Cold start on first request (~3-5 min). |
| `min_containers=1` | One container always running. Response time ~0.9s. Costs GPU time continuously. |
| `scaledown_window=5min` | After last request, container stays warm for 5 minutes before scaling down. |
| `timeout=24h` | Max container lifetime before forced restart. |
| `max_inputs=200` | Up to 200 concurrent requests per container (via `@modal.concurrent`). |

### API Key Storage

```
~/.m-gpux/
└── api_keys.json
```

```json
[
  {
    "name": "production",
    "key": "sk-mgpux-8b37a191eb046c68...",
    "created": "2026-04-12T10:30:00",
    "active": true
  }
]
```

Keys are generated with `secrets.token_hex(24)` (48 hex characters), prefixed with `sk-mgpux-`.

Only the **first active key** is embedded in the deployed Modal script. To use a different key, revoke the old one and redeploy.

---

## App Discovery (stop command)

The top-level `m-gpux stop` command finds running apps by:

1. Running `modal app list --json` for each profile
2. Filtering apps where `description` starts with `m-gpux` and `state` is `deployed` or `running`
3. Presenting them in a selection table
4. Calling `modal app stop <app_id>` on selected apps

The `--all` flag scans every profile in `~/.modal.toml`. Without it, only the current active profile is scanned.

---

## GPU Metrics

The `_metrics_snippet.py` module provides GPU monitoring functions that are injected into generated Modal scripts. These functions use `nvidia-smi` to report:

- GPU utilization percentage
- VRAM usage (used / total)
- GPU temperature
- Power consumption

The `load probe` command connects to a running container to display these metrics live.
