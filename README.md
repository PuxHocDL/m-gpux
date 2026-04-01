# m-gpux

A modern command-line toolkit for Modal workflows:

- Manage multiple Modal profiles
- Launch GPU workloads from an interactive hub
- Track cost usage across accounts

`m-gpux` is built with Typer + Rich for a smooth CLI UX inspired by popular tools.

## Why m-gpux

- Fast setup for GPU sessions (Jupyter, script runner, web shell)
- Multi-profile account management in one place
- Billing visibility for one account or all configured profiles
- Human-friendly command output with interactive prompts

## Installation

### Requirements

- Python 3.10+
- A Modal account with `token_id` and `token_secret`
- Modal CLI available in your shell (`modal` command)

### Install from source

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux
pip install -e .
```

## Quick Start

### 1) Add a profile

```bash
m-gpux account add
```

### 2) Verify profiles

```bash
m-gpux account list
```

### 3) Launch GPU hub

```bash
m-gpux hub
```

### 4) Check billing usage

```bash
m-gpux billing usage --days 30 --all
```

## Command Overview

### Global

```bash
m-gpux --help
m-gpux info
```

### Account commands

```bash
m-gpux account list
m-gpux account add
m-gpux account switch <profile_name>
m-gpux account remove <profile_name>
```

### Billing commands

```bash
m-gpux billing open
m-gpux billing usage
m-gpux billing usage --days 7
m-gpux billing usage --account personal
m-gpux billing usage --all
```

### Compute hub

```bash
m-gpux hub
```

From the hub, choose:

- Jupyter Lab on a selected GPU
- Run a local Python script on a selected GPU
- Interactive web-based Bash shell on a selected GPU

## Configuration

Profiles are stored locally in:

- `~/.modal.toml`

When multiple profiles exist, exactly one can be active. The `hub` workflow uses the active profile credentials.

## Example Workflows

### Run a script on A100

1. Run `m-gpux hub`
2. Select GPU `A100`
3. Select action `Run a Python Script`
4. Enter your script filename
5. Confirm and execute generated `modal_runner.py`

### Audit weekly cost across all profiles

```bash
m-gpux billing usage --days 7 --all
```

## Documentation

Detailed docs are available in the GitHub `docs` section:

- [Documentation Home](docs/index.md)
- [Getting Started](docs/getting-started.md)
- [Command Reference](docs/commands.md)
- [FAQ and Troubleshooting](docs/faq.md)

## Troubleshooting

- `No configured Modal profiles found`
	- Run `m-gpux account add` first.
- `modal: command not found`
	- Install Modal CLI and ensure it is available in your shell.
- Script file not found in hub mode
	- Check filename/path and run from the project directory containing your script.

## Development

```bash
pip install -e .
python -m m_gpux.main --help
```

## License

MIT (or project owner's preferred license).
