# Command Reference

Complete reference for every `m-gpux` command, subcommand, and option.

Use `m-gpux --help` or `m-gpux <command> --help` for inline help at any time.

## Overview

| Command | Purpose |
|---|---|
| `m-gpux` | Show welcome screen with quick actions |
| `m-gpux info` | Print version and framework metadata |
| `m-gpux hub` | Interactive GPU session launcher |
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
| 3. Action | Choose: **Jupyter Lab**, **Run Python script**, **Web Bash shell**, or **vLLM Inference** |
| 4. Review | The generated `modal_runner.py` is displayed with syntax highlighting |
| 5. Launch | Press Enter to execute, or edit the script first |

### Hub actions

#### Jupyter Lab

Launches a GPU-backed Jupyter Lab instance. A public URL is printed to the terminal — click it to open in your browser.

#### Run Python script

Prompts for a local `.py` filename. The script is uploaded and executed on the selected GPU.

#### Web Bash shell

Opens a VS Code-like terminal session in the browser, running on the selected GPU. The shell starts as direct `bash` for smoother typing and cleaner rendering, with a compact prompt, reduced WebSocket heartbeat traffic, and optional `tmux` if you want detachable sessions.

#### Interactive terminal for `input()` scripts

When a Python script contains `input()` calls, the hub can open the same low-latency browser terminal and show the command to run, for example `python main.py`.

#### vLLM Inference

Starts an OpenAI-compatible API server for a selected HuggingFace model. Choose deploy mode for persistent serving, or run mode for one-off testing.

!!! tip "Editing before launch"
    The hub shows the full `modal_runner.py` before executing. You can modify pip packages, timeouts, environment variables, or the container image before pressing Enter.

After execution completes, you're prompted whether to stop the app and release the GPU.

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

The command group can generate a tiny demo dataset, validate a local dataset, then launch a wizard that generates a full `modal_runner.py` training job.

### sample-data

```bash
m-gpux vision sample-data
m-gpux vision sample-data --output ./data/demo-shapes --image-size 160
m-gpux vision sample-data --layout single-root --images-per-class 30
```

Generate or refresh a small local image-classification dataset for demos and smoke tests. The repository includes the default generated dataset at `data/m-gpux-vision-sample`; the generated classes are `circle`, `square`, and `triangle`, written as PNG images with no external downloads.

| Option | Description | Default |
|---|---|---|
| `--output`, `-o` | Destination folder | `data/m-gpux-vision-sample` |
| `--layout` | Dataset layout: `split` or `single-root` | `split` |
| `--image-size` | Generated image size in pixels | `128` |
| `--images-per-class` | Images per class for single-root layout | `24` |
| `--train-per-class` | Training images per class for split layout | `12` |
| `--val-per-class` | Validation images per class for split layout | `4` |
| `--test-per-class` | Test images per class for split layout; use `0` to skip | `4` |
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
| `--batch-size` | Batch size | Model-dependent suggestion |
| `--image-size` | Input image resolution | Model-dependent suggestion |
| `--learning-rate`, `--lr` | Optimizer learning rate | `3e-4` |
| `--validation-split` | Validation fraction for non-pre-split datasets | `0.2` |
| `--pretrained/--no-pretrained` | Initialize from pretrained ImageNet weights | `--pretrained` |
| `--mixed-precision/--no-mixed-precision` | Use AMP on GPU | `--mixed-precision` |
| `--artifact-volume` | Modal Volume name for checkpoints and metrics | `m-gpux-vision-artifacts` |

### Supported dataset layouts

`vision train` supports these local folder layouts:

```text
dataset/
  train/
    cat/
    dog/
  val/
    cat/
    dog/
  test/
    cat/
    dog/
```

or:

```text
dataset/
  cat/
  dog/
```

For the second layout, `m-gpux` creates a validation split automatically.

### What gets trained

The generated job includes:

- A TorchVision image-classification model (ResNet, EfficientNet, ConvNeXt, DenseNet, ViT, Swin, and more)
- Configurable optimizer, scheduler, augmentation strength, early stopping, and gradient accumulation
- Mixed precision training on GPU
- Checkpoints, config, history, and summary JSON saved to a Modal Volume

### Artifacts

Artifacts are written into the Modal Volume you select, under a run-specific folder such as:

```text
m-gpux-vision-artifacts/
  imgclf-resnet50-20260420-113500/
    checkpoints/
      best_model.pt
      last_model.pt
    config.json
    history.json
    summary.json
```

You can download files later with the Modal CLI:

```bash
modal volume get m-gpux-vision-artifacts <run-name>/summary.json summary.json
modal volume get m-gpux-vision-artifacts <run-name>/checkpoints/best_model.pt best_model.pt
```

### predict

```bash
m-gpux vision predict
m-gpux vision predict --input ./samples --run-name imgclf-resnet50-20260420-113500 --gpu T4
```

Load a saved checkpoint from the artifact volume and run inference on a local image file or folder.

| Option | Description | Default |
|---|---|---|
| `--input`, `-i` | Local image file or folder | `./samples` if it exists, otherwise current directory |
| `--run-name` | Experiment name inside the artifact volume | Interactive prompt |
| `--checkpoint-path` | Explicit checkpoint path inside the volume | `<run-name>/checkpoints/best_model.pt` |
| `--gpu`, `-g` | Modal GPU type | Interactive chooser |
| `--top-k` | Number of ranked classes per image | `3` |
| `--batch-size` | Inference batch size | `16` |
| `--max-images` | Optional cap on images from an input folder | No cap |
| `--mixed-precision/--no-mixed-precision` | Use AMP on GPU | `--mixed-precision` |
| `--artifact-volume` | Modal Volume name for checkpoints/predictions | `m-gpux-vision-artifacts` |

`vision predict` reads the saved `config` and `class_names` from the checkpoint, reconstructs the model automatically, and writes a JSON prediction report back into the artifact volume.

### evaluate

```bash
m-gpux vision evaluate
m-gpux vision evaluate --dataset ./data/cats-vs-dogs --run-name imgclf-resnet50-20260420-113500 --split test --gpu T4
```

Evaluate a saved checkpoint on a local dataset and persist a detailed metrics report to the artifact volume.

| Option | Description | Default |
|---|---|---|
| `--dataset`, `-d` | Local dataset folder | `./data` if it exists, otherwise current directory |
| `--run-name` | Experiment name inside the artifact volume | Interactive prompt |
| `--checkpoint-path` | Explicit checkpoint path inside the volume | `<run-name>/checkpoints/best_model.pt` |
| `--gpu`, `-g` | Modal GPU type | Interactive chooser |
| `--split` | Which split to evaluate: `auto`, `train`, `val`, `test` when available | `auto` |
| `--top-k` | Top-k accuracy to compute | `5` |
| `--batch-size` | Evaluation batch size | `32` |
| `--validation-split` | Fallback validation fraction for single-root datasets | `0.2` |
| `--mixed-precision/--no-mixed-precision` | Use AMP on GPU | `--mixed-precision` |
| `--artifact-volume` | Modal Volume name for checkpoints/evaluation reports | `m-gpux-vision-artifacts` |

The JSON report includes loss, accuracy, top-k accuracy, confusion matrix, macro F1, and per-class precision/recall/F1.

### export

```bash
m-gpux vision export
m-gpux vision export --run-name imgclf-resnet50-20260420-113500 --format all
```

Export a saved checkpoint into deployment-friendly formats.

| Option | Description | Default |
|---|---|---|
| `--run-name` | Experiment name inside the artifact volume | Interactive prompt |
| `--checkpoint-path` | Explicit checkpoint path inside the volume | `<run-name>/checkpoints/best_model.pt` |
| `--format` | Export format: `onnx`, `torchscript`, or `all` | `all` |
| `--output-dir` | Output directory inside the artifact volume | `<run-name>/exports/export-<timestamp>` |
| `--artifact-volume` | Modal Volume name for checkpoints/exports | `m-gpux-vision-artifacts` |

Artifacts written by `vision export` include:

- `model.onnx` when ONNX export is selected
- `model.ts` when TorchScript export is selected
- `labels.json`
- `export_summary.json`

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
| 3.5 | vLLM engine tuning (GPU mem utilization, max seqs, tensor parallel) | `0.92`, `128`, `1` |
| 4 | Min containers / keep warm | `1` |
| 5 | API key (select existing or auto-create) | First active key |

**What gets deployed:**

- A Modal app named `m-gpux-llm-api` with:
    - **Auth proxy** (FastAPI + uvicorn on port 8000) — validates `Authorization: Bearer` headers, retry with backoff, backpressure (429 when overloaded), internal streaming for long inference
    - **vLLM backend** (on port 8001) — OpenAI-compatible `/v1/chat/completions`, `/v1/models`, etc.
    - **Shared Volumes** — `m-gpux-hf-cache` and `m-gpux-vllm-cache` persist model weights across deployments
    - **Stats endpoint** (`/stats`) — real-time metrics: inflight requests, latency percentiles, token counts, GPU/CPU/RAM/disk usage

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
| `/stats` endpoint | Always `200 OK` (no auth required) |
| Too many concurrent requests | `429 Too Many Requests` with `retry_after` |

**Supported API routes:**

| Route | Method | Description |
|---|---|---|
| `/health` | GET | Health check + vLLM readiness + inflight count |
| `/stats` | GET | Full metrics: latency, throughput, GPU/CPU/RAM, tokens |
| `/v1/models` | GET | List loaded models |
| `/v1/chat/completions` | POST | Chat completion (streaming & non-streaming) |
| `/v1/completions` | POST | Text completion |

**Proxy resilience features:**

| Feature | Behavior |
|---|---|
| Retry with backoff | 3 attempts with 1s, 2s, 4s delays on connection errors |
| Backpressure | Returns 429 when >150 concurrent requests in-flight |
| Internal streaming | Non-stream requests use streaming internally to prevent timeout on long inference |
| Error recovery | `RemoteProtocolError`, `ReadError` caught and retried; stream errors yield SSE error event |

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

Live terminal dashboard with Rich, showing:

- **GPU** — VRAM usage, compute utilization, memory bandwidth, temperature, power draw (progress bars)
- **System** — CPU load, RAM usage, disk usage (progress bars)
- **Traffic** — in-flight requests with capacity bar, success rate, error counts (4xx/5xx/429)
- **Latency** — avg, P50, P95, P99, min, max with scaled bars
- **Tokens** — prompt/completion counts with ratio bars

Color coding: cyan (<40%) → green (<70%) → yellow (<90%) → red (≥90%).

### logs

```bash
m-gpux serve logs
```

Streams live logs from the deployed `m-gpux-llm-api` app. Press Ctrl+C to stop.

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
