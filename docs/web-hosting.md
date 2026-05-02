# Web Hosting

`m-gpux host` lets us deploy regular web apps on Modal without writing the full deployment boilerplate by hand. It covers three common targets:

- `asgi` for FastAPI, Starlette, Quart, or any ASGI app
- `wsgi` for Flask, Django, or any WSGI app
- `static` for plain HTML, CSS, and JavaScript folders

Unlike short-lived compute jobs, a deployed web endpoint keeps the public URL alive while Modal recycles containers behind the scenes. That means we can scale to zero for cost savings or keep one warm replica alive for low-latency production traffic.

## Before You Start

Have these ready before running the wizard:

1. A working local app or static folder
2. A correct entry path such as `main:app` or `project.wsgi:application`
3. Any required Python dependencies
4. A Modal profile already configured with `m-gpux account add`

If the app does not run locally first, deployment debugging becomes much harder. The easiest path is:

1. Run the app locally
2. Confirm the correct entry point
3. Confirm `requirements.txt` is accurate
4. Then run `m-gpux host ...`

## Quick Start

```bash
m-gpux host asgi --entry main:app
m-gpux host wsgi --entry app:app
m-gpux host static --dir ./site
```

Each subcommand opens a guided flow that asks for:

1. Modal profile
2. App name
3. CPU or GPU compute
4. Python dependencies or `requirements.txt`
5. Upload exclude patterns
6. Warm replica strategy
7. Deploy mode: persistent `deploy` or one-off `run`

<figure class="doc-figure">
  <img src="assets/host-deploy-flow.svg" alt="m-gpux host deployment flow">
  <figcaption>All hosting targets share the same generate, review, and deploy path.</figcaption>
</figure>

## Command Map

```bash
m-gpux host asgi --entry main:app
m-gpux host wsgi --entry app:app
m-gpux host static --dir ./site
```

Use this rule of thumb:

- choose `asgi` when your framework speaks ASGI natively
- choose `wsgi` when your framework exposes a classic WSGI app object
- choose `static` when you only need to serve files

## How It Works

The host plugin generates a `modal_runner.py` file, shows it for review, and then either:

- runs `modal deploy modal_runner.py` for a long-lived public URL
- runs `modal run modal_runner.py` for a temporary test session

The generated app name follows the pattern `m-gpux-host-<slug>`.

!!! info "Persistent vs temporary"
    Choose `deploy` when you want a stable Modal URL that stays online until you stop it. Choose `run` when you just want to validate the app quickly.

### What you review before launch

Before Modal executes anything, the plugin shows the generated `modal_runner.py`.

That review step is important because it lets you catch:

- the wrong app entry
- missing dependencies
- the wrong upload root
- compute settings that do not match your workload

If something looks off, edit the script first and then continue.

## Supported Targets

### ASGI

Use `m-gpux host asgi` when your app exposes an ASGI object such as:

```python
from fastapi import FastAPI

app = FastAPI()
```

Example:

```bash
m-gpux host asgi --entry main:app
```

What the entry means:

- `main` is the Python module
- `app` is the variable inside that module

Common examples:

- `main:app` for FastAPI
- `server:app` for Starlette
- `project.asgi:application` for Django ASGI

Example Django ASGI command:

```bash
m-gpux host asgi --entry project.asgi:application
```

### WSGI

Use `m-gpux host wsgi` for frameworks that expose a WSGI app object:

```python
from flask import Flask

app = Flask(__name__)
```

Example:

```bash
m-gpux host wsgi --entry app:app
```

Common examples:

- `app:app` for Flask
- `project.wsgi:application` for Django WSGI

Example Django WSGI command:

```bash
m-gpux host wsgi --entry project.wsgi:application
```

### Static

Use `m-gpux host static` to serve a directory directly with Python's built-in `http.server`.

Example:

```bash
m-gpux host static --dir ./site
```

This is a good fit for:

- landing pages
- documentation exports
- dashboards built as plain HTML/CSS/JS
- frontend prototypes

It is not the right choice when:

- you need server-side routes or API logic
- you need authentication handled by your Python app
- your frontend must call local backend code inside the same process

## Compute Choices

The host flow supports both CPU and GPU:

- CPU is the default and is the right choice for most web apps
- GPU is useful when the endpoint itself runs inference or media workloads

Examples:

- FastAPI + REST API: CPU
- Flask admin tool: CPU
- FastAPI + PyTorch image generation: GPU

### CPU hosting

Choose CPU when:

- your app is mostly routing, JSON, forms, or dashboards
- inference happens elsewhere
- startup speed and cost matter more than raw compute

### GPU hosting

Choose GPU when:

- the request handler itself loads a model
- you run image, audio, or video inference inside the app
- the app must serve GPU-backed endpoints directly

The compute picker maps to Modal function settings such as:

- `cpu=<cores>, memory=<mb>` for CPU hosting
- `gpu="<type>"` for GPU hosting

## Dependencies

For ASGI and WSGI apps, `m-gpux host` can install dependencies in two ways:

- If `requirements.txt` exists, it offers to install from that file
- Otherwise, it asks for a comma-separated package list

Static hosting does not install Python dependencies because it only serves files.

!!! tip "Framework packages"
    For FastAPI, include packages like `fastapi` and `uvicorn`. For Flask, include `flask`. If your app imports anything extra, it needs to be part of the deployment image too.

### Dependency examples

FastAPI:

```text
fastapi,uvicorn
```

Flask:

```text
flask
```

Django:

```text
django
```

## Upload Behavior

The command uploads the selected project directory into the Modal container:

- ASGI and WSGI apps are uploaded to `/app`
- Static sites are uploaded to `/site`

Default exclude patterns:

```text
.venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox,dist,build
```

You can change these interactively before launch.

### What should usually be excluded

Usually exclude:

- local virtual environments
- Git history
- Python caches
- build output
- large frontend dependency folders that are rebuilt elsewhere

Be careful not to exclude:

- templates
- static assets your app needs
- `.env`-style config files if your app truly depends on local file reads

## Warm Replicas

The wizard asks whether to keep one replica warm:

- `Auto-scale to 0` means the app goes idle when unused and may cold start later
- `Keep 1 warm` sets `min_containers=1` to reduce latency

This is one of the most important production knobs:

- Use scale-to-zero for personal tools, demos, and low-traffic apps
- Use one warm container for public endpoints or internal apps that need faster first-byte response

### Latency tradeoff

Scale-to-zero saves money, but the first request after idle time may wait for container startup. Keeping one warm container costs more, but avoids that cold-start path for most traffic.

## Deploy Modes

### Deploy

`deploy` is for real hosting.

Behavior:

- writes `modal_runner.py`
- lets you inspect or edit it
- runs `modal deploy`
- leaves the service online until stopped

### Run

`run` is for testing.

Behavior:

- executes the generated script immediately
- useful for quick validation
- not the right choice for a stable production URL

### Expected URL shape

When you choose `deploy`, Modal returns a public URL that typically looks like:

```text
https://<workspace>--m-gpux-host-<name>.modal.run
```

The exact hostname is assigned by Modal, but the app name and workspace are reflected in it.

## Generated Templates

The plugin uses three Modal patterns under the hood:

- `@modal.asgi_app()` for ASGI targets
- `@modal.wsgi_app()` for WSGI targets
- `@modal.web_server()` for static hosting

All generated functions use:

- `timeout=86400`
- `scaledown_window=300`
- `min_containers` from the warm-replica choice
- `@modal.concurrent(max_inputs=100)`

### Why these defaults exist

- `timeout=86400` avoids accidental early termination for long-lived services
- `scaledown_window=300` gives the container a short grace period before scaling down
- `max_inputs=100` allows the service to accept multiple concurrent requests without forcing a one-request-only model

## Project Layout Examples

### FastAPI

```text
my-api/
  main.py
  requirements.txt
```

Run:

```bash
cd my-api
m-gpux host asgi --entry main:app
```

### Flask

```text
my-flask-app/
  app.py
  requirements.txt
```

Run:

```bash
cd my-flask-app
m-gpux host wsgi --entry app:app
```

### Static Site

```text
my-site/
  index.html
  style.css
  app.js
```

Run:

```bash
cd my-site
m-gpux host static --dir .
```

## Operating The Deployment

After deploy, common next steps are:

```bash
m-gpux stop
modal app list
modal logs m-gpux-host-my-app
```

Use `m-gpux stop` when you want a guided stop flow. Use `modal` directly if you want deeper inspection.

## Example Projects In This Repository

The repository already includes ready-to-deploy examples:

- `examples/host-asgi`
- `examples/host-wsgi`
- `examples/host-static`

These are useful when you want to test the hosting flow end to end before deploying your own app.

## Common Commands

```bash
m-gpux host asgi --entry main:app
m-gpux host wsgi --entry app:app
m-gpux host static --dir ./site
m-gpux stop
```

Use `m-gpux stop` to shut down a deployment later.

## Troubleshooting

### Import errors on startup

Usually means the generated image is missing a dependency. Check:

- `requirements.txt`
- manually entered pip packages
- the entry path such as `main:app`

Also check whether your project expects a package layout that only works when launched from a different working directory.

### Static site loads but assets 404

Usually means:

- the wrong directory was passed to `--dir`
- asset paths inside `index.html` are incorrect
- files were excluded by the upload pattern list

For static sites, verify that relative paths inside `index.html` still make sense when the site root is the uploaded folder itself.

### Cold starts feel slow

Use `Keep 1 warm` during the hosting flow so the deployment keeps one live replica.

### App works locally but not on Modal

Review the generated `modal_runner.py` and compare:

- Python module path
- app variable name
- dependency installation
- uploaded directory root

That preview step is there so we can catch mismatches before deployment.

### I need a reproducible production setup

For production, the safest pattern is:

1. keep a real `requirements.txt`
2. use explicit app entry paths
3. choose `deploy`
4. keep one warm replica if latency matters
5. store the reviewed `modal_runner.py` or copy its settings into your own permanent deployment script later
