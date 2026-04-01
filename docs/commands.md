# Command Reference

Use `m-gpux --help` for global help at any time.

## Global

```bash
m-gpux --help
m-gpux info
```

## account

Manage local Modal profiles.

### list

```bash
m-gpux account list
```

Displays all configured profiles and marks the active profile.

### add

```bash
m-gpux account add
```

Adds or updates a profile by prompting for credentials.

### switch

```bash
m-gpux account switch <profile_name>
```

Activates the selected profile.

### remove

```bash
m-gpux account remove <profile_name>
```

Deletes a profile. If active profile is removed, another profile becomes active automatically.

## billing

Track usage from one or more profiles.

### open

```bash
m-gpux billing open
```

Opens Modal usage dashboard in your browser.

### usage

```bash
m-gpux billing usage
m-gpux billing usage --days 7
m-gpux billing usage --account personal
m-gpux billing usage --all
```

Options:

- `--days`: Lookback period in days (default: 30)
- `--account`, `-a`: Check one named profile
- `--all`: Aggregate all configured profiles

## hub

Start interactive provisioning for GPU sessions.

```bash
m-gpux hub
```

Inside the hub:

1. Pick GPU type: `T4`, `L4`, `A10G`, `A100`, `A100-80GB`, `H100`
2. Pick action:
   - Jupyter Lab
   - Run Python script
   - Web Bash shell
3. Review generated `modal_runner.py`
4. Confirm execution

Notes:

- Temporary runner file is generated before execution.
- You can edit dependencies or runtime settings before pressing Enter.
- You can remove the temporary file after execution.
