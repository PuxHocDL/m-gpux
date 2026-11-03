# Projects, Sweeps & Run Anywhere

An `mgpux.toml` file declares the tasks a repo runs on Modal: the command, GPU,
image, secrets and volumes. Anyone who clones the repo runs `m-gpux up train`
instead of re-answering the Hub wizard, a sweep reuses the same task over a
parameter grid, and every run is recorded with its exit codes, metrics and an
estimated cost.

```bash
m-gpux init                                  # write mgpux.toml for this folder
m-gpux up train                              # run a task on Modal
m-gpux up train -- --epochs 5                # extra arguments for its command
m-gpux sweep train --grid lr=1e-4,3e-4 --grid batch=16,32
m-gpux runs list                             # history: status, compute, cost, best result
m-gpux run train.py --gpu T4                 # free Kaggle quota → Colab → Modal credit
```

## mgpux.toml

```toml
[project]
name = "llm-ft"
account = "auto"          # a profile name, "auto" (most credit left), or omit for the active one

[defaults]                # applied to every task
python = "3.12"
gpu = ["H100", "A100-80GB"]   # fallback order; "none" for CPU only
gpu_count = 1
timeout = "2h"
requirements = "requirements.txt"
secrets = ["hf"]          # Modal Secret names (see m-gpux secrets sync)
volumes = { "/data" = "my-dataset" }
hf_cache = true           # shared Hugging Face cache volume (m-gpux-hf-cache)

[tasks.train]
command = "python train.py --epochs 3"

[tasks.eval]
command = "python eval.py"
gpu = "L4"

[sweeps.lr]
task = "train"
grid = { lr = [1e-4, 3e-4], batch = [16, 32] }
metric = "loss"
mode = "min"
max_parallel = 4
```

`m-gpux init` writes a commented starter file: it picks `train.py` / `main.py`
as the first task and adds `requirements.txt` when there is one.

| Key | Meaning |
| --- | --- |
| `command` | Shell command run in `/workspace` (your project folder, uploaded with `exclude` patterns removed) |
| `gpu` | One GPU type, a list in fallback order, or `"none"` |
| `gpu_count`, `cpu`, `memory` | Per container; `memory` in MB |
| `timeout` | Seconds or `30m` / `2h` (10 s – 24 h) |
| `python`, `image` | Python for `debian_slim`, or a published image from `m-gpux image build` |
| `requirements`, `pip`, `apt` | Dependencies baked into the image |
| `env`, `secrets` | Plain environment variables, and Modal Secrets by name |
| `volumes`, `hf_cache` | Extra mounts, and the shared Hugging Face cache |
| `exclude` | Patterns not uploaded (defaults skip `.git`, `.venv`, `node_modules`, `outputs`, …) |
| `max_parallel`, `retries` | Containers at once for sweeps, and retries per job |

## What a job sees

| Variable | Value |
| --- | --- |
| `MGPUX_OUTPUT_DIR` | `/outputs/<run id>/<job index>`, on the `m-gpux-<project>-outputs` volume |
| `MGPUX_RUN_ID`, `MGPUX_JOB_INDEX` | The run and this job's index |
| `MGPUX_PARAMS`, `MGPUX_PARAM_<NAME>` | Sweep parameters as JSON and one variable each |

Report metrics by printing one line, or by writing `$MGPUX_OUTPUT_DIR/result.json`:

```python
print("MGPUX_RESULT " + json.dumps({"loss": loss, "acc": acc}))
```

Download a run's files with
`m-gpux volume get m-gpux-<project>-outputs /<run id> ./outputs`, or pass
`--download` to `m-gpux up`.

## Sweeps

`m-gpux sweep NAME` takes a `[sweeps.*]` name or a task name plus `--grid`
options (they merge with the file's grid). Parameters fill `{name}`
placeholders in the command, or are appended as `--name value`:

```toml
[tasks.train]
command = "python train.py --lr {lr}"    # {lr} is filled; batch becomes --batch 16
```

All jobs run in one Modal app through `Function.map`, `max_parallel` at a time.
The table at the end marks the best job by `metric` / `mode`, and the run is
saved for `m-gpux runs show <id>`. Grids larger than `--max-runs` (64) are
refused.

## Run anywhere

`m-gpux run script.py` checks capacity before choosing where to run:

1. **Kaggle** accounts with a free GPU slot and enough weekly GPU hours (T4 / P100), pushed as a private kernel
2. **Colab** accounts that are logged in (compute units, or the free T4)
3. **Modal** accounts with enough credit for `--hours` at the GPU's price

`--plan` prints the table and stops; `--where modal|kaggle|colab` limits the
choice; `--account` forces one. Only accounts you configured are considered —
use accounts you are entitled to under each platform's terms.

## Notifications and history

`up`, `sweep` and `run` send `run.done`, `run.failed` and `sweep.done`
notifications when channels are configured ([Workspaces](workspaces.md#notifications)).
`m-gpux runs list` and the dashboard's **Runs** page list every run with its
status, compute time, estimated cost and best result.

## GitHub Actions

`m-gpux init --github-action` writes `.github/workflows/m-gpux.yml`. The action
installs m-gpux and runs a task with the `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`
repository secrets:

```yaml
- uses: actions/checkout@v4
- uses: PuxHocDL/m-gpux@v3.2.0
  with:
    task: train                 # or: sweep: lr, grid: "seed=1,2,3"
    modal-token-id: ${{ secrets.MODAL_TOKEN_ID }}
    modal-token-secret: ${{ secrets.MODAL_TOKEN_SECRET }}
```

Outputs: `run-id` and `status`. The job fails when any task job fails.
`--yes` and `--account env` (credentials from the environment) are what the
action uses, and both work in any CI.
