# Compute Gateway

`m-gpux gateway` turns scripts in your project into an authenticated,
asynchronous HTTP API on Modal. You declare the tasks callers may run in
`mgpux.gateway.toml`; callers submit a JSON input, get a job ID back
immediately, and poll for the result. Each task runs in its own autoscaling
Modal Function (CPU or GPU), so a burst of jobs fans out across containers and
scales back to zero when idle.

```text
client ──POST /v1/jobs──▶ gateway (FastAPI, auth) ──spawn──▶ task-<name> Function ──▶ your command
       ◀── 202 {id} ─────┘
client ──GET /v1/jobs/{id}──▶ gateway ──FunctionCall.get(timeout=0)──▶ running │ succeeded │ failed │ expired
```

## Quick start

```bash
m-gpux gateway init          # writes mgpux.gateway.toml + mgpux_worker.py (a CPU echo task)
m-gpux gateway validate      # offline check of the manifest
m-gpux gateway deploy        # pick a profile (or AUTO), deploy, save URL + API key
m-gpux gateway submit echo --input '{"hello": "Modal"}' --wait
```

`deploy` prints the endpoint URL and saves it, with the API key, to
`~/.m-gpux/gateway.json`. Every other command reads that file.

## The manifest

```toml
[gateway]
name = "m-gpux-compute-gateway"   # Modal app name: lowercase, digits, dashes
source = "."                      # directory copied into /workspace of each task image
python_version = "3.12"           # 3.10 – 3.14
max_input_bytes = 1048576         # request body limit (≤ 10 MiB)
max_output_bytes = 1048576        # stdout / stderr kept per job (≤ 10 MiB)
exclude = [".git", ".venv", "node_modules"]

[tasks.echo]
description = "Verify the gateway with a cheap CPU JSON echo task."
command = ["python", "mgpux_worker.py"]
packages = []
cpu = 0.25
memory = 256          # MiB
timeout = 60          # seconds per attempt, 10 – 86400
retries = 1           # 0 – 10
max_containers = 10
scaledown_window = 30 # seconds a container stays warm after its last job

[tasks.inference]
command = ["python", "inference.py"]
packages = ["torch", "transformers"]
gpu = ["L4", "A10G"]  # a string, or a fallback list Modal tries in order
timeout = 900
max_containers = 5
```

Rules the validator enforces:

- `command` must be an **array**. It runs with `shell=False` in `/workspace`, so
  callers can never inject shell syntax; they only choose a declared task and
  pass JSON.
- Task names match `^[A-Za-z][A-Za-z0-9_-]{0,63}$`.
- Unknown values are rejected before anything reaches Modal.

## Writing a task

A task reads one JSON object from **stdin** (also available as the
`MGPUX_INPUT_JSON` environment variable) and writes its result to **stdout**.
JSON output is returned parsed; anything else is returned as a string.

```python
import json, sys

payload = json.load(sys.stdin)
json.dump({"ok": True, "echo": payload}, sys.stdout)
```

A non-zero exit marks the job `failed` (after any `retries`), with stderr in the
error message. Output beyond `max_output_bytes` is cut and flagged
`"truncated": true`.

## HTTP API

Send the key as `Authorization: Bearer <key>` or `X-API-Key: <key>`. Interactive
docs are served at `<url>/docs` (`m-gpux gateway open`).

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness check (no auth) |
| `GET /v1/tasks` | Declared tasks with description, GPU and timeout |
| `POST /v1/jobs` | Body `{"task": "...", "input": {...}}` → `202` with the job |
| `GET /v1/jobs/{id}` | `202` while running; `200` with the final job otherwise |
| `GET /v1/jobs/{id}/logs?limit=100` | Recent stdout, stderr and system log lines |
| `DELETE /v1/jobs/{id}` | Cancel a running job |

```bash
URL=https://<workspace>--m-gpux-compute-gateway-gateway.modal.run   # from `m-gpux gateway show`
KEY=$(m-gpux gateway key)
curl -s -X POST "$URL/v1/jobs" -H "Authorization: Bearer $KEY" \
     -H "Idempotency-Key: order-42" \
     -d '{"task": "echo", "input": {"n": 1}}'
```

### Job states

| Status | Meaning |
|---|---|
| `running` | Queued or executing |
| `succeeded` | `result` holds `output`, `stderr`, `exit_code`, `duration_ms`, `truncated` |
| `failed` | The command exited non-zero, raised, or exceeded its `timeout`; see `error` |
| `cancelled` | Cancelled through `DELETE` / `m-gpux gateway cancel` |
| `expired` | Modal keeps spawned results for **7 days**; the result is gone |

Job metadata lives in a Modal Dict (`<name>-jobs`), whose entries expire after 7
days without reads or writes. After that, `GET /v1/jobs/{id}` returns `404`, and
`m-gpux gateway jobs --refresh` marks the local copy `expired`.

### Idempotent submissions

Send an `Idempotency-Key` header (up to 200 characters) to make retries safe:
a repeat with the same key returns the original job with
`"idempotent_replay": true` instead of starting a second one.

## Security model

- Each deploy generates a fresh key and stores it in a **new Modal Secret**. The
  generated `modal_gateway.py` contains only the Secret's name, never the key,
  so the key does not appear in source, command lines or deploy logs. The
  previous Secret is deleted after a successful redeploy on the same profile.
- Keys are compared with `hmac.compare_digest`.
- Only jobs submitted through this gateway are visible; other FunctionCall IDs
  in the workspace return `404`.
- The gateway handlers use Modal's async (`.aio`) interface throughout, so one
  container serves up to 100 concurrent requests without blocking.

## Costs

The gateway container is CPU-only and scales to zero. Each task bills like any
Modal Function for the time it runs, plus `scaledown_window` of warm idle time.
Keep `max_containers` low on GPU tasks to cap spend; budgets set with
`m-gpux budget` apply to the profile you deploy to.

## Commands

See the [command reference](commands.md#gateway) for every option.
