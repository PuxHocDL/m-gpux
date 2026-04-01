# m-gpux Documentation

Welcome to the official docs for `m-gpux`, a production-focused CLI for Modal GPU operations.

## What is m-gpux?

`m-gpux` helps you run high-performance compute workflows from terminal-first commands:

- Manage multiple Modal identities in one place
- Launch GPU runtimes through a guided interactive hub
- Track usage costs by account or across all profiles

## Start Here

- New user setup: [Getting Started](getting-started.md)
- Full command list: [Command Reference](commands.md)
- Common issues: [FAQ and Troubleshooting](faq.md)

## Common Workflows

### Launch Jupyter on a GPU

1. `m-gpux account add`
2. `m-gpux hub`
3. Select your GPU and choose Jupyter mode

### Check weekly cost across all accounts

`m-gpux billing usage --days 7 --all`

## Links

- Repository: [PuxHocDL/m-gpux](https://github.com/PuxHocDL/m-gpux)
- Project README: [README](https://github.com/PuxHocDL/m-gpux/blob/main/README.md)
