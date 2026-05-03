# Dev Container Mode

`m-gpux dev` is the fastest path from a local folder to a persistent Modal-powered development environment.

It is designed for the workflow where you want a remote CPU/GPU box that still feels like your current project:

```bash
cd my-project
m-gpux dev
```

## What You Get

`m-gpux dev` creates a browser terminal with:

- direct `bash --login` for clean terminal rendering
- the current folder available at `/workspace`
- local files refreshed into `/workspace` on each launch
- a Modal Volume behind `/workspace`
- remote edits and outputs auto-committed roughly every 20 seconds
- session metadata saved locally for `m-gpux sessions`

## Local Files Win On Launch

When you launch a dev container, `m-gpux` uploads the current folder to `/workspace_seed`, then copies it into the Volume-backed `/workspace`.

Files with the same relative path are overwritten by your local copy. Remote-only files are left alone.

This means:

- editing `train.py` locally then relaunching uses the new `train.py`
- remote outputs such as `experiments/` or `checkpoints/` remain available
- you no longer need to delete individual Volume paths just to refresh code

## Pull Remote Work Back

The terminal prints the exact Volume name and pull command. It looks like:

```bash
modal volume get m-gpux-workspace-my-project-abc123abcd / ./m-gpux-workspace
```

Use this when you want to copy remote outputs back to local disk.

## Run From A Preset

If you often use the same GPU, packages, and excludes:

```bash
m-gpux dev --preset rl-a100
```

Create presets directly with `m-gpux preset create`, or save one when `m-gpux dev` asks at the end of the wizard.

## Good Fits

Use dev mode for:

- RL training loops
- quick GPU debugging
- dataset preprocessing on Modal CPU
- long-running terminal work
- experiments that produce remote artifacts

For short one-off scripts, `m-gpux hub` -> Run Python Script is still simpler.
