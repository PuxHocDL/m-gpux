import typer
from rich.console import Console
from rich.table import Table
import webbrowser
from modal.billing import workspace_billing_report
from datetime import datetime, timezone, timedelta

app = typer.Typer(no_args_is_help=True)
console = Console()

@app.command("open")
def open_dashboard():
    """Open the Modal usage dashboard in your web browser."""
    url = "https://modal.com/settings/usage"
    console.print(f"[cyan]Opening Modal usage dashboard: {url}[/cyan]")
    webbrowser.open(url)

@app.command("usage", help="Check workspace usage cost for the customized period.", rich_help_panel="Cloud Finance")
def check_usage(
    days: int = typer.Option(30, help="Number of days to check usage for"),
    account: str = typer.Option(None, "--account", "-a", help="Specific account profile to check"),
    all_accounts: bool = typer.Option(False, "--all", help="Check all configured profiles")
):
    """Aggregate billing reports. Support querying across all local Modal profiles."""
    from .account import load_config
    from modal.client import Client
    from rich.prompt import Prompt
    
    doc = load_config()
    profiles = list(doc.keys())
    
    if not profiles:
        console.print("[red]No configured Modal profiles found. Please run `m-gpux account add` first.[/red]")
        raise typer.Exit(1)
        
    targets = []
    if all_accounts:
        targets = profiles
    elif account:
        if account not in profiles:
            console.print(f"[red]Profile '{account}' not found![/red]")
            raise typer.Exit(1)
        targets = [account]
    else:
        # Interactive prompt
        options = profiles + ["ALL"]
        choice = Prompt.ask("Choose account to check", choices=options, default="ALL" if "ALL" in options else options[0])
        if choice == "ALL":
            targets = profiles
        else:
            targets = [choice]
            
    console.print(f"\\n[cyan]Fetching billing report for the last {days} days...[/cyan]")
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    
    table = Table(title=f"Workspace Usage (Last {days} Days)")
    table.add_column("Account", style="magenta")
    table.add_column("Environment", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Cost (USD)", style="red", justify="right")
    
    global_total = 0
    
    for p in targets:
        token_id = doc[p].get("token_id")
        token_secret = doc[p].get("token_secret")
        # Ensure they are str
        if not token_id or not token_secret:
            continue
            
        try:
            client = Client.from_credentials(str(token_id), str(token_secret))
            reports = workspace_billing_report(start=start_time, resolution="d", client=client)
            
            p_total = 0
            # Aggregate per environment
            env_costs = {}
            for r in reports:
                env = r.get("environment_name", "Unknown")
                cost = float(r.get("cost", 0))
                desc = r.get("description", "")
                
                key = f"{env} - {desc}"
                env_costs[key] = env_costs.get(key, 0) + cost
                p_total += cost
                global_total += cost
                
            for name, cost in sorted(env_costs.items(), key=lambda x: x[1], reverse=True):
                if cost > 0:
                    table.add_row(p, name.split(" - ")[0], name.split(" - ")[1], f"${cost:.4f}")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch billing for '{p}': {e}[/yellow]")
            
    console.print()
    console.print(table)
    console.print(f"\\n[bold green]Total Global Accumulated Cost: ${global_total:.4f}[/bold green]")
    console.print("[dim]Note: Each Modal Starter Tier account provides $30/month in credits.[/dim]")
