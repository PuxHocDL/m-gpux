# Kaggle & Colab

m-gpux also drives the free and prepaid GPUs outside Modal: **Kaggle** notebooks
(weekly GPU/TPU hours per account) and **Google Colab** runtimes (compute units
per Google account). Both work the way m-gpux treats Modal profiles: many
accounts side by side, a status view across all of them, and **AUTO** to pick
the account with the most capacity left.

| | Kaggle | Colab |
|---|---|---|
| CLI it drives | `kaggle` (`pip install kaggle`) | `colab` (`uv tool install google-colab-cli`, Python 3.12+) |
| Accounts | `~/.kaggle/zoo.json` | `~/.colab_accounts/<name>` (+ `main`) |
| Capacity | GPU / TPU hours per week, 2 GPU sessions at once | compute-unit balance and burn rate |
| AUTO picks | most GPU hours left with a free slot | most compute units left |

Both pages are also in the [web dashboard](dashboard.md) under **Other clouds**.

## Kaggle

### Accounts

Accounts live in `~/.kaggle/zoo.json`, one entry per Kaggle username:

```json
{
  "accounts": {
    "me":   {"default": true, "team": "My team", "note": "this machine's own login"},
    "mate": {"token": "KGAT_…", "team": "My team", "no_submit": ["some-competition"]}
  }
}
```

- `default: true` (or no token) uses the machine's normal Kaggle credentials.
- Every other account runs the CLI with its own `KAGGLE_API_TOKEN`.
- `no_submit` lists competitions that account must never submit to; m-gpux
  refuses `competitions submit` for them.
- `team` groups accounts when counting today's submissions.

```bash
m-gpux kaggle add KGAT_… --team "My team" --note "laptop"   # username is detected
m-gpux kaggle accounts                                       # GPU / TPU hours left, reset time
m-gpux kaggle remove mate
```

### Status and free slots

```bash
m-gpux kaggle status                    # running / queued kernels and free GPU slots per account
m-gpux kaggle status --comp <slug>      # plus submissions used today, per team
m-gpux kaggle free                      # accounts that can start a GPU kernel now
```

### Pushing kernels

`push` takes a folder with `kernel-metadata.json` (as created by
`kaggle kernels init` or kept in a `kaggle_push/<name>/` folder):

```bash
m-gpux kaggle push kaggle_push/my-run                    # as the owner in the metadata
m-gpux kaggle push kaggle_push/my-run --as mate          # as another account
m-gpux kaggle push kaggle_push/my-run --as auto --wait   # AUTO, then wait and download the output
m-gpux kaggle watch mate/my-run --out kaggle_out/my-run  # wait for a pushed kernel, then download
```

Pushing as another account rewrites the `id` owner in a temporary copy of the
folder; your files are never modified. Private datasets in `dataset_sources`
must be shared with that account.

### Anything else

`run` executes any `kaggle` command as an account (`no_submit` still applies):

```bash
m-gpux kaggle run mate -- competitions submissions <slug>
m-gpux kaggle run auto -- kernels list --mine
```

## Colab

### Accounts

colab-cli stores its login in `~/.config/colab-cli/token.json`, so each extra
Google account gets its own home folder under `~/.colab_accounts/`. `main` is
your normal home.

```bash
m-gpux colab login work       # opens Google's OAuth flow in the terminal
m-gpux colab accounts         # compute units, burn rate, live runtimes
m-gpux colab remove work
```

Accounts whose login expired show **Login expired**; run `m-gpux colab login
<name>` again. Background views never trigger the login prompt.

### Running work

```bash
m-gpux colab run train.py --gpu A100 --as auto -- --epochs 3   # fresh VM, released afterwards
m-gpux colab new -s trainer --gpu L4 --as work                 # a named runtime that stays up
m-gpux colab as work -- exec -s trainer -f step.py             # any colab command as an account
m-gpux colab sessions                                          # live runtimes on every account
m-gpux colab stop trainer --as work
```

GPUs: `T4`, `L4`, `G4`, `A100`, `H100`; TPUs: `v5e1`, `v6e1`. `--high-mem`
needs Colab Pro.

### Windows

google-colab-cli imports the Unix-only `termios` / `tty` modules at start-up,
although only `colab console` uses them. m-gpux puts small stand-ins on
`PYTHONPATH` for every `colab` call, so all other commands run natively on
Windows. `colab console` and `colab ssh` remain Linux/macOS only.

## Compatibility

The account files are the same ones used by the standalone `kzoo.py` and
`colab_as.py` scripts, so accounts added with either tool show up in both.
