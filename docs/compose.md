# Docker Compose

Use `m-gpux compose` when you already have a `docker-compose.yml` or `compose.yml` and want to run that stack on Modal without rewriting it into raw Modal code first.

## What `m-gpux` does

The compose workflow inspects your local Compose file, detects services, ports, environment variables, and common infrastructure images, then generates a temporary Modal script for review before launch.

There are two deployment modes:

| Mode | Command | Best for |
|---|---|---|
| **Subprocess mode** | `m-gpux compose up` | Typical app stacks where multiple services can run together inside one Modal container |
| **VM mode** | `m-gpux compose vm up` | Heavier or more Docker-native workloads such as Triton, custom base images, or multi-port services |

## Quick start

From the folder that contains your Compose file:

```bash
m-gpux compose check
m-gpux compose up
```

If you need the VM-oriented flow:

```bash
m-gpux compose vm check
m-gpux compose vm up
```

## Compose file discovery

If you do not pass `--file`, `m-gpux` looks for these names in the current directory:

- `docker-compose.yml`
- `docker-compose.yaml`
- `compose.yml`
- `compose.yaml`

You can also point to a specific file:

```bash
m-gpux compose check --file ./deploy/compose.prod.yml
```

## Commands

### `compose check`

```bash
m-gpux compose check
```

Analyzes the Compose file without deploying it. This is the fastest way to confirm detected services, tunnels, and environment references before you spend compute.

### `compose up`

```bash
m-gpux compose up
```

Runs the single-container workflow. `m-gpux` will:

1. Select or auto-pick a Modal profile.
2. Parse services, ports, commands, and known images.
3. Generate a Modal script that runs the services as managed subprocesses.
4. Attach a workspace volume so the project can be synced and reused.
5. Launch the Modal app in detached mode and track it locally as a session.

### `compose sync`

```bash
m-gpux compose sync
```

Watches local files and syncs changed content into the workspace volume used by a running compose deployment.

Use this when the stack is already up and you want to iterate on application code without redeploying from scratch.

### `compose vm check`

```bash
m-gpux compose vm check
```

Performs the same analysis as `compose check`, but from the VM deployment perspective. This is useful when you expect a full image workflow with tunneled ports or custom Dockerfile behavior.

### `compose vm up`

```bash
m-gpux compose vm up
```

Uses the VM-oriented generator. This is the right choice when your stack depends on image-level behavior that is awkward to flatten into the simpler subprocess flow.

## `x-mgpux` metadata

Compose files can include an `x-mgpux` block for release-specific overrides:

```yaml
x-mgpux:
  base_image: nvcr.io/nvidia/tritonserver:24.10-py3
  apt_packages:
    - ffmpeg
    - git
```

This lets you steer the generated Modal environment without abandoning the Compose file as your source of truth.

## Environment variables

`m-gpux compose` reads environment definitions from the Compose file and also surfaces referenced variables that are missing locally so you can fill them in before launch.

That makes it friendlier for stacks that rely on `.env` values, database credentials, or API keys.

## Good fits

- FastAPI or Flask app plus Redis/Postgres
- Inference services that expose one or more HTTP ports
- Local developer stacks you want to lift onto Modal quickly
- Triton or custom Dockerfile workloads that need VM mode

## Current limits

- Compose networking is adapted to Modal's execution model, so some multi-container assumptions are mapped into one-container or VM-oriented behavior.
- The generated Modal script is intentionally reviewable and editable, but not every Compose feature maps 1:1.
- For highly custom production infrastructure, you may still choose to turn the reviewed script into a hand-maintained Modal app later.
