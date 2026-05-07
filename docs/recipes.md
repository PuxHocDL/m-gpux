# Recipes

These recipes show how the main product flows fit together.

## Remote GPU Devbox

```bash
cd my-project
m-gpux dev
```

Choose your profile, compute, dependencies, and excludes. Save a preset when prompted if you expect to reuse the setup.

Later:

```bash
m-gpux sessions list
m-gpux sessions pull <session-id> --to ./m-gpux-workspace
m-gpux sessions stop <session-id>
```

## RL Training Loop

```bash
m-gpux dev
python train_lamarckian_rl.py
```

On the next launch, local code edits overwrite matching files in the Volume, while remote-only folders such as `experiments/` remain.

## Reusable Preset

```bash
m-gpux preset create
m-gpux preset run rl-a100
```

Use this when you repeatedly select the same GPU, dependency setup, and exclude patterns.

## Web App Hosting

```bash
m-gpux host asgi --entry main:app
```

Use `host` for FastAPI, Flask, Django, or static sites when you want a stable Modal URL.

## Compose Stack On Modal

```bash
cd my-compose-project
m-gpux compose check
m-gpux compose up
```

When the stack needs fuller image semantics or multiple tunneled ports:

```bash
m-gpux compose vm check
m-gpux compose vm up
```

If you keep iterating on the code after launch:

```bash
m-gpux compose sync
```

## Recover Remote Files

If you created files inside a Hub/dev terminal:

```bash
m-gpux sessions list
m-gpux sessions pull <session-id> --to ./remote-output
```

If you only know the Volume name:

```bash
modal volume get <volume-name> / ./remote-output
```
