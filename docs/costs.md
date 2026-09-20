# Costs, Budgets & Images

## GPU catalog

Every compute picker shows the estimated price per hour next to each option.

| GPU | VRAM | Max per container | Notes |
|---|---|---|---|
| `T4` | 16 GB | 8 | Light inference / exploration |
| `L4` | 24 GB | 8 | Best price/performance for inference |
| `A10` | 24 GB | 4 | Formerly `A10G` |
| `L40S` | 48 GB | 8 | Strong inference |
| `A100` / `A100-40GB` / `A100-80GB` | 40 / 80 GB | 8 | `A100` may be upgraded to 80GB at no extra cost |
| `RTX-PRO-6000` | 96 GB | 8 | Blackwell workstation GPU |
| `H100` | 80 GB | 8 | May be upgraded to H200 at no extra cost |
| `H100!` | 80 GB | 8 | Pinned H100, never upgraded |
| `H200` | 141 GB | 8 | HBM3e |
| `B200` | 180 GB | 8 | Blackwell |
| `B200+` | 180 GB | 8 | B200 or B300, whichever is free first, billed as B200 |
| `B300` | 288 GB | 8 | Blackwell Ultra |

`hub`, `dev` and `preset create` ask how many GPUs to attach (`H100:4`).

## Prices

```bash
m-gpux billing rates             # prices used for estimates
m-gpux billing rates --refresh   # fetch live prices from Modal (modal>=1.5.4)
```

Live prices are cached in `~/.m-gpux/rates.json`. Without a cache, a built-in snapshot of Modal's list prices is used.

## Budgets

A budget is a monthly spending limit per account. It can be below the free $30 credit (to keep a reserve) or above it (if you pay for extra usage).

```bash
m-gpux budget set 20                 # default for every account
m-gpux budget set 50 -a team-a100    # one account
m-gpux budget show                   # used / limit / left for every account
m-gpux budget check --stop           # stop m-gpux apps on accounts over budget; exit code 2 if any
m-gpux budget watch --interval 600   # keep enforcing until Ctrl+C
m-gpux budget clear -a team-a100
```

Budgets also change how accounts are picked:

- **AUTO** chooses the account with the most money left under its budget (or free credit).
- Picking an account by hand that has less than $1 left offers to switch to the best account instead (`MGPUX_SKIP_CREDIT_CHECK=1` turns this off).

`budget watch` only enforces limits while it runs. For unattended enforcement, run `m-gpux budget check --stop` from cron or Task Scheduler.

## Billing reports

```bash
m-gpux billing usage --all --resources   # per-app cost + breakdown by CPU / memory / GPU type
m-gpux billing summary --all             # metered vs. credits vs. billed, this month
```

## Published images

Installing the same packages on every cold start is slow. Build once, publish, and reuse:

```bash
m-gpux image build torch --pip torch,torchvision,transformers
m-gpux image build myproj -r requirements.txt --all   # publish to every account
m-gpux image list
```

When the selected account has published images, `m-gpux hub` and `m-gpux dev up` offer them as the base image. Image names are per workspace, which is why `--all` builds on each account; m-gpux remembers where each image exists in `~/.m-gpux/images.json`.
