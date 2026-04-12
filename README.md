# m-gpux

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![CLI](https://img.shields.io/badge/interface-Typer%20%2B%20Rich-0ea5e9)](https://typer.tiangolo.com/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-22c55e)](https://puxhocdl.github.io/m-gpux/)

`m-gpux` is a professional CLI toolkit for Modal power users who need fast GPU access, multi-profile account control, and simple cost visibility.

## Highlights

- **LLM API Server** — Deploy any HuggingFace model as an OpenAI-compatible endpoint with API key auth
- Interactive GPU hub for Jupyter, script execution, and web shell sessions
- Multi-account profile management in one command namespace
- Billing inspection per profile or across all configured accounts
- Friendly terminal UX with rich tables, prompts, and guided flows

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Commands](#core-commands)
- [Documentation](#documentation)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Installation

### Requirements

- Python 3.10+
- Modal account credentials (`token_id`, `token_secret`)
- Modal CLI in PATH (`modal` command)

### Install from source

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux
pip install -e .
```

### Install from PyPI

```bash
pip install m-gpux
```

## Quick Start

```bash
# 1) Add your first profile
m-gpux account add

# 2) Check configured profiles
m-gpux account list

# 3) Launch the interactive GPU hub
m-gpux hub

# 4) Deploy an LLM as an OpenAI-compatible API
m-gpux serve deploy

# 5) Inspect 30-day usage across all accounts
m-gpux billing usage --days 30 --all
```

## Core Commands

### Global

```bash
m-gpux --help
m-gpux info
```

### Profile Management

```bash
m-gpux account list
m-gpux account add
m-gpux account switch <profile_name>
m-gpux account remove <profile_name>
```

### Billing

```bash
m-gpux billing open
m-gpux billing usage --days 7
m-gpux billing usage --account personal
m-gpux billing usage --all
```

### Interactive Hub

```bash
m-gpux hub
```

Hub actions:

- Jupyter Lab on selected GPU
- Run local Python script on selected GPU
- Interactive web Bash shell on selected GPU

### LLM API Server

```bash
# Create an API key
m-gpux serve keys create

# Deploy a model (interactive wizard)
m-gpux serve deploy

# Check warm status
m-gpux serve warmup

# Stop the server
m-gpux serve stop
```

Deploy any HuggingFace model as an OpenAI-compatible API with:

- Bearer token authentication (401/403)
- Streaming & non-streaming chat completions
- Configurable GPU, context length, and keep-warm containers
- 11 popular model presets (Qwen, Llama, Gemma, Phi, etc.)

### API Key Management

```bash
m-gpux serve keys create        # Generate a new key
m-gpux serve keys list          # List all keys (masked)
m-gpux serve keys show <name>   # Reveal full key value
m-gpux serve keys revoke <name> # Revoke a key
```

### Stop Running Apps

```bash
m-gpux stop          # Stop apps on current profile
m-gpux stop --all    # Stop apps across ALL profiles
```

## Documentation

- Website: https://puxhocdl.github.io/m-gpux/
- Local docs index: [docs/index.md](docs/index.md)
- Getting started: [docs/getting-started.md](docs/getting-started.md)
- Commands: [docs/commands.md](docs/commands.md)
- FAQ: [docs/faq.md](docs/faq.md)

## Architecture

- `m_gpux/main.py`: CLI entrypoint and command registration
- `m_gpux/commands/account.py`: profile CRUD and active profile switching
- `m_gpux/commands/billing.py`: usage aggregation and billing dashboard links
- `m_gpux/commands/hub.py`: guided GPU runtime launcher
- `m_gpux/commands/serve.py`: LLM API deployment, auth proxy, API key management
- `m_gpux/commands/load.py`: live GPU hardware metrics probe

## Configuration

Modal profiles are persisted in `~/.modal.toml`.

If the active profile is removed, another existing profile is promoted automatically.

## Troubleshooting

- `No configured Modal profiles found`
  - Run `m-gpux account add`.
- `modal: command not found`
  - Install Modal CLI and ensure PATH is set correctly.
- Script file does not exist in hub mode
  - Run command from the script directory or provide the correct filename.

## Contributing

```bash
pip install -e .
python -m m_gpux.main --help
```

Open PRs are welcome for UX polish, command improvements, and docs quality.

## Release to PyPI

The repository includes automated PyPI publishing via GitHub Actions.

1. Configure a Trusted Publisher on PyPI with:
  - Project: `m-gpux`
  - Owner: `PuxHocDL`
  - Repository: `m-gpux`
  - Workflow: `publish-pypi.yml`
  - Environment: `pypi`
2. Create GitHub environment `pypi` in repository settings.
3. Bump `version` in `pyproject.toml`.
4. Create and push a version tag:

```bash
git tag v1.0.8
git push origin v1.0.8
```

The workflow `Publish Python Package` will build and publish automatically with OIDC.

## License

MIT
