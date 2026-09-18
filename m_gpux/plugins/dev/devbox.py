"""Dev containers on Modal Sandboxes.

A dev box is a long-lived Sandbox running ``sshd``, with the project copied to
``/workspace``. It can be paused (filesystem snapshot → terminate) and resumed
later from that snapshot, so installed packages and edited files survive.

Local state lives in ``~/.m-gpux/dev.json``; the SSH key m-gpux uses lives in
``~/.m-gpux/ssh/``; each box gets a ``Host m-gpux-<name>`` block in
``~/.ssh/config`` so ``ssh`` and VS Code Remote-SSH just work.
"""

from __future__ import annotations

import fnmatch
import io
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from m_gpux.core.console import console
from m_gpux.core.ignore import to_recursive_ignore
from m_gpux.core.profiles import load_config
from m_gpux.core.state import STATE_DIR, _read_json, _write_json, utc_now

DEV_APP_NAME = "m-gpux-dev"
DEV_TAG = "m-gpux-dev"
DEV_STATE_PATH = STATE_DIR / "dev.json"
SSH_DIR = STATE_DIR / "ssh"
KEY_PATH = SSH_DIR / "id_ed25519"
KNOWN_HOSTS_PATH = SSH_DIR / "known_hosts"
SSH_CONFIG_PATH = Path.home() / ".ssh" / "config"
WORKDIR = "/workspace"
MAX_TIMEOUT_HOURS = 24
DEFAULT_EXCLUDES = [
    ".venv", "venv", "__pycache__", ".git", "node_modules", ".mypy_cache",
    ".pytest_cache", "*.egg-info", ".tox", "dist", "build",
]

# Entrypoint: install the key, start sshd in the foreground (it keeps the box alive).
SETUP_SCRIPT = r"""
set -e
mkdir -p /root/.ssh /run/sshd /etc/ssh/sshd_config.d
if [ -n "$MGPUX_AUTHORIZED_KEY" ]; then
  printf '%s\n' "$MGPUX_AUTHORIZED_KEY" > /root/.ssh/authorized_keys
  chmod 700 /root/.ssh
  chmod 600 /root/.ssh/authorized_keys
  # SSH sessions otherwise lose the container env (CUDA paths, HF cache, ...).
  env | grep -v -e '^MGPUX_AUTHORIZED_KEY=' -e '^_=' -e '^PWD=' -e '^SHLVL=' -e '^HOME=' \
      > /root/.ssh/environment || true
  ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1 || ssh-keygen -A
  cat > /etc/ssh/sshd_config.d/mgpux.conf <<'EOF'
PermitRootLogin prohibit-password
PasswordAuthentication no
PermitUserEnvironment yes
ClientAliveInterval 30
EOF
  grep -q 'm-gpux workdir' /root/.bashrc 2>/dev/null || \
    printf '\n# m-gpux workdir\ncd /workspace 2>/dev/null || true\n' >> /root/.bashrc
  exec /usr/sbin/sshd -D -e
fi
exec sleep infinity
"""


# ─── State ─────────────────────────────────────────────────────


def load_boxes() -> dict[str, dict[str, Any]]:
    data = _read_json(DEV_STATE_PATH, {})
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def save_box(name: str, box: dict[str, Any]) -> None:
    boxes = load_boxes()
    box["updated_at"] = utc_now()
    boxes[name] = box
    _write_json(DEV_STATE_PATH, boxes)


def delete_box(name: str) -> None:
    boxes = load_boxes()
    boxes.pop(name, None)
    _write_json(DEV_STATE_PATH, boxes)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40] or "dev"


def resolve_name(name: Optional[str]) -> str:
    """Pick the box to act on: explicit name, else this folder's box, else the only box."""
    boxes = load_boxes()
    if name:
        if name not in boxes:
            raise KeyError(f"No dev box named '{name}'. See `m-gpux dev list`.")
        return name
    here = slugify(Path.cwd().name)
    if here in boxes:
        return here
    if len(boxes) == 1:
        return next(iter(boxes))
    if not boxes:
        raise KeyError("No dev boxes yet. Create one with `m-gpux dev up`.")
    raise KeyError(f"Several dev boxes exist ({', '.join(boxes)}); pass a name.")


# ─── Modal plumbing ────────────────────────────────────────────


def client_for(profile: str):
    from modal.client import Client

    doc = load_config()
    if profile not in doc:
        raise KeyError(f"Profile '{profile}' not found in ~/.modal.toml")
    return Client.from_credentials(str(doc[profile]["token_id"]), str(doc[profile]["token_secret"]))


def build_image(client, *, base_image: Optional[str], python_version: str, local_dir: Optional[str],
                excludes: list[str], requirements: Optional[str]):
    import modal

    if base_image:
        image = modal.Image.from_name(base_image, client=client)
    else:
        image = modal.Image.debian_slim(python_version=python_version)
    image = image.apt_install("openssh-server", "git", "curl", "wget", "tmux", "htop")
    if requirements:
        image = image.pip_install_from_requirements(requirements)
    if local_dir:
        image = image.add_local_dir(local_dir, WORKDIR, copy=True, ignore=to_recursive_ignore(excludes))
    return image


def public_ip() -> Optional[str]:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as r:
            ip = r.read().decode().strip()
        return ip if re.fullmatch(r"[0-9a-fA-F:.]+", ip) else None
    except Exception:
        return None


def create_sandbox(client, name: str, image, box: dict[str, Any]):
    """Start the Sandbox for *box* and wait until sshd accepts connections."""
    import modal

    app = modal.App.lookup(DEV_APP_NAME, create_if_missing=True, client=client)
    kwargs: dict[str, Any] = {
        "app": app,
        "image": image,
        "timeout": int(box["timeout_hours"] * 3600),
        "workdir": WORKDIR,
        "tags": {DEV_TAG: name},
        "client": client,
    }
    if box.get("gpu"):
        kwargs["gpu"] = box["gpu"]
    if box.get("cpu"):
        kwargs["cpu"] = float(box["cpu"])
    if box.get("memory"):
        kwargs["memory"] = int(box["memory"])
    if box.get("allow_cidr"):
        kwargs["inbound_cidr_allowlist"] = [box["allow_cidr"]]
    if box.get("ssh", True):
        kwargs["env"] = {"MGPUX_AUTHORIZED_KEY": ensure_ssh_key()}
        kwargs["unencrypted_ports"] = [22]
        kwargs["readiness_probe"] = modal.Probe.with_tcp(22)

    with modal.enable_output():
        sb = modal.Sandbox.create("bash", "-c", SETUP_SCRIPT, **kwargs)
    if box.get("ssh", True):
        sb.wait_until_ready(timeout=300)
        host, port = sb.tunnels(timeout=60)[22].tcp_socket
        box["ssh_host"], box["ssh_port"] = host, int(port)
        write_ssh_config(name, host, int(port))
    box["sandbox_id"] = sb.object_id
    box["state"] = "running"
    box["started_at"] = time.time()
    return sb


def get_sandbox(box: dict[str, Any]):
    import modal

    if not box.get("sandbox_id"):
        return None
    sb = modal.Sandbox.from_id(box["sandbox_id"], client=client_for(box["profile"]))
    return sb if sb.poll() is None else None


# ─── SSH ───────────────────────────────────────────────────────


def ensure_ssh_key() -> str:
    """Create m-gpux's own ed25519 key on first use; return the public key text."""
    pub = KEY_PATH.with_suffix(".pub")
    if not pub.exists():
        if not shutil.which("ssh-keygen"):
            raise RuntimeError("ssh-keygen not found. Install the OpenSSH client, or use --no-ssh.")
        SSH_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "m-gpux-dev", "-f", str(KEY_PATH)],
            check=True,
        )
    return pub.read_text(encoding="utf-8").strip()


def ssh_host_alias(name: str) -> str:
    return f"m-gpux-{name}"


def _config_block(name: str, host: str, port: int) -> str:
    key = str(KEY_PATH).replace("\\", "/")
    known = str(KNOWN_HOSTS_PATH).replace("\\", "/")
    return (
        f"# >>> m-gpux dev: {name}\n"
        f"Host {ssh_host_alias(name)}\n"
        f"    HostName {host}\n"
        f"    Port {port}\n"
        f"    User root\n"
        f'    IdentityFile "{key}"\n'
        f"    IdentitiesOnly yes\n"
        f"    StrictHostKeyChecking no\n"
        f'    UserKnownHostsFile "{known}"\n'
        f"    ServerAliveInterval 30\n"
        f"    LogLevel ERROR\n"
        f"# <<< m-gpux dev: {name}\n"
    )


def _strip_block(text: str, name: str) -> str:
    pattern = re.compile(
        rf"# >>> m-gpux dev: {re.escape(name)}\n.*?# <<< m-gpux dev: {re.escape(name)}\n", re.S
    )
    return pattern.sub("", text)


def write_ssh_config(name: str, host: str, port: int) -> None:
    SSH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = SSH_CONFIG_PATH.read_text(encoding="utf-8") if SSH_CONFIG_PATH.exists() else ""
    text = _strip_block(text, name)
    # Host blocks must come before any catch-all `Host *` the user may have.
    text = _config_block(name, host, port) + ("\n" + text if text.strip() else "")
    SSH_CONFIG_PATH.write_text(text, encoding="utf-8", newline="\n")
    # A resumed box has a new tunnel address; drop stale host keys for it.
    KNOWN_HOSTS_PATH.unlink(missing_ok=True)


def remove_ssh_config(name: str) -> None:
    if SSH_CONFIG_PATH.exists():
        text = SSH_CONFIG_PATH.read_text(encoding="utf-8")
        SSH_CONFIG_PATH.write_text(_strip_block(text, name), encoding="utf-8", newline="\n")


# ─── Sync ──────────────────────────────────────────────────────


def _excluded(rel: str, patterns: list[str]) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(fnmatch.fnmatch(part, pat) for part in parts for pat in patterns) or any(
        fnmatch.fnmatch(rel, pat) for pat in patterns
    )


def pack_dir(local_dir: str, excludes: list[str], since: float = 0.0) -> tuple[bytes, int]:
    """tar.gz of *local_dir* (files modified after *since*), minus excluded paths."""
    buf = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(local_dir):
            rel_root = os.path.relpath(root, local_dir)
            dirs[:] = [d for d in dirs if not _excluded(os.path.normpath(os.path.join(rel_root, d)), excludes)]
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.normpath(os.path.join(rel_root, fname)).replace("\\", "/")
                if _excluded(rel, excludes) or os.path.getmtime(full) <= since:
                    continue
                tar.add(full, arcname=rel)
                count += 1
    return buf.getvalue(), count


def push(sb, local_dir: str, excludes: list[str], since: float = 0.0) -> int:
    data, count = pack_dir(local_dir, excludes, since)
    if count == 0:
        return 0
    remote = "/tmp/mgpux-push.tgz"
    sb.filesystem.write_bytes(data, remote)
    p = sb.exec("bash", "-c", f"tar xzf {remote} -C {WORKDIR} && rm -f {remote}")
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(p.stderr.read())
    return count


def pull(sb, dest: str, excludes: list[str]) -> int:
    remote = "/tmp/mgpux-pull.tgz"
    exclude_args = " ".join(f"--exclude='{pat}'" for pat in excludes)
    p = sb.exec("bash", "-c", f"tar czf {remote} {exclude_args} -C {WORKDIR} .")
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(p.stderr.read())
    data = sb.filesystem.read_bytes(remote)
    sb.exec("rm", "-f", remote).wait()
    dest_path = os.path.abspath(dest)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = []
        for m in tar.getmembers():
            target = os.path.abspath(os.path.join(dest_path, m.name))
            if not target.startswith(dest_path) or m.issym() or m.islnk():
                continue  # never write outside dest or follow links
            members.append(m)
            count += m.isfile()
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest_path, members=members, filter="data")
        else:
            tar.extractall(dest_path, members=members)
    return count
