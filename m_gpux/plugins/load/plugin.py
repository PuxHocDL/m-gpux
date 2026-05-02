import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
import subprocess
import json
import time
import os
import tomlkit
from typing import Optional

app = typer.Typer(no_args_is_help=True)
console = Console()

MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")

LOAD_SCRIPT = '''
import modal
import subprocess
import json
import time
import sys

app = modal.App("m-gpux-load-monitor")
image = modal.Image.debian_slim().pip_install("gputil", "psutil")

@app.function(image=image, {compute_spec}, timeout=120)
def collect_metrics():
    import GPUtil
    import psutil
    import platform

    metrics = {{}}

    # --- GPU metrics ---
    gpus = GPUtil.getGPUs()
    gpu_list = []
    for g in gpus:
        gpu_list.append({{
            "id": g.id,
            "name": g.name,
            "driver": g.driver,
            "memory_total_mb": round(g.memoryTotal, 1),
            "memory_used_mb": round(g.memoryUsed, 1),
            "memory_free_mb": round(g.memoryFree, 1),
            "memory_util_pct": round(g.memoryUtil * 100, 1),
            "gpu_util_pct": round(g.load * 100, 1),
            "temperature_c": g.temperature,
        }})
    metrics["gpus"] = gpu_list

    # --- CPU metrics ---
    metrics["cpu"] = {{
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "utilization_pct": psutil.cpu_percent(interval=1),
        "freq_mhz": round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else None,
        "processor": platform.processor() or platform.machine(),
    }}

    # --- Memory metrics ---
    mem = psutil.virtual_memory()
    metrics["memory"] = {{
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "utilization_pct": mem.percent,
    }}

    # --- Disk metrics ---
    disk = psutil.disk_usage("/")
    metrics["disk"] = {{
        "total_gb": round(disk.total / (1024**3), 2),
        "used_gb": round(disk.used / (1024**3), 2),
        "free_gb": round(disk.free / (1024**3), 2),
        "utilization_pct": disk.percent,
    }}

    # --- System info ---
    metrics["system"] = {{
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
    }}

    # --- Uptime / timing ---
    boot = psutil.boot_time()
    metrics["uptime_seconds"] = round(time.time() - boot, 1)

    print("__METRICS_JSON_START__")
    print(json.dumps(metrics))
    print("__METRICS_JSON_END__")
'''


def _load_profiles():
    if not os.path.exists(MODAL_CONFIG_PATH):
        return []
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    profiles = []
    for name in doc:
        is_active = doc[name].get("active", False)
        profiles.append((name, is_active))
    return profiles


def _get_active_profile() -> Optional[str]:
    profiles = _load_profiles()
    for name, is_active in profiles:
        if is_active:
            return name
    if profiles:
        return profiles[0][0]
    return None


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    empty = width - filled
    if pct >= 90:
        color = "red"
    elif pct >= 60:
        color = "yellow"
    else:
        color = "green"
    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}] {pct:.1f}%"


def _render_metrics(metrics: dict, gpu_type: str, elapsed: float) -> Panel:
    """Build a rich Panel with all metrics."""
    from rich.columns import Columns

    tables = []

    # --- GPU Table ---
    for g in metrics.get("gpus", []):
        gt = Table(title=f"GPU {g['id']}: {g['name']}", border_style="cyan", expand=True)
        gt.add_column("Metric", style="bold white", ratio=1)
        gt.add_column("Value", ratio=2)
        gt.add_row("Driver", str(g["driver"]))
        gt.add_row("VRAM Total", f"{g['memory_total_mb']:.0f} MB")
        gt.add_row("VRAM Used", f"{g['memory_used_mb']:.0f} MB")
        gt.add_row("VRAM Free", f"{g['memory_free_mb']:.0f} MB")
        gt.add_row("VRAM Util", _bar(g["memory_util_pct"]))
        gt.add_row("GPU Util", _bar(g["gpu_util_pct"]))
        gt.add_row("Temperature", f"{g['temperature_c']}°C" if g["temperature_c"] else "N/A")
        tables.append(gt)

    # --- CPU Table ---
    cpu = metrics.get("cpu", {})
    ct = Table(title="CPU", border_style="green", expand=True)
    ct.add_column("Metric", style="bold white", ratio=1)
    ct.add_column("Value", ratio=2)
    ct.add_row("Processor", str(cpu.get("processor", "N/A")))
    ct.add_row("Physical Cores", str(cpu.get("physical_cores", "N/A")))
    ct.add_row("Logical Cores", str(cpu.get("logical_cores", "N/A")))
    ct.add_row("Frequency", f"{cpu['freq_mhz']} MHz" if cpu.get("freq_mhz") else "N/A")
    ct.add_row("Utilization", _bar(cpu.get("utilization_pct", 0)))
    tables.append(ct)

    # --- Memory Table ---
    mem = metrics.get("memory", {})
    mt = Table(title="System Memory", border_style="magenta", expand=True)
    mt.add_column("Metric", style="bold white", ratio=1)
    mt.add_column("Value", ratio=2)
    mt.add_row("Total", f"{mem.get('total_gb', 0):.2f} GB")
    mt.add_row("Used", f"{mem.get('used_gb', 0):.2f} GB")
    mt.add_row("Available", f"{mem.get('available_gb', 0):.2f} GB")
    mt.add_row("Utilization", _bar(mem.get("utilization_pct", 0)))
    tables.append(mt)

    # --- Disk Table ---
    disk = metrics.get("disk", {})
    dt = Table(title="Disk", border_style="yellow", expand=True)
    dt.add_column("Metric", style="bold white", ratio=1)
    dt.add_column("Value", ratio=2)
    dt.add_row("Total", f"{disk.get('total_gb', 0):.2f} GB")
    dt.add_row("Used", f"{disk.get('used_gb', 0):.2f} GB")
    dt.add_row("Free", f"{disk.get('free_gb', 0):.2f} GB")
    dt.add_row("Utilization", _bar(disk.get("utilization_pct", 0)))
    tables.append(dt)

    # --- System / Timing ---
    sys_info = metrics.get("system", {})
    uptime = metrics.get("uptime_seconds", 0)
    st = Table(title="System & Timing", border_style="bright_blue", expand=True)
    st.add_column("Metric", style="bold white", ratio=1)
    st.add_column("Value", ratio=2)
    st.add_row("Platform", f"{sys_info.get('platform', '')} {sys_info.get('platform_release', '')}")
    st.add_row("Architecture", str(sys_info.get("architecture", "N/A")))
    st.add_row("Python", str(sys_info.get("python_version", "N/A")))
    st.add_row("Container Uptime", f"{uptime:.0f}s ({uptime/60:.1f} min)")
    st.add_row("Probe Round-trip", f"{elapsed:.1f}s")
    tables.append(st)

    from rich.columns import Columns
    grid = Columns(tables, equal=True, expand=True)
    return Panel(grid, title=f"[bold cyan]m-gpux load — {gpu_type}[/bold cyan]", border_style="bright_cyan", expand=True)


# Import the hub GPU/CPU lists so we stay in sync
from m_gpux.core import AVAILABLE_GPUS, AVAILABLE_CPUS


@app.command("probe")
def load_probe(
    gpu: str = typer.Option(None, "--gpu", "-g", help="GPU type to probe (e.g. T4, A100, H100). If omitted, shows picker."),
    cpu: int = typer.Option(None, "--cpu", "-c", help="CPU cores to probe (e.g. 2, 4, 8). If set, probes CPU-only."),
):
    """
    Spin up a short-lived Modal container and report GPU, CPU, memory, disk,
    and timing metrics back to the terminal.
    """
    from rich.prompt import Prompt
    from m_gpux.core.ui import arrow_select

    if gpu is None and cpu is None:
        console.print("\n[bold cyan]Select compute type to probe:[/bold cyan]")
        compute_options = [
            ("GPU", "Probe a GPU container"),
            ("CPU", "Probe a CPU-only container"),
        ]
        compute_idx = arrow_select(compute_options, title="Compute Type", default=0)

        if compute_idx == 1:
            # CPU mode
            cpu_keys = list(AVAILABLE_CPUS.keys())
            cpu_options = []
            for k in cpu_keys:
                cores, mem, desc = AVAILABLE_CPUS[k]
                cpu_options.append((f"{cores} cores", desc))
            cpu_idx = arrow_select(cpu_options, title="Select CPU", default=3)
            selected_cores, selected_memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
            compute_spec = f'cpu={selected_cores}, memory={selected_memory}'
            compute_label = f"CPU ({selected_cores} cores, {selected_memory} MB)"
        else:
            # GPU mode
            console.print("\n[bold cyan]Select GPU to probe:[/bold cyan]")
            gpu_options = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
            gpu_idx = arrow_select(gpu_options, title="Select GPU", default=1)
            gpu = list(AVAILABLE_GPUS.values())[gpu_idx][0]
            compute_spec = f'gpu="{gpu}"'
            compute_label = gpu
    elif cpu is not None:
        # CPU specified via CLI flag
        memory = cpu * 512  # scale memory with cores
        compute_spec = f'cpu={cpu}, memory={memory}'
        compute_label = f"CPU ({cpu} cores, {memory} MB)"
    else:
        # GPU specified via CLI flag
        compute_spec = f'gpu="{gpu}"'
        compute_label = gpu

    console.print(f"\n[cyan]Probing [bold]{compute_label}[/bold] — spinning up container...[/cyan]")

    script_content = LOAD_SCRIPT.replace("{compute_spec}", compute_spec)
    runner_file = "_m_gpux_load_probe.py"

    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(script_content)

    t0 = time.time()
    try:
        result = subprocess.run(
            ["modal", "run", runner_file],
            capture_output=True, text=True, timeout=300,
        )
        elapsed = time.time() - t0

        output = result.stdout + result.stderr

        if "__METRICS_JSON_START__" in output:
            json_str = output.split("__METRICS_JSON_START__")[1].split("__METRICS_JSON_END__")[0].strip()
            metrics = json.loads(json_str)
            panel = _render_metrics(metrics, compute_label, elapsed)
            console.print()
            console.print(panel)
        else:
            console.print(f"[bold red]Could not parse metrics from container output.[/bold red]")
            if output.strip():
                console.print(Panel(output.strip(), title="Raw Output", border_style="red"))

        if result.returncode != 0 and "__METRICS_JSON_START__" not in output:
            console.print(f"[bold red]modal run exited with code {result.returncode}[/bold red]")

    except subprocess.TimeoutExpired:
        console.print("[bold red]Probe timed out after 300s.[/bold red]")
    except FileNotFoundError:
        console.print("[bold red]'modal' CLI not found. Make sure Modal is installed.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
    finally:
        try:
            os.remove(runner_file)
        except OSError:
            pass


# ─── Plugin registration ──────────────────────────────────────
from m_gpux.core.plugin import PluginBase as _PluginBase


class LoadPlugin(_PluginBase):
    name = "load"
    help = "Probe a GPU container and display live hardware metrics."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        root_app.add_typer(
            app,
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )
