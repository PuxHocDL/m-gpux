# Dev Boxes

`m-gpux dev` gives you a GPU (or CPU) machine on Modal that you use like any remote server: SSH into it, open it in VS Code, pause it overnight, and pick up exactly where you left off.

```bash
cd my-project
m-gpux dev            # same as: m-gpux dev up
```

Under the hood each box is a [Modal Sandbox](https://modal.com/docs/guide/sandboxes) running `sshd`, with your folder copied into `/workspace`.

## Quick start

```bash
m-gpux dev up                 # pick account + GPU, uploads this folder
m-gpux dev code               # open /workspace in VS Code (Remote-SSH)
ssh m-gpux-my-project         # or plain ssh — the host alias is written for you
m-gpux dev pause              # snapshot everything, stop billing compute
m-gpux dev resume             # continue later — installs and files are still there
m-gpux dev down               # delete the box
```

## Commands

| Command | What it does |
|---|---|
| `dev up` | Create a box for the current folder and connect |
| `dev list` | All boxes with state, account, cost/hour and auto-stop time |
| `dev ssh [name]` | SSH session |
| `dev code [name]` | Open the box in VS Code via Remote-SSH |
| `dev shell [name]` | Terminal via `modal shell` (via SSH on Windows, where `modal shell` isn't supported) |
| `dev sync push` / `pull` | Copy files local → box, or box → local |
| `dev pause [name]` | Snapshot the full filesystem, then stop the box |
| `dev resume [name]` | Start again from the last snapshot |
| `dev down [name]` | Stop the box and forget it |
| `dev web` | The classic browser terminal (ttyd) dev container |

`[name]` defaults to the box for the current folder, or the only box you have.

### `dev up` options

| Option | Description | Default |
|---|---|---|
| `--name`, `-n` | Box name | current folder name |
| `--image` | Start from a published image (`m-gpux image build`) | asked if you have any |
| `--hours` | Auto-stop after N hours (max 24) | `12` |
| `--ssh/--no-ssh` | Run `sshd` for ssh / VS Code | on |
| `--lock-ip` | Only accept connections from your current public IP | off |
| `--upload/--no-upload` | Copy this folder into `/workspace` | on |

## Pause and resume

`dev pause` takes a snapshot of the whole filesystem: `pip install`ed packages, apt packages, datasets you downloaded, edited code. Then it stops the box. While paused, no compute is billed. `dev resume` boots a new box from that snapshot in a few seconds, with a fresh SSH address that is written to `~/.ssh/config` for you.

Snapshots are kept for 30 days by default (`--keep-days`).

!!! warning "Auto-stop"
    A box stops on its own after `--hours` (Modal Sandboxes live at most 24 hours). Anything not paused or synced by then is lost, so run `m-gpux dev pause` at the end of a session. `dev list` shows each box's auto-stop time.

## File sync

```bash
m-gpux dev sync push          # only files changed since the last push
m-gpux dev sync push --all    # everything
m-gpux dev sync pull          # box → the folder the box was created from (asks first)
m-gpux dev sync pull --to ./from-box
```

Sync skips the exclude patterns you chose at `dev up` (`.venv`, `node_modules`, `.git`, … by default). With VS Code Remote-SSH you edit files on the box directly, so you mainly need `pull` for results and checkpoints.

## SSH details

- m-gpux uses its own key, `~/.m-gpux/ssh/id_ed25519`, created on first use. Your own keys are never touched.
- Each box gets a `Host m-gpux-<name>` block in `~/.ssh/config`, between `# >>> m-gpux dev` markers; `dev down` removes it.
- Password login is disabled; only the m-gpux key is accepted.
- `--lock-ip` restricts the box's inbound connections to your current public IP.

## Cost

Sandbox CPU and memory cost about 3× Function rates (`m-gpux billing rates` shows both); GPU prices are the same. The `dev up` picker shows the estimated $/hour for each choice, and `dev list` shows it for running boxes.

## Classic mode

The previous browser-terminal container (ttyd + Modal Volume + `msync`) is still available:

```bash
m-gpux dev web
m-gpux dev --preset rl-a100    # presets run in classic mode
```
