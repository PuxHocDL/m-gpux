# Session Manager

`m-gpux sessions` is the local control plane for Hub and dev container runs.

When a detached Hub/dev app keeps running, `m-gpux` records metadata in:

```text
~/.m-gpux/sessions.json
```

Detached apps default to staying alive after launch. Once Modal starts the app successfully, the session is saved automatically; choosing to stop it at the final prompt updates the tracked state.

## Common Commands

```bash
m-gpux sessions list
m-gpux sessions show <session-id>
m-gpux sessions logs <session-id>
m-gpux sessions pull <session-id> --to ./m-gpux-workspace
m-gpux sessions stop <session-id>
m-gpux sessions forget <session-id>
```

## Typical Flow

Launch a dev container:

```bash
m-gpux dev
```

Later, list tracked sessions:

```bash
m-gpux sessions list
```

Pull the remote workspace:

```bash
m-gpux sessions pull sess-1234abcd --to ./remote-output
```

Stop the remote app:

```bash
m-gpux sessions stop sess-1234abcd
```

## What Is Tracked

Each session stores:

- session ID
- kind (`dev`, `bash`, `jupyter`, or `interactive`)
- Modal profile
- compute label
- Modal app name
- workspace Volume name
- local project path
- preset name when launched from a preset

## URL Recovery

Tunnel URLs are printed by the remote Modal app. If the local CLI did not capture one, use:

```bash
m-gpux sessions logs <session-id>
```

The logs include the Web Bash or Jupyter ready message and URL.
