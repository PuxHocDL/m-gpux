"""``image`` plugin — prebuild and publish reusable Modal Images.

A published image starts in seconds instead of re-running ``pip install`` on
every cold start. ``hub`` and ``dev`` offer published images as a base when the
selected account has one.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Optional

import typer
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.images import forget_image, list_images, record_image
from m_gpux.core.modal_cli import modal_cmd, modal_env
from m_gpux.core.plugin import PluginBase
from m_gpux.core.profiles import get_all_profiles, select_profile
from m_gpux.core.workspaces import WorkspaceError, for_each, resolve_targets, short_error

app = typer.Typer(no_args_is_help=True)

# Packages every m-gpux interactive image needs (ttyd shell, sshd for dev, basics).
BASE_APT = ["git", "curl", "wget", "tmux", "htop", "openssh-server", "build-essential"]

BUILD_SCRIPT = """
import modal

image = (
    modal.Image.debian_slim(python_version=__PYTHON__)
    .apt_install(*__APT__)
    __PIP__
)
app = modal.App.lookup("m-gpux-images", create_if_missing=True)
with modal.enable_output():
    image.build(app)
image.publish(__NAME__)
print("PUBLISHED", image.object_id)
"""


def _split(csv: str) -> list[str]:
    return [p.strip() for p in csv.split(",") if p.strip()]


def build_script(name: str, python: str, requirements: Optional[str], pip_pkgs: list[str], apt_pkgs: list[str]) -> str:
    """The standalone script that builds and publishes one image."""
    pip_expr = ""
    if requirements:
        pip_expr += f".pip_install_from_requirements({requirements!r})"
    if pip_pkgs:
        pip_expr += f".pip_install(*{pip_pkgs!r})"
    return (
        BUILD_SCRIPT.replace("__PYTHON__", repr(python))
        .replace("__APT__", repr(BASE_APT + apt_pkgs))
        .replace("__PIP__", pip_expr)
        .replace("__NAME__", repr(name))
    )


def _publish_to(profile: str, script: str) -> bool:
    runner = "modal_image_build.py"
    with open(runner, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)
    env = modal_env(profile)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    try:
        return subprocess.run([sys.executable, runner], env=env).returncode == 0
    finally:
        try:
            os.remove(runner)
        except OSError:
            pass


@app.command("build")
def build_command(
    name: str = typer.Argument(..., help="Image name, optionally with a tag: 'torch' or 'torch:2.8'"),
    python: str = typer.Option("3.12", "--python", help="Python version"),
    requirements: Optional[str] = typer.Option(None, "--requirements", "-r", help="requirements.txt to bake in"),
    pip: str = typer.Option("", "--pip", help="Extra pip packages, comma-separated"),
    apt: str = typer.Option("", "--apt", help="Extra apt packages, comma-separated"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile to publish to"),
    all_accounts: bool = typer.Option(False, "--all", help="Publish to every configured profile"),
) -> None:
    """Build an image once and publish it under NAME for fast reuse."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(:[A-Za-z0-9._-]+)?", name):
        console.print("[red]Use letters, digits, '.', '_' or '-' (optionally ':tag').[/red]")
        raise typer.Exit(1)

    pip_pkgs = _split(pip)
    apt_pkgs = _split(apt)
    req = None
    if requirements:
        if not os.path.exists(requirements):
            console.print(f"[red]{requirements} not found.[/red]")
            raise typer.Exit(1)
        req = os.path.abspath(requirements).replace("\\", "/")
    script = build_script(name, python, req, pip_pkgs, apt_pkgs)

    if all_accounts:
        targets = get_all_profiles()
    elif account:
        targets = [account]
    else:
        chosen = select_profile()
        if chosen is None:
            raise typer.Exit(1)
        targets = [chosen]

    if not targets:
        console.print("[red]No configured Modal profiles found. Run `m-gpux account add` first.[/red]")
        raise typer.Exit(1)

    summary = (
        f"py{python}"
        + (f" + {os.path.basename(requirements)}" if requirements else "")
        + (f" + {', '.join(pip_pkgs)}" if pip_pkgs else "")
    )
    ok = 0
    for profile in targets:
        console.print(f"\n[bold cyan]Building '{name}' on {profile}...[/bold cyan]")
        if _publish_to(profile, script):
            # The recipe lets `image sync` rebuild it on workspaces that lack it.
            record_image(
                name,
                profile,
                python=python,
                summary=summary,
                recipe={"requirements": req, "pip": pip_pkgs, "apt": apt_pkgs},
            )
            console.print(f"[green]Published '{name}' to {profile}.[/green]")
            ok += 1
        else:
            console.print(f"[red]Build failed on {profile}.[/red]")
    console.print(
        f"\n[bold]{ok}/{len(targets)} published.[/bold] "
        "[dim]`m-gpux hub` and `m-gpux dev` will offer it as a base image.[/dim]"
    )
    if ok < len(targets):
        raise typer.Exit(1)


def _published_in(names: list[str]):
    def check(_profile: str, client) -> set[str]:
        import modal
        from modal.exception import NotFoundError

        present = set()
        for image_name in names:
            try:
                modal.Image.from_name(image_name, client=client).hydrate()
                present.add(image_name)
            except NotFoundError:
                pass
        return present

    return check


def _targets(spec: Optional[str], *, default_active: bool = True) -> list[str]:
    try:
        return resolve_targets(spec, default_active=default_active)
    except WorkspaceError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command("status")
def status_command(
    names: Optional[list[str]] = typer.Argument(None, help="Image names (default: every image m-gpux built)."),
    to: Optional[str] = typer.Option(None, "--to", help="Profiles: 'all' (default), or a comma list."),
) -> None:
    """Which workspace has which published image (checked on Modal, not just locally)."""
    wanted = list(names or sorted(list_images()))
    if not wanted:
        console.print("[yellow]No images to check. Build one with: m-gpux image build NAME --pip ...[/yellow]")
        return
    profiles = _targets(to, default_active=False)
    with console.status(f"Checking {len(wanted)} image(s) in {len(profiles)} workspace(s)..."):
        found = for_each(profiles, _published_in(wanted))
    table = Table(title="Images per workspace")
    table.add_column("Image", style="cyan")
    for profile in profiles:
        table.add_column(profile, justify="center")
    for image_name in wanted:
        cells = []
        for profile in profiles:
            result = found[profile]
            if isinstance(result, Exception):
                cells.append("[red]error[/red]")
            else:
                cells.append("[green]✓[/green]" if image_name in result else "[dim]—[/dim]")
        table.add_row(image_name, *cells)
    console.print(table)
    for profile, result in found.items():
        if isinstance(result, Exception):
            console.print(f"[red]{profile}: {short_error(result)}[/red]")


@app.command("sync")
def sync_command(
    name: str = typer.Argument(..., help="An image built with `m-gpux image build`."),
    to: str = typer.Option("all", "--to", help="Profiles: 'all' (default) or a comma list."),
    force: bool = typer.Option(False, "--force", help="Rebuild even where the image already exists."),
) -> None:
    """Build an image on every target workspace that does not have it yet."""
    meta = list_images().get(name)
    if not meta:
        console.print(f"[red]'{name}' was not built with m-gpux. Build it first: m-gpux image build {name} ...[/red]")
        raise typer.Exit(1)
    recipe = meta.get("recipe")
    if not isinstance(recipe, dict):
        console.print(
            f"[red]'{name}' was built before m-gpux recorded image recipes.[/red] "
            f"[dim]Rebuild it once with `m-gpux image build {name} ... --all`.[/dim]"
        )
        raise typer.Exit(1)
    requirements = recipe.get("requirements")
    if requirements and not os.path.exists(requirements):
        console.print(f"[red]{requirements} (from the recipe) no longer exists.[/red]")
        raise typer.Exit(1)
    profiles = _targets(to)
    if not force:
        with console.status("Checking which workspaces already have it..."):
            found = for_each(profiles, _published_in([name]))
        profiles = [p for p in profiles if not (isinstance(found[p], set) and name in found[p])]
        if not profiles:
            console.print(f"[green]'{name}' is already published to every target workspace.[/green]")
            return
    script = build_script(
        name, meta.get("python", "3.12"), requirements, list(recipe.get("pip", [])), list(recipe.get("apt", []))
    )
    ok = 0
    for profile in profiles:
        console.print(f"\n[bold cyan]Building '{name}' on {profile}...[/bold cyan]")
        if _publish_to(profile, script):
            record_image(name, profile)
            ok += 1
            console.print(f"[green]Published '{name}' to {profile}.[/green]")
        else:
            console.print(f"[red]Build failed on {profile}.[/red]")
    console.print(f"\n[bold]{ok}/{len(profiles)} built.[/bold]")
    if ok < len(profiles):
        raise typer.Exit(1)


@app.command("list")
def list_command(
    remote: bool = typer.Option(False, "--remote", help="Also list names Modal knows for the active profile"),
) -> None:
    """List images published with m-gpux."""
    images = list_images()
    if not images:
        console.print("[yellow]No published images yet. Try: m-gpux image build torch --pip torch,numpy[/yellow]")
    else:
        table = Table(title="Published images")
        table.add_column("Name", style="cyan")
        table.add_column("Contents")
        table.add_column("Accounts", style="magenta")
        table.add_column("Updated", style="dim")
        for name, meta in sorted(images.items()):
            table.add_row(
                name, meta.get("summary", ""), ", ".join(meta.get("profiles", [])), meta.get("updated_at", "")
            )
        console.print(table)
    if remote:
        subprocess.run(modal_cmd("image", "names", "list"))


@app.command("forget")
def forget_command(name: str) -> None:
    """Remove an image from m-gpux's list (the published name stays on Modal)."""
    if forget_image(name):
        console.print(f"[green]Forgot '{name}'.[/green]")
    else:
        console.print(f"[yellow]'{name}' is not in the list.[/yellow]")


class ImagePlugin(PluginBase):
    name = "image"
    help = "Prebuild & publish reusable images for near-instant starts."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
