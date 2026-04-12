# Command Reference

Complete reference for every `m-gpux` command, subcommand, and option.

Use `m-gpux --help` or `m-gpux <command> --help` for inline help at any time.

## Overview

| Command | Purpose |
|---|---|
| `m-gpux` | Show welcome screen with quick actions |
| `m-gpux info` | Print version and framework metadata |
| `m-gpux hub` | Interactive GPU session launcher |
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

Prints version number and framework metadata.

---

## account

Manage local Modal profiles. Profiles are stored in `~/.modal.toml`.

### list

```bash
m-gpux account list
```

Displays a Rich table of all configured profiles. The active profile is highlighted.

**Example output:**

```
┌──────────┬────────────┬──────────┐
│ Profile  │ Workspace  │ Active   │
├──────────┼────────────┼──────────┤
│ personal │ puxpuxx    │ ✓        │
│ work     │ team-ai    │          │
└──────────┴────────────┴──────────┘
```

### add

```bash
m-gpux account add
```

Interactive prompt to add or update a profile. You'll be asked for:

- **Profile name** — a local label (e.g. `personal`, `work`, `team-gpu`)
- **Token ID** — from [modal.com/settings](https://modal.com/settings)
- **Token Secret** — shown once when the token is created

If a profile with the same name exists, its credentials are updated.

### switch

```bash
m-gpux account switch <profile_name>
```

Sets `<profile_name>` as the active Modal profile. All subsequent commands use this profile.

### remove

```bash
m-gpux account remove <profile_name>
```

Deletes a profile from `~/.modal.toml`. If the removed profile was active, another existing profile is automatically promoted.

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
| `--all` | Aggregate usage across ALL configured profiles | `false` |

**Example:**

```bash
# Last 7 days, all profiles combined
m-gpux billing usage --days 7 --all
```

---

## hub

Start interactive provisioning for GPU sessions.

```bash
m-gpux hub
```

The hub is a step-by-step wizard:

| Step | What happens |
|---|---|
| 1. Profile | Select which Modal profile to use (if multiple exist) |
| 2. GPU | Pick from 13 GPU types (T4 → B200) |
| 3. Action | Choose: **Jupyter Lab**, **Run Python script**, or **Web Bash shell** |
| 4. Review | The generated `modal_runner.py` is displayed with syntax highlighting |
| 5. Launch | Press Enter to execute, or edit the script first |

### Hub actions

#### Jupyter Lab

Launches a GPU-backed Jupyter Lab instance. A public URL is printed to the terminal — click it to open in your browser.

#### Run Python script

Prompts for a local `.py` filename. The script is uploaded and executed on the selected GPU.

#### Web Bash shell

Opens an interactive terminal session in the browser, running on the selected GPU.

!!! tip "Editing before launch"
    The hub shows the full `modal_runner.py` before executing. You can modify pip packages, timeouts, environment variables, or the container image before pressing Enter.

After execution completes, you're prompted whether to stop the app and release the GPU.

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

Interactive 5-step wizard to deploy a model:

| Step | Prompt | Default |
|---|---|---|
| 1 | Model (11 presets or custom HuggingFace ID) | `Qwen/Qwen2.5-7B-Instruct` |
| 2 | GPU type | Recommended for selected model |
| 3 | Max context length (tokens) | `4096` |
| 4 | Min containers / keep warm | `1` |
| 5 | API key (select existing or auto-create) | First active key |

**What gets deployed:**

- A Modal app named `m-gpux-llm-api` with:
    - **Auth proxy** (FastAPI + uvicorn on port 8000) — validates `Authorization: Bearer` headers
    - **vLLM backend** (on port 8001) — OpenAI-compatible `/v1/chat/completions`, `/v1/models`, etc.
    - **Shared Volumes** — `m-gpux-hf-cache` and `m-gpux-vllm-cache` persist model weights across deployments

**Endpoint URL format:**

```
https://<workspace>--m-gpux-llm-api-serve.modal.run
```

**Auth behavior:**

| Scenario | Response |
|---|---|
| No `Authorization` header | `401 Unauthorized` |
| Invalid key | `403 Forbidden` |
| Valid key | Request proxied to vLLM |
| `/health` endpoint | Always `200 OK` (no auth required) |

**Supported API routes:**

| Route | Method | Description |
|---|---|---|
| `/health` | GET | Health check + vLLM readiness |
| `/v1/models` | GET | List loaded models |
| `/v1/chat/completions` | POST | Chat completion (streaming & non-streaming) |
| `/v1/completions` | POST | Text completion |

### stop

```bash
m-gpux serve stop
```

Stops the `m-gpux-llm-api` app on the current Modal profile. If no app is deployed, prints a warning.

### warmup

```bash
m-gpux serve warmup
m-gpux serve warmup --url https://workspace--m-gpux-llm-api-serve.modal.run
m-gpux serve warmup --model Qwen/Qwen3-8B
```

| Option | Description | Default |
|---|---|---|
| `--url` | Full base URL of the deployment | Auto-detected from profiles |
| `--model` | Model name for the warmup completion | `Qwen/Qwen3.5-35B-A3B` |

**What it does:**

1. Sends a GET to `/v1/models` to trigger cold start (if scale-to-zero)
2. Sends a minimal chat completion (`max_tokens=1`) to initialize the vLLM engine
3. Reports timing for each phase

### keys create

```bash
m-gpux serve keys create
m-gpux serve keys create --name production
```

| Option | Description | Default |
|---|---|---|
| `--name` | Label for the key | Prompted interactively |

Generates a new API key in the format `sk-mgpux-<48 hex chars>` and stores it in `~/.m-gpux/api_keys.json`.

### keys list

```bash
m-gpux serve keys list
```

Shows a Rich table of all keys with:

- Name
- Masked key value (`sk-mgpux-8b37a1...bbe6`)
- Creation date
- Status (Active / Revoked)

### keys show

```bash
m-gpux serve keys show <name>
```

Reveals the full, unmasked API key value for the given key name.

### keys revoke

```bash
m-gpux serve keys revoke <name>
```

Marks a key as revoked locally. The key remains in the file but is flagged inactive.

!!! warning "Redeploy required"
    Revoking a key only updates the local store. You must run `m-gpux serve deploy` again to propagate the change to the running server.

---

## stop

Stop running m-gpux apps across profiles.

```bash
m-gpux stop
m-gpux stop --all
```

| Option | Description | Default |
|---|---|---|
| `--all` | Scan ALL configured Modal profiles | Current profile only |

**How it works:**

1. Scans for running apps whose description starts with `m-gpux` and state is `deployed` or `running`
2. Displays a numbered table of matching apps
3. Lets you select individual apps or stop all at once

**Example interaction:**

```
┌───┬──────────┬────────────────────┬──────────────────┬──────────┐
│ # │ Profile  │ App ID             │ Name             │ State    │
├───┼──────────┼────────────────────┼──────────────────┼──────────┤
│ 1 │ personal │ ap-abc123...       │ m-gpux-llm-api   │ deployed │
│ 2 │ work     │ ap-def456...       │ m-gpux-jupyter   │ running  │
└───┴──────────┴────────────────────┴──────────────────┴──────────┘

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
