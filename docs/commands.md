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

## serve

Deploy LLMs as OpenAI-compatible APIs with API key authentication.

### deploy

```bash
m-gpux serve deploy
```

Interactive wizard that walks through:

1. **Model selection** — choose from 11 presets or enter a custom HuggingFace model ID
2. **GPU selection** — T4, L4, A10G, A100, A100-80GB, H100
3. **Context length** — max sequence length for the model
4. **Keep warm** — number of containers to keep warm (0 = cold start, 1+ = always ready)
5. **API key** — select an existing key or create a new one

After confirmation, deploys a Modal app with:

- FastAPI auth proxy on port 8000 (Bearer token validation)
- vLLM backend on port 8001 (OpenAI-compatible API)
- Shared HuggingFace and vLLM model caches

### stop

```bash
m-gpux serve stop
```

Stops the deployed LLM API server on the current profile.

### warmup

```bash
m-gpux serve warmup
```

Sends a health-check request to the deployed endpoint to verify readiness.

### keys create

```bash
m-gpux serve keys create
m-gpux serve keys create --name production
```

Generates a new API key (`sk-mgpux-...`) and stores it locally in `~/.m-gpux/api_keys.json`.

### keys list

```bash
m-gpux serve keys list
```

Shows all API keys with masked values, creation date, and status (Active / Revoked).

### keys show

```bash
m-gpux serve keys show <name>
```

Reveals the full API key value for the given key name.

### keys revoke

```bash
m-gpux serve keys revoke <name>
```

Marks a key as revoked. Requires redeployment (`m-gpux serve deploy`) to take effect.

## stop

Stop running m-gpux apps (Jupyter, shells, LLM servers).

```bash
m-gpux stop
m-gpux stop --all
```

Options:

- `--all`: Scan and stop apps across all configured Modal profiles

Displays a table of running apps and lets you select which to stop (or stop all at once).
