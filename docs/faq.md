# FAQ and Troubleshooting

## Installation & Setup

### Where are profiles stored?

Profiles are stored in `~/.modal.toml`. Each profile contains a `token_id` and `token_secret`.

### Where are API keys stored?

API keys for `m-gpux serve` are stored in `~/.m-gpux/api_keys.json`. This file is local-only and not synced to Modal.

### What Python versions are supported?

Python 3.10, 3.11, and 3.12 are supported. Python 3.13+ may work but is not officially tested.

---

## Profile & Account Issues

### "No configured Modal profiles found"

You haven't added any profiles yet:

```bash
m-gpux account add
```

Then verify:

```bash
m-gpux account list
```

### I cannot switch to a profile

Ensure the profile exists first:

```bash
m-gpux account list
m-gpux account switch <profile_name>
```

If the profile name has a typo, `account list` will show the correct names.

### `modal: command not found`

The Modal CLI is not installed or not in your PATH:

```bash
pip install modal
modal --version
```

On Windows, ensure the Python Scripts folder is in your PATH.

---

## Hub Issues

### Script file does not exist

Ensure you run `m-gpux hub` from the folder containing your script, or provide the correct filename when prompted. The hub looks in the current working directory.

### Hub session times out

Modal has a configurable timeout (default 24 hours). For long-running sessions, you can edit the generated `modal_runner.py` and increase the `timeout` parameter before pressing Enter.

### Web Bash terminal feels jittery

The Web Bash shell is tuned for a VS Code-like experience: direct `bash`, a simple prompt, no default `tmux` wrapper, a longer `ttyd` WebSocket ping interval, and a 10,000-line browser scrollback. If you need detachable sessions, run `tmux` manually from inside the shell.

### I cannot scroll in the Web Bash terminal

Use the mouse wheel or trackpad inside the terminal area. The terminal keeps 10,000 lines of browser scrollback and uses smooth wheel scrolling. If you start `tmux`, scrolling changes to tmux copy-mode behavior; press `Ctrl+b` then `[` or use tmux mouse mode to browse older output.

### Files I create in Hub do not appear on my local machine

Hub sessions mount `/workspace` on a Modal Volume and auto-commit changes roughly every 20 seconds for Jupyter, Web Bash, and interactive terminals. On each new launch, your current local workspace is copied into `/workspace` and overwrites files with the same relative path, so local code edits take effect without deleting remote-only outputs such as `experiments/`.

Because detached Modal jobs cannot directly write back to your local disk, pull the saved workspace when you need it:

```bash
modal volume get <sync-volume-name> / ./m-gpux-workspace
```

The terminal prints the exact sync volume name and pull command when it starts.

### Can I install custom pip packages?

Yes. Before pressing Enter, edit the generated `modal_runner.py` and add packages to the `.pip_install()` call:

```python
image = modal.Image.debian_slim().pip_install(
    "jupyter", "numpy", "pandas", "scikit-learn", "my-package"
)
```

---

## LLM API Server (serve) Issues

### Cold start takes too long (~5 minutes)

This is normal for scale-to-zero deployments. Two solutions:

1. **Keep warm** - set `min_containers=1` during deploy (Step 4). This keeps one container always running (~0.9s response time), but costs GPU time even when idle.
2. **Pre-warm** - run `m-gpux serve warmup` before sending real traffic.

### First deploy is very slow (10-15 min)

The first deployment downloads model weights from HuggingFace to a Modal Volume. Subsequent deploys reuse the cached weights and are much faster (~1-3 min).

### 401 Unauthorized

You're missing the `Authorization` header:

```bash
curl https://your-endpoint/v1/models \
  -H "Authorization: Bearer sk-mgpux-..."
```

### 403 Forbidden

Your API key is invalid. Check your key:

```bash
m-gpux serve keys list    # see all keys
m-gpux serve keys show <name>   # reveal full key
```

If the key was revoked, create a new one and redeploy.

### 503 Model is still loading

The vLLM backend hasn't finished loading the model yet. Wait 1-2 minutes after cold start and retry. You can check readiness via:

```bash
curl https://your-endpoint/health
# {"status": "ok", "vllm_ready": true}   ← ready
# {"status": "ok", "vllm_ready": false}  ← still loading
```

### How do I change the model after deploying?

Run `m-gpux serve deploy` again. Each deployment overwrites the previous one. Your cached model weights are preserved in shared Volumes.

### Can I use this as a drop-in for OpenAI / OpenRouter?

Yes. The endpoint supports the same `/v1/chat/completions` and `/v1/models` routes. Any client that works with OpenAI (Python SDK, LangChain, LlamaIndex, Aider, Continue, etc.) works with m-gpux by changing `base_url` and `api_key`.

### How do I use streaming?

Set `stream: true` in your request body:

```bash
curl https://your-endpoint/v1/chat/completions \
  -H "Authorization: Bearer sk-mgpux-..." \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen3-8B", "messages": [{"role":"user","content":"Hi"}], "stream": true}'
```

Or with the OpenAI Python SDK:

```python
stream = client.chat.completions.create(
    model="Qwen/Qwen3-8B",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### I revoked a key but it still works

Key revocation is local-only. You must redeploy to propagate the change:

```bash
m-gpux serve keys revoke old-key
m-gpux serve deploy    # redeploy with updated keys
```

---

## Billing Issues

### `billing usage` fails for one account

Possible causes:

- Invalid or expired token for that profile
- Network / Modal API issues
- Profile credentials were rotated on Modal dashboard

Fix: update credentials with `m-gpux account add` using the same profile name.

### How accurate is billing data?

`m-gpux billing usage` queries the Modal API directly. The data matches what you see on [modal.com/usage](https://modal.com/usage).

---

## Stopping & Cleanup

### How do I stop everything?

```bash
m-gpux stop --all
```

This scans all configured profiles, lists every running m-gpux app, and lets you stop them individually or all at once.

### Does stopping release the GPU immediately?

Yes. When you stop an app, the container is terminated and the GPU is released. You stop being charged immediately.

### I stopped the server but the endpoint still responds

Modal may cache the endpoint for a few seconds after stopping. Wait 10-30 seconds and try again. The endpoint will return 404 once fully stopped.
