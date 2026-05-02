# M-GPUX — Modal GPU Orchestrator for VS Code

> Provision GPU workloads, manage multi-profile Modal accounts, and track cloud billing — all without leaving your editor.

---

## Features

- **GPU Hub Wizard** — Guided multi-step flow to launch Jupyter, Python scripts, web shells, or vLLM inference servers on any NVIDIA GPU
- **Multi-Account Management** — Add, switch, and remove Modal profiles from the sidebar
- **Live Billing** — See remaining credits per account directly in the sidebar; hover for detailed breakdown
- **Hardware Probing** — Inspect GPU/CPU/RAM metrics on any Modal container
- **Native VS Code UI** — Output Channels for logs, progress notifications with cancel, clickable URL pop-ups when tunnels are ready

---

## Requirements

| Requirement | Purpose |
|-------------|---------|
| **VS Code** ≥ 1.85 | Extension host |
| **Python** ≥ 3.9 | Required by Modal CLI |
| **Modal CLI** (`pip install modal`) | Core cloud runtime |
| **m-gpux CLI** (`pip install m-gpux`) | Optional — needed for Load Probe and Billing Usage commands |

---

## Installation

```bash
# From VSIX file
code --install-extension m-gpux-2.2.0.vsix
```

Or in VS Code: `Ctrl+Shift+P` → **Extensions: Install from VSIX...**

After installing, run **Reload Window** (`Ctrl+Shift+P` → `Reload Window`).

---

## Getting Started

### 1. Open the Sidebar

Click the **GPU chip icon** on the Activity Bar (left edge). Two panels appear:

| Panel | Description |
|-------|-------------|
| **Accounts** | Lists all configured Modal profiles with active status and remaining credit |
| **Quick Actions** | One-click access to GPU Hub, Probe, Billing, and Info |

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
| A10G | 24 GB | Training/inference |
| L40S | 48 GB | Ada Lovelace |
| A100 | 40 GB | High performance (SXM) |
| A100-40GB | 40 GB | Ampere 40 GB variant |
| A100-80GB | 80 GB | Extreme performance |
| RTX-PRO-6000 | 48 GB | Pro workstation |
| H100 | 80 GB | Hopper |
| H100! | 80 GB | H100 reserved/priority |
| H200 | 141 GB | Hopper + HBM3e |
| B200 | — | Blackwell (latest gen) |
| B200+ | — | B200 reserved/priority |

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

- **Sidebar** — Each account shows remaining credit (e.g. `$27.50 left`). Hover for a used/remaining breakdown.
- **Billing Usage** — Click in Quick Actions to run `m-gpux billing usage --all` and see a detailed cost table.
- **Billing Dashboard** — Opens [modal.com/settings/usage](https://modal.com/settings/usage) in your browser.

---

## All Commands

Open the Command Palette (`Ctrl+Shift+P`) and type `M-GPUX`:

| Command | Description |
|---------|-------------|
| `M-GPUX: Open GPU Hub` | Launch the GPU provisioning wizard |
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

The extension reads and writes `~/.modal.toml` directly — the same file used by the Modal CLI. No separate config needed.

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
| `modal: command not found` | Install Modal: `pip install modal` |
| Load Probe doesn't work | Install the CLI: `pip install m-gpux` |
| `charmap codec can't encode` error | Update to the latest extension version (fixed: sets `PYTHONIOENCODING=utf-8`) |
| Profile won't switch | Verify `~/.modal.toml` is valid TOML |
| Billing shows no data | Click ⟳ Refresh — billing is fetched async via the Modal SDK |
