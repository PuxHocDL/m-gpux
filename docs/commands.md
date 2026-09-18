# Command Reference

Complete reference for every `m-gpux` command, subcommand, and common workflow.

Use `m-gpux --help` or `m-gpux <command> --help` for inline help at any time.

## Overview

| Command | Purpose |
|---|---|
| `m-gpux` | Show welcome screen with quick actions |
| `m-gpux info` | Print version and framework metadata |
| `m-gpux dev` | Dev boxes: SSH / VS Code Remote, pause & resume, file sync |
| `m-gpux hub` | Interactive GPU session launcher |
| `m-gpux sessions` | List, stop, inspect, and pull Hub/dev sessions |
| `m-gpux preset` | Save and rerun common workload presets |
| `m-gpux host` | Deploy ASGI, WSGI, or static web apps |
| `m-gpux compose` | Analyze and deploy Docker Compose stacks on Modal |
| `m-gpux serve` | Deploy LLMs as OpenAI-compatible APIs |
| `m-gpux stop` | Stop running m-gpux apps |
| `m-gpux account` | Manage Modal profiles |
| `m-gpux billing` | Track compute costs and prices |
| `m-gpux budget` | Monthly spending limits per account, with auto-stop |
| `m-gpux image` | Prebuild & publish reusable images |
| `m-gpux load` | GPU hardware metrics probe |

---

## Global

### Welcome screen

```bash
m-gpux
```

Displays the ASCII logo and a Quick Actions table with the most common commands.

### info

```bash
m-gpux info
```

Prints the version number and framework metadata.

---

## account

Manage local Modal profiles. Profiles are stored in `~/.modal.toml`.

### list

```bash
m-gpux account list
```

Displays a table of all configured profiles. The active profile is marked.

**Example output:**

| Profile | Workspace | Active |
|---|---|---|
| personal | puxpuxx | yes |
| work | team-ai |  |

### add

```bash
m-gpux account add
```

Interactive prompt to add or update a profile. You will be asked for:

- **Profile name** - a local label such as `personal`, `work`, or `team-gpu`
- **Token ID** - from [modal.com/settings](https://modal.com/settings)
- **Token Secret** - shown once when the token is created

If a profile with the same name already exists, its credentials are updated.

### switch

```bash
m-gpux account switch <profile_name>
```

Sets `<profile_name>` as the active Modal profile. All subsequent commands use this profile unless a command lets you override it.

### remove

```bash
m-gpux account remove <profile_name>
```

Deletes a profile from `~/.modal.toml`. If the removed profile was active, another existing profile is promoted automatically.

---

## billing

Track usage costs from one or more profiles.

### open

```bash
m-gpux billing open
```

Opens the Modal usage dashboard in your default browser.

### usage

```bash
m-gpux billing usage
m-gpux billing usage --days 7
m-gpux billing usage --account personal
m-gpux billing usage --all
```

| Option | Description | Default |
|---|---|---|
| `--days` | Lookback period in days | `30` |
| `--account`, `-a` | Check a specific named profile | Active profile |
| `--all` | Aggregate usage across all configured profiles | `false` |
| `--resources`, `-r` | Add a cost breakdown by resource (CPU, memory, each GPU type) | `false` |

**Example:**

```bash
m-gpux billing usage --days 7 --all --resources
```

### rates

```bash
m-gpux billing rates
m-gpux billing rates --refresh
```

Prices per GPU-hour, CPU core-hour and GiB-hour (Functions vs. Sandboxes) used for the estimates in every picker. `--refresh` fetches live prices (`modal>=1.5.4`).

### summary

```bash
m-gpux billing summary
m-gpux billing summary --all
```

Shows the current billing cycle per account: metered cost, credits and other adjustments, the amount actually billed, and the spending category (deployed apps, notebooks, volumes…) that cost the most. Requires `modal>=1.5.3`.

---

## dev

Persistent dev boxes on Modal Sandboxes.

```bash
m-gpux dev up [--name NAME] [--image IMG] [--hours 12] [--lock-ip] [--no-ssh]
m-gpux dev list
m-gpux dev ssh | code | shell [NAME]
m-gpux dev sync push [--all] | pull [--to DIR]
m-gpux dev pause [NAME] [--keep-days 30]
m-gpux dev resume [NAME] [--hours N]
m-gpux dev down [NAME]
m-gpux dev web            # classic browser terminal
m-gpux dev --preset NAME  # classic mode from a preset
```

See [Dev Boxes](dev-container.md) for the full guide.

---

## budget

```bash
m-gpux budget set 20 [-a ACCOUNT]
m-gpux budget show
m-gpux budget check [--stop]
m-gpux budget watch [--interval 600] [--no-stop]
m-gpux budget clear [-a ACCOUNT]
```

See [Costs, Budgets & Images](costs.md).

---

## image

```bash
m-gpux image build NAME [--python 3.12] [-r requirements.txt] [--pip a,b] [--apt x,y] [-a ACCOUNT | --all]
m-gpux image list [--remote]
m-gpux image forget NAME
```

---

## sessions

Manage Hub/dev sessions tracked in `~/.m-gpux/sessions.json`.

```bash
m-gpux sessions list
m-gpux sessions show <session-id>
m-gpux sessions logs <session-id>
m-gpux sessions open <session-id>
m-gpux sessions pull <session-id> --to ./remote-workspace
m-gpux sessions stop <session-id>
m-gpux sessions forget <session-id>
```

The most common workflow is:

```bash
m-gpux sessions list
m-gpux sessions pull sess-1234abcd --to ./m-gpux-workspace
m-gpux sessions stop sess-1234abcd
```

`sessions logs` streams by default. Use `--no-follow` with `--tail`, `--since` or `--search` to read history instead:

```bash
m-gpux sessions logs sess-1234abcd --no-follow --tail 500
m-gpux sessions logs sess-1234abcd --since 2h --search error
```

Sessions are recorded as soon as a detached Hub/dev app starts successfully. If you stop it at the final prompt, the tracked state changes to `stopped`.

---

## preset

Save and rerun common workload choices.

```bash
m-gpux preset create
m-gpux preset list
m-gpux preset show rl-a100
m-gpux preset run rl-a100
m-gpux preset delete rl-a100
```

Presets store:

- action (`bash`, `dev`, `jupyter`, or `interactive`)
- selected profile
- compute settings
- pip dependency setup
- upload exclude patterns

Hub and `m-gpux dev` ask whether you want to save a preset after you configure a workload.

---

## hub

Start interactive provisioning for GPU sessions.

```bash
m-gpux hub
```

The hub is a step-by-step wizard:

| Step | What happens |
|---|---|
| 1. Profile | Select which Modal profile to use if multiple exist |
| 2. GPU | Pick from the available Modal GPU types |
| 3. Action | Choose Jupyter Lab, Run Python script, Web Bash shell, or vLLM Inference |
| 4. Python | Choose Python 3.10, 3.11, 3.12, 3.13, 3.14, or enter a custom Modal-supported version |
| 5. Review | The generated `modal_runner.py` is shown for inspection |
| 6. Launch | Press Enter to execute, or edit the script first |

### Hub actions

#### Jupyter Lab

Launches a GPU-backed Jupyter Lab instance. A public URL is printed to the terminal so you can open it in the browser.

#### Run Python script

Prompts for a local `.py` filename. The script is uploaded and executed on the selected GPU.

#### Web Bash shell

Opens a VS Code-like terminal session in the browser. The shell now starts as direct `bash` for smoother typing, cleaner rendering, scrollback support, and optional manual `tmux` when you want detachable sessions.

The remote `/workspace` is backed by a Modal Volume. Files keep the same relative paths as your local workspace. Commits are on demand: run `msync` in the shell to push `/workspace` to the Volume, or `msync pull` to pick up changes pushed from elsewhere; Modal commits once more when the container exits. On a new launch, local files overwrite matching paths in the Volume, while remote-only outputs remain. The terminal prints a `modal volume get ...` command you can run later to pull remote changes back to your machine.

#### Interactive terminal for `input()` scripts

When a Python script contains `input()` calls, the hub can open the same low-latency browser terminal and show the command to run, such as `python main.py`.

#### vLLM Inference

Starts an OpenAI-compatible API server for a selected HuggingFace model. Choose deploy mode for persistent serving, or run mode for one-off testing.

!!! tip "Editing before launch"
    The hub shows the full `modal_runner.py` before executing. You can modify pip packages, timeouts, environment variables, or the container image before pressing Enter.

After execution completes, you are prompted whether to stop the app and release the GPU.

---

## host

Deploy regular web apps with generated Modal templates.

```bash
m-gpux host --help
```

The host command group supports:

- `m-gpux host asgi` for FastAPI, Starlette, Quart, and Django ASGI
- `m-gpux host wsgi` for Flask and Django WSGI
- `m-gpux host static` for static HTML, CSS, and JavaScript folders

Every host command accepts `--server` to run on Modal's low-latency `@app.server()` primitive (`modal>=1.5.1`; ASGI via uvicorn, WSGI via gunicorn, static via `http.server`; URLs end in `.modal.direct`), and `--strategy rolling|recreate` for redeploys. `rolling` (default) keeps the old version serving until new containers are ready; `recreate` stops old containers immediately so the next request is guaranteed to hit the new code.

### asgi

```bash
m-gpux host asgi --entry main:app
```

Use this when your project exposes an ASGI application object.

| Option | Description | Default |
|---|---|---|
| `--entry` | Python entry in `<module>:<object>` form | Prompted interactively |
| `--name` | App name suffix used in `m-gpux-host-<name>` | Prompted interactively |
| `--project-dir` | Local project folder to upload | Current directory |

Generated behavior:

- uploads your project into the container at `/app`
- installs dependencies from `requirements.txt` or manually entered packages
- exposes the app with `@modal.asgi_app()`

Common entries:

- `main:app` for FastAPI
- `server:app` for Starlette
- `project.asgi:application` for Django ASGI

### wsgi

```bash
m-gpux host wsgi --entry app:app
```

Use this when your project exposes a WSGI application object.

| Option | Description | Default |
|---|---|---|
| `--entry` | Python entry in `<module>:<object>` form | Prompted interactively |
| `--name` | App name suffix used in `m-gpux-host-<name>` | Prompted interactively |
| `--project-dir` | Local project folder to upload | Current directory |

Generated behavior:

- uploads your project into the container at `/app`
- installs dependencies from `requirements.txt` or manually entered packages
- exposes the app with `@modal.wsgi_app()`

Common entries:

- `app:app` for Flask
- `project.wsgi:application` for Django WSGI

### static

```bash
m-gpux host static --dir ./site
```

Serve a static directory with Python's built-in HTTP server.

| Option | Description | Default |
|---|---|---|
| `--dir` | Local directory containing the static site | Prompted interactively |
| `--name` | App name suffix used in `m-gpux-host-<name>` | Prompted interactively |

Generated behavior:

- uploads your files into the container at `/site`
- starts `python -m http.server 8000`
- exposes the site with `@modal.web_server(8000)`

### Shared hosting flow

All host flows ask for:

1. Profile
2. App name
3. CPU or GPU compute
4. Dependency setup
5. Upload exclude patterns
6. Warm replicas
7. `deploy` vs `run`

Default upload excludes:

```text
.venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox,dist,build
```

Generated templates use:

- `timeout=86400`
- `scaledown_window=300`
- `@modal.concurrent(max_inputs=100)`
- `min_containers=0` or `1` depending on the warm-replica choice

!!! note "Deploy vs run"
    Choose `deploy` for a stable public URL that should stay online. Choose `run` for quick validation when you only want a temporary session.

For the full walkthrough, see [Web Hosting](web-hosting.md).

---

## compose

Analyze and deploy Compose projects from the current folder.

```bash
m-gpux compose --help
```

### check

```bash
m-gpux compose check
m-gpux compose check --file ./deploy/compose.prod.yml
```

Parses the Compose file and shows detected services, ports, and deployment hints without launching anything.

### up

```bash
m-gpux compose up
m-gpux compose up --file ./docker-compose.yml
```

Runs the standard single-container deployment flow.

Typical flow:

1. Choose or auto-pick a Modal profile
2. Analyze the Compose services
3. Collect environment values and exclude patterns
4. Generate a Modal script for review
5. Launch a detached Modal app and track it as a session

### sync

```bash
m-gpux compose sync
```

Watches local files and syncs changes into the workspace volume used by the running compose deployment. The container does not reload on its own — run `msync pull` inside it when you want the pushed files loaded.

### vm check

```bash
m-gpux compose vm check
```

Analyzes the stack for the VM-oriented deployment path.

### vm up

```bash
m-gpux compose vm up
```

Uses the VM-oriented generator for workloads that need fuller image behavior, tunneled ports, or custom Dockerfile semantics.

### sandbox

```bash
m-gpux compose sandbox up
m-gpux compose sandbox ps
m-gpux compose sandbox logs [service]
m-gpux compose sandbox logs redis --no-follow --tail 200
m-gpux compose sandbox exec web -- ls -la /app
m-gpux compose sandbox down
```

Each service runs in its own Modal Sandbox, tagged with its service name so `ps`, `logs` and `exec` can find it. Services wait for their dependencies with readiness probes. HTTP ports get HTTPS URLs; raw TCP ports (Redis, Postgres, …) get `tcp://host:port` tunnels, and `service:port` references in environment variables are rewritten to them. `exec SERVICE -- CMD` runs a command on any OS; `exec SERVICE` without a command opens an interactive shell (not on Windows, where `modal shell` is unsupported). `logs --no-follow` reads stored history and needs `modal>=1.5.5`.

### Compose notes

- Supported file discovery: `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml`
- Local environment references are surfaced during the flow so missing values can be filled in
- `x-mgpux` metadata can override base image, apt packages, and related generation details

For the full workflow, see [Docker Compose](compose.md).

---

## serve

Deploy LLMs as OpenAI-compatible APIs with API key authentication.

```bash
m-gpux serve --help
```

### deploy

```bash
m-gpux serve deploy
```

Interactive wizard to deploy a model:

| Step | Prompt | Default |
|---|---|---|
| 1 | Model preset or custom HuggingFace ID | `Qwen/Qwen2.5-7B-Instruct` |
| 2 | GPU type | Recommended for selected model |
| 3 | Max context length | `4096` |
| 4 | vLLM engine tuning | `0.92`, `128`, `1` |
| 5 | Min containers / keep warm | `1` |
| 6 | API key | First active key |

| Option | Description | Default |
|---|---|---|
| `--strategy` | `rolling` keeps old containers serving during a redeploy; `recreate` replaces them immediately | `rolling` |

The endpoint URL is read from the deploy output and saved to `~/.m-gpux/serve.json`, so `dashboard` and `warmup` find it without `--url`.

What gets deployed:

- an auth proxy on port `8000`
- a vLLM backend on port `8001`
- shared cache volumes for model weights
- `/health` and `/stats` endpoints for monitoring

### dashboard

```bash
m-gpux serve dashboard
m-gpux serve dashboard --url https://workspace--m-gpux-llm-api-serve.modal.run
m-gpux serve dashboard --interval 5
```

| Option | Description | Default |
|---|---|---|
| `--url`, `-u` | Base URL of the deployed API | Last deployed URL, else guessed from profiles |
| `--interval`, `-i` | Refresh interval in seconds | `3.0` |

Displays a live terminal dashboard for GPU, system, traffic, latency, and token metrics.

### logs

```bash
m-gpux serve logs
m-gpux serve logs --no-follow --tail 300
m-gpux serve logs --since 1h --search "CUDA out of memory"
```

| Option | Description | Default |
|---|---|---|
| `--follow/--no-follow` | Keep streaming new lines | `--follow` |
| `--tail`, `-n` | Only the last N entries | all / 100 |
| `--since` | Start of range (`2h`, `2026-09-01T05:00`) | — |
| `--search`, `-s` | Only lines containing this text | — |
| `--source` | `stdout`, `stderr` or `system` | all |

### stop

```bash
m-gpux serve stop
```

Stops the `m-gpux-llm-api` app on the current Modal profile.

### restart

```bash
m-gpux serve restart
m-gpux serve restart --strategy rolling
```

Replaces the server's containers with fresh ones without redeploying code (`modal app rollover`). Handy after a hung vLLM engine or a changed Secret. `recreate` (default) swaps everything immediately; `rolling` avoids downtime.

### warmup

```bash
m-gpux serve warmup
m-gpux serve warmup --url https://workspace--m-gpux-llm-api-serve.modal.run
m-gpux serve warmup --model Qwen/Qwen3-8B
```

Triggers the deployment, waits for the backend to become responsive, and sends a tiny completion to warm the engine.

### keys create

```bash
m-gpux serve keys create
m-gpux serve keys create --name production
```

Generates a new API key in the format `sk-mgpux-<48 hex chars>` and stores it in `~/.m-gpux/api_keys.json`.

### keys list

```bash
m-gpux serve keys list
```

Shows a table of all keys with name, masked value, creation date, and status.

### keys show

```bash
m-gpux serve keys show <name>
```

Reveals the full API key value for the given key name.

### keys revoke

```bash
m-gpux serve keys revoke <name>
```

Marks a key as revoked locally.

!!! warning "Redeploy required"
    Revoking a key only updates the local store. Run `m-gpux serve deploy` again to propagate the change to the running server.

---

## stop

Stop running m-gpux apps across profiles.

```bash
m-gpux stop
m-gpux stop --all
```

| Option | Description | Default |
|---|---|---|
| `--all` | Scan all configured Modal profiles | Current profile only |

How it works:

1. Scans for running apps whose description starts with `m-gpux`
2. Displays a numbered table of matching apps
3. Lets you select individual apps or stop all at once

**Example interaction:**

| # | Profile | App ID | Name | State |
|---|---|---|---|---|
| 1 | personal | ap-abc123... | m-gpux-llm-api | deployed |
| 2 | work | ap-def456... | m-gpux-jupyter | running |

```text
  0: Stop ALL (2 apps)
  1: m-gpux-llm-api (personal)
  2: m-gpux-jupyter (work)

Select app to stop (0=all):
```

---

## load

Probe GPU hardware metrics on a running container.

### probe

```bash
m-gpux load probe
```

Displays live GPU utilization, VRAM usage, and temperature from a running m-gpux container.
