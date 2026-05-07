# Command Reference

Complete reference for every `m-gpux` command, subcommand, and common workflow.

Use `m-gpux --help` or `m-gpux <command> --help` for inline help at any time.

## Overview

| Command | Purpose |
|---|---|
| `m-gpux` | Show welcome screen with quick actions |
| `m-gpux info` | Print version and framework metadata |
| `m-gpux dev` | Launch a persistent Modal dev container for the current folder |
| `m-gpux hub` | Interactive GPU session launcher |
| `m-gpux sessions` | List, stop, inspect, and pull Hub/dev sessions |
| `m-gpux preset` | Save and rerun common workload presets |
| `m-gpux host` | Deploy ASGI, WSGI, or static web apps |
| `m-gpux compose` | Analyze and deploy Docker Compose stacks on Modal |
| `m-gpux vision` | Train computer vision models on Modal GPUs |
| `m-gpux serve` | Deploy LLMs as OpenAI-compatible APIs |
| `m-gpux stop` | Stop running m-gpux apps |
| `m-gpux account` | Manage Modal profiles |
| `m-gpux billing` | Track compute costs |
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

**Example:**

```bash
m-gpux billing usage --days 7 --all
```

---

## dev

Launch a persistent Modal dev container for the current folder.

```bash
m-gpux dev
m-gpux dev --preset rl-a100
```

The dev container uses the same Web Bash terminal as Hub, but optimizes the flow for day-to-day remote development:

- selects a Modal profile
- selects CPU or GPU compute
- installs `requirements.txt` or extra packages
- uploads the current folder into `/workspace_seed`
- mounts `/workspace` on a Modal Volume
- copies local files into `/workspace` on every launch, overwriting matching paths
- auto-commits remote changes roughly every 20 seconds
- tracks the session locally for `m-gpux sessions`

At the end of the wizard, `m-gpux` asks whether you want to save the workload as a preset.

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
| 4. Review | The generated `modal_runner.py` is shown for inspection |
| 5. Launch | Press Enter to execute, or edit the script first |

### Hub actions

#### Jupyter Lab

Launches a GPU-backed Jupyter Lab instance. A public URL is printed to the terminal so you can open it in the browser.

#### Run Python script

Prompts for a local `.py` filename. The script is uploaded and executed on the selected GPU.

#### Web Bash shell

Opens a VS Code-like terminal session in the browser. The shell now starts as direct `bash` for smoother typing, cleaner rendering, scrollback support, and optional manual `tmux` when you want detachable sessions.

The remote `/workspace` is backed by a Modal Volume. Files keep the same relative paths as your local workspace and are auto-committed about every 20 seconds. On a new launch, local files overwrite matching paths in the Volume, while remote-only outputs remain. The terminal prints a `modal volume get ...` command you can run later to pull remote changes back to your machine.

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

Watches local files and syncs changes into the workspace volume used by the running compose deployment.

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

### Compose notes

- Supported file discovery: `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml`
- Local environment references are surfaced during the flow so missing values can be filled in
- `x-mgpux` metadata can override base image, apt packages, and related generation details

For the full workflow, see [Docker Compose](compose.md).

---

## vision

Train image classification models on Modal GPUs from local datasets.

```bash
m-gpux vision sample-data
m-gpux vision train
m-gpux vision predict
m-gpux vision evaluate
m-gpux vision export
```

### sample-data

```bash
m-gpux vision sample-data
m-gpux vision sample-data --output ./data/demo-shapes --image-size 160
m-gpux vision sample-data --layout single-root --images-per-class 30
```

Generate or refresh a small local image-classification dataset for demos and smoke tests.

| Option | Description | Default |
|---|---|---|
| `--output`, `-o` | Destination folder | `data/m-gpux-vision-sample` |
| `--layout` | Dataset layout: `split` or `single-root` | `split` |
| `--image-size` | Generated image size in pixels | `128` |
| `--images-per-class` | Images per class for single-root layout | `24` |
| `--train-per-class` | Training images per class for split layout | `12` |
| `--val-per-class` | Validation images per class for split layout | `4` |
| `--test-per-class` | Test images per class for split layout | `4` |
| `--seed` | Random seed for deterministic sample images | `42` |
| `--force` | Overwrite files in the destination folder | `false` |

### train

```bash
m-gpux vision train
m-gpux vision train --dataset ./data/cats-vs-dogs --model resnet50 --gpu A10G
```

| Option | Description | Default |
|---|---|---|
| `--dataset`, `-d` | Local dataset folder | `./data` if it exists, otherwise current directory |
| `--model`, `-m` | TorchVision image-classification model builder | Interactive chooser |
| `--gpu`, `-g` | Modal GPU type | Interactive chooser |
| `--epochs` | Number of training epochs | `10` |
| `--batch-size` | Batch size | Suggested interactively |
| `--image-size` | Input image resolution | Suggested interactively |
| `--learning-rate`, `--lr` | Optimizer learning rate | `3e-4` |
| `--validation-split` | Validation fraction for non-pre-split datasets | `0.2` |
| `--pretrained/--no-pretrained` | Initialize from pretrained ImageNet weights | `--pretrained` |
| `--mixed-precision/--no-mixed-precision` | Use AMP on GPU | `--mixed-precision` |
| `--artifact-volume` | Modal Volume name for checkpoints and metrics | `m-gpux-vision-artifacts` |

### predict

```bash
m-gpux vision predict
m-gpux vision predict --input ./samples --run-name imgclf-resnet50-20260420-113500 --gpu T4
```

Load a saved checkpoint from the artifact volume and run inference on a local image file or folder.

### evaluate

```bash
m-gpux vision evaluate
m-gpux vision evaluate --dataset ./data/cats-vs-dogs --run-name imgclf-resnet50-20260420-113500 --split test --gpu T4
```

Evaluate a saved checkpoint on a local dataset and persist a detailed metrics report.

### export

```bash
m-gpux vision export
m-gpux vision export --run-name imgclf-resnet50-20260420-113500 --format all
```

Export a saved checkpoint into deployment-friendly formats such as ONNX and TorchScript.

For the full training workflow, dataset layouts, and artifact structure, see [Vision Training](vision.md).

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
| `--url`, `-u` | Base URL of the deployed API | Auto-detected from profiles |
| `--interval`, `-i` | Refresh interval in seconds | `3.0` |

Displays a live terminal dashboard for GPU, system, traffic, latency, and token metrics.

### logs

```bash
m-gpux serve logs
```

Streams live logs from the deployed `m-gpux-llm-api` app.

### stop

```bash
m-gpux serve stop
```

Stops the `m-gpux-llm-api` app on the current Modal profile.

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
