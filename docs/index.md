# m-gpux Documentation

Welcome to the official docs for **m-gpux**, a production-focused CLI toolkit for Modal GPU operations.

> One CLI to manage profiles, launch GPU runtimes, deploy web apps and LLM APIs, and track cloud costs.

## What is m-gpux?

`m-gpux` turns Modal's serverless GPU platform into a streamlined developer experience:

| Capability | Description |
|---|---|
| **Multi-profile management** | Add, switch, and remove Modal identities, all stored in `~/.modal.toml` |
| **Dev Container Mode** | Turn the current folder into a persistent Modal CPU/GPU devbox with Volume-backed `/workspace` |
| **Interactive GPU Hub** | Guided wizard to launch Jupyter Lab, run Python scripts, or open a web shell on any GPU |
| **Session Manager** | Track running Hub/dev sessions, pull remote workspaces, view logs, and stop apps |
| **Workload Presets** | Save repeatable compute, dependency, and exclude settings for common workloads |
| **Web Hosting** | Deploy ASGI apps, WSGI apps, and static sites with generated Modal templates, dependency prompts, and deploy/run modes |
| **Vision Training** | Generate sample image data, then train classification models from local folders with configurable model, GPU, optimizer, scheduler, and checkpointing |
| **LLM API Server** | Deploy any HuggingFace model as an OpenAI-compatible endpoint with Bearer token auth, streaming, and warm containers |
| **API Key Management** | Create, list, show, and revoke `sk-mgpux-*` keys stored locally in `~/.m-gpux/api_keys.json` |
| **Billing Dashboard** | Inspect 7/30/90-day usage per profile or aggregated across all accounts |
| **GPU Metrics Probe** | Live hardware utilization (GPU %, VRAM, temperature) on running containers |
| **App Lifecycle** | Stop any running m-gpux app (Jupyter, shells, hosted apps, LLM servers) from one command |

## Quick Install

```bash
pip install m-gpux
```

Or from source:

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux && pip install -e .
```

!!! info "Requirements"
    Python 3.10+, Modal CLI installed (`pip install modal`), and at least one Modal account with `token_id` / `token_secret`.

## Start Here

| Page | What you'll learn |
|---|---|
| [Getting Started](getting-started.md) | Install, add your first profile, and launch a GPU session in 5 minutes |
| [Command Reference](commands.md) | Every command, flag, and option with examples |
| [Dev Container Mode](dev-container.md) | Use `m-gpux dev` as a persistent Modal-powered project workspace |
| [Session Manager](sessions.md) | Manage tracked dev and Hub sessions |
| [Workload Presets](presets.md) | Save and rerun common launch configs |
| [Recipes](recipes.md) | Practical flows for devboxes, RL training, hosting, and file recovery |
| [Web Hosting](web-hosting.md) | Host FastAPI, Flask, Django, or static sites on Modal with `m-gpux host` |
| [Vision Training](vision.md) | End-to-end image classification workflow on Modal GPUs |
| [Architecture](architecture.md) | How m-gpux works internally: proxy layer, template generation, profile resolution |
| [FAQ & Troubleshooting](faq.md) | Common errors and how to fix them |

## Common Workflows

### 1. Open A Modal Dev Container

```bash
cd my-project
m-gpux dev
```

`m-gpux dev` launches a browser terminal backed by a Modal Volume. Local files refresh into `/workspace` every launch, while remote-only outputs stay available until you pull or clean them.

```bash
m-gpux sessions list
m-gpux sessions pull <session-id> --to ./m-gpux-workspace
```

### 2. Launch Jupyter on a GPU

```bash
m-gpux account add
m-gpux hub
```

The hub generates a `modal_runner.py` script, shows it for review, then executes `modal run` to start a GPU-backed Jupyter Lab with a public URL.

!!! note "Hub terminal update"
    The hub can launch Jupyter, Python scripts, vLLM serving, or a clean VS Code-like Web Bash terminal. The terminal uses direct `bash` by default, keeps `tmux` optional, and reduces WebSocket heartbeat noise for smoother interaction.

### 3. Deploy an LLM as an OpenAI-compatible API

```bash
m-gpux serve keys create --name prod
m-gpux serve deploy
```

The wizard walks through:

1. **Model**  11 presets or a custom HuggingFace model ID
2. **GPU**  choose the hardware for inference
3. **Context length**  max sequence length
4. **Engine tuning**  GPU memory utilization, max concurrent sequences, tensor parallel size
5. **Keep warm**  `0` scales to zero, `1+` keeps container(s) always running
6. **API key**  pick an existing key or auto-create one

After deploy, monitor your server with the live dashboard:

```bash
m-gpux serve dashboard
```

### 4. Train an image classification model

```bash
m-gpux vision sample-data
m-gpux vision train --dataset ./data/m-gpux-vision-sample
```

The vision wizard walks through:

1. **Dataset folder**  accepts `train/`, `val/`, optional `test/` splits or a single root folder with class subdirectories
2. **Model**  choose from many TorchVision backbones such as ResNet, EfficientNet, ConvNeXt, DenseNet, ViT, Swin, and more
3. **Training knobs**  GPU, epochs, batch size, image size, optimizer, scheduler, augmentation, mixed precision, and early stopping
4. **Artifacts**  checkpoints and metrics are persisted in a Modal Volume for later download with `modal volume get`

After training, run inference on fresh local images:

```bash
m-gpux vision predict
```

### 5. Host a web app on Modal

```bash
m-gpux host asgi --entry main:app
```

The hosting flow supports:

1. **ASGI**  FastAPI, Starlette, Quart, Django ASGI
2. **WSGI**  Flask, Django WSGI
3. **Static**  plain HTML, CSS, and JavaScript folders

During the wizard, `m-gpux` asks for:

1. App name
2. CPU or GPU compute
3. Python dependencies or `requirements.txt`
4. Upload exclude patterns
5. Warm replica strategy
6. `deploy` vs `run`

!!! note "Full web guide"
    The complete walkthrough lives in [Web Hosting](web-hosting.md), including project layouts, generated Modal patterns, scaling behavior, and troubleshooting.

### 6. Save A Reusable Workload Preset

```bash
m-gpux preset create
m-gpux preset run rl-a100
```

Hub and dev mode can also ask whether you want to save a preset after you configure a workload.

### 7. Check costs across all accounts

```bash
m-gpux billing usage --days 7 --all
```

Aggregates compute spend from every configured profile into a single Rich table.

### 8. Stop running apps and release GPUs

```bash
m-gpux stop --all
m-gpux serve stop
```

!!! tip "Pro workflow"
    Keep one profile for personal experiments and one for team workloads, then run `m-gpux billing usage --all` weekly to track total burn across both.

## Supported GPUs

m-gpux supports all Modal GPU types:

| # | GPU | VRAM | Best for |
|---|---|---|---|
| 1 | T4 | 16 GB | Light inference, exploration |
| 2 | L4 | 24 GB | Cost/performance balance |
| 3 | A10G | 24 GB | Training and inference |
| 4 | L40S | 48 GB | Large-batch inference |
| 5 | A100 | 40 GB | High-performance training |
| 6 | A100-40GB | 40 GB | Ampere 40GB variant |
| 7 | A100-80GB | 80 GB | Large models (30B+) |
| 8 | RTX PRO 6000 | 48 GB | Pro workstation GPU |
| 9 | H100 | 80 GB | Hopper architecture |
| 10 | H100! | 80 GB | H100 reserved (guaranteed) |
| 11 | H200 | 141 GB | HBM3e, next-gen Hopper |
| 12 | B200 |  | Blackwell architecture |
| 13 | B200+ |  | B200 reserved (guaranteed) |

## Links

- **PyPI**: [pypi.org/project/m-gpux](https://pypi.org/project/m-gpux/)
- **Repository**: [github.com/PuxHocDL/m-gpux](https://github.com/PuxHocDL/m-gpux)
- **Issues**: [github.com/PuxHocDL/m-gpux/issues](https://github.com/PuxHocDL/m-gpux/issues)
- **Modal docs**: [modal.com/docs](https://modal.com/docs)
