# m-gpux Documentation

Welcome to the official docs for **m-gpux** — a production-focused CLI toolkit for Modal GPU operations.

> One CLI to manage profiles, launch GPU runtimes, deploy LLM APIs, and track cloud costs.

## What is m-gpux?

`m-gpux` turns Modal's serverless GPU platform into a streamlined developer experience:

| Capability | Description |
|---|---|
| **Multi-profile management** | Add, switch, and remove Modal identities — all stored in `~/.modal.toml` |
| **Interactive GPU Hub** | Guided wizard to launch Jupyter Lab, run Python scripts, or open a web shell on any GPU (T4 → B200) |
| **LLM API Server** | Deploy any HuggingFace model as an OpenAI-compatible endpoint with Bearer token auth, streaming, and warm containers |
| **API Key Management** | Create, list, show, and revoke `sk-mgpux-*` keys — stored locally in `~/.m-gpux/api_keys.json` |
| **Billing Dashboard** | Inspect 7/30/90-day usage per profile or aggregated across all accounts |
| **GPU Metrics Probe** | Live hardware utilization (GPU %, VRAM, temperature) on running containers |
| **App Lifecycle** | Stop any running m-gpux app (Jupyter, shells, LLM servers) from one command |

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
| [Architecture](architecture.md) | How m-gpux works internally — proxy layer, template generation, profile resolution |
| [FAQ & Troubleshooting](faq.md) | Common errors and how to fix them |

## Common Workflows

### 1. Launch Jupyter on a GPU

```bash
m-gpux account add          # one-time setup
m-gpux hub                  # pick GPU → pick Jupyter → launch
```

The hub generates a `modal_runner.py` script, shows it for review, then executes `modal run` to start a GPU-backed Jupyter Lab with a public URL.

### 2. Deploy an LLM as an OpenAI-compatible API

```bash
m-gpux serve keys create --name prod     # generate API key
m-gpux serve deploy                      # 6-step wizard
```

The wizard walks through:

1. **Model** — 11 presets (Qwen, Llama, Gemma, Mistral, DeepSeek, Phi) or custom HuggingFace ID
2. **GPU** — T4, L4, A10G, L40S, A100, A100-80GB, H100, H200, B200
3. **Context length** — max sequence length (lower = faster startup)
3.5. **Engine tuning** — GPU memory utilization, max concurrent sequences, tensor parallel size
4. **Keep warm** — `0` scales to zero (saves cost), `1+` keeps container(s) always running (no cold start)
5. **API key** — pick an existing key or auto-create one

After deploy, monitor your server with the live dashboard:

```bash
m-gpux serve dashboard
```

Your endpoint is a drop-in replacement for OpenAI / OpenRouter:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<workspace>--m-gpux-llm-api-serve.modal.run/v1",
    api_key="sk-mgpux-...",
)
resp = client.chat.completions.create(
    model="Qwen/Qwen3-8B",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in resp:
    print(chunk.choices[0].delta.content or "", end="")
```

### 3. Check costs across all accounts

```bash
m-gpux billing usage --days 7 --all
```

Aggregates compute spend from every configured profile into a single Rich table.

### 4. Stop running apps and release GPUs

```bash
m-gpux stop --all       # scan ALL profiles, pick which to stop
m-gpux serve stop       # stop only the LLM API server
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
| 12 | B200 | — | Blackwell architecture |
| 13 | B200+ | — | B200 reserved (guaranteed) |

## Model Presets (serve deploy)

| # | Model | Size | Recommended GPU |
|---|---|---|---|
| 1 | `Qwen/Qwen2.5-1.5B-Instruct` | 1.5B | T4 / L4 |
| 2 | `Qwen/Qwen2.5-7B-Instruct` | 7B | A10G |
| 3 | `Qwen/Qwen3-8B` | 8B | A10G |
| 4 | `Qwen/Qwen3.5-35B-A3B` | 35B MoE | A100-80GB |
| 5 | `meta-llama/Llama-3.1-8B-Instruct` | 8B | A10G |
| 6 | `google/gemma-2-9b-it` | 9B | A10G |
| 7 | `mistralai/Mistral-7B-Instruct-v0.3` | 7B | A10G |
| 8 | `Qwen/Qwen2.5-72B-Instruct-AWQ` | 72B AWQ | A100-80GB |
| 9 | `meta-llama/Llama-3.1-70B-Instruct` | 70B | H100 |
| 10 | `deepseek-ai/DeepSeek-V2-Lite-Chat` | 16B | A100 |
| 11 | `microsoft/Phi-3-medium-4k-instruct` | 14B | A10G |

Select **0** during the wizard to enter any custom HuggingFace model ID.

## Links

- **PyPI**: [pypi.org/project/m-gpux](https://pypi.org/project/m-gpux/)
- **Repository**: [github.com/PuxHocDL/m-gpux](https://github.com/PuxHocDL/m-gpux)
- **Issues**: [github.com/PuxHocDL/m-gpux/issues](https://github.com/PuxHocDL/m-gpux/issues)
- **Modal docs**: [modal.com/docs](https://modal.com/docs)
