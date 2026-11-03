"""``volume`` plugin — browse and move data in Modal Volumes on any account.

Listing and browsing use the SDK (in parallel across accounts); transfers and
deletes go through the ``modal volume`` CLI with ``MODAL_PROFILE`` pinned, so
progress bars and edge cases behave exactly like Modal's own tool.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Any, Optional

import typer
from rich.prompt import Confirm
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.modal_cli import modal_cmd, modal_env
from m_gpux.core.plugin import PluginBase
from m_gpux.core.workspaces import WorkspaceError, client_for, for_each, resolve_targets, short_error

app = typer.Typer(no_args_is_help=True)

HF_CACHE = "m-gpux-hf-cache"


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(1)


def _one(account: Optional[str]) -> str:
    try:
        return resolve_targets(account)[0]
    except WorkspaceError as exc:
        _fail(str(exc))
        raise


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def entries(account: str, name: str, path: str = "/", recursive: bool = False) -> list[dict[str, Any]]:
    """``[{path, type, size, mtime}]`` for a directory of a volume."""
    import modal

    volume = modal.Volume.from_name(name, client=client_for(account))
    out = []
    for entry in volume.listdir(path or "/", recursive=recursive):
        kind = getattr(entry.type, "name", str(entry.type)).lower()
        out.append({"path": entry.path, "type": kind, "size": int(entry.size or 0), "mtime": int(entry.mtime or 0)})
    return sorted(out, key=lambda e: (e["type"] != "directory", e["path"]))


def summarize_usage(files: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    """``[(top-level entry, bytes, files)]`` largest first, from a recursive listing."""
    totals: dict[str, list[int]] = {}
    for entry in files:
        if entry["type"] != "file":
            continue
        top = entry["path"].lstrip("/").split("/", 1)[0] or "/"
        bucket = totals.setdefault(top, [0, 0])
        bucket[0] += entry["size"]
        bucket[1] += 1
    return sorted(((k, v[0], v[1]) for k, v in totals.items()), key=lambda r: r[1], reverse=True)


@app.command("list")
def list_command(
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile(s): name, comma list or 'all'."),
    all_accounts: bool = typer.Option(False, "--all", help="Every account."),
) -> None:
    """Volumes per account."""
    try:
        profiles = resolve_targets("all" if all_accounts else account)
    except WorkspaceError as exc:
        _fail(str(exc))
        return

    def names(_profile: str, client) -> list[tuple[str, str]]:
        import modal

        rows = []
        for volume in modal.Volume.objects.list(client=client):
            created = ""
            try:
                info = volume.info()
                created = str(getattr(info, "created_at", "") or "")[:10]
            except Exception:
                pass
            rows.append((volume.name or "?", created))
        return rows

    with console.status(f"Listing volumes on {len(profiles)} account(s)..."):
        found = for_each(profiles, names)
    table = Table(title="Volumes")
    table.add_column("Account", style="magenta")
    table.add_column("Volume", style="cyan")
    table.add_column("Created", style="dim")
    for profile, result in found.items():
        if isinstance(result, Exception):
            table.add_row(profile, f"[red]{short_error(result)}[/red]", "")
            continue
        if not result:
            table.add_row(profile, "[dim]none[/dim]", "")
        for name, created in sorted(result):
            note = " [dim](shared HF cache)[/dim]" if name == HF_CACHE else ""
            table.add_row(profile, name + note, created)
    console.print(table)


@app.command("ls")
def ls_command(
    name: str = typer.Argument(..., help="Volume name."),
    path: str = typer.Argument("/", help="Directory inside the volume."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: active)."),
) -> None:
    """List a directory of a volume."""
    profile = _one(account)
    try:
        items = entries(profile, name, path)
    except Exception as exc:
        _fail(f"{name}:{path} on {profile}: {short_error(exc)}")
        return
    table = Table(title=f"{name}:{path} ({profile})")
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Modified", style="dim")
    for e in items:
        label = e["path"].rstrip("/").split("/")[-1] + ("/" if e["type"] == "directory" else "")
        modified = datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M") if e["mtime"] else ""
        table.add_row(label, "" if e["type"] == "directory" else human_size(e["size"]), modified)
    console.print(table if items else f"[dim]{name}:{path} is empty.[/dim]")


@app.command("du")
def du_command(
    name: str = typer.Argument(..., help="Volume name."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: active)."),
) -> None:
    """Space used per top-level folder."""
    profile = _one(account)
    with console.status(f"Walking {name}..."):
        try:
            files = entries(profile, name, "/", recursive=True)
        except Exception as exc:
            _fail(f"{name} on {profile}: {short_error(exc)}")
            return
    rows = summarize_usage(files)
    table = Table(title=f"{name} ({profile})")
    table.add_column("Entry", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Files", justify="right")
    for top, size, count in rows:
        table.add_row(top, human_size(size), str(count))
    total = sum(r[1] for r in rows)
    table.add_row("[bold]total[/bold]", f"[bold]{human_size(total)}[/bold]", str(sum(r[2] for r in rows)))
    console.print(table)


def _modal(profile: str, *args: str) -> None:
    result = subprocess.run(modal_cmd("volume", *args), env=modal_env(profile))
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command("get")
def get_command(
    name: str = typer.Argument(..., help="Volume name."),
    remote: str = typer.Argument(..., help="File or folder in the volume."),
    local: str = typer.Argument(".", help="Local destination."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: active)."),
    force: bool = typer.Option(False, "--force", help="Overwrite local files."),
) -> None:
    """Download from a volume."""
    _modal(_one(account), "get", *(["--force"] if force else []), name, remote, local)


@app.command("put")
def put_command(
    name: str = typer.Argument(..., help="Volume name (created if missing)."),
    local: str = typer.Argument(..., help="Local file or folder."),
    remote: str = typer.Argument("/", help="Destination in the volume."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: active)."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Upload to a volume."""
    profile = _one(account)
    subprocess.run(modal_cmd("volume", "create", name), env=modal_env(profile), capture_output=True)
    _modal(profile, "put", *(["--force"] if force else []), name, local, remote)


@app.command("rm")
def rm_command(
    name: str = typer.Argument(..., help="Volume name."),
    remote: str = typer.Argument(..., help="File or folder to delete."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Delete a folder."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: active)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask."),
) -> None:
    """Delete a file or folder inside a volume."""
    profile = _one(account)
    if not yes and not Confirm.ask(f"Delete {name}:{remote} on {profile}?", default=False):
        raise typer.Exit(0)
    _modal(profile, "rm", *(["-r"] if recursive else []), name, remote)


@app.command("delete")
def delete_command(
    name: str = typer.Argument(..., help="Volume to delete with all its data."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: active)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask."),
) -> None:
    """Delete a whole volume (irreversible)."""
    profile = _one(account)
    if not yes and not Confirm.ask(f"Delete volume '{name}' and ALL its data on {profile}?", default=False):
        raise typer.Exit(0)
    _modal(profile, "delete", "--yes", name)


class VolumePlugin(PluginBase):
    name = "volume"
    help = "Browse, upload, download and clean Modal Volumes on any account."
    rich_help_panel = "Workspace"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
