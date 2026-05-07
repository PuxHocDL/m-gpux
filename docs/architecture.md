# Architecture

This page explains how `m-gpux` is put together: the CLI/plugin system, the generated Modal scripts, the Web Bash terminal path, and the LLM API server proxy layer.

## Project Structure

`m-gpux` is organized around a small core plus feature plugins. The CLI entrypoint discovers plugins and attaches their Typer commands to the root app.

```text
m_gpux/
  __init__.py
  main.py                    # CLI entrypoint and plugin registration
  core/
    console.py               # shared Rich console
    gpus.py                  # GPU and CPU catalogs
    metrics.py               # metrics snippet injected into generated scripts
    plugin.py                # PluginBase, registry, entry-point discovery
    profiles.py              # Modal profile loading, switching, selection
    runner.py                # generated script execution helpers
    state.py                 # local sessions, presets, and other state files
    ui.py                    # interactive arrow-key menu
  plugins/
    account/                 # profile CRUD
    billing/                 # usage reports and billing links
    compose/                 # Docker Compose analysis, deployment, and sync
    dev/                     # persistent Modal dev container command
    host/                    # ASGI, WSGI, and static hosting
    hub/                     # Jupyter, scripts, Web Bash, vLLM launchers
    info/                    # CLI/package diagnostics
    load/                    # GPU hardware probe
    preset/                  # reusable workload presets
    serve/                   # LLM API deployment and API key management
    sessions/                # local session tracking and workspace pull
    stop/                    # discover and stop running apps
    video/                   # text-to-video workflows
    vision/                  # image-classification workflows
```

## CLI Framework

The root command is `m_gpux.main:app`, registered in `pyproject.toml` as the `m-gpux` console script. The root app stays intentionally small: it loads built-in plugins, discovers third-party plugins through the `m_gpux.plugins` entry-point group, and lets each plugin register its own command tree.

This keeps the feature surface easy to extend:

- Core modules own shared behavior such as profiles, generated-script execution, GPU catalogs, and UI helpers.
- Plugins own user-facing workflows such as `hub`, `serve`, `vision`, `host`, and `billing`.
- Local state in `~/.m-gpux` tracks sessions, API keys, and workload presets.
- Third-party packages can add commands without editing the root CLI.

## Profile Management

Profiles are stored in `~/.modal.toml`. Each section represents one Modal identity:

```toml
[personal]
token_id = "ak-..."
token_secret = "as-..."

[work]
token_id = "ak-..."
token_secret = "as-..."
```

When a workflow needs a target account, `m-gpux` either uses the selected profile or activates it through:

```bash
modal profile activate <name>
```

The hub can also offer an automatic profile choice when enough billing information is available.

## Generated Script Pattern

Most workflows follow the same transparent execution pattern:

1. Collect parameters through prompts or command flags.
2. Generate a `modal_runner.py` file from a Python template.
3. Show the script for review before execution.
4. Run it with `modal run`, or deploy it with `modal deploy`.

This pattern is used by `hub`, `host`, `compose`, `vision`, `video`, and `serve`. The generated script is intentionally editable so users can inspect Modal decorators, dependencies, timeout settings, volumes, and uploaded paths before committing to a run.

## Compose Deployment Architecture

`compose` adds a bridge layer between Docker Compose and Modal.

The workflow:

1. Finds and parses a local Compose file.
2. Detects services, commands, ports, environment references, and common infra images.
3. Generates a temporary Modal app that either runs services as subprocesses in one container or provisions a VM-oriented container flow.
4. Attaches a workspace volume so local project files and later sync operations can reuse the same working directory.

This keeps Compose as the local source of truth while still giving users a reviewable Modal script before launch.

## Web Bash Terminal

The Web Bash shell uses `ttyd` as the browser terminal bridge. The default path is deliberately close to VS Code's integrated terminal:

The important choices are:

- `ttyd` launches `bash --login` directly by default.
- The prompt is simple ASCII, not a powerline or emoji-heavy prompt.
- Browser scrollback is enabled with a larger 10,000-line buffer and wheel scrolling.
- `/workspace` is backed by a Modal Volume for Jupyter, Web Bash, and interactive terminals, with auto-commit roughly every 20 seconds.
- `tmux` is still installed and configured, but users start it manually when they need detachable sessions.
- Terminal rendering options favor stable glyph layout and repaint behavior.

This reduces the common browser-terminal problems where tmux status lines, unicode prompt glyphs, or font-width mismatches make characters appear overwritten.

## Vision Training Architecture

`vision train` packages a local dataset into the Modal container with `Image.add_local_dir`, then runs a PyTorch image-classification training loop on the selected GPU.

The generated training app includes:

- Dataset layout validation for `train/`, `val/`, optional `test/`, or a single folder of class subdirectories.
- TorchVision model initialization with optional pretrained weights.
- Configurable optimizer, scheduler, augmentation, mixed precision, early stopping, and gradient accumulation.
- Persistent checkpoint and metrics storage in a Modal Volume.

Downstream commands reuse the same artifacts:

- `vision predict` loads checkpoints and class labels to classify new local images.
- `vision evaluate` loads checkpoints and computes accuracy, top-k accuracy, confusion matrix, macro F1, and per-class metrics.
- `vision export` writes deployment artifacts such as ONNX, TorchScript, labels, and export summaries.

## LLM API Server Architecture

`serve deploy` creates a two-process architecture inside one Modal GPU container. The proxy starts quickly on port `8000`, which satisfies Modal's web server startup probe. vLLM starts in the background on port `8001` and can take longer to load model weights.

## Why Two Processes?

Large models may take minutes to load. Modal's `@modal.web_server(port=8000)` expects a listening web server within the startup timeout. If vLLM owned the public port directly, slow model loading could look like a failed startup.

The split solves that:

- FastAPI starts immediately and exposes `/health`.
- vLLM loads in the background on `localhost:8001`.
- The proxy returns clear loading or retry behavior instead of losing requests.
- The public API gets auth, metrics, and backpressure before GPU inference work begins.

## Auth Flow

The proxy applies these gates before forwarding a request:

1. Public paths such as `/health`, `/docs`, `/openapi.json`, and `/stats` can pass without an API key.
2. API paths require an `Authorization: Bearer ...` header.
3. Missing keys return `401`.
4. Invalid keys return `403`.
5. Excess concurrent requests return `429`.
6. Valid requests are proxied to vLLM with retry and streaming support.

## Proxy Resilience

The auth proxy includes several behaviors to reduce request loss under load:

| Feature | Details |
|---|---|
| Retry with backoff | Retries transient connect, timeout, protocol, and read errors. |
| Backpressure | Tracks in-flight requests and rejects excess work with `429`. |
| Internal streaming | Keeps long non-stream responses alive while collecting chunks from vLLM. |
| Stream error recovery | Converts mid-stream failures into structured SSE error events when possible. |
| Metrics tracking | Tracks latency, status, and token usage for dashboard and stats views. |

## Streaming

For streaming requests (`"stream": true`), the proxy forwards vLLM's server-sent events directly to the client.

That means:

- Time-to-first-token stays close to direct vLLM access.
- Chunks are yielded as they arrive.
- `text/event-stream` is preserved.
- Client SDKs can consume the endpoint like an OpenAI-compatible API.

## Model Caching

Two Modal Volumes persist model artifacts across deployments and cold starts:

| Volume | Mount Path | Contents |
|---|---|---|
| `m-gpux-hf-cache` | `/root/.cache/huggingface` | HuggingFace model downloads |
| `m-gpux-vllm-cache` | `/root/.cache/vllm` | vLLM compiled model artifacts |

The first deploy may spend several minutes downloading weights. Later deploys reuse the cached model data, so startup is usually much faster.

## Container Lifecycle

| Setting | Behavior |
|---|---|
| `min_containers=0` | Scale to zero when idle. First request after idle may cold start. |
| `min_containers=1` | Keep one container warm for lower first-token latency. |
| `scaledown_window=5min` | Keep the container warm briefly after the last request. |
| `timeout=24h` | Maximum function lifetime before restart. |
| `max_inputs=200` | Allow many concurrent inputs per container through Modal concurrency. |

## API Key Storage

API keys are stored locally:

```text
~/.m-gpux/
  api_keys.json
```

Example:

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

Keys are generated with `secrets.token_hex(24)` and prefixed with `sk-mgpux-`.

Only the active key selected during `serve deploy` is embedded in the generated Modal script. If you rotate keys, redeploy the server.

## App Discovery

`m-gpux stop` finds running apps by:

1. Running `modal app list --json` for one profile or every configured profile.
2. Filtering apps whose description starts with `m-gpux` and whose state is `deployed` or `running`.
3. Presenting the matches in a selection table.
4. Calling `modal app stop <app_id>` on selected apps.

Use `m-gpux stop --all` when you want to scan every profile in `~/.modal.toml`.

## GPU Metrics

The shared metrics snippet uses `nvidia-smi` to report:

- GPU utilization percentage.
- VRAM usage.
- GPU temperature.
- Power consumption.

Generated Modal scripts can print one-time metrics at startup, and the `load probe` command can run a live hardware check for a selected GPU.
