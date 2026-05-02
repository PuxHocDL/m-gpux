# Getting Started

This guide gets you from zero to running GPU workloads in under 5 minutes.

## Prerequisites

| Requirement | Why |
|---|---|
| Python 3.10+ | Runtime for the CLI |
| Modal account | You need `token_id` and `token_secret` — get them at [modal.com/settings](https://modal.com/settings) |
| `modal` CLI | Must be installed and available in PATH (`pip install modal`) |

## Install

### From PyPI (recommended)

```bash
pip install m-gpux
```

### From source (development)

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux
pip install -e .
```

Verify the install:

```bash
m-gpux --help
```

You should see the welcome screen with Quick Actions.

## Step 1: Add your first profile

```bash
m-gpux account add
```

You will be prompted for:

| Field | Description | Where to find it |
|---|---|---|
| **Profile name** | A label like `personal` or `work` | You choose this |
| **Token ID** | Modal API token ID | [modal.com/settings](https://modal.com/settings) → API Tokens |
| **Token Secret** | Modal API token secret | Same page, shown once at creation |

Profiles are stored in `~/.modal.toml`. You can add as many as you need.

## Step 2: Verify your profiles

```bash
m-gpux account list
```

You'll see a Rich table showing all configured profiles, with the active one marked.

## Step 3: Launch a GPU session

```bash
m-gpux hub
```

The interactive hub walks you through:

1. **Select a profile** (if multiple exist)
2. **Pick a GPU** — from T4 (16GB, cheapest) to B200 (latest gen)
3. **Pick an action**:
    - **Jupyter Lab** — opens a GPU-backed notebook in your browser
    - **Run Python script** — execute a local `.py` file on the GPU
    - **Web Bash shell** — interactive terminal in the browser
4. **Review the generated script** — the hub creates a transparent `modal_runner.py`
5. **Press Enter** to launch, or edit the script first

!!! info "What happens under the hood"
    The hub generates a Modal deployment script (`modal_runner.py`) with your chosen GPU and action, then runs `modal run modal_runner.py`. The script is fully editable — you can add pip packages, change timeouts, or customize the container image before launching.

!!! tip "Smooth browser terminal"
    The Web Bash shell now uses direct `bash` by default for smoother interaction, cleaner rendering, and fewer WebSocket heartbeat interruptions. `tmux` is still installed; run `tmux` manually when you want detachable sessions.

## Step 4: Check your costs

```bash
m-gpux billing usage --days 30 --all
```

This aggregates usage across all your configured profiles for the last 30 days.

To open the Modal billing dashboard in your browser:

```bash
m-gpux billing open
```

---

## Deploy an LLM API

Turn any HuggingFace model into a production OpenAI-compatible API with authentication.

### 1. Create an API key

```bash
m-gpux serve keys create --name my-key
```

This generates a `sk-mgpux-...` key and stores it in `~/.m-gpux/api_keys.json`.

!!! warning "Save your key"
    You can always retrieve it later with `m-gpux serve keys show my-key`, but treat it like a password.

### 2. Deploy with the interactive wizard

```bash
m-gpux serve deploy
```

The 5-step wizard guides you through:

| Step | What you choose | Default |
|---|---|---|
| 1. Model | 11 presets or custom HuggingFace ID | `Qwen/Qwen2.5-7B-Instruct` |
| 2. GPU | T4 through B200 | Based on model size |
| 3. Context length | Max tokens (lower = less VRAM) | `4096` |
| 4. Keep warm | `0` = scale-to-zero, `1` = always on | `1` |
| 5. API key | Select existing or auto-create | First active key |

After confirmation, `m-gpux` deploys a Modal app with:

- **Auth proxy** (FastAPI on port 8000) — validates Bearer tokens, returns 401/403 for invalid auth
- **vLLM backend** (port 8001) — serves the model with OpenAI-compatible API
- **Shared caches** — HuggingFace and vLLM model weights persist in Modal Volumes

### 3. Test your endpoint

```bash
# Health check (no auth required)
curl https://<workspace>--m-gpux-llm-api-serve.modal.run/health

# List models (requires auth)
curl https://<workspace>--m-gpux-llm-api-serve.modal.run/v1/models \
  -H "Authorization: Bearer sk-mgpux-..."

# Chat completion
curl https://<workspace>--m-gpux-llm-api-serve.modal.run/v1/chat/completions \
  -H "Authorization: Bearer sk-mgpux-..." \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-7B-Instruct", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### 4. Use with OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<workspace>--m-gpux-llm-api-serve.modal.run/v1",
    api_key="sk-mgpux-...",
)

# Non-streaming
response = client.chat.completions.create(
    model="Qwen/Qwen2.5-7B-Instruct",
    messages=[{"role": "user", "content": "Explain quantum computing in 3 sentences."}],
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="Qwen/Qwen2.5-7B-Instruct",
    messages=[{"role": "user", "content": "Write a haiku about GPUs."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### 5. Warm up the server

If you set `keep_warm=0` (scale-to-zero), the first request triggers a cold start (~3-5 min). Pre-warm it:

```bash
m-gpux serve warmup --url https://<workspace>--m-gpux-llm-api-serve.modal.run
```

### 6. Stop when done

```bash
m-gpux serve stop       # stop the LLM API server
m-gpux stop --all       # stop ALL running m-gpux apps across profiles
```

---

## Typical daily workflow

```
┌─ Morning ───────────────────────────────────┐
│  m-gpux account switch work                 │
│  m-gpux hub → Jupyter on A100               │
│  ... train / experiment ...                 │
├─ Afternoon ─────────────────────────────────┤
│  m-gpux serve deploy → API for team         │
│  m-gpux billing usage --days 1              │
├─ Evening ───────────────────────────────────┤
│  m-gpux stop --all                          │
│  m-gpux billing usage --days 1 --all        │
└─────────────────────────────────────────────┘
```
