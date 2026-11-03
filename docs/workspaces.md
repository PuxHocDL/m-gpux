# Workspaces: Secrets, Images, Volumes & Notifications

Every Modal profile is its own workspace with its own Secrets, images and
Volumes, so a job that works on one account fails on another with "Secret not
found". These commands keep workspaces in step and tell you when something
needs attention.

## Secrets

```bash
m-gpux secrets status                          # matrix: which workspace has which Secret
m-gpux secrets sync hf HF_TOKEN --to all        # same keys on every workspace
m-gpux secrets sync wandb --from-dotenv .env --to "last hope 3,do-mi-xi"
m-gpux secrets delete old-key --to all
```

Modal never returns secret values, so `sync` always starts from a local source,
in this order: the `--from-dotenv` file, an environment variable with the same
name, then a hidden prompt. Name the variables only — `HF_TOKEN=...` on the
command line is refused so values stay out of shell history. Existing Secrets
are merged (other keys are kept) unless `--replace` is given. Values are sent
straight to Modal and never printed or stored by m-gpux.

`--to` takes `all`, a comma-separated list of profiles, or nothing for the
active profile.

## Images

```bash
m-gpux image build torch --pip torch,transformers --all
m-gpux image status                 # checked on Modal, not just in the local list
m-gpux image sync torch --to all    # build it where it is missing
```

`image build` records the recipe (Python, requirements, pip and apt packages),
so `image sync` can rebuild the same image on workspaces that lack it — for
example after you add an account. Images built before 3.2 have no recipe;
rebuild them once with `--all`.

## Volumes

```bash
m-gpux volume list --all                     # every volume on every account
m-gpux volume ls my-data /checkpoints --account "last hope 3"
m-gpux volume du my-data                     # size per top-level folder
m-gpux volume get my-data /checkpoints ./ckpt
m-gpux volume put my-data ./dataset /dataset # creates the volume if needed
m-gpux volume rm my-data /tmp -r
m-gpux volume delete my-data                 # the whole volume (asks first)
```

`m-gpux-hf-cache` is the shared Hugging Face cache that `serve`, the Hub's vLLM
and project tasks (`hf_cache = true`) mount at `/root/.cache/huggingface`, so a
model is downloaded once per account. The dashboard's **Volumes** page and the
VS Code **Browse Volumes** command browse and download the same data.

## Notifications

```bash
m-gpux notify add discord          # webhook URL asked with a hidden prompt, then a test message
m-gpux notify add telegram         # bot token (hidden) + chat id
m-gpux notify add ntfy --events run.done,run.failed,credit.low
m-gpux notify list                 # targets masked
m-gpux notify test
m-gpux notify watch                # keep watching until Ctrl+C
m-gpux notify watch --once         # one pass, for cron / Task Scheduler
m-gpux notify send "Training done" "val loss 0.12" --event run.done
```

Channel types: **discord**, **slack**, **telegram**, **ntfy** (phone push via
ntfy.sh or self-hosted) and **webhook** (any HTTPS endpoint; receives
`{source, event, level, title, message, time}` as JSON).

| Event | Sent by |
| --- | --- |
| `run.done`, `run.failed` | `m-gpux up` / `run` |
| `sweep.done` | `m-gpux sweep`, with the best result |
| `job.done`, `job.failed` | `gateway submit/result --wait`, and `notify watch` for unfinished jobs |
| `app.stopped` | `notify watch`: a running m-gpux app disappeared |
| `app.long_running` | `notify watch`: an app ran longer than `--long-running` (default 4h) |
| `credit.low` | `notify watch`: an account has less than `--low-credit` dollars left (default $5) |
| `budget.over` | `budget check`, and `notify watch` (once per month per account) |

Channels are stored in `~/.m-gpux/notify.json`, written owner-only where the OS
supports it. Webhook URLs and bot tokens are credentials: they are never
printed, and a failing channel never breaks the command that triggered it.
