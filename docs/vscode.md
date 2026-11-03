# VS Code Extension

The [M-GPUX extension](https://marketplace.visualstudio.com/items?itemName=puxpux.m-gpux)
puts accounts, sessions and every m-gpux workflow in the sidebar. It shells out
to the `modal` and `m-gpux` CLIs, and offers to set up a private copy of the
CLI the first time one is needed.

## Overview panel

The **Overview** panel at the top of the M-GPUX sidebar shows:

- the active account with its remaining credit or budget, and a Switch button
- running sessions, spend and credit left across accounts
- launch tiles: GPU Hub, Projects, Run anywhere, Dev Box, Serve LLM, Dashboard
- session cards with open / logs / pull / push / stop, and **Use as notebook kernel** for Jupyter sessions
- recent runs from `mgpux.toml` projects, with their best result and cost
- accounts with spend bars (click to switch), presets, and a **More tools** list

The classic Accounts, Sessions, Presets and Quick Actions trees sit below it.
The status bar shows the active account and its remaining credit, and turns
amber at 90% used; a warning pops up once a day when the active account has
less than 10% left.

## Notebook kernels

Run a local `.ipynb` on a Modal GPU without leaving the editor (requires the
Jupyter extension):

1. Start a Jupyter session from the GPU Hub, or click **Launch a GPU Jupyter server on Modal…** in the kernel picker.
2. In the notebook, open the kernel picker → **Select Another Kernel… → M-GPUX · Modal GPUs** → pick the session.
3. Run cells. Files written in the notebook land in the session's `/workspace` volume; use **Pull** on the session to bring them back.

The **Use Modal GPU as Notebook Kernel** button on the notebook toolbar and on
Jupyter session cards opens the same picker. Sessions that scaled to zero are
listed too; the first cell cold-starts them. **Find running M-GPUX Jupyter
apps** adopts sessions started from the CLI or another window.

## Workspace tools

| Command | What it does |
| --- | --- |
| **Projects (mgpux.toml)** | Create the file, run or sweep a task, open the run history ([Projects](projects.md)) |
| **Run Script Anywhere** | Also on the Explorer context menu for `.py` files: Kaggle → Colab → Modal |
| **Secrets & Images Sync** | Secret / image status and sync across every workspace ([Workspaces](workspaces.md)) |
| **Browse Volumes** | Navigate any account's Volumes and download a file or folder into the workspace |
| **Notifications** | Add Discord / Slack / Telegram / ntfy / webhook channels, test, watch |

Commands that ask for a credential (a webhook URL, a secret value) run in a
terminal so the CLI can prompt for it without echoing.
