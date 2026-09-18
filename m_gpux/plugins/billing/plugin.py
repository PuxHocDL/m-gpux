import typer
from rich.console import Console
from rich.table import Table
import webbrowser
from typing import Optional
from datetime import datetime, timezone, timedelta

app = typer.Typer(no_args_is_help=True)
console = Console()

@app.command("open")
def open_dashboard():
    """Open the Modal usage dashboard in your web browser."""
    url = "https://modal.com/settings/usage"
    console.print(f"[cyan]Opening Modal usage dashboard: {url}[/cyan]")
    webbrowser.open(url)

def _resolve_targets(doc, account: Optional[str], all_accounts: bool) -> list[str]:
    from rich.prompt import Prompt

    profiles = list(doc.keys())
    if not profiles:
        console.print("[red]No configured Modal profiles found. Please run `m-gpux account add` first.[/red]")
        raise typer.Exit(1)
    if all_accounts:
        return profiles
    if account:
        if account not in profiles:
            console.print(f"[red]Profile '{account}' not found![/red]")
            raise typer.Exit(1)
        return [account]
    choice = Prompt.ask("Choose account to check", choices=profiles + ["ALL"], default="ALL")
    return profiles if choice == "ALL" else [choice]


def _credentials(doc, profile: str) -> Optional[tuple[str, str]]:
    token_id = doc[profile].get("token_id")
    token_secret = doc[profile].get("token_secret")
    if not token_id or not token_secret:
        return None
    return str(token_id), str(token_secret)


@app.command("usage", help="Check workspace usage cost for the customized period.", rich_help_panel="Cloud Finance")
def check_usage(
    days: int = typer.Option(30, help="Number of days to check usage for"),
    account: str = typer.Option(None, "--account", "-a", help="Specific account profile to check"),
    all_accounts: bool = typer.Option(False, "--all", help="Check all configured profiles"),
    resources: bool = typer.Option(
        False, "--resources", "-r", help="Break cost down by resource (CPU, memory, each GPU type)"
    ),
):
    """Aggregate billing reports. Support querying across all local Modal profiles."""
    from m_gpux.core.billing import billing_report
    from m_gpux.core.profiles import load_config

    doc = load_config()
    targets = _resolve_targets(doc, account, all_accounts)

    console.print(f"\n[cyan]Fetching billing report for the last {days} days...[/cyan]")
    start_time = datetime.now(timezone.utc) - timedelta(days=days)

    table = Table(title=f"Workspace Usage (Last {days} Days)")
    table.add_column("Account", style="magenta")
    table.add_column("Environment", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Cost (USD)", style="red", justify="right")

    global_total = 0.0
    resource_totals: dict[str, float] = {}

    for p in targets:
        creds = _credentials(doc, p)
        if creds is None:
            continue
        try:
            rows = billing_report(*creds, start=start_time)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch billing for '{p}': {e}[/yellow]")
            continue

        per_app: dict[tuple[str, str], float] = {}
        for r in rows:
            key = (r["environment_name"] or "Unknown", r["description"])
            per_app[key] = per_app.get(key, 0.0) + r["cost"]
            global_total += r["cost"]
            for res, cost in r["cost_by_resource"].items():
                resource_totals[res] = resource_totals.get(res, 0.0) + cost

        for (env, desc), cost in sorted(per_app.items(), key=lambda x: x[1], reverse=True):
            if cost > 0:
                table.add_row(p, env, desc, f"${cost:.4f}")

    console.print()
    console.print(table)

    if resources:
        if resource_totals:
            res_table = Table(title="Cost by Resource")
            res_table.add_column("Resource", style="cyan")
            res_table.add_column("Cost (USD)", style="red", justify="right")
            for res, cost in sorted(resource_totals.items(), key=lambda x: x[1], reverse=True):
                if cost > 0:
                    res_table.add_row(res, f"${cost:.4f}")
            console.print(res_table)
        else:
            console.print("[yellow]Per-resource breakdown needs modal>=1.5.1 (pip install -U modal).[/yellow]")

    console.print(f"\n[bold green]Total Global Accumulated Cost: ${global_total:.4f}[/bold green]")
    console.print("[dim]Note: Each Modal Starter Tier account provides $30/month in credits.[/dim]")


@app.command("summary", help="Metered vs. billed cost for the current billing cycle, per account.", rich_help_panel="Cloud Finance")
def billing_summary_command(
    account: str = typer.Option(None, "--account", "-a", help="Specific account profile to check"),
    all_accounts: bool = typer.Option(False, "--all", help="Check all configured profiles"),
):
    """Show usage, credits applied and the amount actually invoiced this month."""
    from m_gpux.core.billing import billing_summary
    from m_gpux.core.profiles import load_config

    doc = load_config()
    targets = _resolve_targets(doc, account, all_accounts)

    table = Table(title="Billing Summary (This Month)")
    table.add_column("Account", style="magenta")
    table.add_column("Metered", style="white", justify="right")
    table.add_column("Credits & adjustments", style="green", justify="right")
    table.add_column("Billed", style="red", justify="right")
    table.add_column("Top category", style="cyan")

    for p in targets:
        creds = _credentials(doc, p)
        if creds is None:
            continue
        try:
            summary = billing_summary(*creds)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch summary for '{p}': {e}[/yellow]")
            continue
        if summary is None:
            console.print("[red]`billing summary` needs modal>=1.5.3. Run: pip install -U modal[/red]")
            raise typer.Exit(1)
        adjustments = sum(summary["adjustments"].values())
        breakdown = summary["metered_cost_breakdown"]
        top = max(breakdown.items(), key=lambda x: x[1], default=None)
        table.add_row(
            p,
            f"${summary['metered_cost']:.2f}",
            f"${adjustments:.2f}",
            f"${summary['billed_cost']:.2f}",
            f"{top[0]} (${top[1]:.2f})" if top and top[1] > 0 else "-",
        )

    console.print(table)


@app.command("rates", help="Current Modal prices per GPU, CPU core and GiB of memory.", rich_help_panel="Cloud Finance")
def rates_command(
    refresh: bool = typer.Option(False, "--refresh", help="Fetch live prices from Modal (needs modal>=1.5.4)"),
    account: str = typer.Option(None, "--account", "-a", help="Profile to fetch with (default: active)"),
):
    """Show the prices m-gpux uses for its cost estimates."""
    from m_gpux.core.gpus import GPU_CATALOG
    from m_gpux.core.pricing import gpu_hourly, load_rates, rates_age_seconds, refresh_rates
    from m_gpux.core.profiles import load_config, load_profiles

    if refresh:
        doc = load_config()
        name = account or next((n for n, active in load_profiles() if active), None) or next(iter(doc), None)
        creds = _credentials(doc, name) if name in doc else None
        if creds is None:
            console.print("[red]No usable profile to fetch prices with.[/red]")
            raise typer.Exit(1)
        try:
            refresh_rates(*creds)
            console.print(f"[green]Prices refreshed via '{name}'.[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not fetch live prices ({e}); showing cached/static prices.[/yellow]")

    rates = load_rates()
    age = rates_age_seconds()
    source = f"live, fetched {age / 3600:.1f}h ago" if age is not None else "built-in snapshot — run with --refresh"

    table = Table(title=f"Modal prices ({source})")
    table.add_column("GPU", style="cyan")
    table.add_column("VRAM", justify="right")
    table.add_column("$/hour", style="red", justify="right")
    table.add_column("$/hour ×8", style="dim", justify="right")
    for gpu, vram, max_n, _ in GPU_CATALOG:
        price = gpu_hourly(gpu, rates)
        if price is None:
            continue
        table.add_row(gpu, f"{vram} GB", f"${price:.2f}", f"${price * max_n:.2f}" if max_n == 8 else "-")
    console.print(table)

    cpu = Table(title="CPU & memory")
    cpu.add_column("Resource", style="cyan")
    cpu.add_column("Functions", justify="right")
    cpu.add_column("Sandboxes (dev, compose sandbox)", justify="right")
    cpu.add_row("CPU core-hour", f"${rates['cpu_hour_cost']:.4f}", f"${rates['cpu_hour_cost_sandbox']:.4f}")
    cpu.add_row("GiB memory-hour", f"${rates['mem_gib_hour_cost']:.4f}", f"${rates['mem_gib_hour_cost_sandbox']:.4f}")
    console.print(cpu)
    console.print(f"[dim]Volume storage: ${rates['volume_storage_gib_month_cost']:.2f}/GiB-month[/dim]")


# ─── Plugin registration ──────────────────────────────────────
from m_gpux.core.plugin import PluginBase as _PluginBase


class BillingPlugin(_PluginBase):
    name = "billing"
    help = "Track infrastructure costs across workspaces."
    rich_help_panel = "Identity & Finance"

    def register(self, root_app):
        root_app.add_typer(
            app,
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )
