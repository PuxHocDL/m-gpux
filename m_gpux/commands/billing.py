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

@app.command("usage")
def check_usage(days: int = typer.Option(30, help="Number of days to check usage for")):
    """Check workspace usage cost for the customized period."""
    console.print(f"[cyan]Fetching billing report for the last {days} days...[/cyan]")
    
    try:
        start_time = datetime.now(timezone.utc) - timedelta(days=days)
        reports = workspace_billing_report(start=start_time, resolution="d")
        
        table = Table(title=f"Workspace Usage (Last {days} Days)")
        table.add_column("Environment", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Cost (USD)", style="red", justify="right")
        
        env_costs = {}
        total_cost = 0
        
        for r in reports:
            env = r.get("environment_name", "Unknown")
            cost = float(r.get("cost", 0))
            desc = r.get("description", "")
            
            key = f"{env} - {desc}"
            env_costs[key] = env_costs.get(key, 0) + cost
            total_cost += cost
            
        for name, cost in sorted(env_costs.items(), key=lambda x: x[1], reverse=True):
            if cost > 0:
                table.add_row(name.split(" - ")[0], name.split(" - ")[1], f"${cost:.4f}")
                
        console.print(table)
        console.print(f"\n[bold green]Total Accumulated Cost: ${total_cost:.4f}[/bold green]")
        console.print("[dim]Note: Modal Starter Tier provides $30/month in credits.[/dim]")
    except Exception as e:
        console.print(f"[red]Error fetching billing report: {e}[/red]")
        console.print("[yellow]Try using `m-gpux billing open` to check the web dashboard instead.[/yellow]")
