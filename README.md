# m-gpux

Professional CLI tooling for Modal GPU workflows: account profiles, interactive runtimes, web hosting, Docker Compose deployments, model serving, vision training, sessions, and billing visibility.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/PyPI-m--gpux-f59e0b?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/m-gpux/)
[![CLI](https://img.shields.io/badge/CLI-Typer%20%2B%20Rich-0ea5e9?style=for-the-badge&logo=terminal&logoColor=white)](https://typer.tiangolo.com/)
[![Docs](https://img.shields.io/badge/Docs-GitHub%20Pages-22c55e?style=for-the-badge&logo=github&logoColor=white)](https://puxhocdl.github.io/m-gpux/)
[![License](https://img.shields.io/badge/License-MIT-gray?style=for-the-badge)](https://github.com/PuxHocDL/m-gpux/blob/main/LICENSE)

## Highlights

- Interactive GPU Hub for Jupyter, Python scripts, browser Bash sessions, and vLLM inference.
- Runtime selection for Modal images, including Python 3.10, 3.11, 3.12, 3.13, 3.14, or a custom supported version.
- Docker Compose deployment on Modal with subprocess, VM, and sandbox multi-container modes.
- VS Code extension support for launching Hub workflows from the editor.
- Web hosting for ASGI, WSGI, and static sites with persistent Modal URLs.
- OpenAI-compatible LLM API serving with auth, streaming, warmup, logs, and metrics.
- Vision workflows for sample data generation, training, prediction, evaluation, and export.
- Multi-profile Modal account management, sessions tracking, stop commands, and billing reports.

## Installation

Requirements:

- Python 3.10 or newer.
- Modal credentials configured through `modal setup` or `m-gpux account add`.
- The `modal` CLI available on your PATH.

Install from PyPI:

```bash
pip install m-gpux
```

Install from source:

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux
pip install -e .
```

## Quick Start

```bash
# Add and inspect Modal profiles
m-gpux account add
m-gpux account list

# Launch the guided GPU hub
m-gpux hub

# Train a tiny vision demo
m-gpux vision sample-data
m-gpux vision train --dataset ./data/m-gpux-vision-sample

# Host a FastAPI app
m-gpux host asgi --entry main:app

# Analyze and deploy Docker Compose
m-gpux compose check
m-gpux compose up

# Deploy an OpenAI-compatible model endpoint
m-gpux serve deploy

# Review cost usage
m-gpux billing usage --days 30 --all
```

## Core Commands

### Accounts

```bash
m-gpux account list
m-gpux account add
m-gpux account switch <profile_name>
m-gpux account remove <profile_name>
```

Profiles are stored in `~/.modal.toml`. If the active profile is removed, another existing profile is promoted automatically.

### Interactive Hub

```bash
m-gpux hub
```

Hub guides you through profile selection, GPU or CPU selection, action selection, Python runtime selection, environment setup, file upload rules, generated script review, and launch.

Actions include:

- Jupyter Lab on selected Modal compute.
- Local Python script execution on remote GPUs.
- Browser Bash shell with a clean direct `bash` session and optional manual `tmux`.
- vLLM inference using a CUDA base image and the selected Python runtime.

The same Python runtime choice is preserved in generated scripts, session metadata, workload presets, and the VS Code Hub wizard.

### Docker Compose

```bash
m-gpux compose check
m-gpux compose up
m-gpux compose sync
```

Compose support can analyze services, ports, commands, environment variables, volumes, Dockerfiles, and `x-mgpux` metadata before generating Modal deployment code.

Deployment modes:

- `compose up`: runs supported services in a generated Modal app using subprocess orchestration.
- `compose vm up`: provisions a Modal GPU container for full-image or VM-style workloads such as Triton.
- `compose sandbox up`: runs Compose services as isolated Modal Sandboxes for true multi-container separation.

Sandbox commands:

```bash
m-gpux compose sandbox check
m-gpux compose sandbox up
m-gpux compose sandbox ps
m-gpux compose sandbox logs
m-gpux compose sandbox exec <service>
m-gpux compose sandbox down
```

Recent Compose improvements include Dockerfile `WORKDIR` detection, target-stage handling, BuildKit mount preprocessing for Modal builders, specialized Triton defaults, minimal image detection, dependency readiness checks, tunnel support, and service lifecycle helpers.

### Presets And Dev Shells

```bash
m-gpux dev
m-gpux preset create
m-gpux preset run <name>
```

Dev and preset flows now carry the selected Python runtime through saved workload metadata and regenerated Modal scripts. Existing presets default to Python 3.12 when no runtime has been saved.

### Web Hosting

```bash
m-gpux host asgi --entry main:app
m-gpux host wsgi --entry app:app
m-gpux host static --dir ./site
```

Hosting creates persistent Modal URLs for FastAPI, Starlette, Flask, Django, and static folders. Projects can auto-detect dependencies, upload local files, scale to zero, and optionally keep warm replicas.

### Model Serving

```bash
m-gpux serve deploy
m-gpux serve dashboard
m-gpux serve logs
m-gpux serve warmup
m-gpux serve stop
m-gpux serve keys create
m-gpux serve keys list
m-gpux serve keys show <name>
m-gpux serve keys revoke <name>
```

`serve` deploys Hugging Face models behind an OpenAI-compatible API with bearer-token auth, streaming and non-streaming chat completions, warmup, resilient proxying, logs, and a live metrics dashboard.

### Vision

```bash
m-gpux vision sample-data
m-gpux vision train
m-gpux vision predict
```

Vision workflows support local image-folder datasets, configurable TorchVision backbones, GPU selection, training knobs, checkpoints, metrics, evaluation reports, and ONNX or TorchScript export.

### Sessions, Billing, And Stop

```bash
m-gpux sessions list
m-gpux sessions open <id>
m-gpux billing open
m-gpux billing usage --days 7 --all
m-gpux stop
m-gpux stop --all
```

Use sessions to reopen generated app URLs, billing to inspect Modal usage, and stop to clean up running apps on one or all profiles.

## VS Code Extension

The `m-gpux-vscode` extension mirrors the Hub wizard in VS Code. It can launch Hub actions, inspect accounts, show billing usage, and generate Modal scripts from the current workspace. The Hub wizard now includes the same Python runtime picker as the CLI.

```bash
cd m-gpux-vscode
npm install
npm run compile
```

## Examples

Ready-to-deploy sample projects live in `examples/`:

| Example | Command | Description |
| --- | --- | --- |
| `examples/host-static` | `m-gpux host static --dir .` | Static HTML/CSS/JS site |
| `examples/host-asgi` | `m-gpux host asgi --entry main:app` | FastAPI app with health and demo endpoints |
| `examples/host-wsgi` | `m-gpux host wsgi --entry app:app` | Flask task board with REST CRUD API |

## Documentation

- Website: https://puxhocdl.github.io/m-gpux/
- Getting started: `docs/getting-started.md`
- Commands reference: `docs/commands.md`
- Compose guide: `docs/compose.md`
- Presets guide: `docs/presets.md`
- Sessions guide: `docs/sessions.md`
- FAQ: `docs/faq.md`

## Architecture

| Component | Responsibility |
| --- | --- |
| `m_gpux/main.py` | CLI entrypoint and plugin registration |
| `m_gpux/core/` | Shared console, UI, runner, metrics, state, profiles, and plugin helpers |
| `m_gpux/plugins/account/` | Modal profile CRUD and switching |
| `m_gpux/plugins/hub/` | Guided GPU runtime launcher |
| `m_gpux/plugins/compose/` | Compose analysis, subprocess mode, VM mode, sandbox mode, and sync |
| `m_gpux/plugins/dev/` | Browser shell development workflow |
| `m_gpux/plugins/preset/` | Workload preset creation and replay |
| `m_gpux/plugins/host/` | ASGI, WSGI, and static hosting |
| `m_gpux/plugins/serve/` | LLM serving, keys, logs, warmup, dashboard |
| `m_gpux/plugins/vision/` | Image classification data, training, prediction, and export |
| `m-gpux-vscode/` | VS Code extension |

## Troubleshooting

- `No configured Modal profiles found`: run `m-gpux account add`.
- `modal: command not found`: install Modal and make sure the CLI is on your PATH.
- `Script file does not exist in hub mode`: run from the script directory or pass the correct path.
- Compose deployment fails on a custom image: run `m-gpux compose check` or `m-gpux compose sandbox check` to inspect image, Dockerfile, ports, volumes, and command detection.

## Contributing

```bash
pip install -e .
python -m m_gpux.main --help
```

For VS Code changes:

```bash
cd m-gpux-vscode
npm install
npm run compile
```

## Release

Update versions in `pyproject.toml`, `m_gpux/__init__.py`, `m-gpux-vscode/package.json`, and `m-gpux-vscode/package-lock.json`, then tag and push:

```bash
git tag v<version>
git push origin main v<version>
```

The GitHub Actions publishing workflow builds and uploads the Python package from release tags.

## License

MIT
