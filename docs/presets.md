# Workload Presets

Presets let you save repeatable workload choices so you do not rebuild the same launch config every day.

```bash
m-gpux preset create
m-gpux preset run rl-a100
```

Hub and `m-gpux dev` also ask whether you want to save a preset after you configure a workload.

## What A Preset Stores

A preset can store:

- action (`bash`, `dev`, `jupyter`, or `interactive`)
- Modal profile
- compute configuration
- pip dependency setup
- upload exclude patterns

Presets are stored locally in:

```text
~/.m-gpux/presets.json
```

## Commands

```bash
m-gpux preset list
m-gpux preset show <name>
m-gpux preset run <name>
m-gpux preset delete <name>
```

## Example

Create a preset:

```bash
m-gpux preset create
```

Run it from any project folder:

```bash
m-gpux preset run rl-a100
```

Run it through dev mode:

```bash
m-gpux dev --preset rl-a100
```

## Recommended Presets

Useful presets to keep around:

- `rl-a100` for reinforcement learning experiments
- `debug-cpu` for cheap CPU-only debugging
- `vision-l4` for image-classification work
- `shell-h100` for short high-end GPU debugging
