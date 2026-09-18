<div align="center">
  <a href="https://puxhocdl.github.io/m-gpux/">
    <img alt="m-gpux logo" src="https://raw.githubusercontent.com/PuxHocDL/m-gpux/main/m-gpux-vscode/resources/icon.png" width="96">
  </a>
  <h1>m-gpux</h1>
  <p><strong>The GPU workbench for Modal.</strong></p>

  <p>
    <a href="https://pypi.org/project/m-gpux/"><img alt="PyPI - License" src="https://img.shields.io/pypi/l/m-gpux"></a>
    <a href="https://pypistats.org/packages/m-gpux"><img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/m-gpux"></a>
    <a href="https://pypi.org/project/m-gpux/"><img alt="Version" src="https://img.shields.io/pypi/v/m-gpux?label=version"></a>
    <a href="https://pypi.org/project/m-gpux/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/m-gpux"></a>
    <a href="https://marketplace.visualstudio.com/items?itemName=puxpux.m-gpux"><img alt="VS Code Marketplace" src="https://img.shields.io/visual-studio-marketplace/v/puxpux.m-gpux?label=VS%20Code"></a>
  </p>
</div>

m-gpux is a CLI for getting real work done on [Modal](https://modal.com) GPUs. It turns a folder on your laptop into a GPU dev box, a Jupyter session, a hosted web app, an OpenAI-compatible LLM endpoint, or a whole Docker Compose stack — across every Modal account you own, with the price per hour in front of you before anything starts.

> [!TIP]
> Just getting started? Run `m-gpux dev up` inside a project folder. You get a GPU box you can `ssh` or open in VS Code, and `m-gpux dev pause` snapshots it so you can pick up tomorrow with your packages and files intact.

## Quickstart

```bash
pip install m-gpux         # also installs the `modal` CLI that m-gpux drives
m-gpux account add         # paste a `modal token set ...` command
```

```bash
cd my-project
m-gpux dev up              # pick an account and a GPU; this folder lands in /workspace
m-gpux dev code            # open it in VS Code (Remote-SSH)
m-gpux dev pause           # snapshot everything, stop paying for compute
```

If you'd rather click through a menu, `m-gpux hub` launches Jupyter, a script run, a browser terminal, or vLLM on any GPU from one guided wizard.

For the same workflows inside your editor, install the [m-gpux VS Code extension](https://marketplace.visualstudio.com/items?itemName=puxpux.m-gpux).

> [!TIP]
> Juggling several Modal accounts? `m-gpux budget set 20` caps what each one may spend this month, and the **AUTO** account picker always lands on the account with the most budget left.

## m-gpux ecosystem

The CLI works on its own, and each piece below plugs into the same accounts, presets, and budgets.

- **[CLI](https://pypi.org/project/m-gpux/)** — dev boxes, Hub, hosting, serving, Compose, budgets, and billing from one command
- **[VS Code extension](https://marketplace.visualstudio.com/items?itemName=puxpux.m-gpux)** — accounts, sessions, presets, and the Hub / host / serve wizards in a sidebar
- **[Documentation](https://puxhocdl.github.io/m-gpux/)** — guides for every workflow, plus the full command reference
- **[Examples](examples/)** — ready-to-deploy FastAPI, Flask, and static-site projects for `m-gpux host`

## Why use m-gpux?

m-gpux wraps Modal's primitives (Sandboxes, Functions, Servers, Volumes, named Images) into workflows that fit how you already develop.

- **Dev boxes that survive the night** — Sandboxes running `sshd`, reachable with plain `ssh` or VS Code Remote-SSH. `pause` snapshots the whole filesystem and `resume` boots it back in seconds; `sync push/pull` moves files both ways
- **Every GPU, priced up front** — T4 through H100, H200, B200, and B300, including multi-GPU containers (`H100:8`), with $/hour in every picker and `m-gpux billing rates` for the live price table
- **Many accounts, one budget** — per-account monthly limits, budget-aware AUTO selection, a warning before you launch on an account that's nearly empty, and `budget check --stop` to shut down apps on accounts that go over
- **From localhost to a URL** — `m-gpux host` deploys FastAPI, Flask, Django, or a static folder with scale-to-zero; `--server` uses Modal's low-latency `@app.server()` primitive
- **Your own OpenAI-compatible endpoint** — `m-gpux serve deploy` puts any Hugging Face model behind vLLM with API keys, streaming, warmup, logs, and a live metrics dashboard
- **Docker Compose, lifted as-is** — run a `docker-compose.yml` as one container, a full VM-style image (Triton, gRPC), or one Sandbox per service with readiness probes and working service-to-service addresses
- **Starts in seconds, not minutes** — `m-gpux image build` bakes your dependencies once and publishes them to every account; Hub and dev boxes offer them as the base image
- **Nothing hidden** — every workflow generates a plain Modal script you can read and edit before it runs

## Resources

- [Documentation](https://puxhocdl.github.io/m-gpux/) — getting started, guides, and FAQ
- [Command reference](https://puxhocdl.github.io/m-gpux/commands/) — every command and option
- [Dev boxes](https://puxhocdl.github.io/m-gpux/dev-container/) — SSH, VS Code, pause/resume, and sync in depth
- [Costs, budgets & images](https://puxhocdl.github.io/m-gpux/costs/) — GPU catalog, prices, budgets, and published images
- [Docker Compose guide](https://puxhocdl.github.io/m-gpux/compose/) — subprocess, VM, and sandbox modes
- [Architecture](https://puxhocdl.github.io/m-gpux/architecture/) — plugins, the generated-script pattern, and how third-party plugins add commands
- [Issues](https://github.com/PuxHocDL/m-gpux/issues) — bug reports and feature requests

## Contributing

```bash
git clone https://github.com/PuxHocDL/m-gpux.git
cd m-gpux
pip install -e .
m-gpux --help
```

Each command group is a plugin in `m_gpux/plugins/<name>/plugin.py`, registered in both `m_gpux/plugins/__init__.py` and the `m_gpux.plugins` entry-point group in `pyproject.toml`. The VS Code extension lives in `m-gpux-vscode/` (`npm install && npx tsc --noEmit`), and the landing site in `m-gpux-ui/`.

## License

[MIT](https://pypi.org/project/m-gpux/)
