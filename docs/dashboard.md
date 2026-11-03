# Web Dashboard

`m-gpux ui` opens a local web console for everything m-gpux manages: your Modal
accounts, the apps, containers and sandboxes running on them, tracked sessions,
deployed endpoints, presets, images, spend and budgets. It runs entirely on your
machine and talks to Modal with the credentials already in `~/.modal.toml`.

```bash
m-gpux ui                 # serves on 127.0.0.1:7878 and opens your browser
m-gpux ui --port 9000     # another port (the next free one is used if it is taken)
m-gpux ui --no-browser    # just print the link
```

From VS Code, run **M-GPUX: Open Web Dashboard** or click **Dashboard** in the
Actions view. The terminal it opens keeps the server alive; close it to stop.

## Pages

| Page | What it shows | What you can do |
|---|---|---|
| **Overview** | Accounts, credit left, spend this month, live apps, containers, sandboxes, recent sessions | Jump to any area |
| **Accounts** | Every profile with its workspace, connection status and a usage meter against its monthly cap | Add (verified with Modal before saving), make active, set a budget, remove |
| **Apps** | Deployed, running and detached apps across accounts; filter Live / m-gpux / All | Read recent logs, open on modal.com, stop |
| **Containers** | Every container running right now | Read logs, stop |
| **Sandboxes** | Dev boxes tracked by m-gpux and every running Modal Sandbox | Terminate (with a reminder to `dev pause` instead) |
| **Sessions** | Hub, dev and deploy launches from `sessions.json` | Inspect, forget |
| **Endpoints** | The `serve` LLM API and the compute gateway, with recent gateway jobs | Open API docs; keys are never shown |
| **Runs** | `m-gpux up` / `sweep` / `run` results: status, jobs, compute time, estimated cost, best metric | Open a run for per-job exit codes, metrics and the command to download its outputs |
| **Presets & images** | Saved presets and published images | Copy the command that runs them |
| **Volumes** | Every Volume on every account (run outputs and the shared HF cache are tagged) | Browse folders, see sizes, copy the download command |
| **Sync & alerts** | Which workspace has which Secret and image; notification channels (targets masked) | Send a test notification |
| **Usage & pricing** | Spend per account, budgets, GPU prices per hour | Edit budgets |

The **account switcher** in the top bar scopes every page to one account, like
switching environments. Press **Ctrl K** for the command palette (pages,
actions, accounts), **R** to refresh and **/** to jump to a page's filter.

Session states are reconciled with what is actually on Modal: a session recorded
as running whose account was removed shows **Account removed**, and one whose app
is no longer live shows **Not running**. Both appear under **Needs cleanup**.

## Freshness

Data is cached briefly on the server (account details 5 minutes, apps,
containers and sandboxes 15 seconds) and pages refresh every 30 seconds while
visible. **Refresh** forces a fresh read. On start, the dashboard warms its
caches while the browser opens, so the overview is usually ready within a few
seconds.

## Security

The dashboard can stop apps and edit `~/.modal.toml`, so it is locked down:

- It listens on `127.0.0.1` only (unless you pass `--host`, which prints a warning).
- Every API call needs the random token in the printed link. The token lives in
  the URL *fragment*, which browsers never send to servers or put in referrers,
  and it changes on every start.
- Requests whose `Host` header is not the dashboard's own address are refused,
  which blocks DNS-rebinding attacks from web pages.
- A strict Content-Security-Policy applies, nothing is loaded from the internet,
  and token secrets and API keys are never sent to the page.

Keep the link private: anyone with it, on your machine, can act on your accounts
until you stop the server.

## How it reads Modal

Workspaces, billing and sandboxes come from the Modal SDK, with one reused client
per account on a single background event loop so all accounts load
concurrently. Apps and containers come from `modal app list --json` and
`modal container list --json`, the same public commands `m-gpux stop` uses.
Accounts that cannot be reached are listed in a banner; the rest of the page
still loads.
