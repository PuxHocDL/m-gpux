# M-GPUX — Modal GPU Orchestrator for VS Code

> Provision GPU workloads, manage multi-profile Modal accounts, and track cloud billing — all without leaving your editor.

---

## Features

- **GPU Hub Wizard** — Guided multi-step flow to launch Jupyter, Python scripts, web shells, or vLLM inference servers on any NVIDIA GPU
- **Persistent Dev Boxes** — Create, open, pause, resume, and sync Modal Sandboxes from Quick Actions
- **Multi-Account Management** — Add, switch, and remove Modal profiles from the sidebar
- **Budget-Aware Billing** — See current-cycle usage and remaining m-gpux budget/credit per account
- **Session Management** — Restore, discover, stop, and sync remote sessions without losing profile context
- **Hardware Probing** — Inspect GPU/CPU/RAM metrics on any Modal container
- **Native VS Code UI** — Output Channels for logs, progress notifications with cancel, clickable URL pop-ups when tunnels are ready

---

## Requirements

| Requirement | Purpose |
|-------------|---------|
| **VS Code** ≥ 1.85 | Extension host |
| **Python** ≥ 3.10 | Used once to create the extension's private CLI environment |
| **Modal account** | Token credentials for cloud workloads |

You do **not** need to install `m-gpux` or `modal` globally. On first use the
extension offers **Set up CLI**, creates an isolated virtual environment in VS
Code's extension storage, and installs a compatible version of both tools. An
existing CLI on `PATH` or the explicit `mgpux.cliPath` setting is still
preferred.

---

## Installation

```bash
# From VSIX file
code --install-extension m-gpux-3.0.0.vsix
```

Or in VS Code: `Ctrl+Shift+P` → **Extensions: Install from VSIX...**

After installing, run **Reload Window** (`Ctrl+Shift+P` → `Reload Window`).

---

## Getting Started

### 1. Open the Sidebar

Click the **GPU chip icon** on the Activity Bar (left edge). Four panels appear:

| Panel | Description |
|-------|-------------|
| **Accounts** | Lists all configured Modal profiles with active status and remaining credit |
| **Active Sessions** | Live/restored workloads with logs, stop, and workspace sync actions |
| **Presets** | Shared CLI/extension workload presets |
| **Quick Actions** | GPU Hub, Dev Box, hosting, serving, Compose, billing, and management |

### 2. Add Your First Account

Click the **+** button on the Accounts panel header, or run `Ctrl+Shift+P` → `M-GPUX: Add Account`.

You can add credentials in two ways:

- **Paste shortcut** — Paste a full `modal token set --token-id ak-... --token-secret as-... --profile=myname` command. The extension parses it automatically.
- **Manual entry** — Leave the input empty and fill in Token ID, Token Secret, and Profile Name step by step.

The first profile is automatically set as active.

### 3. Launch a GPU Workload

Click **GPU Hub** in Quick Actions, or run `Ctrl+Shift+P` → `M-GPUX: Open GPU Hub`.

The wizard walks you through four steps:

#### Step 1 — Select Profile
Choose a Modal account. **AUTO** uses the currently active profile.

#### Step 2 — Choose GPU

| GPU | VRAM | Notes |
|-----|------|-------|
| T4 | 16 GB | Budget inference |
| L4 | 24 GB | Balanced cost/perf |
| A10 | 24 GB | Training/inference (formerly A10G) |
| L40S | 48 GB | Ada Lovelace |
| A100 | 40 GB | High performance (SXM) |
| A100-40GB | 40 GB | Ampere 40 GB variant |
| A100-80GB | 80 GB | Extreme performance |
| RTX-PRO-6000 | 96 GB | Blackwell workstation GPU |
| H100 | 80 GB | Hopper |
| H100! | 80 GB | H100 reserved/priority |
| H200 | 141 GB | Hopper + HBM3e |
| B200 | 180 GB | Blackwell |
| B200+ | 180 GB | B200 or B300, whichever is available first |
| B300 | 288 GB | Blackwell Ultra |

#### Step 3 — Choose Application

| Application | Description |
|-------------|-------------|
| **Jupyter Lab** | Interactive notebook server with auto-tunneling. Your workspace files are mounted at `/workspace`. |
| **Run Python Script** | Pick a `.py` file from your workspace and execute it remotely on the selected GPU. |
| **Bash Shell** | VS Code-like web terminal using direct `bash`, a clean prompt, reduced heartbeat noise, and optional `tmux`. |
| **vLLM Inference Server** | Deploy an OpenAI-compatible LLM API. Models: Qwen 1.5B/7B, Llama 3.1 8B, Gemma 9B, Mistral 7B. |

#### Step 4 — Configure & Launch

- For Jupyter and Python: optionally use `requirements.txt` and set exclude patterns for file upload.
- The extension generates a `modal_runner.py` script and opens it in the editor for review.
- Click **Launch** → the process runs in the background with a progress notification.
- When a tunnel URL is detected, a notification pops up with **Open in Browser** and **Copy URL** buttons.
- The temp script is cleaned up automatically when the process exits.

---

## Account Management

| Action | How |
|--------|-----|
| **Add** | `+` button on Accounts panel, or `Ctrl+Shift+P` → `M-GPUX: Add Account` |
| **Switch** | Click a profile name in the sidebar, or click the status bar, or `Ctrl+Shift+P` → `M-GPUX: Switch Account` |
| **Remove** | Right-click a profile → Remove Account, or `Ctrl+Shift+P` → `M-GPUX: Remove Account` |
| **Refresh** | Click the ⟳ button on the Accounts panel header — fetches live billing data |

### Status Bar

The bottom-left of VS Code shows `☁ M-GPUX: <profile-name>`. Click it to switch profiles.

### Billing

- **Sidebar** — Each account shows remaining m-gpux budget when configured, otherwise remaining monthly credit.
- **Billing Usage** — Uses Modal's current-cycle billing API with a compatibility fallback, across profiles in parallel.
- **Billing Dashboard** — Opens [modal.com/settings/usage](https://modal.com/settings/usage) in your browser.

---

## All Commands

Open the Command Palette (`Ctrl+Shift+P`) and type `M-GPUX`:

| Command | Description |
|---------|-------------|
| `M-GPUX: Set Up / Update CLI` | Install, repair, update, or select the CLI used by the extension |
| `M-GPUX: Open GPU Hub` | Launch the GPU provisioning wizard |
| `M-GPUX: Create / Start Dev Box` | Start a Sandbox dev box for the workspace |
| `M-GPUX: Manage Dev Box` | Open, pause, resume, sync, list, or delete a dev box |
| `M-GPUX: Add Account` | Add a new Modal profile |
| `M-GPUX: Switch Account` | Switch the active profile |
| `M-GPUX: Remove Account` | Delete a profile |
| `M-GPUX: Refresh Accounts` | Reload accounts and fetch billing data |
| `M-GPUX: Probe GPU Hardware` | Spin up a container and display hardware metrics |
| `M-GPUX: Show Billing Usage` | Aggregate billing report across accounts |
| `M-GPUX: Open Billing Dashboard` | Open Modal usage page in browser |
| `M-GPUX: Show Info` | Display extension version and profile count |

---

## Configuration

The extension reads and writes `~/.modal.toml` directly — the same file used by the Modal CLI. `mgpux.cliPath` can point to an existing compatible executable; otherwise the extension uses `PATH` or its private managed environment.

Example `~/.modal.toml`:

```toml
[personal]
token_id = "ak-xxxx"
token_secret = "as-xxxx"
active = true

[work]
token_id = "ak-yyyy"
token_secret = "as-yyyy"
```

---

## Quick Workflow

```
1. Open VS Code with your Python project
2. Click the M-GPUX icon on the sidebar
3. Add an account if you haven't already (+ button)
4. Click "GPU Hub" → pick a GPU → pick Jupyter Lab
5. Review the generated script → click Launch
6. Notification pops up with your Jupyter URL → Open in Browser
7. Code on a remote GPU with your workspace files ready at /workspace
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Extension not visible in sidebar | `Ctrl+Shift+P` → `Reload Window` |
| `modal: command not found` | Run `M-GPUX: Set Up / Update CLI`; the managed environment includes Modal |
| Dev Box or Compose action says CLI is missing | Choose **Install automatically**, or set `mgpux.cliPath` to an existing executable |
| `charmap codec can't encode` error | Update to the latest extension version (fixed: sets `PYTHONIOENCODING=utf-8`) |
| Profile won't switch | Verify `~/.modal.toml` is valid TOML |
| Billing shows no data | Click ⟳ Refresh — billing is fetched async via the Modal SDK |
