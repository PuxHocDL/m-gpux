"""m-gpux compose plugin — Deploy Docker Compose stacks on Modal.

Translates a docker-compose.yml into a single Modal container that runs all
services as managed subprocesses with proper hostname resolution via /etc/hosts.

This overcomes Modal's single-container limitation by:
1. Parsing docker-compose.yml to extract services, ports, envs, commands
2. Installing required service binaries (redis, nginx, postgres, etc.)
3. Writing /etc/hosts entries so service names resolve to 127.0.0.1
4. Running all services as background processes with a supervisor loop
5. Exposing the main service port via a Modal tunnel
"""

import os
import sys
import hashlib
import base64
import shlex
import subprocess
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from m_gpux.core.ui import arrow_select
from m_gpux.core.runner import execute_modal_temp_script
from m_gpux.core.state import new_session_id, save_preset
from m_gpux.core.metrics import FUNCTIONS as _METRICS_FUNCTIONS

app = typer.Typer(no_args_is_help=True)
console = Console()

MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")

# ---------------------------------------------------------------------------
# Known service images → apt packages / install commands
# ---------------------------------------------------------------------------
SERVICE_INSTALLERS: dict[str, dict] = {
    "redis": {
        "apt": ["redis-server"],
        "start_cmd": "redis-server --bind 127.0.0.1 --port {port} --daemonize no{extra_args}",
        "default_port": 6379,
        "detect_images": ["redis", "bitnami/redis", "redis/redis-stack"],
    },
    "postgres": {
        "apt": ["postgresql", "postgresql-client"],
        "start_cmd": (
            "su -c \"pg_ctlcluster $(pg_lsclusters -h | head -1 | awk '{print $1}') main start\" postgres "
            "&& tail -f /var/log/postgresql/*.log"
        ),
        "default_port": 5432,
        "detect_images": ["postgres", "bitnami/postgresql"],
        "setup_cmds": [
            "su -c \"pg_ctlcluster $(pg_lsclusters -h | head -1 | awk '{print $1}') main start\" postgres",
        ],
    },
    "memcached": {
        "apt": ["memcached"],
        "start_cmd": "memcached -u root -l 127.0.0.1 -p {port}",
        "default_port": 11211,
        "detect_images": ["memcached"],
    },
    "nginx": {
        "apt": ["nginx"],
        "start_cmd": "nginx -g 'daemon off;' -c /tmp/nginx_compose.conf",
        "default_port": 80,
        "detect_images": ["nginx"],
    },
    "rabbitmq": {
        "apt": ["rabbitmq-server"],
        "start_cmd": "rabbitmq-server",
        "default_port": 5672,
        "detect_images": ["rabbitmq"],
    },
    "mongodb": {
        "apt": ["mongodb-org"],
        "start_cmd": "mongod --bind_ip 127.0.0.1 --port {port}",
        "default_port": 27017,
        "detect_images": ["mongo", "mongodb/mongodb-community-server"],
        "extra_setup": (
            "curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | "
            "gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg && "
            "echo 'deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] "
            "https://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main' "
            "> /etc/apt/sources.list.d/mongodb-org-7.0.list && apt-get update"
        ),
    },
}


def _load_profiles():
    """Load all profiles from ~/.modal.toml."""
    import tomlkit
    if not os.path.exists(MODAL_CONFIG_PATH):
        return []
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    profiles = []
    for name in doc:
        is_active = doc[name].get("active", False)
        profiles.append((name, is_active))
    return profiles


def _select_profile() -> Optional[str]:
    """Interactive profile picker."""
    profiles = _load_profiles()
    if not profiles:
        console.print("[yellow]No Modal profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return None
    if len(profiles) == 1:
        name, _ = profiles[0]
        console.print(f"  Using profile: [bold cyan]{name}[/bold cyan]")
        return name

    env_profile = os.environ.get("MGPUX_PROFILE", "").strip()
    if env_profile:
        names = [name for name, _ in profiles]
        if env_profile in names:
            console.print(f"  Using profile from MGPUX_PROFILE: [bold cyan]{env_profile}[/bold cyan]")
            return env_profile
        console.print(f"[yellow]MGPUX_PROFILE={env_profile!r} not found among configured profiles, falling back to picker.[/yellow]")

    console.print("\n[bold cyan]Select Workspace / Profile[/bold cyan]")
    profile_options = [("AUTO", "Smart pick (most credit remaining)")]
    for name, is_active in profiles:
        marker = " (active)" if is_active else ""
        profile_options.append((name, f"Modal profile{marker}"))

    choice_idx = arrow_select(profile_options, title="Select Workspace", default=0)
    if choice_idx == 0:
        from m_gpux.core.profiles import get_best_profile
        console.print("  [cyan]Scanning all accounts for best balance...[/cyan]")
        best_name, best_remaining = get_best_profile()
        if best_name is None:
            console.print("[bold red]Could not determine best profile.[/bold red]")
            return None
        console.print(f"  [bold green]Auto-selected: {best_name} (${best_remaining:.2f} remaining)[/bold green]")
        return best_name

    selected_name, _ = profiles[choice_idx - 1]
    console.print(f"  Using profile: [bold cyan]{selected_name}[/bold cyan]")
    return selected_name


def _activate_profile(profile_name: str):
    """Activate the given profile via `modal profile activate`."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    subprocess.run(
        ["modal", "profile", "activate", profile_name],
        capture_output=True, text=True, env=env,
    )


def _find_compose_file() -> Optional[str]:
    """Find docker-compose.yml or compose.yml in current directory."""
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        if os.path.exists(name):
            return name
    return None


def _parse_compose(path: str) -> dict:
    """Parse a docker-compose YAML file. Returns the raw dict."""
    try:
        import yaml
    except ImportError:
        console.print("[bold red]PyYAML is required for compose parsing.[/bold red]")
        console.print("Install it: [bold]pip install pyyaml[/bold]")
        raise typer.Exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "services" not in data:
        console.print(f"[bold red]No 'services' key found in {path}[/bold red]")
        raise typer.Exit(1)

    return data


def _detect_service_type(service_name: str, service_config: dict) -> Optional[str]:
    """Detect which known service type a compose service maps to."""
    image = service_config.get("image", "")
    image_base = image.split(":")[0].lower() if image else ""

    # Check by image name
    for svc_type, info in SERVICE_INSTALLERS.items():
        for pattern in info["detect_images"]:
            if pattern in image_base:
                return svc_type

    # Check by service name — only match if the name IS the service type
    # (avoid false positives like "dev" matching nothing)
    name_lower = service_name.lower().strip("-_")
    for svc_type in SERVICE_INSTALLERS:
        if name_lower == svc_type:
            return svc_type

    # Also check build context paths for infra services
    build = service_config.get("build", {})
    if isinstance(build, dict):
        context = build.get("context", "").lower()
        dockerfile = build.get("dockerfile", "").lower()
    elif isinstance(build, str):
        context = build.lower()
        dockerfile = ""
    else:
        context = dockerfile = ""

    for svc_type in SERVICE_INSTALLERS:
        if svc_type in context or svc_type in dockerfile:
            return svc_type

    return None


def _command_to_shell(command) -> str:
    """Convert a compose command (string or list) to a proper shell command string."""
    if not command:
        return ""
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        # For list commands like ["bash", "-lc", "sleep infinity"]
        # we need to properly quote arguments that contain spaces
        return " ".join(shlex.quote(str(arg)) for arg in command)
    return str(command)


def _extract_dockerfile_workdir(service_config: dict, compose_dir: str = ".") -> str:
    """Extract WORKDIR from Dockerfile for the target build stage.

    Returns the last WORKDIR found in the target stage (or final stage),
    or empty string if not found.
    """
    import re

    build = service_config.get("build", {})
    if not build:
        return ""

    if isinstance(build, str):
        context = build
        dockerfile_path = "Dockerfile"
        target = ""
    elif isinstance(build, dict):
        context = build.get("context", ".")
        dockerfile_path = build.get("dockerfile", "Dockerfile")
        target = build.get("target", "")
    else:
        return ""

    full_path = os.path.join(compose_dir, context, dockerfile_path)
    if not os.path.exists(full_path):
        full_path = os.path.join(compose_dir, dockerfile_path)
        if not os.path.exists(full_path):
            return ""

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    stages = {}
    current_stage = "__default__"
    last_workdir = ""

    for line in lines:
        stripped = line.strip()
        from_match = re.match(r'^FROM\s+\S+(?:\s+AS\s+(\S+))?', stripped, re.IGNORECASE)
        if from_match:
            if last_workdir:
                stages[current_stage] = last_workdir
            current_stage = from_match.group(1) or f"__stage_{len(stages)}__"
            # Inherit workdir from parent stage if it's a local stage reference
            parent_ref = stripped.split()[1].lower()
            for stage_name in stages:
                if stage_name.lower() == parent_ref:
                    last_workdir = stages[stage_name]
                    break
            else:
                last_workdir = ""
            continue

        workdir_match = re.match(r'^WORKDIR\s+(.+)$', stripped, re.IGNORECASE)
        if workdir_match:
            last_workdir = workdir_match.group(1).strip()

    if last_workdir:
        stages[current_stage] = last_workdir

    if target:
        for stage_name, wd in stages.items():
            if stage_name == target or stage_name.lower() == target.lower():
                return wd
    # No target: return last stage's workdir
    return last_workdir


def _extract_dockerfile_cmd(service_config: dict, compose_dir: str = ".") -> str:
    """Extract CMD from Dockerfile for a service with build config.
    
    Supports multi-stage builds with target specification.
    Returns the shell command string or empty string if not found.
    """
    build = service_config.get("build", {})
    if not build:
        return ""

    if isinstance(build, str):
        context = build
        dockerfile_path = "Dockerfile"
        target = ""
    elif isinstance(build, dict):
        context = build.get("context", ".")
        dockerfile_path = build.get("dockerfile", "Dockerfile")
        target = build.get("target", "")
    else:
        return ""

    # Resolve dockerfile path relative to compose dir
    full_path = os.path.join(compose_dir, context, dockerfile_path)
    if not os.path.exists(full_path):
        # Try just the dockerfile path from compose dir
        full_path = os.path.join(compose_dir, dockerfile_path)
        if not os.path.exists(full_path):
            return ""

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    # Parse Dockerfile stages and their CMDs
    import re
    stages = {}  # stage_name -> last CMD in that stage
    current_stage = "__default__"
    last_cmd = ""

    for line in lines:
        stripped = line.strip()
        # Match FROM ... AS stage_name
        from_match = re.match(r'^FROM\s+\S+(?:\s+AS\s+(\S+))?', stripped, re.IGNORECASE)
        if from_match:
            # Save CMD from previous stage
            if last_cmd:
                stages[current_stage] = last_cmd
            current_stage = from_match.group(1) or f"__stage_{len(stages)}__"
            last_cmd = ""
            continue

        # Match CMD
        cmd_match = re.match(r'^CMD\s+(.+)$', stripped, re.IGNORECASE)
        if cmd_match:
            cmd_value = cmd_match.group(1).strip()
            # Parse JSON array form: CMD ["arg1", "arg2", ...]
            if cmd_value.startswith("["):
                try:
                    import json
                    parts = json.loads(cmd_value)
                    if isinstance(parts, list):
                        # Detect "sh -c <script>" or "bash -c <script>" pattern
                        # Return just the script — subprocess shell=True handles $VAR expansion
                        if (len(parts) >= 3 and
                                parts[0] in ("sh", "bash", "/bin/sh", "/bin/bash") and
                                parts[1] == "-c"):
                            last_cmd = parts[2]
                        else:
                            last_cmd = " ".join(shlex.quote(str(p)) for p in parts)
                    else:
                        last_cmd = cmd_value
                except Exception:
                    last_cmd = cmd_value
            else:
                # Shell form: CMD command arg1 arg2
                last_cmd = cmd_value

    # Save last stage
    if last_cmd:
        stages[current_stage] = last_cmd

    # Find the CMD for the target stage
    if target and target in stages:
        return stages[target]
    elif target:
        # Target not found, try case-insensitive
        for stage_name, cmd in stages.items():
            if stage_name.lower() == target.lower():
                return cmd
        return ""
    else:
        # No target specified, return last CMD (final stage)
        if stages:
            # Return the last stage's CMD
            return last_cmd or list(stages.values())[-1]
        return ""


def _extract_dockerfile_envs(service_config: dict, compose_dir: str = ".") -> dict[str, str]:
    """Extract ENV vars from Dockerfile for a service with build config.
    
    Collects ENVs from all stages up to and including the target stage
    (since multi-stage builds inherit from parent stages).
    """
    build = service_config.get("build", {})
    if not build:
        return {}

    if isinstance(build, str):
        context = build
        dockerfile_path = "Dockerfile"
        target = ""
    elif isinstance(build, dict):
        context = build.get("context", ".")
        dockerfile_path = build.get("dockerfile", "Dockerfile")
        target = build.get("target", "")
    else:
        return {}

    full_path = os.path.join(compose_dir, context, dockerfile_path)
    if not os.path.exists(full_path):
        full_path = os.path.join(compose_dir, dockerfile_path)
        if not os.path.exists(full_path):
            return {}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return {}

    import re
    # Join backslash-continued lines
    joined_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        while line.rstrip().endswith('\\') and i + 1 < len(lines):
            line = line.rstrip()[:-1] + ' ' + lines[i + 1].strip().rstrip('\n')
            i += 1
        joined_lines.append(line)
        i += 1

    # Track stages and their accumulated ENVs
    stages = {}  # stage_name -> dict of env vars
    current_stage = "__default__"
    current_envs = {}
    # Track stage inheritance (FROM parent AS child)
    stage_parents = {}  # stage_name -> parent_stage_name

    for line in joined_lines:
        stripped = line.strip()
        from_match = re.match(r'^FROM\s+(\S+)(?:\s+AS\s+(\S+))?', stripped, re.IGNORECASE)
        if from_match:
            # Save current stage envs
            stages[current_stage] = dict(current_envs)
            parent_ref = from_match.group(1)
            current_stage = from_match.group(2) or f"__stage_{len(stages)}__"
            # Inherit envs from parent stage if it's a local stage
            if parent_ref in stages:
                current_envs = dict(stages[parent_ref])
            else:
                current_envs = {}
            stage_parents[current_stage] = parent_ref
            continue

        # Match ENV KEY=VALUE or ENV KEY VALUE
        env_match = re.match(r'^ENV\s+(.+)$', stripped, re.IGNORECASE)
        if env_match:
            env_content = env_match.group(1)
            # Parse KEY=VALUE pairs — value can be quoted or unquoted (non-whitespace)
            pairs = re.findall(r'(\w+)=("(?:[^"\\]|\\.)*"|\'[^\']*\'|\S+)', env_content)
            if pairs:
                for k, v in pairs:
                    # Strip quotes
                    v = v.strip('"').strip("'")
                    current_envs[k] = v
            else:
                # Old-style: ENV KEY VALUE
                parts = env_content.split(None, 1)
                if len(parts) == 2:
                    current_envs[parts[0]] = parts[1]

    # Save last stage
    stages[current_stage] = dict(current_envs)

    # Return envs for target stage
    if target:
        for stage_name, envs in stages.items():
            if stage_name == target or stage_name.lower() == target.lower():
                return envs
    # No target, return last stage envs
    return current_envs


def _resolve_env_vars(env_dict: dict[str, str], user_provided: dict[str, str] = None) -> dict[str, str]:
    """Resolve ${VAR} references and remove empty/unresolvable values.
    
    If user_provided is given, substitute ${VAR} with user-provided values.
    Otherwise, check os.environ. Drop vars that can't be resolved.
    """
    import re
    resolved = {}
    lookup = user_provided or {}
    for k, v in env_dict.items():
        if not v:
            continue
        # Replace ${VAR} or ${VAR:-default} patterns
        def _sub(m):
            var_name = m.group(1)
            default = m.group(3) or ""
            return lookup.get(var_name, os.environ.get(var_name, default))
        v = re.sub(r'\$\{([A-Z_][A-Z_0-9]*)(:-([^}]*))?\}', _sub, v)
        # Replace bare $VAR references
        def _sub_bare(m):
            var_name = m.group(1)
            return lookup.get(var_name, os.environ.get(var_name, ""))
        v = re.sub(r'\$([A-Z_][A-Z_0-9]*)', _sub_bare, v)
        if v:
            resolved[k] = v
    return resolved


def _topological_sort(services: dict) -> list[str]:
    """Sort service names respecting depends_on ordering."""
    # Build adjacency: service -> list of services it depends on
    deps = {}
    for name, config in services.items():
        depends = config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        deps[name] = [d for d in depends if d in services]

    # Kahn's algorithm
    in_degree = {name: 0 for name in services}
    for name, dep_list in deps.items():
        in_degree[name] = len(dep_list)

    queue = [n for n in services if in_degree[n] == 0]
    result = []
    while queue:
        queue.sort()  # deterministic
        node = queue.pop(0)
        result.append(node)
        for name, dep_list in deps.items():
            if node in dep_list:
                in_degree[name] -= 1
                if in_degree[name] == 0:
                    queue.append(name)

    # Add any remaining (circular deps) at the end
    for name in services:
        if name not in result:
            result.append(name)

    return result


def _extract_port(service_config: dict, default: int = 0) -> int:
    """Extract the first container-side port from a service config."""
    ports = service_config.get("ports", [])
    if ports:
        port_str = str(ports[0])
        # Handle "host:container" or "host:container/protocol"
        if ":" in port_str:
            container_port = port_str.split(":")[-1].split("/")[0]
        else:
            container_port = port_str.split("/")[0]
        try:
            return int(container_port)
        except ValueError:
            pass
    return default


def _extract_env_vars(service_config: dict) -> dict[str, str]:
    """Extract environment variables from a service config."""
    env = service_config.get("environment", {})
    if isinstance(env, list):
        # Convert list format ["KEY=val", ...] to dict
        result = {}
        for item in env:
            if "=" in item:
                k, v = item.split("=", 1)
                result[k] = v
            else:
                result[item] = ""
        return result
    return dict(env) if env else {}


def _workspace_volume_name(local_dir: str) -> str:
    """Return a stable Modal Volume name for the current local workspace."""
    root = os.path.abspath(local_dir)
    base = os.path.basename(root.rstrip("\\/")) or "workspace"
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in base)
    slug = "-".join(part for part in slug.split("-") if part)[:32] or "workspace"
    digest = hashlib.sha1(root.encode("utf-8")).hexdigest()[:10]
    return f"m-gpux-compose-{slug}-{digest}"


def _build_compose_script(
    *,
    services: dict,
    main_service: str,
    main_port: int,
    compute_spec: str,
    local_dir: str,
    workspace_volume: str,
    exclude_patterns: list[str],
    pip_section: str,
    use_tunnel: bool = True,
    user_env_values: dict[str, str] = None,
    python_version: str = "3.12",
    use_uv: bool = False,
    selected_services: list[str] = None,
    base_image: Optional[str] = None,
    extra_apt_packages: list[str] = None,
    volume_mounts: list[tuple[str, str]] = None,
) -> str:
    """Generate the Modal script that runs all compose services."""

    # Determine which services to actually run: selected services + transitive dependencies
    def _get_transitive_deps(svc_name, all_services, visited=None):
        """Get all transitive dependencies of a service."""
        if visited is None:
            visited = set()
        if svc_name in visited:
            return visited
        visited.add(svc_name)
        svc_config = all_services.get(svc_name, {})
        depends = svc_config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        for dep in depends:
            if dep in all_services:
                _get_transitive_deps(dep, all_services, visited)
        return visited

    active_service_names = set()
    target_services = selected_services or [main_service]
    for svc in target_services:
        active_service_names.update(_get_transitive_deps(svc, services))
    # Filter services dict to only active ones
    services = {k: v for k, v in services.items() if k in active_service_names}

    # Collect all service names for /etc/hosts (keep all for hostname resolution)
    all_service_names = list(services.keys())

    # Collect apt packages needed
    apt_packages = set([
        "bash", "curl", "nano", "git", "ca-certificates",
        "build-essential", "procps", "net-tools",
    ])

    # Collect service start commands and env vars
    service_entries = []  # (name, start_cmd, env_dict, port)
    custom_app_services = []  # Services without known installers (user app)

    # Sort services by dependency order
    ordered_names = _topological_sort(services)

    for svc_name in ordered_names:
        svc_config = services[svc_name]
        svc_type = _detect_service_type(svc_name, svc_config)
        svc_env = _extract_env_vars(svc_config)
        svc_port = _extract_port(svc_config)

        if svc_type and svc_type in SERVICE_INSTALLERS:
            installer = SERVICE_INSTALLERS[svc_type]
            apt_packages.update(installer["apt"])
            port = svc_port or installer["default_port"]

            # Build extra args (e.g., redis password)
            extra_args = ""
            if svc_type == "redis":
                password = svc_env.get("REDIS_PASSWORD", "")
                if not password:
                    # Check for common env var patterns
                    for k, v in svc_env.items():
                        if "password" in k.lower() and v:
                            password = v
                            break
                if password:
                    # Use shell variable expansion at runtime
                    extra_args = " --requirepass $REDIS_PASSWORD"

            start_cmd = installer["start_cmd"].format(
                port=port, extra_args=extra_args
            )
            service_entries.append((svc_name, start_cmd, svc_env, port, svc_type))
        else:
            # This is the user's application service
            command = _command_to_shell(svc_config.get("command", ""))
            # Only the main service defaults to main_port; others use 0 (no port check)
            port = svc_port or (main_port if svc_name == main_service else 0)
            custom_app_services.append((svc_name, command, svc_env, port))

    # Build the apt install list
    apt_list = sorted(apt_packages)

    # Build environment block for all services (resolve ${VAR} references)
    all_env_vars = {}
    # First, extract ENV vars from Dockerfiles (defaults like UVICORN_WORKERS=1)
    # Skip build-tool vars that don't belong at runtime
    _skip_env_prefixes = ("UV_", "PYTHON_INSTALL", "PATH")
    _skip_env_exact = {"PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "PYTHONPATH"}
    compose_dir = local_dir  # project root where Dockerfile lives
    for svc_name, svc_config in services.items():
        dockerfile_envs = _extract_dockerfile_envs(svc_config, compose_dir=compose_dir)
        for k, v in dockerfile_envs.items():
            if k in _skip_env_exact:
                continue
            if any(k.startswith(p) for p in _skip_env_prefixes):
                continue
            all_env_vars[k] = v
    # Then overlay compose environment: vars (these override Dockerfile ENVs)
    for svc_name, svc_config in services.items():
        svc_env = _extract_env_vars(svc_config)
        all_env_vars.update(svc_env)
    # Merge user-provided env values directly (they override compose refs)
    if user_env_values:
        all_env_vars.update(user_env_values)
    all_env_vars = _resolve_env_vars(all_env_vars, user_provided=user_env_values)

    # Generate the script
    env_exports = "\n".join(
        f'    os.environ["{k}"] = "{v}"'
        for k, v in all_env_vars.items()
        if v  # skip empty values
    )

    hosts_entries = "\n".join(
        f'    "127.0.0.1 {name}",'
        for name in all_service_names
    )

    # Determine nginx port for config generation
    nginx_port = 80
    has_nginx = False
    for svc_name, start_cmd, svc_env, port, svc_type in service_entries:
        if svc_type == "nginx":
            nginx_port = port
            has_nginx = True
            break

    # Build service command registry for the supervisor
    # Format: (name, command, cwd, is_infra, port)
    svc_registry_entries = []
    for svc_name, start_cmd, svc_env, port, svc_type in service_entries:
        svc_registry_entries.append(
            f'    "{svc_name}": {{"cmd": {repr(start_cmd)}, "cwd": "/", "port": {port}, "infra": True}},'
        )
    for svc_name, command, svc_env, port in custom_app_services:
        if command:
            svc_registry_entries.append(
                f'    "{svc_name}": {{"cmd": {repr(command)}, "cwd": "/workspace", "port": {port}, "infra": False}},'
            )

    svc_registry_block = "\n".join(svc_registry_entries)

    # Infrastructure service names (start first, wait for ports)
    infra_names = [svc_name for svc_name, _, _, _, _ in service_entries]
    app_names = [svc_name for svc_name, command, _, _ in custom_app_services if command]

    # Collect all services with ports for multi-tunnel
    # (service_name, port) — deduplicate by port, skip idle commands
    tunnel_services = []
    seen_ports = set()
    _idle_keywords = ("sleep ", "tail -f", "sleep infinity", "bash", "/bin/bash", "cat")
    # Main service first
    seen_ports.add(main_port)
    tunnel_services.append((main_service, main_port))
    # Infrastructure services with ports (e.g., nginx on 8080)
    for svc_name, start_cmd, svc_env, port, svc_type in service_entries:
        if port and port not in seen_ports:
            seen_ports.add(port)
            tunnel_services.append((svc_name, port))
    # App services with ports — only if command actually serves something
    for svc_name, command, svc_env, port in custom_app_services:
        if port and port not in seen_ports and command:
            cmd_lower = command.strip().lower()
            # Skip idle/placeholder commands that won't bind a port
            if any(cmd_lower.startswith(k) or f"'{k}" in cmd_lower for k in _idle_keywords):
                continue
            seen_ports.add(port)
            tunnel_services.append((svc_name, port))

    # Determine tunnel section
    if use_tunnel:
        if len(tunnel_services) == 1:
            tunnel_block = f"""
    with modal.forward({main_port}, unencrypted=True) as tunnel:
        print("\\n" + "=" * 60)
        print(f"[COMPOSE READY] {{tunnel.url}}")
        print(f"  Main service: {main_service} (port {main_port})")
        print(f"  Services running: {{', '.join(procs.keys())}}")
        print(f"  Workspace: /workspace")
        print(f"  Volume: {workspace_volume}")
        print("=" * 60 + "\\n", flush=True)

        _supervisor_loop(procs, svc_commands, restart_counts)
"""
        else:
            # Build multi-tunnel using contextlib.ExitStack
            tunnel_ports_repr = repr(tunnel_services)
            tunnel_block = f"""
    from contextlib import ExitStack
    tunnel_ports = {tunnel_ports_repr}
    with ExitStack() as stack:
        tunnels = {{}}
        for svc_name, port in tunnel_ports:
            tun = stack.enter_context(modal.forward(port, unencrypted=True))
            tunnels[svc_name] = (port, tun.url)

        print("\\n" + "=" * 60)
        print("[COMPOSE READY] All tunnels open")
        print("-" * 60)
        for svc_name, (port, url) in tunnels.items():
            main_marker = " ★" if svc_name == "{main_service}" else ""
            print(f"  {{svc_name}} (port {{port}}): {{url}}{{main_marker}}")
        print("-" * 60)
        print(f"  Services running: {{', '.join(procs.keys())}}")
        print(f"  Workspace: /workspace")
        print(f"  Volume: {workspace_volume}")
        print("=" * 60 + "\\n", flush=True)

        _supervisor_loop(procs, svc_commands, restart_counts)
"""
    else:
        tunnel_block = f"""
    print("\\n" + "=" * 60)
    print("[COMPOSE READY] All services running on localhost")
    print(f"  Main service: {main_service} (port {main_port})")
    print(f"  Services running: {{', '.join(procs.keys())}}")
    print(f"  Workspace: /workspace")
    print("=" * 60 + "\\n", flush=True)

    _supervisor_loop(procs, svc_commands, restart_counts)
"""

    # Split pip_section into pre-add (normal) and post-add (needs workspace files)
    if pip_section.startswith("__POST_ADD__"):
        pre_add_pip = ""
        post_add_pip = pip_section.replace("__POST_ADD__", "")
        # Must use copy=True when running commands after add_local_dir
        add_local_extra = ", copy=True"
    else:
        pre_add_pip = pip_section
        post_add_pip = ""
        add_local_extra = ""

    # Generate uv sync block for _prepare_workspace if needed
    uv_sync_code = ""
    if use_uv:
        uv_sync_code = ('    print("[COMPOSE] Running uv sync...", flush=True)\n'
                        '    os.environ["UV_LINK_MODE"] = "copy"\n'
                        '    subprocess.run(["uv", "sync", "--frozen"], cwd="/workspace", check=True)\n'
                        '    print("[COMPOSE] uv sync complete", flush=True)\n')

    # Determine image line — use base_image if provided (e.g. tritonserver)
    if base_image:
        # Nếu image gốc của service (như Triton) đã có sẵn Python, dùng nó luôn
        if _image_has_python(base_image):
            image_from_line = f'modal.Image.from_registry("{base_image}")'
        else:
            # Nếu chưa có (như bản Triton C++ thuần), mới thêm python vào
            image_from_line = f'modal.Image.from_registry("{base_image}", add_python="{python_version}")'
    else:
        # Mặc định của m-gpux
        image_from_line = f'modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="{python_version}")'

    # Merge extra_apt_packages into apt_list
    if extra_apt_packages:
        for pkg in extra_apt_packages:
            if pkg not in apt_list:
                apt_list.append(pkg)
        apt_list = sorted(set(apt_list))

    # Build volume setup code for model_repository etc.
    # --- ĐOẠN CHỈNH SỬA 2: Đảm bảo mount đúng model_repository ---
    volume_setup_code = ""
    if volume_mounts:
        volume_lines = []
        for local_path, container_path in volume_mounts:
            # Chuẩn hóa đường dẫn
            clean_local = local_path.replace("./", "")
            volume_lines.append(f'    print(f"[COMPOSE] Mounting /workspace_seed/{clean_local} to {container_path}")')
            volume_lines.append(f'    os.makedirs(os.path.dirname("{container_path}"), exist_ok=True)')
            # Dùng symlink để tiết kiệm dung lượng và thời gian thay vì copy (nếu Modal cho phép)
            # Hoặc dùng cp -a như cũ nhưng phải chính xác
            volume_lines.append(f'    if os.path.exists("/workspace_seed/{clean_local}"):')
            volume_lines.append(f'        subprocess.run(["cp", "-a", "/workspace_seed/{clean_local}/.", "{container_path}/"], check=False)')
        volume_setup_code = "\n".join(volume_lines)

    script = f'''
import modal
import os
import sys
import subprocess
import threading
import time
import signal
import socket

# __METRICS__

MAX_RESTARTS = 5  # per service

app = modal.App("m-gpux-compose")
workspace_volume = modal.Volume.from_name("{workspace_volume}", create_if_missing=True)
image = (
    {image_from_line}
    .entrypoint([])
    .apt_install({repr(apt_list)})
    {pre_add_pip}
    .add_local_dir("{local_dir}", remote_path="/workspace_seed", ignore={repr(to_recursive_ignore(exclude_patterns))}{add_local_extra})
    {post_add_pip}
)

# Service command registry
svc_commands = {{
{svc_registry_block}
}}

INFRA_ORDER = {repr(infra_names)}
APP_ORDER = {repr(app_names)}

def _prepare_workspace():
    os.makedirs("/workspace", exist_ok=True)
    subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
{uv_sync_code}    workspace_volume.commit()

def _setup_volume_mounts():
    """Setup volume mounts (model_repository, etc.)."""
{volume_setup_code if volume_setup_code else "    pass"}

def _start_workspace_autocommit(interval=20):
    def _loop():
        while True:
            time.sleep(interval)
            try:
                workspace_volume.commit()
            except Exception:
                pass
    threading.Thread(target=_loop, daemon=True).start()

def _start_workspace_autoreload(interval=3):
    """Periodically reload the volume to pick up external changes (from compose sync)."""
    def _loop():
        while True:
            time.sleep(interval)
            try:
                workspace_volume.reload()
            except Exception:
                pass
    threading.Thread(target=_loop, daemon=True).start()

def _write_hosts():
    """Add service name entries to /etc/hosts for local resolution."""
    entries = [
{hosts_entries}
    ]
    with open("/etc/hosts", "a") as f:
        f.write("\\n# m-gpux compose services\\n")
        for entry in entries:
            f.write(entry + "\\n")
    print("[COMPOSE] /etc/hosts updated with service entries:", entries, flush=True)

def _setup_nginx():
    """Setup nginx config: use workspace copy if present, else generate minimal one."""
    import glob
    # Look for user's nginx config in workspace (common patterns)
    candidates = (
        glob.glob("/workspace/nginx/nginx.conf") +
        glob.glob("/workspace/nginx/*.conf") +
        glob.glob("/workspace/config/nginx*.conf") +
        glob.glob("/workspace/nginx.conf")
    )
    if candidates:
        conf_src = candidates[0]
        print(f"[COMPOSE] Using nginx config: {{conf_src}}", flush=True)
        subprocess.run(["cp", conf_src, "/tmp/nginx_compose.conf"], check=False)
    else:
        # Generate a minimal reverse-proxy config
        conf = (
            "user root;\\n"
            "worker_processes auto;\\n"
            "error_log /var/log/nginx/error.log warn;\\n"
            "pid /tmp/nginx.pid;\\n"
            "events {{ worker_connections 1024; }}\\n"
            "http {{\\n"
            "    access_log /var/log/nginx/access.log;\\n"
            "    server {{\\n"
            "        listen {nginx_port};\\n"
            "        location / {{\\n"
            "            proxy_pass http://127.0.0.1:{main_port};\\n"
            "            proxy_set_header Host $$host;\\n"
            "            proxy_set_header X-Real-IP $$remote_addr;\\n"
            "        }}\\n"
            "    }}\\n"
            "}}\\n"
        )
        with open("/tmp/nginx_compose.conf", "w") as f:
            f.write(conf)
        print("[COMPOSE] Generated default nginx proxy config on port {nginx_port}", flush=True)
    # Ensure log dir exists and fix permissions
    os.makedirs("/var/log/nginx", exist_ok=True)
    # Fix nginx user issue on non-alpine
    subprocess.run(["sed", "-i", "s/^user nginx/user root/", "/tmp/nginx_compose.conf"], check=False)

def _setup_environment():
    """Set all environment variables from compose config."""
{env_exports if env_exports else "    pass"}

def _is_idle_command(cmd):
    """Return True if the command is a placeholder/idle command that won't bind a port."""
    import re
    cmd_stripped = cmd.strip().lower()
    idle_patterns = [
        r'^(bash|sh|/bin/bash|/bin/sh)(\s+-\w+)*\s*$',
        r'^sleep\s+',
        r'^tail\s+-f',
        r'^cat\s*$',
        r'^bash\s+-lc\s+.sleep\s+',
    ]
    for pattern in idle_patterns:
        if re.match(pattern, cmd_stripped):
            return True
    return False

def _wait_for_port(port, timeout=30):
    """Block until a port is accepting connections or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False

def _start_service(name, procs):
    """Start a single service by name. Returns the Popen object."""
    info = svc_commands[name]
    cmd = info["cmd"]
    cwd = info["cwd"]
    print(f"[COMPOSE] Starting {{name}}: {{cmd}}", flush=True)
    log_path = f"/tmp/compose_{{name}}.log"
    log_f = open(log_path, "w")
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=cwd,
        env={{**os.environ}},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    def _fwd():
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace")
                sys.stdout.write(line)
                sys.stdout.flush()
                log_f.write(line)
                log_f.flush()
        except Exception:
            pass
        finally:
            log_f.close()
    threading.Thread(target=_fwd, daemon=True).start()
    procs[name] = proc
    return proc

def _show_recent_log(name, n=20):
    """Print the last n lines from a service's log file."""
    log_path = f"/tmp/compose_{{name}}.log"
    try:
        with open(log_path) as f:
            lines = f.readlines()
        recent = lines[-n:] if len(lines) > n else lines
        if recent:
            print(f"[COMPOSE] Recent output from {{name}}:", flush=True)
            for line in recent:
                print(f"  | {{line.rstrip()}}", flush=True)
        else:
            print(f"[COMPOSE] No output captured from {{name}} yet", flush=True)
    except FileNotFoundError:
        print(f"[COMPOSE] No log file for {{name}}", flush=True)

def _supervisor_loop(procs, svc_commands, restart_counts):
    """Monitor all processes; auto-restart crashed ones up to MAX_RESTARTS."""
    while True:
        time.sleep(5)
        for name, proc in list(procs.items()):
            ret = proc.poll()
            if ret is not None:
                count = restart_counts.get(name, 0)
                if count >= MAX_RESTARTS:
                    if count == MAX_RESTARTS:  # print only once
                        print(f"[COMPOSE] FATAL: {{name}} crashed {{MAX_RESTARTS}} times. Giving up.", flush=True)
                        restart_counts[name] = count + 1
                    continue
                restart_counts[name] = count + 1
                print(f"[COMPOSE] {{name}} exited (code {{ret}}). Restarting ({{count+1}}/{{MAX_RESTARTS}})...", flush=True)
                time.sleep(2)  # back-off before restart
                _start_service(name, procs)

@app.function(image=image, {compute_spec}, timeout=86400, volumes={{"/workspace": workspace_volume}})
def run_compose():
    _print_metrics()
    _prepare_workspace()
    _setup_volume_mounts()
    _start_workspace_autocommit()
    _start_workspace_autoreload()

    # Setup hostname resolution and environment
    _write_hosts()
    _setup_environment()
{"    _setup_nginx()" if has_nginx else ""}

    os.chdir("/workspace")
    procs = {{}}
    restart_counts = {{}}

    # --- Phase 1: Start infrastructure services and wait for ports ---
    for name in INFRA_ORDER:
        _start_service(name, procs)
        port = svc_commands[name]["port"]
        if port:
            print(f"[COMPOSE] Waiting for {{name}} on port {{port}}...", flush=True)
            if _wait_for_port(port, timeout=30):
                print(f"[COMPOSE] {{name}} ready (port {{port}})", flush=True)
            else:
                print(f"[COMPOSE] WARNING: {{name}} port {{port}} not responding after 30s", flush=True)
                _show_recent_log(name)
        else:
            time.sleep(2)

    # --- Phase 2: Start application services ---
    for name in APP_ORDER:
        _start_service(name, procs)
        port = svc_commands[name]["port"]
        cmd = svc_commands[name]["cmd"]
        if port and not _is_idle_command(cmd):
            print(f"[COMPOSE] Waiting for {{name}} on port {{port}}...", flush=True)
            if _wait_for_port(port, timeout=30):
                print(f"[COMPOSE] {{name}} ready (port {{port}})", flush=True)
            else:
                # Check if process already died
                if procs[name].poll() is not None:
                    print(f"[COMPOSE] ERROR: {{name}} exited immediately (code {{procs[name].returncode}})", flush=True)
                    _show_recent_log(name)
                else:
                    print(f"[COMPOSE] WARNING: {{name}} port {{port}} not responding (may still be starting)", flush=True)
                    _show_recent_log(name)
        else:
            # No port defined or idle command — background/worker service, just let it start
            time.sleep(2)
            if procs[name].poll() is not None:
                print(f"[COMPOSE] WARNING: {{name}} exited immediately (code {{procs[name].returncode}})", flush=True)
                _show_recent_log(name)
            else:
                print(f"[COMPOSE] {{name}} started (no port check)", flush=True)
{tunnel_block}
'''
    return script


# ---------------------------------------------------------------------------
# Available GPU/CPU specs (mirrored from hub plugin for consistency)
# ---------------------------------------------------------------------------
AVAILABLE_GPUS = {
    "1":  ("T4",            "Light inference/exploration (16GB)"),
    "2":  ("L4",            "Balance of cost/performance (24GB)"),
    "3":  ("A10G",          "Good alternative for training/inference (24GB)"),
    "4":  ("L40S",          "Ada Lovelace, great for inference (48GB)"),
    "5":  ("A100",          "High performance (40GB, default SXM)"),
    "6":  ("A100-80GB",     "Extreme performance (80GB)"),
    "7":  ("H100",          "Hopper architecture (80GB)"),
    "8":  ("H200",          "Next-gen Hopper with HBM3e (141GB)"),
}

AVAILABLE_CPUS = {
    "1":  (2,   2048,   "2 cores, 2 GB"),
    "2":  (4,   4096,   "4 cores, 4 GB"),
    "3":  (8,   8192,   "8 cores, 8 GB"),
    "4":  (16,  16384,  "16 cores, 16 GB"),
    "5":  (32,  32768,  "32 cores, 32 GB"),
}


def compose_main(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Deploy a Docker Compose stack on Modal.

    Translates multi-container docker-compose.yml into a single Modal container
    with all services running as managed subprocesses. Service hostnames are
    resolved via /etc/hosts to 127.0.0.1.

    Supports: Redis, PostgreSQL, Nginx, Memcached, RabbitMQ, MongoDB + your app.
    """

    console.print(Panel.fit(
        "[bold magenta]m-gpux Compose[/bold magenta]\n"
        "Deploy Docker Compose stacks on Modal GPU/CPU containers.\n"
        "[dim]Multi-container → single container with process supervisor[/dim]",
        border_style="cyan",
    ))

    # --- Find compose file ---
    compose_path = file or _find_compose_file()
    if compose_path is None:
        console.print("[bold red]No docker-compose.yml or compose.yml found in current directory.[/bold red]")
        console.print("[dim]Use --file to specify a path, or cd into your project.[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[green]Found compose file:[/green] [bold]{compose_path}[/bold]")

    # --- Parse compose file ---
    data = _parse_compose(compose_path)
    services = data["services"]

    # --- Read x-mgpux metadata for smart image/package detection ---
    mgpux_meta = _parse_x_mgpux(data)
    detected_base_image = mgpux_meta.get("base_image") or _detect_compose_base_image(services)
    detected_extra_apt = list(mgpux_meta.get("apt_packages", [])) + _detect_infra_apt_packages(services)
    detected_volume_mounts = _extract_volume_mounts(services)
    detected_pip_from_meta = mgpux_meta.get("pip_packages", [])

    # --- Display services ---
    console.print(f"\n[bold cyan]Services detected ({len(services)}):[/bold cyan]")
    svc_table = Table(show_header=True, header_style="bold cyan")
    svc_table.add_column("Service")
    svc_table.add_column("Image")
    svc_table.add_column("Type")
    svc_table.add_column("Ports")

    for svc_name, svc_config in services.items():
        image = svc_config.get("image", "(build)")
        svc_type = _detect_service_type(svc_name, svc_config) or "app"
        ports = ", ".join(str(p) for p in svc_config.get("ports", [])) or "-"
        svc_table.add_row(svc_name, image, svc_type, ports)

    console.print(svc_table)

    # --- Identify main service ---
    app_services = []
    infra_services = []
    for svc_name, svc_config in services.items():
        svc_type = _detect_service_type(svc_name, svc_config)
        if svc_type:
            infra_services.append(svc_name)
        else:
            app_services.append(svc_name)

    if not app_services:
        console.print("[yellow]No application service detected. All services appear to be infrastructure.[/yellow]")
        main_service = list(services.keys())[0]
    elif len(app_services) == 1:
        main_service = app_services[0]
    else:
        console.print("\n[bold cyan]Multiple app services found. Select the main one:[/bold cyan]")
        svc_options = [(name, f"Expose this service's port via tunnel") for name in app_services]
        idx = arrow_select(svc_options, title="Main Service", default=0)
        main_service = app_services[idx]

    main_port = _extract_port(services[main_service])
    if not main_port:
        main_port_str = Prompt.ask(
            f"[bold cyan]Which port does '{main_service}' listen on?[/bold cyan]",
            default="8000",
        )
        main_port = int(main_port_str)

    console.print(f"\n[green]Main service:[/green] [bold]{main_service}[/bold] (port {main_port})")

    # --- Select additional services to run ---
    # By default: main_service + transitive deps. Allow user to add more.
    other_app_services = [s for s in app_services if s != main_service]
    extra_services = []
    if other_app_services:
        add_more = Prompt.ask(
            f"\n[bold cyan]Also start other app services?[/bold cyan] ({', '.join(other_app_services)})",
            choices=["y", "n"], default="n",
        )
        if add_more == "y":
            console.print("[dim]Select services to include (space-separated, or 'all'):[/dim]")
            extra_input = Prompt.ask(
                f"  Services",
                default="all",
            )
            if extra_input.strip().lower() == "all":
                extra_services = other_app_services
            else:
                for s in extra_input.split():
                    s = s.strip().strip(",")
                    if s in other_app_services:
                        extra_services.append(s)
                    elif s:
                        console.print(f"  [yellow]Unknown service: {s}[/yellow]")
            if extra_services:
                console.print(f"  [green]Will also start:[/green] {', '.join(extra_services)}")

    # Store which services to actually run (used later in script generation)
    selected_services = [main_service] + extra_services

    # --- Check for services with no command (build-only) ---
    # These rely on Dockerfile CMD — try to extract it automatically
    missing_cmd_services = []
    for svc_name in app_services:
        svc_config = services[svc_name]
        cmd = svc_config.get("command", "")
        if not cmd:
            # Try to extract CMD from Dockerfile
            dockerfile_cmd = _extract_dockerfile_cmd(svc_config, compose_dir=os.path.dirname(compose_path) or ".")
            if dockerfile_cmd:
                services[svc_name]["command"] = dockerfile_cmd
                console.print(f"  [dim]{svc_name}: auto-detected CMD → {dockerfile_cmd}[/dim]")
            else:
                missing_cmd_services.append(svc_name)

    if missing_cmd_services:
        console.print(f"\n[bold yellow]Warning:[/bold yellow] {len(missing_cmd_services)} service(s) have no "
                      f"'command:' in compose and no CMD found in Dockerfile.")
        console.print("[dim]Provide the startup command for each, or press Enter to skip (service won't start).[/dim]\n")

        for svc_name in missing_cmd_services:
            svc_config = services[svc_name]
            # Try to guess command from common patterns
            port = _extract_port(svc_config)
            default_cmd = ""
            if svc_name == main_service:
                default_cmd = f"uvicorn app.main:app --host 0.0.0.0 --port {port or main_port}"

            cmd_input = Prompt.ask(
                f"  [cyan]{svc_name}[/cyan] command",
                default=default_cmd if default_cmd else "",
            )
            if cmd_input.strip():
                # Inject command back into the services dict
                services[svc_name]["command"] = cmd_input.strip()

    # --- Select workspace/profile ---
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    # --- Compute selection ---
    console.print("\n[bold cyan]Select Compute Type[/bold cyan]")
    compute_type_options = [
        ("GPU", "GPU acceleration (recommended for ML workloads)"),
        ("CPU", "CPU-only (cheaper, good for web apps)"),
    ]
    compute_type_idx = arrow_select(compute_type_options, title="Compute Type", default=0)
    use_cpu = (compute_type_idx == 1)

    if use_cpu:
        cpu_keys = list(AVAILABLE_CPUS.keys())
        cpu_options = []
        for k in cpu_keys:
            cores, mem, desc = AVAILABLE_CPUS[k]
            cpu_options.append((f"{cores} cores", desc))
        cpu_idx = arrow_select(cpu_options, title="Select CPU", default=2)
        selected_cores, selected_memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
        compute_spec = f'cpu={selected_cores}, memory={selected_memory}'
        compute_label = f"CPU ({selected_cores} cores, {selected_memory} MB)"
    else:
        gpu_options = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
        gpu_idx = arrow_select(gpu_options, title="Select GPU", default=1)
        selected_gpu = list(AVAILABLE_GPUS.values())[gpu_idx][0]
        compute_spec = f'gpu="{selected_gpu}"'
        compute_label = selected_gpu

    console.print(f"[green]Compute:[/green] [bold]{compute_label}[/bold]")

    # --- Environment setup ---
    console.print("\n[bold cyan]Environment Setup[/bold cyan]")
    pip_section = ""
    user_python_version = "3.12"  # default
    use_uv = False
    if os.path.exists("requirements.txt"):
        use_req = Prompt.ask(
            "[green]Found requirements.txt.[/green] Install dependencies?",
            choices=["y", "n"], default="y",
        )
        if use_req == "y":
            req_escaped = os.path.abspath("requirements.txt").replace("\\", "/")
            pip_section = f'\n    .pip_install_from_requirements("{req_escaped}")'
    elif os.path.exists("pyproject.toml"):
        use_pyproject = Prompt.ask(
            "[green]Found pyproject.toml.[/green] Install project dependencies?",
            choices=["y", "n"], default="y",
        )
        if use_pyproject == "y":
            # Detect if project uses uv (uv.lock present)
            use_uv = os.path.exists("uv.lock")
            if use_uv:
                # Install uv at build time; uv sync will run at container start from /workspace
                pip_section = '__POST_ADD__\n    .run_commands("pip install uv")'
                console.print("  [dim]Detected uv.lock → will use uv sync at startup[/dim]")
            else:
                # Fallback to pip install
                pip_section = '__POST_ADD__\n    .run_commands("pip install /workspace_seed/")'
            # Detect requires-python to pick the right Python version
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            try:
                with open("pyproject.toml", "rb") as _f:
                    _pyproj = tomllib.load(_f)
                _req_python = _pyproj.get("project", {}).get("requires-python", "")
                if _req_python:
                    import re as _re_py
                    # Extract minimum version like ">=3.13" -> "3.13"
                    _m = _re_py.search(r'(\d+\.\d+)', _req_python)
                    if _m:
                        _detected_py = _m.group(1)
                        if float(_detected_py) > 3.12:
                            console.print(f"  [dim]Detected requires-python: {_req_python} → using Python {_detected_py}[/dim]")
                            user_python_version = _detected_py
            except Exception:
                pass
    else:
        specify_req = Prompt.ask(
            "Specify a requirements.txt or pyproject.toml path?",
            choices=["y", "n"], default="n",
        )
        if specify_req == "y":
            req_input = Prompt.ask("Enter path to requirements.txt or pyproject.toml")
            if os.path.exists(req_input):
                req_escaped = os.path.abspath(req_input).replace("\\", "/")
                if req_input.endswith("pyproject.toml"):
                    pip_section = f'\n    .run_commands("pip install {os.path.dirname(req_escaped) or "."}")'
                else:
                    pip_section = f'\n    .pip_install_from_requirements("{req_escaped}")'
            else:
                console.print(f"[bold red]File not found: {req_input}[/bold red]")

    if not pip_section:
        pip_section = '\n    .pip_install("uvicorn", "fastapi", "httpx")'

    # --- Exclude patterns ---
    default_excludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox"
    exclude_input = Prompt.ask(
        "[bold cyan]Patterns to exclude from upload[/bold cyan]",
        default=default_excludes,
    )
    exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]

    # --- Detect unresolved environment variables ---
    # Collect all env vars from all services and prompt for ${VAR} references
    import re as _re
    all_raw_env = {}
    for svc_config in services.values():
        svc_env = _extract_env_vars(svc_config)
        all_raw_env.update(svc_env)

    # Find variables that reference ${SOMETHING} and aren't in os.environ
    unresolved_vars = set()
    for k, v in all_raw_env.items():
        refs = _re.findall(r'\$\{([A-Z_][A-Z_0-9]*)', str(v))
        for ref in refs:
            if ref not in os.environ:
                unresolved_vars.add(ref)
        # Also check if the key itself has no value (bare env var name)
        if not v and k not in os.environ:
            unresolved_vars.add(k)

    user_env_values = {}
    if unresolved_vars:
        console.print(f"\n[bold cyan]Environment Variables[/bold cyan]")
        console.print("[dim]These variables are referenced in compose but not set locally.[/dim]")
        for var in sorted(unresolved_vars):
            val = Prompt.ask(f"  [cyan]{var}[/cyan]", default="")
            if val:
                user_env_values[var] = val

    local_dir_escaped = os.path.abspath(".").replace("\\", "/")
    workspace_volume = _workspace_volume_name(".")

    # --- Generate and execute script ---
    console.print("\n[bold cyan]Generating Modal compose script...[/bold cyan]")

    script = _build_compose_script(
        services=services,
        main_service=main_service,
        main_port=main_port,
        compute_spec=compute_spec,
        local_dir=local_dir_escaped,
        workspace_volume=workspace_volume,
        exclude_patterns=exclude_patterns,
        pip_section=pip_section,
        use_tunnel=True,
        user_env_values=user_env_values,
        python_version=user_python_version,
        use_uv=use_uv,
        selected_services=selected_services,
    )

    # Show summary
    console.print(Panel(
        f"[bold]Compose Deployment Summary[/bold]\n\n"
        f"  Compose file: {compose_path}\n"
        f"  Services: {', '.join(services.keys())}\n"
        f"  Main service: {main_service} (port {main_port})\n"
        f"  Compute: {compute_label}\n"
        f"  Volume: {workspace_volume}\n\n"
        f"[dim]All service hostnames resolve to 127.0.0.1 inside the container.[/dim]\n"
        f"[dim]Your app can connect to redis:6379, postgres:5432, etc. as usual.[/dim]",
        title="DEPLOYMENT PLAN",
        border_style="green",
    ))

    execute_modal_temp_script(
        script,
        f"Compose stack ({', '.join(services.keys())}) on {compute_label}",
        detach=True,
        session_metadata={
            "id": new_session_id(),
            "kind": "compose",
            "profile": selected_profile,
            "compute": compute_label,
            "workspace_volume": workspace_volume,
            "local_dir": os.path.abspath("."),
            "app_name": "m-gpux-compose",
            "services": list(services.keys()),
            "main_service": main_service,
            "main_port": main_port,
        },
    )


def compose_check(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Analyze a Docker Compose file and show what m-gpux compose will do.
    
    Validates service detection, port mapping, and shows the deployment plan
    without actually deploying.
    """
    compose_path = file or _find_compose_file()
    if compose_path is None:
        console.print("[bold red]No compose file found.[/bold red]")
        raise typer.Exit(1)

    data = _parse_compose(compose_path)
    services = data["services"]

    console.print(Panel.fit(
        f"[bold magenta]Compose Analysis[/bold magenta] — {compose_path}",
        border_style="cyan",
    ))

    for svc_name, svc_config in services.items():
        svc_type = _detect_service_type(svc_name, svc_config)
        port = _extract_port(svc_config)
        env_vars = _extract_env_vars(svc_config)
        image = svc_config.get("image", "(build from Dockerfile)")
        command = svc_config.get("command", "(default)")

        if svc_type:
            installer = SERVICE_INSTALLERS[svc_type]
            status = f"[green]✓ Supported[/green] → installed via apt ({', '.join(installer['apt'])})"
            port = port or installer["default_port"]
        else:
            status = "[cyan]→ App service[/cyan] (runs your code)"

        console.print(f"\n  [bold]{svc_name}[/bold] {status}")
        console.print(f"    Image: {image}")
        console.print(f"    Port: {port or 'not specified'}")
        if command and command != "(default)":
            console.print(f"    Command: {command}")
        if env_vars:
            console.print(f"    Env vars: {', '.join(env_vars.keys())}")

    console.print(f"\n[bold green]Result:[/bold green] All {len(services)} services can run in a single Modal container.")
    console.print("[dim]Run `m-gpux compose up` to deploy.[/dim]")


def compose_sync(
    interval: int = typer.Option(2, "--interval", "-i", help="Sync interval in seconds"),
    exclude: str = typer.Option(
        ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox,hf_cache,models,data",
        "--exclude", "-e", help="Comma-separated patterns to exclude",
    ),
):
    """
    Watch local files and sync changes to the running Modal container's volume.

    Monitors your project directory for changes and pushes modified files
    to the Modal Volume used by `compose up`. The container sees changes
    immediately since the volume is mounted at /workspace.

    Tip: Use with `--reload` in your app (e.g. uvicorn --reload) for hot-reload.
    """
    import time as _time
    import fnmatch
    import pathlib

    console.print(Panel.fit(
        "[bold magenta]m-gpux Compose Sync[/bold magenta]\n"
        "Watch local files → push to Modal Volume → container sees changes",
        border_style="cyan",
    ))

    # Determine volume name
    workspace_volume = _workspace_volume_name(".")
    console.print(f"[green]Volume:[/green] [bold]{workspace_volume}[/bold]")

    # Parse excludes
    exclude_patterns = [p.strip() for p in exclude.split(",") if p.strip()]
    console.print(f"[dim]Excluding: {', '.join(exclude_patterns)}[/dim]")

    def _should_exclude(rel_path: str) -> bool:
        parts = pathlib.PurePosixPath(rel_path).parts
        for pattern in exclude_patterns:
            # Check each path component
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
            # Check full path
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    # Build initial file state (mtime index)
    local_dir = os.path.abspath(".")

    def _scan_files() -> dict[str, float]:
        """Return {relative_path: mtime} for all non-excluded files."""
        result = {}
        for root, dirs, files in os.walk(local_dir):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if not _should_exclude(
                os.path.relpath(os.path.join(root, d), local_dir).replace("\\", "/")
            )]
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, local_dir).replace("\\", "/")
                if _should_exclude(rel):
                    continue
                try:
                    result[rel] = os.path.getmtime(full)
                except OSError:
                    pass
        return result

    console.print("[cyan]Scanning files...[/cyan]")
    prev_state = _scan_files()
    console.print(f"[green]Tracking {len(prev_state)} files[/green]")
    console.print(f"[bold green]Watching for changes (every {interval}s). Ctrl+C to stop.[/bold green]\n")

    sync_count = 0
    try:
        while True:
            _time.sleep(interval)
            curr_state = _scan_files()

            # Find changed/new files
            changed = []
            for path, mtime in curr_state.items():
                if path not in prev_state or prev_state[path] < mtime:
                    changed.append(path)

            # Find deleted files
            deleted = [p for p in prev_state if p not in curr_state]

            if not changed and not deleted:
                continue

            sync_count += 1

            # Push changes via `modal volume put`
            if changed:
                console.print(f"[cyan][sync #{sync_count}][/cyan] {len(changed)} file(s) changed")
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                # Upload changed files in batches
                for rel_path in changed:
                    local_path = os.path.join(local_dir, rel_path.replace("/", os.sep))
                    remote_path = f"/workspace/{rel_path}"
                    result = subprocess.run(
                        ["modal", "volume", "put", workspace_volume, local_path, remote_path, "--force"],
                        capture_output=True, text=True, env=env,
                    )
                    if result.returncode == 0:
                        console.print(f"  [green]↑[/green] {rel_path}")
                    else:
                        console.print(f"  [red]✗[/red] {rel_path}: {result.stderr.strip()}")

            if deleted:
                console.print(f"[yellow][sync #{sync_count}][/yellow] {len(deleted)} file(s) deleted")
                for rel_path in deleted:
                    remote_path = f"/workspace/{rel_path}"
                    subprocess.run(
                        ["modal", "volume", "rm", workspace_volume, remote_path],
                        capture_output=True, text=True, env=env,
                    )
                    console.print(f"  [red]−[/red] {rel_path}")

            prev_state = curr_state

    except KeyboardInterrupt:
        console.print(f"\n[bold yellow]Sync stopped.[/bold yellow] ({sync_count} syncs performed)")


# ─── VM Deployment Support ────────────────────────────────────
# Provision GPU containers on Modal and run multi-service compose stacks.
# Uses Modal as the infrastructure provider — detects Triton Server, handles
# gRPC + HTTP tunnels, model repository volumes, and ensemble pipelines.
# User does NOT need their own VM — m-gpux creates the container for them.


# Known specialized images and their properties
_KNOWN_IMAGES = {
    "tritonserver": {
        "patterns": ["nvcr.io/nvidia/tritonserver", "tritonserver", "nvidia/tritonserver"],
        "has_python": True, # Các bản -py3 của NVIDIA đã có sẵn python
        "default_cmd": "tritonserver --model-repository=/app/model_repository --log-verbose=1",
        "default_port": 8000,
        "extra_ports": [8001, 8002],
    },
}


def _detect_compose_base_image(services: dict) -> Optional[str]:
    """Detect if any service uses a specialized container image (e.g. Triton Server).
    
    Returns the image registry path if found, or None for generic workloads.
    """
    for svc_config in services.values():
        image = svc_config.get("image", "")
        if not image:
            continue
        image_lower = image.lower()
        for info in _KNOWN_IMAGES.values():
            for pattern in info["patterns"]:
                if pattern in image_lower:
                    return image
    return None


def _image_has_python(base_image: Optional[str]) -> bool:
    """Check if the base image already includes Python."""
    if not base_image:
        return False
    image_lower = base_image.lower()
    for info in _KNOWN_IMAGES.values():
        for pattern in info["patterns"]:
            if pattern in image_lower:
                return info.get("has_python", False)
    return False


# Images built FROM scratch or minimal distroless — no /bin/sh, can't add_python
_MINIMAL_IMAGE_PATTERNS = [
    "cloudflare/cloudflared",
    "cloudflared",
    "gcr.io/distroless/",
    "busybox",
    "traefik",
    "haproxy",
    "envoyproxy/envoy",
    "hashicorp/consul",
    "hashicorp/vault",
    "quay.io/coreos/etcd",
    "grafana/grafana",
    "prom/prometheus",
    "minio/minio",
]


def _is_minimal_image(image_name: str) -> bool:
    """Check if an image is scratch/distroless-based (no shell, can't add Python)."""
    name_lower = image_name.lower().split(":")[0]  # strip tag
    return any(pat in name_lower for pat in _MINIMAL_IMAGE_PATTERNS)


def _detect_infra_apt_packages(services: dict) -> list[str]:
    """Detect infrastructure services (redis, postgres, etc.) that need apt packages.
    
    When running everything in a single container, we need to install
    binaries for infra services that would normally be separate containers.
    """
    apt_packages = []
    for svc_name, svc_config in services.items():
        image = svc_config.get("image", "").lower()
        name_lower = svc_name.lower()
        # Redis
        if "redis" in image or name_lower == "redis":
            apt_packages.append("redis-server")
        # PostgreSQL
        elif "postgres" in image or name_lower in ("postgres", "postgresql", "db"):
            apt_packages.extend(["postgresql", "postgresql-client"])
        # Memcached
        elif "memcached" in image or name_lower == "memcached":
            apt_packages.append("memcached")
        # Nginx
        elif "nginx" in image or name_lower == "nginx":
            apt_packages.append("nginx")
    return apt_packages


def _get_known_image_default_cmd(image: str) -> Optional[str]:
    """Get default command for a known image if not specified in compose."""
    image_lower = image.lower()
    for info in _KNOWN_IMAGES.values():
        for pattern in info["patterns"]:
            if pattern in image_lower:
                return info.get("default_cmd")
    return None


def _parse_x_mgpux(data: dict) -> dict:
    """Parse x-mgpux metadata from compose file for explicit configuration.
    
    Supports:
      x-mgpux:
        base_image: nvcr.io/nvidia/tritonserver:25.04-py3
        pip_packages: ["gliner", "transformers", ...]
        apt_packages: ["redis-server"]
    """
    return data.get("x-mgpux", {})


def _detect_gpu_requirement(services: dict) -> bool:
    """Check if any service in the compose file requires GPU."""
    for svc_config in services.values():
        # Check deploy.resources.reservations.devices
        deploy = svc_config.get("deploy", {})
        if isinstance(deploy, dict):
            resources = deploy.get("resources", {})
            if isinstance(resources, dict):
                reservations = resources.get("reservations", {})
                if isinstance(reservations, dict):
                    devices = reservations.get("devices", [])
                    for dev in (devices if isinstance(devices, list) else []):
                        if isinstance(dev, dict) and "gpu" in str(dev.get("capabilities", [])):
                            return True
        # Check runtime: nvidia
        if svc_config.get("runtime") == "nvidia":
            return True
    return False


def _extract_volume_mounts(services: dict) -> list[tuple[str, str]]:
    """Extract host:container volume mounts from services.
    
    Returns list of (local_path, container_path) tuples for bind mounts.
    """
    mounts = []
    seen = set()
    for svc_config in services.values():
        volumes = svc_config.get("volumes", [])
        for vol in volumes:
            if isinstance(vol, str) and ":" in vol:
                parts = vol.split(":")
                if len(parts) >= 2:
                    local_path = parts[0]
                    container_path = parts[1]
                    # Only include relative/local path mounts (not named volumes)
                    if local_path.startswith("./") or local_path.startswith("/") or local_path.startswith(".."):
                        key = (local_path, container_path)
                        if key not in seen:
                            seen.add(key)
                            mounts.append(key)
            elif isinstance(vol, dict):
                source = vol.get("source", "")
                target = vol.get("target", "")
                vol_type = vol.get("type", "bind")
                if vol_type == "bind" and source and target:
                    key = (source, target)
                    if key not in seen:
                        seen.add(key)
                        mounts.append(key)
    return mounts


def _collect_all_ports(services: dict) -> list[tuple[str, int]]:
    """Collect all exposed ports across all services.
    
    Returns list of (service_name, port) tuples.
    """
    result = []
    seen_ports = set()
    for svc_name, svc_config in services.items():
        ports = svc_config.get("ports", [])
        for port_spec in ports:
            port_str = str(port_spec)
            # Parse "host:container" or just "container"
            if ":" in port_str:
                container_port = port_str.split(":")[-1].split("/")[0]
            else:
                container_port = port_str.split("/")[0]
            try:
                port = int(container_port)
                if port not in seen_ports:
                    seen_ports.add(port)
                    result.append((svc_name, port))
            except ValueError:
                pass
    return result


def _build_vm_compose_script(
    *,
    services: dict,
    base_image: Optional[str],
    compute_spec: str,
    local_dir: str,
    workspace_volume: str,
    exclude_patterns: list[str],
    tunnel_ports: list[tuple[str, int]],
    volume_mounts: list[tuple[str, str]],
    pip_packages: list[str] = None,
    extra_apt: list[str] = None,
) -> str:
    """Generate a Modal script that runs compose services as subprocesses.
    
    Uses the detected base image (e.g. tritonserver) or falls back to CUDA image.
    All services run as subprocesses within a single Modal container.
    Services can communicate via localhost (all ports on 127.0.0.1).
    """

    # Determine base image — don't add Python if image already has it
    if base_image:
        if _image_has_python(base_image):
            image_line = f'modal.Image.from_registry("{base_image}")'
        else:
            image_line = f'modal.Image.from_registry("{base_image}", add_python="3.11")'
    else:
        image_line = 'modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")'

    # Collect commands for each service
    service_commands = {}
    ordered_services = _topological_sort(services)
    for svc_name in ordered_services:
        svc_config = services[svc_name]
        command = _command_to_shell(svc_config.get("command", ""))
        if not command:
            # Try extracting from Dockerfile
            compose_dir = local_dir
            command = _extract_dockerfile_cmd(svc_config, compose_dir=compose_dir)
        if not command:
            # Try known image default command
            svc_image = svc_config.get("image", "")
            if svc_image:
                command = _get_known_image_default_cmd(svc_image)
        if not command:
            # Fallback for common infra services
            svc_image = svc_config.get("image", "").lower()
            name_lower = svc_name.lower()
            if "redis" in svc_image or name_lower == "redis":
                port = _extract_port(svc_config) or 6379
                command = f"redis-server --bind 127.0.0.1 --port {port} --daemonize no"
        if command:
            port = _extract_port(svc_config)
            service_commands[svc_name] = {"cmd": command, "port": port}

    # Collect environment variables from all services
    all_env = {}
    for svc_name, svc_config in services.items():
        svc_env = _extract_env_vars(svc_config)
        # Replace service hostname references with localhost
        for k, v in svc_env.items():
            for other_svc in services:
                if other_svc in str(v):
                    v = v.replace(other_svc, "127.0.0.1")
            all_env[k] = v
        # Also extract Dockerfile ENVs
        dockerfile_envs = _extract_dockerfile_envs(svc_config, compose_dir=local_dir)
        for k, v in dockerfile_envs.items():
            if k not in all_env:
                all_env[k] = v

    # Build volume copy commands for model_repository etc.
    volume_copy_lines = []
    for local_path, container_path in volume_mounts:
        # Normalize local path relative to workspace
        if local_path.startswith("./"):
            local_path = local_path[2:]
        # makedirs BEFORE copy
        volume_copy_lines.append(
            f'    os.makedirs("{container_path}", exist_ok=True)'
        )
        volume_copy_lines.append(
            f'    subprocess.run(["cp", "-a", "/workspace_seed/{local_path}/.", "{container_path}/"], check=False)'
        )
        volume_copy_lines.append(
            f'    print("[VM] Volume mount: /workspace_seed/{local_path} → {container_path}", flush=True)'
        )

    volume_copy_block = "\n".join(volume_copy_lines) if volume_copy_lines else "    pass  # no volume mounts"

    # Build service registry
    svc_registry_lines = []
    infra_names = []
    for svc_name, info in service_commands.items():
        svc_registry_lines.append(
            f'    "{svc_name}": {{"cmd": {repr(info["cmd"])}, "port": {info["port"]}}},'
        )
        infra_names.append(svc_name)
    svc_registry_block = "\n".join(svc_registry_lines)

    # Environment exports
    env_exports = "\n".join(
        f'    os.environ["{k}"] = "{v}"'
        for k, v in all_env.items()
        if v and "${" not in v  # skip unresolved refs
    )

    # /etc/hosts entries for service name resolution
    hosts_entries = "\n".join(
        f'    "127.0.0.1 {name}",'
        for name in services.keys()
    )

    # Pip install line
    pip_line = ""
    if pip_packages:
        quoted_pkgs = ", ".join(f'"{p}"' for p in pip_packages)
        pip_line = f"\n    .pip_install({quoted_pkgs})"

    # Extra apt packages — include infra service binaries
    infra_apt = _detect_infra_apt_packages(services)
    apt_list = list(extra_apt or []) + infra_apt + ["curl", "procps", "net-tools"]
    apt_line = f"\n    .apt_install({repr(sorted(set(apt_list)))})" if apt_list else ""

    # Tunnel section
    if len(tunnel_ports) == 1:
        svc_name, port = tunnel_ports[0]
        tunnel_block = f'''
    with modal.forward({port}, unencrypted=True) as tunnel:
        print("\\n" + "=" * 60)
        print(f"[VM READY] {{tunnel.url}}")
        print(f"  Service: {svc_name} (port {port})")
        print(f"  All services: {{', '.join(svc_commands.keys())}}")
        print("=" * 60 + "\\n", flush=True)
        _supervisor_loop(procs, svc_commands)
'''
    else:
        tunnel_ports_repr = repr(tunnel_ports)
        tunnel_block = f'''
    from contextlib import ExitStack
    tunnel_ports = {tunnel_ports_repr}
    with ExitStack() as stack:
        tunnels = {{}}
        for svc_name, port in tunnel_ports:
            tun = stack.enter_context(modal.forward(port, unencrypted=True))
            tunnels[svc_name] = (port, tun.url)

        print("\\n" + "=" * 60)
        print("[VM READY] All tunnels open")
        print("-" * 60)
        for svc_name, (port, url) in tunnels.items():
            print(f"  {{svc_name}} (port {{port}}): {{url}}")
        print("-" * 60)
        print(f"  Services running: {{', '.join(procs.keys())}}")
        print("=" * 60 + "\\n", flush=True)
        _supervisor_loop(procs, svc_commands)
'''

    script = f'''
import modal
import os
import sys
import subprocess
import threading
import time
import socket

# __METRICS__

MAX_RESTARTS = 5

app = modal.App("m-gpux-compose-vm")
workspace_volume = modal.Volume.from_name("{workspace_volume}", create_if_missing=True)
image = (
    {image_line}
    .entrypoint([]){apt_line}{pip_line}
    .add_local_dir("{local_dir}", remote_path="/workspace_seed", ignore={repr(to_recursive_ignore(exclude_patterns))})
)

# Service command registry
svc_commands = {{
{svc_registry_block}
}}

SERVICE_ORDER = {repr(infra_names)}

def _setup_volumes():
    """Copy volume-mounted directories into place."""
{volume_copy_block}

def _setup_environment():
    """Set environment variables from compose config."""
{env_exports if env_exports else "    pass"}

def _write_hosts():
    """Add service name entries to /etc/hosts for localhost resolution."""
    entries = [
{hosts_entries}
    ]
    with open("/etc/hosts", "a") as f:
        f.write("\\n# m-gpux compose-vm services\\n")
        for entry in entries:
            f.write(entry + "\\n")
    print("[VM] /etc/hosts updated:", entries, flush=True)

def _wait_for_port(port, timeout=60):
    """Block until a port is accepting connections or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False

def _start_service(name, procs):
    """Start a single service by name."""
    info = svc_commands[name]
    cmd = info["cmd"]
    print(f"[VM] Starting {{name}}: {{cmd}}", flush=True)
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd="/workspace_seed",
        env={{**os.environ}},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    def _fwd():
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace")
                sys.stdout.write(f"[{{name}}] {{line}}")
                sys.stdout.flush()
        except Exception:
            pass
    threading.Thread(target=_fwd, daemon=True).start()
    procs[name] = proc
    return proc

def _supervisor_loop(procs, svc_commands):
    """Monitor processes; auto-restart crashed ones."""
    restart_counts = {{}}
    while True:
        time.sleep(5)
        for name, proc in list(procs.items()):
            ret = proc.poll()
            if ret is not None:
                count = restart_counts.get(name, 0)
                if count >= MAX_RESTARTS:
                    if count == MAX_RESTARTS:
                        print(f"[VM] FATAL: {{name}} crashed {{MAX_RESTARTS}} times. Giving up.", flush=True)
                        restart_counts[name] = count + 1
                    continue
                restart_counts[name] = count + 1
                print(f"[VM] {{name}} exited (code {{ret}}). Restarting ({{count+1}}/{{MAX_RESTARTS}})...", flush=True)
                time.sleep(2)
                _start_service(name, procs)

@app.function(image=image, {compute_spec}, timeout=86400, volumes={{"/workspace": workspace_volume}})
def run_compose_vm():
    _print_metrics()

    # Setup
    _write_hosts()
    _setup_environment()
    _setup_volumes()

    procs = {{}}

    # Start all services in dependency order
    for name in SERVICE_ORDER:
        _start_service(name, procs)
        port = svc_commands[name]["port"]
        if port:
            print(f"[VM] Waiting for {{name}} on port {{port}}...", flush=True)
            if _wait_for_port(port, timeout=60):
                print(f"[VM] {{name}} ready (port {{port}})", flush=True)
            else:
                print(f"[VM] WARNING: {{name}} port {{port}} not responding after 60s", flush=True)
        else:
            time.sleep(3)

    # Open tunnels and supervise
{tunnel_block}
'''
    return script


def compose_vm_up(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Deploy a Docker Compose stack on a Modal GPU container.

    Parses your compose file, detects services (Triton Server, custom apps, etc.),
    provisions a Modal GPU container with the correct base image, and runs all
    services as managed subprocesses with tunnel access.

    This is the "Full Triton Server" / multi-service path that uses Modal's
    infrastructure — no need for your own VM.

    Examples:
        m-gpux compose vm up -f compose.triton.yaml
        m-gpux compose vm up
    """
    console.print(Panel.fit(
        "[bold magenta]m-gpux Compose VM[/bold magenta]\n"
        "Provision GPU container on Modal & deploy compose stack.\n"
        "[dim]Multi-service • Triton/gRPC • NVIDIA GPU • Auto-tunnel[/dim]",
        border_style="cyan",
    ))

    # --- Find compose file ---
    compose_path = file or _find_compose_file()
    if compose_path is None:
        console.print("[bold red]No docker-compose.yml or compose.yml found.[/bold red]")
        console.print("[dim]Use --file / -f to specify a path.[/dim]")
        raise typer.Exit(1)

    console.print(f"[green]Compose file:[/green] [bold]{compose_path}[/bold]")

    # --- Parse compose file ---
    data = _parse_compose(compose_path)
    services = data["services"]

    # --- Read x-mgpux metadata for explicit configuration ---
    mgpux_meta = _parse_x_mgpux(data)

    # --- Detect base image (x-mgpux.base_image overrides auto-detection) ---
    base_image = mgpux_meta.get("base_image") or _detect_compose_base_image(services)
    has_gpu = _detect_gpu_requirement(services)

    # --- Display services ---
    svc_table = Table(show_header=True, header_style="bold cyan")
    svc_table.add_column("Service")
    svc_table.add_column("Image / Build")
    svc_table.add_column("Ports")
    svc_table.add_column("GPU")

    for svc_name, svc_config in services.items():
        image = svc_config.get("image", "")
        build_cfg = svc_config.get("build", "")
        display_img = image or (f"build: {build_cfg}" if isinstance(build_cfg, str) else "build: .")
        ports = ", ".join(str(p) for p in svc_config.get("ports", [])) or "-"
        # Per-service GPU check
        svc_gpu = False
        deploy = svc_config.get("deploy", {})
        if isinstance(deploy, dict):
            resources = deploy.get("resources", {})
            if isinstance(resources, dict):
                reservations = resources.get("reservations", {})
                if isinstance(reservations, dict):
                    devices = reservations.get("devices", [])
                    for dev in (devices if isinstance(devices, list) else []):
                        if isinstance(dev, dict) and "gpu" in str(dev.get("capabilities", [])):
                            svc_gpu = True
        if svc_config.get("runtime") == "nvidia":
            svc_gpu = True
        gpu_label = "[bold green]✓ GPU[/bold green]" if svc_gpu else "-"
        svc_table.add_row(svc_name, display_img[:60], ports, gpu_label)

    console.print(svc_table)

    if base_image:
        console.print(f"\n[green]Detected base image:[/green] [bold]{base_image}[/bold]")
        if "triton" in base_image.lower():
            console.print("[dim]  → Full Triton Inference Server (ensemble, gRPC, HTTP, metrics)[/dim]")

    # --- Collect ports for tunneling ---
    tunnel_ports = _collect_all_ports(services)
    if tunnel_ports:
        console.print(f"\n[cyan]Ports to tunnel:[/cyan] {', '.join(f'{name}:{port}' for name, port in tunnel_ports)}")

    # --- Volume mounts ---
    volume_mounts = _extract_volume_mounts(services)
    if volume_mounts:
        console.print(f"[cyan]Volume mounts:[/cyan]")
        for local_p, container_p in volume_mounts:
            console.print(f"  {local_p} → {container_p}")

    # --- Select workspace/profile ---
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    # --- Compute selection ---
    console.print("\n[bold cyan]Select Compute[/bold cyan]")
    if has_gpu:
        gpu_options = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
        # Default to T4 for inference, A10G for Triton
        default_gpu_idx = 2 if base_image and "triton" in base_image.lower() else 1
        gpu_idx = arrow_select(gpu_options, title="Select GPU", default=default_gpu_idx)
        selected_gpu = list(AVAILABLE_GPUS.values())[gpu_idx][0]
        compute_spec = f'gpu="{selected_gpu}"'
        compute_label = selected_gpu
    else:
        compute_type_options = [
            ("GPU", "GPU acceleration"),
            ("CPU", "CPU-only (cheaper)"),
        ]
        compute_type_idx = arrow_select(compute_type_options, title="Compute Type", default=0)
        if compute_type_idx == 1:
            cpu_keys = list(AVAILABLE_CPUS.keys())
            cpu_options = [(f"{AVAILABLE_CPUS[k][0]} cores", AVAILABLE_CPUS[k][2]) for k in cpu_keys]
            cpu_idx = arrow_select(cpu_options, title="Select CPU", default=2)
            cores, memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
            compute_spec = f'cpu={cores}, memory={memory}'
            compute_label = f"CPU ({cores} cores, {memory} MB)"
        else:
            gpu_options = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
            gpu_idx = arrow_select(gpu_options, title="Select GPU", default=1)
            selected_gpu = list(AVAILABLE_GPUS.values())[gpu_idx][0]
            compute_spec = f'gpu="{selected_gpu}"'
            compute_label = selected_gpu

    console.print(f"[green]Compute:[/green] [bold]{compute_label}[/bold]")

    # --- Extra pip packages ---
    pip_packages = []

    # 1) From x-mgpux metadata (highest priority — explicit user config)
    if mgpux_meta.get("pip_packages"):
        pip_packages.extend(mgpux_meta["pip_packages"])

    # 2) Auto-detect from compose service builds (requirements.txt in build context)
    for svc_name, svc_config in services.items():
        build_ctx = svc_config.get("build", {})
        if isinstance(build_ctx, dict):
            context = build_ctx.get("context", ".")
            req_path = os.path.join(context, "requirements.txt")
            if os.path.exists(req_path):
                with open(req_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("-"):
                            if line not in pip_packages:
                                pip_packages.append(line)

    # 3) If triton base image detected, add essential packages
    if base_image and "triton" in base_image.lower():
        triton_essentials = [
            "tritonclient[grpc]",
            "fastapi",
            "uvicorn[standard]",
        ]
        for pkg in triton_essentials:
            if not any(pkg.split("[")[0] in p for p in pip_packages):
                pip_packages.append(pkg)

    # --- Extra apt packages from x-mgpux ---
    extra_apt = list(mgpux_meta.get("apt_packages", []))

    if pip_packages:
        console.print(f"[cyan]Pip packages:[/cyan] {', '.join(pip_packages[:10])}")
        if len(pip_packages) > 10:
            console.print(f"  [dim]... and {len(pip_packages) - 10} more[/dim]")

    # --- Exclude patterns ---
    default_excludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox"
    exclude_input = Prompt.ask(
        "[bold cyan]Exclude patterns[/bold cyan]",
        default=default_excludes,
    )
    exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]

    # --- Generate script ---
    local_dir_escaped = os.path.abspath(".").replace("\\", "/")
    workspace_volume = _workspace_volume_name(".")

    console.print("\n[bold cyan]Generating Modal VM script...[/bold cyan]")

    script = _build_vm_compose_script(
        services=services,
        base_image=base_image,
        compute_spec=compute_spec,
        local_dir=local_dir_escaped,
        workspace_volume=workspace_volume,
        exclude_patterns=exclude_patterns,
        tunnel_ports=tunnel_ports,
        volume_mounts=volume_mounts,
        pip_packages=pip_packages if pip_packages else None,
        extra_apt=extra_apt if extra_apt else None,
    )

    # Show summary
    console.print(Panel(
        f"[bold]Compose VM Deployment[/bold]\n\n"
        f"  Compose file: {compose_path}\n"
        f"  Base image: {base_image or 'nvidia/cuda:12.8.1-devel-ubuntu22.04'}\n"
        f"  Services: {', '.join(services.keys())}\n"
        f"  Compute: {compute_label}\n"
        f"  Tunnels: {', '.join(f'{n}:{p}' for n, p in tunnel_ports)}\n"
        f"  Volume: {workspace_volume}\n\n"
        f"[dim]All service hostnames resolve to 127.0.0.1 inside the container.\n"
        f"Triton gRPC/HTTP and custom services are tunneled automatically.[/dim]",
        title="DEPLOYMENT PLAN",
        border_style="green",
    ))

    execute_modal_temp_script(
        script,
        f"Compose VM ({', '.join(services.keys())}) on {compute_label}",
        detach=True,
        session_metadata={
            "id": new_session_id(),
            "kind": "compose-vm",
            "profile": selected_profile,
            "compute": compute_label,
            "workspace_volume": workspace_volume,
            "local_dir": os.path.abspath("."),
            "app_name": "m-gpux-compose-vm",
            "services": list(services.keys()),
            "base_image": base_image or "",
            "ports": [p for _, p in tunnel_ports],
        },
    )


def compose_vm_check(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Analyze a compose file for VM deployment without deploying.
    
    Shows detected services, base image, GPU requirements, ports, and volumes.
    """
    compose_path = file or _find_compose_file()
    if compose_path is None:
        console.print("[bold red]No compose file found.[/bold red]")
        raise typer.Exit(1)

    data = _parse_compose(compose_path)
    services = data["services"]

    console.print(Panel.fit(
        f"[bold magenta]Compose VM Analysis[/bold magenta] — {compose_path}",
        border_style="cyan",
    ))

    base_image = _detect_compose_base_image(services)
    has_gpu = _detect_gpu_requirement(services)
    tunnel_ports = _collect_all_ports(services)
    volume_mounts = _extract_volume_mounts(services)

    console.print(f"\n[bold cyan]Base Image:[/bold cyan] {base_image or '(generic CUDA)'}")
    if base_image and "triton" in base_image.lower():
        console.print("  [green]✓ Triton Inference Server detected[/green]")
        console.print("  [dim]Supports: ensemble pipelines, gRPC batching, ONNX/TensorRT backends[/dim]")

    console.print(f"\n[bold cyan]GPU Required:[/bold cyan] {'Yes' if has_gpu else 'No'}")

    console.print(f"\n[bold cyan]Services ({len(services)}):[/bold cyan]")
    for svc_name, svc_config in services.items():
        image = svc_config.get("image", "(build)")
        command = _command_to_shell(svc_config.get("command", "")) or "(from Dockerfile)"
        ports = svc_config.get("ports", [])
        console.print(f"  [bold]{svc_name}[/bold]")
        console.print(f"    Image: {image}")
        console.print(f"    Command: {command[:80]}")
        if ports:
            console.print(f"    Ports: {', '.join(str(p) for p in ports)}")

    if tunnel_ports:
        console.print(f"\n[bold cyan]Tunneled Ports:[/bold cyan]")
        for name, port in tunnel_ports:
            protocol = "gRPC" if port == 8001 else "HTTP" if port in (8000, 8080) else "TCP"
            console.print(f"  {name}:{port} ({protocol})")

    if volume_mounts:
        console.print(f"\n[bold cyan]Volume Mounts:[/bold cyan]")
        for local_p, container_p in volume_mounts:
            console.print(f"  {local_p} → {container_p}")

    console.print(f"\n[bold green]Ready for deployment.[/bold green]")
    console.print("[dim]Run `m-gpux compose vm up` to deploy on Modal.[/dim]")


# ─── Sandbox Multi-Container Mode ─────────────────────────────
# Each Docker Compose service runs in its own Modal Sandbox for true isolation.
# Uses Image.from_dockerfile when available, Sandbox.exec for commands,
# readiness probes for dependency ordering, and tunnels for networking.


def _dockerfile_has_python(dockerfile_path: str) -> bool:
    """Check if a Dockerfile already provides Python (so add_python is not needed)."""
    import re

    try:
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
    except OSError:
        return False

    # Check for uv (installs its own Python), pip, or python in base image
    indicators = [
        r"\buv\s+sync\b",
        r"\buv\s+pip\b",
        r"\bpip\s+install\b",
        r"from\s+.*python:",
        r"apt-get\s+install\s+.*python3?\b",
        r"copy\s+--from=.*uv",
    ]
    return any(re.search(pat, content) for pat in indicators)


def _preprocess_dockerfile_for_modal(dockerfile_path: str, output_path: str, target: str = "") -> bool:
    """Preprocess a Dockerfile to work with Modal's builder.

    Modal's from_dockerfile does NOT support BuildKit features:
    - RUN --mount=type=bind,source=X,target=Y → converted to COPY X Y before the RUN
    - RUN --mount=type=cache,... → mount flag stripped, RUN kept
    - # syntax=docker/dockerfile:1 → removed

    Also handles Docker build targets: if target is specified, truncates the
    Dockerfile after the target stage (Modal doesn't support --target).

    Returns True if preprocessing was needed, False if Dockerfile is compatible as-is.
    """
    import re

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check if preprocessing is needed
    needs_mount_fix = "--mount=" in content
    needs_syntax_fix = "# syntax=" in content.split("\n")[0]
    needs_target_fix = bool(target)
    if not needs_mount_fix and not needs_syntax_fix and not needs_target_fix:
        return False

    lines = content.split("\n")

    # If target is specified, truncate after the target stage
    if target:
        truncated_lines = []
        found_target = False
        in_target_stage = False
        for line in lines:
            stripped = line.strip()
            from_match = re.match(r'^FROM\s+\S+(?:\s+AS\s+(\S+))?', stripped, re.IGNORECASE)
            if from_match:
                stage_name = from_match.group(1) or ""
                if in_target_stage:
                    # We've reached the next FROM after target — stop here
                    break
                if stage_name.lower() == target.lower():
                    found_target = True
                    in_target_stage = True
            truncated_lines.append(line)
        if found_target:
            lines = truncated_lines

    output_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Remove syntax directive
        if line.strip().startswith("# syntax="):
            i += 1
            continue

        # Join backslash-continued lines for RUN commands
        if line.strip().upper().startswith("RUN ") and "--mount=" in line:
            # Collect the full multi-line RUN command
            full_cmd = line.rstrip()
            while full_cmd.endswith("\\") and i + 1 < len(lines):
                i += 1
                full_cmd = full_cmd[:-1] + " " + lines[i].strip()

            # Extract all --mount options
            bind_mounts = []  # (source, target) pairs to convert to COPY
            # Parse --mount=type=bind,source=X,target=Y
            mount_pattern = re.compile(
                r'--mount=type=bind,([^,\s]+(?:,[^,\s]+)*)', re.IGNORECASE
            )
            for mount_match in mount_pattern.finditer(full_cmd):
                mount_opts = mount_match.group(1)
                source = ""
                target = ""
                for opt in mount_opts.split(","):
                    if opt.startswith("source="):
                        source = opt.split("=", 1)[1]
                    elif opt.startswith("target="):
                        target = opt.split("=", 1)[1]
                if source and target:
                    bind_mounts.append((source, target))

            # Emit COPY for each bind mount
            for source, target in bind_mounts:
                # Determine the directory for the target
                target_dir = os.path.dirname(target)
                if target_dir and target_dir != "/" and target_dir != ".":
                    output_lines.append(f"RUN mkdir -p {target_dir}")
                output_lines.append(f"COPY {source} {target}")

            # Strip all --mount=... flags from the RUN command
            cleaned = re.sub(r'\s*--mount=\S+', '', full_cmd)
            # Clean up extra whitespace
            cleaned = re.sub(r'RUN\s+', 'RUN ', cleaned).strip()
            if cleaned and cleaned != "RUN":
                output_lines.append(cleaned)
        else:
            output_lines.append(line)

        i += 1

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(output_lines))

    return True


def _resolve_service_image(
    svc_name: str,
    svc_config: dict,
    compose_dir: str,
    exclude_patterns: list[str],
    python_version: str = "3.12",
) -> str:
    """Generate a Modal Image expression string for a service.

    Priority:
    1. image: <registry> → Image.from_registry
    2. build: with Dockerfile → Image.from_dockerfile
    3. Known infra service → Image.debian_slim + apt_install
    4. Fallback → debian_slim
    """
    image_name = svc_config.get("image", "")
    build_cfg = svc_config.get("build", {})

    # 1) Registry image
    if image_name and not build_cfg:
        # Check if image has python
        if _image_has_python(image_name) or "python" in image_name.lower():
            return f'modal.Image.from_registry("{image_name}").entrypoint([])'
        # Minimal/scratch-based images have no shell — can't add_python
        if _is_minimal_image(image_name):
            return f'modal.Image.from_registry("{image_name}").entrypoint([])'
        return f'modal.Image.from_registry("{image_name}", add_python="{python_version}").entrypoint([])'

    # 2) Dockerfile build
    if build_cfg:
        if isinstance(build_cfg, str):
            context = build_cfg
            dockerfile = "Dockerfile"
            target = ""
        elif isinstance(build_cfg, dict):
            context = build_cfg.get("context", ".")
            dockerfile = build_cfg.get("dockerfile", "Dockerfile")
            target = build_cfg.get("target", "")
        else:
            context = "."
            dockerfile = "Dockerfile"
            target = ""

        dockerfile_full = os.path.join(compose_dir, context, dockerfile)
        context_full = os.path.join(compose_dir, context)

        if os.path.exists(dockerfile_full):
            # Preprocess Dockerfile to handle BuildKit features Modal doesn't support
            safe_name = svc_name.replace("-", "_").replace(".", "_")
            preprocessed_name = f".modal_Dockerfile.{safe_name}"
            preprocessed_path = os.path.join(compose_dir, context, preprocessed_name)

            needs_preprocess = _preprocess_dockerfile_for_modal(dockerfile_full, preprocessed_path, target=target)
            if needs_preprocess:
                actual_dockerfile = os.path.relpath(preprocessed_path, compose_dir).replace("\\", "/")
            else:
                actual_dockerfile = os.path.relpath(dockerfile_full, compose_dir).replace("\\", "/")
                # Remove preprocessed file if it wasn't needed
                try:
                    os.remove(preprocessed_path)
                except OSError:
                    pass

            context_rel = os.path.relpath(context_full, compose_dir).replace("\\", "/")

            # Check if Dockerfile already provides Python (uv, pip, python base image)
            has_python = _dockerfile_has_python(dockerfile_full)

            # Use from_dockerfile for proper multi-stage builds
            lines = [f'modal.Image.from_dockerfile(']
            lines.append(f'        "{actual_dockerfile}",')
            lines.append(f'        context_dir="{context_rel}",')
            if not has_python:
                lines.append(f'        add_python="{python_version}",')
            # Let Modal use AUTO_DOCKERIGNORE (reads .dockerignore automatically)
            # Only add extra ignore patterns if no .dockerignore exists
            dockerignore_path = os.path.join(context_full, ".dockerignore")
            if exclude_patterns and not os.path.exists(dockerignore_path):
                lines.append(f'        ignore={repr(to_recursive_ignore(exclude_patterns))},')
            lines.append(f'    ).entrypoint([])')
            return "\n    ".join(lines)

    # 3) Known infra service
    svc_type = _detect_service_type(svc_name, svc_config)
    if svc_type and svc_type in SERVICE_INSTALLERS:
        installer = SERVICE_INSTALLERS[svc_type]
        apt_pkgs = repr(installer["apt"])
        return f'modal.Image.debian_slim().apt_install({apt_pkgs}).entrypoint([])'

    # 4) Fallback
    return f'modal.Image.debian_slim(python_version="{python_version}").entrypoint([])'


def _get_service_dependencies(svc_config: dict) -> list[str]:
    """Extract depends_on with condition info."""
    depends = svc_config.get("depends_on", [])
    if isinstance(depends, list):
        return [(d, "started") for d in depends]
    if isinstance(depends, dict):
        result = []
        for name, cfg in depends.items():
            if isinstance(cfg, dict):
                condition = cfg.get("condition", "service_started")
            else:
                condition = "service_started"
            result.append((name, condition))
        return result
    return []


def _get_service_ports(svc_config: dict) -> list[int]:
    """Extract all container-side ports from a service."""
    ports = []
    for port_spec in svc_config.get("ports", []):
        port_str = str(port_spec)
        if ":" in port_str:
            container_port = port_str.split(":")[-1].split("/")[0]
        else:
            container_port = port_str.split("/")[0]
        try:
            ports.append(int(container_port))
        except ValueError:
            pass
    # Also check expose
    for port_spec in svc_config.get("expose", []):
        try:
            p = int(str(port_spec).split("/")[0])
            if p not in ports:
                ports.append(p)
        except ValueError:
            pass
    return ports


def _service_needs_gpu(svc_config: dict) -> bool:
    """Check if a specific service requires GPU."""
    deploy = svc_config.get("deploy", {})
    if isinstance(deploy, dict):
        resources = deploy.get("resources", {})
        if isinstance(resources, dict):
            reservations = resources.get("reservations", {})
            if isinstance(reservations, dict):
                devices = reservations.get("devices", [])
                for dev in (devices if isinstance(devices, list) else []):
                    if isinstance(dev, dict) and "gpu" in str(dev.get("capabilities", [])):
                        return True
    if svc_config.get("runtime") == "nvidia":
        return True
    return False


def _build_sandbox_compose_script(
    *,
    services: dict,
    compose_dir: str,
    exclude_patterns: list[str],
    user_env_values: dict[str, str],
    python_version: str = "3.12",
    gpu_spec: str = "T4",
    cpu_spec: tuple[int, int] = None,
    workspace_volume_name: str,
    selected_services: list[str] = None,
    gpu_override: dict[str, bool] = None,
) -> str:
    """Generate a Modal script that deploys each service as a separate Sandbox.

    Key features:
    - Each service runs in its own Sandbox (true isolation)
    - Image.from_dockerfile for Dockerfile-based services
    - Proper depends_on with wait()/wait_until_ready()
    - Inter-service networking via Sandbox tunnels
    - Shared volumes between sandboxes
    """

    # Determine which services to run (selected + transitive deps)
    def _get_transitive_deps(svc_name, all_services, visited=None):
        if visited is None:
            visited = set()
        if svc_name in visited:
            return visited
        visited.add(svc_name)
        svc_config = all_services.get(svc_name, {})
        depends = svc_config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        for dep in depends:
            if dep in all_services:
                _get_transitive_deps(dep, all_services, visited)
        return visited

    active_services = set()
    targets = selected_services or list(services.keys())
    for svc in targets:
        if svc in services:
            active_services.update(_get_transitive_deps(svc, services))
    services = {k: v for k, v in services.items() if k in active_services}

    # ─── Co-locate TCP infra services ─────────────────────────────
    # TCP-only services (redis, postgres, memcached, mongodb) can't communicate
    # across sandboxes via HTTP tunnels. Nginx also needs hostname resolution
    # to its upstream. We embed these as sidecar processes in the sandboxes
    # that depend on them.
    COLOCATE_TYPES = {"redis", "postgres", "memcached", "mongodb", "nginx"}

    # Identify which infra services to co-locate and where
    colocated_infra = {}  # infra_svc_name → list of dependent svc names
    colocate_svcs = set()
    for svc_name, svc_config in services.items():
        svc_type = _detect_service_type(svc_name, svc_config)
        if svc_type in COLOCATE_TYPES:
            colocate_svcs.add(svc_name)
            # Find which services depend on this infra
            dependents = []
            for other_name, other_config in services.items():
                if other_name == svc_name:
                    continue
                dep_list = other_config.get("depends_on", [])
                if isinstance(dep_list, dict):
                    dep_list = list(dep_list.keys())
                if svc_name in dep_list:
                    dependents.append(other_name)
            colocated_infra[svc_name] = dependents

    # Build sidecar info: for each dependent, what infra to embed
    sidecar_map = {}  # svc_name → [(infra_type, start_cmd, port, apt_pkgs)]
    for infra_svc, dependents in colocated_infra.items():
        infra_config = services[infra_svc]
        infra_type = _detect_service_type(infra_svc, infra_config)
        if infra_type not in SERVICE_INSTALLERS:
            continue
        installer = SERVICE_INSTALLERS[infra_type]
        port = _extract_port(infra_config) or installer["default_port"]
        extra_args = ""
        if infra_type == "redis":
            env = _extract_env_vars(infra_config)
            password = env.get("REDIS_PASSWORD", "")
            if not password and user_env_values:
                password = user_env_values.get("REDIS_PASSWORD", "")
            if password:
                extra_args = f" --requirepass {password}"
        start_cmd = installer["start_cmd"].format(port=port, extra_args=extra_args)
        apt_pkgs = installer["apt"]
        for dep in dependents:
            if dep not in sidecar_map:
                sidecar_map[dep] = []
            sidecar_map[dep].append((infra_type, start_cmd, port, apt_pkgs, infra_svc))

    # Remove co-located infra services from the sandbox list — they run as sidecars
    services = {k: v for k, v in services.items() if k not in colocate_svcs}

    ordered = _topological_sort(services)

    # Build image definitions for each service
    image_defs = []
    for svc_name in ordered:
        svc_config = services[svc_name]
        image_expr = _resolve_service_image(
            svc_name, svc_config, compose_dir, exclude_patterns, python_version
        )
        # If this service has sidecars, add apt packages for them
        if svc_name in sidecar_map:
            sidecar_apt = []
            for _, _, _, apt_pkgs, _ in sidecar_map[svc_name]:
                sidecar_apt.extend(apt_pkgs)
            if sidecar_apt:
                image_expr += f'\n    .apt_install({repr(sorted(set(sidecar_apt)))})'
        safe_name = svc_name.replace("-", "_").replace(".", "_")
        image_defs.append(f'image_{safe_name} = (\n    {image_expr}\n)')

    # Build service metadata registry
    svc_meta_entries = []
    for svc_name in ordered:
        svc_config = services[svc_name]
        safe_name = svc_name.replace("-", "_").replace(".", "_")
        command = _command_to_shell(svc_config.get("command", ""))
        if not command:
            command = _extract_dockerfile_cmd(svc_config, compose_dir=compose_dir)
        if not command:
            svc_type = _detect_service_type(svc_name, svc_config)
            if svc_type and svc_type in SERVICE_INSTALLERS:
                port = _extract_port(svc_config) or SERVICE_INSTALLERS[svc_type]["default_port"]
                extra_args = ""
                if svc_type == "redis":
                    password = _extract_env_vars(svc_config).get("REDIS_PASSWORD", "")
                    if password:
                        extra_args = f" --requirepass {password}"
                command = SERVICE_INSTALLERS[svc_type]["start_cmd"].format(
                    port=port, extra_args=extra_args
                )

        ports = _get_service_ports(svc_config)

        # Sidecar infra ports are internal-only (localhost), no need to expose via tunnel

        # Wrap command to start sidecars first
        if svc_name in sidecar_map and command:
            sidecar_cmds = []
            for infra_type, start_cmd, infra_port, _, infra_name in sidecar_map[svc_name]:
                if infra_type == "nginx":
                    # Nginx needs config setup: copy user config, rewrite upstreams to localhost
                    nginx_setup = (
                        'NGINX_CONF=$(find /app -name "nginx.conf" 2>/dev/null | head -1); '
                        'if [ -n "$NGINX_CONF" ]; then cp "$NGINX_CONF" /tmp/nginx_compose.conf; '
                        'sed -i "s/server [a-zA-Z_-]*:/server 127.0.0.1:/g" /tmp/nginx_compose.conf; '
                        'sed -i "s/^user nginx/user root/" /tmp/nginx_compose.conf; '
                        'else echo "worker_processes auto; events { worker_connections 1024; } '
                        f'http {{ server {{ listen {infra_port}; location / {{ proxy_pass http://127.0.0.1:8000; }} }} }}" '
                        '> /tmp/nginx_compose.conf; fi'
                    )
                    sidecar_cmds.append(
                        f'echo "[sidecar] Setting up {infra_name} (nginx)..." && '
                        f'{nginx_setup}'
                    )
                # Start infra in background, wait for port
                sidecar_cmds.append(
                    f'echo "[sidecar] Starting {infra_name} ({infra_type})..."; '
                    f'{start_cmd} & '
                    f'for i in $(seq 1 30); do '
                    f'(echo > /dev/tcp/127.0.0.1/{infra_port}) 2>/dev/null && break; '
                    f'sleep 0.5; done; '
                    f'echo "[sidecar] {infra_name} ready on port {infra_port}"'
                )
            # Combine: start sidecars, then run main command
            sidecar_script = " && ".join(sidecar_cmds)
            command = f'bash -c \'{sidecar_script} && {command}\''

        # Use gpu_override if provided (user selected which services need GPU)
        if gpu_override is not None:
            needs_gpu = gpu_override.get(svc_name, False)
        else:
            needs_gpu = _service_needs_gpu(svc_config)
        deps = _get_service_dependencies(svc_config)
        # Remove co-located infra from deps (they run as sidecars, not separate sandboxes)
        deps = [(d, c) for d, c in deps if d not in colocate_svcs]
        env_vars = _extract_env_vars(svc_config)
        workdir = svc_config.get("working_dir", "") or _extract_dockerfile_workdir(svc_config, compose_dir=compose_dir)

        # Also extract Dockerfile ENVs
        dockerfile_envs = _extract_dockerfile_envs(svc_config, compose_dir=compose_dir)
        _skip_env_prefixes = ("UV_", "PYTHON_INSTALL", "PATH")
        _skip_env_exact = {"PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "PYTHONPATH"}
        for k, v in dockerfile_envs.items():
            if k in _skip_env_exact or any(k.startswith(p) for p in _skip_env_prefixes):
                continue
            if k not in env_vars:
                env_vars[k] = v

        # Modal provisions GPU as device 0; override any fixed device assignment
        if "CUDA_VISIBLE_DEVICES" in env_vars:
            env_vars["CUDA_VISIBLE_DEVICES"] = "0"

        # For services with co-located infra, rewrite hostname references to localhost
        if svc_name in sidecar_map:
            for infra_type, _, infra_port, _, infra_name in sidecar_map[svc_name]:
                # Rewrite env vars that reference the infra service hostname
                for k, v in list(env_vars.items()):
                    if infra_name in str(v):
                        env_vars[k] = v.replace(infra_name, "127.0.0.1")
                # Inject common env vars for the infra type
                if infra_type == "redis":
                    env_vars.setdefault("REDIS_HOST", "127.0.0.1")
                    env_vars.setdefault("REDIS_PORT", str(infra_port))
                elif infra_type == "postgres":
                    env_vars.setdefault("POSTGRES_HOST", "127.0.0.1")
                    env_vars.setdefault("DATABASE_HOST", "127.0.0.1")

        # Resolve env vars with user-provided values
        env_vars = _resolve_env_vars(env_vars, user_provided=user_env_values)

        svc_meta_entries.append({
            "name": svc_name,
            "safe_name": safe_name,
            "command": command or "",
            "ports": ports,
            "needs_gpu": needs_gpu,
            "deps": deps,
            "env_vars": env_vars,
            "workdir": workdir,
        })

    # Build the script
    image_block = "\n\n".join(image_defs)

    # Service metadata as a Python dict in the script
    svc_meta_lines = []
    for meta in svc_meta_entries:
        deps_repr = repr(meta["deps"])
        env_repr = repr(meta["env_vars"])
        svc_meta_lines.append(
            f'    "{meta["name"]}": {{\n'
            f'        "image_var": "image_{meta["safe_name"]}",\n'
            f'        "command": {repr(meta["command"])},\n'
            f'        "ports": {repr(meta["ports"])},\n'
            f'        "needs_gpu": {repr(meta["needs_gpu"])},\n'
            f'        "deps": {deps_repr},\n'
            f'        "env": {env_repr},\n'
            f'        "workdir": {repr(meta["workdir"])},\n'
            f'    }},'
        )
    svc_meta_block = "\n".join(svc_meta_lines)

    # Image variable mapping
    image_map_lines = []
    for meta in svc_meta_entries:
        image_map_lines.append(
            f'    "image_{meta["safe_name"]}": image_{meta["safe_name"]},'
        )
    image_map_block = "\n".join(image_map_lines)

    # GPU spec string for sandboxes
    gpu_spec_str = gpu_spec

    # The sandbox script runs LOCALLY (python, not modal run).
    # Images are built locally with image.build(app), then passed to Sandbox.create().
    # This is required because from_dockerfile needs local file access.

    script = f'''#!/usr/bin/env python3
"""m-gpux Compose Sandbox — local orchestrator.

This script runs LOCALLY and creates Modal Sandboxes for each service.
Images are built locally via image.build(app), then passed to Sandbox.create().
"""
import modal
import modal.exception
import os
import sys
import shlex
import time
import threading

# ─── Service Images ───────────────────────────────────────────
# Defined at module level so Modal SDK can read Dockerfiles locally.
{image_block}

# ─── Image registry (name → image object) ────────────────────
IMAGE_REGISTRY = {{
{image_map_block}
}}

# ─── Service metadata ────────────────────────────────────────
SERVICE_META = {{
{svc_meta_block}
}}

SERVICE_ORDER = {repr(ordered)}
GPU_SPEC = "{gpu_spec_str}"
VOLUME_NAME = "{workspace_volume_name}"

IDLE_CMDS = ("sleep ", "sleep infinity", "tail -f", "cat")
IDLE_CMDS_EXACT = ("bash", "/bin/bash", "sh", "/bin/sh")


def _is_idle_command(cmd: str) -> bool:
    cmd_lower = cmd.strip().lower()
    if cmd_lower in IDLE_CMDS_EXACT:
        return True
    for pattern in IDLE_CMDS:
        if cmd_lower.startswith(pattern):
            return True
    return False


def _resolve_env(env_dict, tunnel_urls_map):
    """Replace service hostname references with tunnel URLs."""
    resolved = dict(env_dict)
    for k, v in resolved.items():
        if not v:
            continue
        for svc_name, urls in tunnel_urls_map.items():
            if svc_name in v:
                for port, url in urls.items():
                    v = v.replace(f"http://{{svc_name}}:{{port}}", url)
                    v = v.replace(f"{{svc_name}}:{{port}}", url.replace("http://", ""))
                if svc_name in v:
                    primary_url = list(urls.values())[0] if urls else ""
                    if primary_url:
                        v = v.replace(svc_name, primary_url.replace("http://", "").replace("https://", ""))
        resolved[k] = v
    return resolved


def _create_sandbox(svc_name, meta, resolved_env, sb_app, workspace_vol):
    """Create and return a Sandbox for a service."""
    image = IMAGE_REGISTRY[meta["image_var"]]
    ports = meta["ports"]
    needs_gpu = meta["needs_gpu"]
    command = meta["command"]
    workdir = meta.get("workdir", "")

    sb_kwargs = {{
        "app": sb_app,
        "image": image,
        "timeout": 86400,
        "volumes": {{"/workspace": workspace_vol}},
    }}

    if workdir:
        sb_kwargs["workdir"] = workdir

    if resolved_env:
        sb_kwargs["secrets"] = [modal.Secret.from_dict(resolved_env)]

    if needs_gpu:
        sb_kwargs["gpu"] = GPU_SPEC

    if ports:
        sb_kwargs["unencrypted_ports"] = ports

    if command and not _is_idle_command(command):
        try:
            cmd_parts = shlex.split(command)
        except ValueError:
            cmd_parts = command.split()
        sb = modal.Sandbox.create(*cmd_parts, **sb_kwargs)
    else:
        sb = modal.Sandbox.create("sleep", "86400", **sb_kwargs)

    return sb


def _stream_logs(name, sandbox):
    """Stream stdout and stderr from a sandbox."""
    def _stream_out():
        try:
            for line in sandbox.stdout:
                print(f"[{{name}}] {{line}}", end="", flush=True)
        except Exception:
            pass

    def _stream_err():
        try:
            for line in sandbox.stderr:
                print(f"[{{name}}:err] {{line}}", end="", flush=True)
        except Exception:
            pass

    threading.Thread(target=_stream_out, daemon=True).start()
    threading.Thread(target=_stream_err, daemon=True).start()


def main():
    print("=" * 60)
    print("[SANDBOX COMPOSE] Initializing...")
    print("=" * 60, flush=True)

    # ─── Setup ────────────────────────────────────────────────────
    sb_app = modal.App.lookup("m-gpux-compose-sandbox", create_if_missing=True)
    workspace_vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

    # ─── Build images locally ─────────────────────────────────────
    print("[SANDBOX COMPOSE] Building images (this may take a while on first run)...", flush=True)
    with modal.enable_output():
        for img_key, img_obj in IMAGE_REGISTRY.items():
            svc_name = img_key.replace("image_", "").replace("_", "-")
            print(f"  Building image for {{svc_name}}...", flush=True)
            try:
                img_obj.build(sb_app)
                print(f"  ✓ {{svc_name}} image ready", flush=True)
            except Exception as e:
                print(f"  ✗ {{svc_name}} image build failed: {{e}}", flush=True)
                raise

    sandboxes = {{}}
    tunnel_urls = {{}}

    try:
        # ─── Phase 1: Create sandboxes in dependency order ────────────
        print("\\n" + "=" * 60)
        print("[SANDBOX COMPOSE] Starting services...")
        print("=" * 60, flush=True)

        for svc_name in SERVICE_ORDER:
            meta = SERVICE_META[svc_name]
            deps = meta["deps"]
            ports = meta["ports"]

            # Wait for dependencies
            for dep_name, condition in deps:
                if dep_name not in sandboxes:
                    print(f"[{{svc_name}}] WARNING: dependency {{dep_name}} not found", flush=True)
                    continue

                dep_sb = sandboxes[dep_name]
                dep_meta = SERVICE_META.get(dep_name, {{}})
                dep_ports = dep_meta.get("ports", [])

                if condition == "service_completed_successfully":
                    print(f"[{{svc_name}}] Waiting for {{dep_name}} to complete...", flush=True)
                    dep_sb.wait()
                    rc = dep_sb.returncode
                    if rc != 0:
                        print(f"[{{svc_name}}] ERROR: {{dep_name}} exited with code {{rc}}", flush=True)
                        raise SystemExit(1)
                    print(f"[{{svc_name}}] {{dep_name}} completed successfully", flush=True)
                elif condition in ("service_started", "service_healthy"):
                    if dep_ports:
                        print(f"[{{svc_name}}] Waiting for {{dep_name}} ports {{dep_ports}}...", flush=True)
                        deadline = time.time() + 120
                        ready = False
                        while time.time() < deadline:
                            try:
                                check_cmd = " && ".join(
                                    f"(echo > /dev/tcp/127.0.0.1/{{p}}) 2>/dev/null"
                                    for p in dep_ports
                                )
                                p = dep_sb.exec("bash", "-c", check_cmd, timeout=5)
                                p.wait()
                                if p.returncode == 0:
                                    ready = True
                                    break
                            except Exception:
                                pass
                            time.sleep(2)
                        if ready:
                            print(f"[{{svc_name}}] {{dep_name}} is ready", flush=True)
                        else:
                            print(f"[{{svc_name}}] WARNING: {{dep_name}} ports not ready after 120s", flush=True)
                    else:
                        time.sleep(3)

            # Resolve env vars with known tunnel URLs
            resolved_env = _resolve_env(meta["env"], tunnel_urls)

            print(f"[{{svc_name}}] Creating sandbox...", flush=True)
            sb = _create_sandbox(svc_name, meta, resolved_env, sb_app, workspace_vol)
            sandboxes[svc_name] = sb
            print(f"[{{svc_name}}] Sandbox created: {{sb.object_id}}", flush=True)

            # Start streaming logs immediately
            _stream_logs(svc_name, sb)

            # Get tunnel URLs
            if ports:
                try:
                    tunnels = sb.tunnels(timeout=60)
                    svc_tunnels = {{}}
                    for port_num, tunnel_obj in tunnels.items():
                        svc_tunnels[port_num] = tunnel_obj.url
                        print(f"[{{svc_name}}] Port {{port_num}} → {{tunnel_obj.url}}", flush=True)
                    tunnel_urls[svc_name] = svc_tunnels
                except Exception as e:
                    print(f"[{{svc_name}}] WARNING: Could not get tunnels: {{e}}", flush=True)
                    tunnel_urls[svc_name] = {{}}

        # ─── Phase 2: Summary ────────────────────────────────────────
        print("\\n" + "=" * 60)
        print("[SANDBOX COMPOSE] All services running!")
        print("-" * 60)
        for svc_name, sb in sandboxes.items():
            status = "running" if sb.poll() is None else f"exited ({{sb.returncode}})"
            urls = tunnel_urls.get(svc_name, {{}})
            url_str = ", ".join(f"{{p}}→{{u}}" for p, u in urls.items()) if urls else "no tunnels"
            print(f"  {{svc_name}}: {{status}} | {{url_str}} | id={{sb.object_id}}")
        print("-" * 60)
        print(f"  Volume: {{VOLUME_NAME}}")
        print("=" * 60 + "\\n", flush=True)

        # Save sandbox IDs for later use (ps, exec, logs, down)
        ids_file = ".m-gpux-sandbox-ids.json"
        import json
        sb_ids = {{name: sb.object_id for name, sb in sandboxes.items()}}
        with open(ids_file, "w") as f:
            json.dump({{"app_name": "m-gpux-compose-sandbox", "sandboxes": sb_ids}}, f, indent=2)
        print(f"[SANDBOX COMPOSE] Sandbox IDs saved to {{ids_file}}", flush=True)

        # ─── Phase 3: Stream logs and monitor ────────────────────────
        for svc_name, sb in sandboxes.items():
            t = threading.Thread(target=_stream_logs, args=(svc_name, sb), daemon=True)
            t.start()

        print("[SANDBOX COMPOSE] Streaming logs... Press Ctrl+C to detach.\\n", flush=True)

        while True:
            time.sleep(10)
            all_done = True
            for svc_name, sb in sandboxes.items():
                rc = sb.poll()
                if rc is None:
                    all_done = False
                elif rc is not None and rc != 0:
                    meta = SERVICE_META[svc_name]
                    if not _is_idle_command(meta.get("command", "")):
                        print(f"[{{svc_name}}] Process exited with code {{rc}}", flush=True)
            if all_done:
                print("[SANDBOX COMPOSE] All services have stopped.", flush=True)
                break

    except KeyboardInterrupt:
        print("\\n[SANDBOX COMPOSE] Detaching (sandboxes keep running on Modal)...", flush=True)
        for sb in sandboxes.values():
            try:
                sb.detach()
            except Exception:
                pass
        print("[SANDBOX COMPOSE] Detached. Use `m-gpux compose sandbox ps` to check status.", flush=True)
        print("[SANDBOX COMPOSE] Use `m-gpux compose sandbox down` to stop all.", flush=True)
        return

    except SystemExit:
        pass

    finally:
        # Detach all (don't terminate — user may want them running)
        for sb in sandboxes.values():
            try:
                sb.detach()
            except Exception:
                pass


if __name__ == "__main__":
    main()
'''
    return script


def compose_sandbox_check(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Analyze a compose file for Sandbox multi-container deployment.

    Shows per-service isolation plan: image strategy, GPU assignment,
    dependency ordering, port tunneling, and Dockerfile detection.
    """
    compose_path = file or _find_compose_file()
    if compose_path is None:
        console.print("[bold red]No compose file found.[/bold red]")
        raise typer.Exit(1)

    data = _parse_compose(compose_path)
    services = data["services"]
    compose_dir = os.path.dirname(os.path.abspath(compose_path)) or "."

    console.print(Panel.fit(
        f"[bold magenta]Compose Sandbox Analysis[/bold magenta] — {compose_path}\n"
        "[dim]Each service → its own Modal Sandbox (true container isolation)[/dim]",
        border_style="cyan",
    ))

    ordered = _topological_sort(services)

    svc_table = Table(show_header=True, header_style="bold cyan")
    svc_table.add_column("Order")
    svc_table.add_column("Service")
    svc_table.add_column("Image Strategy")
    svc_table.add_column("Ports")
    svc_table.add_column("GPU")
    svc_table.add_column("Depends On")

    for idx, svc_name in enumerate(ordered, 1):
        svc_config = services[svc_name]

        # Image strategy
        image_name = svc_config.get("image", "")
        build_cfg = svc_config.get("build", {})
        svc_type = _detect_service_type(svc_name, svc_config)
        if image_name and not build_cfg:
            strategy = f"from_registry({image_name[:30]})"
        elif build_cfg:
            target = ""
            if isinstance(build_cfg, dict):
                target = build_cfg.get("target", "")
                dockerfile = build_cfg.get("dockerfile", "Dockerfile")
                context = build_cfg.get("context", ".")
            else:
                dockerfile = "Dockerfile"
                context = build_cfg
            df_path = os.path.join(compose_dir, context, dockerfile)
            if os.path.exists(df_path):
                strategy = f"from_dockerfile({dockerfile}"
                if target:
                    strategy += f" → {target}"
                strategy += ")"
            else:
                strategy = "debian_slim (no Dockerfile)"
        elif svc_type:
            strategy = f"debian_slim + apt({svc_type})"
        else:
            strategy = "debian_slim"

        # Ports
        ports = _get_service_ports(svc_config)
        ports_str = ", ".join(str(p) for p in ports) if ports else "-"

        # GPU
        needs_gpu = _service_needs_gpu(svc_config)
        gpu_str = "[bold green]✓ GPU[/bold green]" if needs_gpu else "[dim]CPU[/dim]"

        # Dependencies
        deps = _get_service_dependencies(svc_config)
        if deps:
            dep_strs = []
            for dep_name, condition in deps:
                if condition == "service_completed_successfully":
                    dep_strs.append(f"{dep_name} [yellow](wait)[/yellow]")
                else:
                    dep_strs.append(dep_name)
            deps_str = ", ".join(dep_strs)
        else:
            deps_str = "-"

        svc_table.add_row(str(idx), svc_name, strategy, ports_str, gpu_str, deps_str)

    console.print(svc_table)

    # Networking info
    console.print(f"\n[bold cyan]Networking:[/bold cyan]")
    console.print("  Each service gets its own Sandbox with tunneled ports.")
    console.print("  Environment variables referencing service hostnames (e.g. http://redis:6379)")
    console.print("  are automatically rewritten to use tunnel URLs at startup.")

    # Warnings
    warnings = []
    for svc_name, svc_config in services.items():
        image_name = svc_config.get("image", "")
        build_cfg = svc_config.get("build", {})
        if image_name and "cloudflare" in image_name.lower():
            warnings.append(f"  [yellow]⚠ {svc_name}:[/yellow] cloudflared image — tunnel handled by Modal natively")
        if svc_config.get("shm_size"):
            warnings.append(f"  [yellow]⚠ {svc_name}:[/yellow] shm_size not supported in Sandbox mode")
        if svc_config.get("tmpfs"):
            warnings.append(f"  [yellow]⚠ {svc_name}:[/yellow] tmpfs mount — /tmp always available but size not configurable")

    if warnings:
        console.print(f"\n[bold yellow]Warnings:[/bold yellow]")
        for w in warnings:
            console.print(w)

    console.print(f"\n[bold green]Ready for Sandbox deployment ({len(services)} sandboxes).[/bold green]")
    console.print("[dim]Run `m-gpux compose sandbox up` to deploy.[/dim]")


def compose_sandbox_up(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Deploy a Docker Compose stack using Modal Sandboxes (multi-container).

    Each service runs in its own isolated Modal Sandbox. Services with
    Dockerfiles are built via Image.from_dockerfile. Dependencies are
    resolved with proper wait/readiness ordering. Ports are tunneled
    for inter-service communication.

    This mode provides true container isolation — each service has its own
    filesystem, process space, and optional GPU. Best for complex stacks
    like Triton + Redis + App + Nginx.

    Examples:
        m-gpux compose sandbox up
        m-gpux compose sandbox up -f docker-compose.prod.yml
    """
    console.print(Panel.fit(
        "[bold magenta]m-gpux Compose Sandbox[/bold magenta]\n"
        "True multi-container: each service → its own Modal Sandbox.\n"
        "[dim]Dockerfile builds • GPU per-service • dependency ordering • tunneled networking[/dim]",
        border_style="cyan",
    ))

    # --- Find compose file ---
    compose_path = file or _find_compose_file()
    if compose_path is None:
        console.print("[bold red]No docker-compose.yml or compose.yml found.[/bold red]")
        console.print("[dim]Use --file / -f to specify a path.[/dim]")
        raise typer.Exit(1)

    compose_dir = os.path.dirname(os.path.abspath(compose_path)) or "."
    console.print(f"[green]Compose file:[/green] [bold]{compose_path}[/bold]")

    # --- Parse ---
    data = _parse_compose(compose_path)
    services = data["services"]
    ordered = _topological_sort(services)

    # --- Display services ---
    console.print(f"\n[bold cyan]Services ({len(services)}):[/bold cyan]")
    for svc_name in ordered:
        svc_config = services[svc_name]
        ports = _get_service_ports(svc_config)
        gpu = _service_needs_gpu(svc_config)
        deps = _get_service_dependencies(svc_config)
        image = svc_config.get("image", "")
        build_cfg = svc_config.get("build", {})
        src = image or ("Dockerfile" if build_cfg else "debian_slim")
        dep_names = [d[0] for d in deps]
        console.print(
            f"  [bold]{svc_name}[/bold] — {src}"
            f"{' [green]GPU[/green]' if gpu else ''}"
            f"{' → ports ' + ', '.join(str(p) for p in ports) if ports else ''}"
            f"{' | depends: ' + ', '.join(dep_names) if dep_names else ''}"
        )

    # --- Select services ---
    # Categorize: "core" services (have ports or are depended upon by others)
    # vs "one-shot" (no ports, not depended upon, likely batch jobs)
    depended_upon = set()
    for svc_config in services.values():
        depends = svc_config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        depended_upon.update(depends)

    core_services = []
    optional_services = []
    for svc_name in ordered:
        svc_config = services[svc_name]
        ports = _get_service_ports(svc_config)
        has_deps_on_it = svc_name in depended_upon
        depends = svc_config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        # Core: has ports, or is depended upon, or depends on something (part of a chain)
        if ports or has_deps_on_it or depends:
            core_services.append(svc_name)
        else:
            optional_services.append(svc_name)

    selected_services = None
    all_names = list(services.keys())

    if optional_services:
        console.print(f"\n[bold cyan]Service categories:[/bold cyan]")
        console.print(f"  [green]Core[/green] ({len(core_services)}): {', '.join(core_services)}")
        console.print(f"  [yellow]Optional[/yellow] ({len(optional_services)}): {', '.join(optional_services)}")

        run_choice_options = [
            ("Core only", f"Start {len(core_services)} core services (recommended)"),
            ("All", f"Start all {len(all_names)} services"),
            ("Custom", "Pick specific services"),
        ]
        run_idx = arrow_select(run_choice_options, title="Which services?", default=0)

        if run_idx == 0:
            selected_services = core_services
            console.print(f"  [green]Selected:[/green] {', '.join(selected_services)} (+ dependencies)")
        elif run_idx == 1:
            selected_services = None  # all
        else:
            # Custom selection with numbered list
            console.print("[dim]Enter service names or numbers (space-separated):[/dim]")
            for i, name in enumerate(all_names, 1):
                marker = "[green]●[/green]" if name in core_services else "[yellow]○[/yellow]"
                console.print(f"  {marker} {i}. {name}")
            svc_input = Prompt.ask("  Services", default=" ".join(str(i+1) for i, n in enumerate(all_names) if n in core_services))
            selected_services = []
            for token in svc_input.split():
                token = token.strip().rstrip(",")
                if token.isdigit():
                    idx = int(token) - 1
                    if 0 <= idx < len(all_names):
                        selected_services.append(all_names[idx])
                elif token in services:
                    selected_services.append(token)
            if not selected_services:
                console.print("[bold red]No valid services selected.[/bold red]")
                raise typer.Exit(1)
            console.print(f"  [green]Selected:[/green] {', '.join(selected_services)} (+ dependencies)")
    elif len(all_names) > 3:
        run_all = Prompt.ask(
            f"\n[bold cyan]Run all {len(all_names)} services?[/bold cyan]",
            choices=["y", "n"], default="y",
        )
        if run_all == "n":
            console.print("[dim]Enter service names (space-separated):[/dim]")
            svc_input = Prompt.ask("  Services", default=all_names[0])
            selected_services = [s.strip() for s in svc_input.split() if s.strip() in services]
            if not selected_services:
                console.print("[bold red]No valid services selected.[/bold red]")
                raise typer.Exit(1)
            console.print(f"  [green]Selected:[/green] {', '.join(selected_services)} (+ dependencies)")

    # Show auto-added dependencies so user knows what will be built
    if selected_services:
        def _get_all_deps(svc, all_svcs, visited=None):
            if visited is None:
                visited = set()
            if svc in visited:
                return visited
            visited.add(svc)
            dep_cfg = all_svcs.get(svc, {}).get("depends_on", [])
            if isinstance(dep_cfg, dict):
                dep_cfg = list(dep_cfg.keys())
            for d in dep_cfg:
                if d in all_svcs:
                    _get_all_deps(d, all_svcs, visited)
            return visited

        all_needed = set()
        for s in selected_services:
            all_needed.update(_get_all_deps(s, services))
        auto_added = sorted(all_needed - set(selected_services))
        if auto_added:
            console.print(f"  [dim]Auto-added dependencies:[/dim] [yellow]{', '.join(auto_added)}[/yellow]")

    # --- Profile ---
    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    # --- GPU selection (for GPU services) ---
    # Determine which services will actually run (selected + deps)
    if selected_services:
        _running_svcs = set()
        for s in selected_services:
            _running_svcs.update(_get_all_deps(s, services))
    else:
        _running_svcs = set(services.keys())

    gpu_flagged = [s for s in ordered if s in _running_svcs and _service_needs_gpu(services[s])]
    gpu_spec = "T4"
    cpu_spec = None
    gpu_override = {}  # svc_name → bool (True=GPU, False=CPU)

    if gpu_flagged:
        console.print(f"\n[bold cyan]GPU Configuration[/bold cyan]")
        console.print(f"[dim]Compose marks these services for GPU: {', '.join(gpu_flagged)}[/dim]")
        console.print(f"[dim]Each GPU sandbox costs extra. Select which services truly need GPU:[/dim]")

        for svc_name in gpu_flagged:
            svc_config = services[svc_name]
            cmd = _command_to_shell(svc_config.get("command", "")) or "(default)"
            use_gpu = Prompt.ask(
                f"  [cyan]{svc_name}[/cyan] ({cmd[:60]}) — GPU?",
                choices=["y", "n"], default="y",
            )
            gpu_override[svc_name] = (use_gpu == "y")

        actual_gpu_svcs = [s for s, v in gpu_override.items() if v]
        if actual_gpu_svcs:
            gpu_options = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
            gpu_idx = arrow_select(gpu_options, title="GPU", default=1)
            gpu_spec = list(AVAILABLE_GPUS.values())[gpu_idx][0]
            console.print(f"[green]GPU services:[/green] [bold]{', '.join(actual_gpu_svcs)}[/bold] → {gpu_spec}")
        else:
            console.print("[dim]No services will use GPU.[/dim]")
    else:
        console.print("\n[dim]No GPU services detected. All sandboxes will use CPU.[/dim]")

    # --- Python version detection ---
    python_version = "3.12"
    if os.path.exists(os.path.join(compose_dir, "pyproject.toml")):
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            with open(os.path.join(compose_dir, "pyproject.toml"), "rb") as _f:
                _pyproj = tomllib.load(_f)
            _req_python = _pyproj.get("project", {}).get("requires-python", "")
            if _req_python:
                import re as _re_py
                _m = _re_py.search(r'(\d+\.\d+)', _req_python)
                if _m:
                    python_version = _m.group(1)
                    console.print(f"[dim]Python version: {python_version} (from pyproject.toml)[/dim]")
        except Exception:
            pass

    # --- Exclude patterns ---
    default_excludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox"
    exclude_input = Prompt.ask(
        "[bold cyan]Exclude patterns[/bold cyan]",
        default=default_excludes,
    )
    exclude_patterns = [p.strip() for p in exclude_input.split(",") if p.strip()]

    # --- Detect unresolved env vars ---
    import re as _re
    all_raw_env = {}
    for svc_config in services.values():
        svc_env = _extract_env_vars(svc_config)
        all_raw_env.update(svc_env)

    unresolved_vars = set()
    for k, v in all_raw_env.items():
        refs = _re.findall(r'\$\{([A-Z_][A-Z_0-9]*)', str(v))
        for ref in refs:
            if ref not in os.environ:
                unresolved_vars.add(ref)
        if not v and k not in os.environ:
            unresolved_vars.add(k)

    user_env_values = {}
    if unresolved_vars:
        console.print(f"\n[bold cyan]Environment Variables[/bold cyan]")
        console.print("[dim]Referenced in compose but not set locally.[/dim]")
        for var in sorted(unresolved_vars):
            val = Prompt.ask(f"  [cyan]{var}[/cyan]", default="")
            if val:
                user_env_values[var] = val

    workspace_volume = _workspace_volume_name(".")

    # --- Generate script ---
    console.print("\n[bold cyan]Generating Sandbox compose script...[/bold cyan]")

    script = _build_sandbox_compose_script(
        services=services,
        compose_dir=compose_dir,
        exclude_patterns=exclude_patterns,
        user_env_values=user_env_values,
        python_version=python_version,
        gpu_spec=gpu_spec,
        cpu_spec=cpu_spec,
        workspace_volume_name=workspace_volume,
        selected_services=selected_services,
        gpu_override=gpu_override,
    )

    # --- Summary ---
    active_count = len(selected_services) if selected_services else len(services)
    gpu_services = [s for s, v in gpu_override.items() if v]

    console.print(Panel(
        f"[bold]Sandbox Compose Deployment[/bold]\n\n"
        f"  Compose file: {compose_path}\n"
        f"  Sandboxes: {active_count} services (+ dependencies)\n"
        f"  GPU services: {', '.join(gpu_services) if gpu_services else 'none'} → {gpu_spec}\n"
        f"  Volume: {workspace_volume}\n\n"
        f"[dim]Each service runs in its own isolated Sandbox.\n"
        f"Ports are tunneled. Dependencies wait for readiness.\n"
        f"Service hostnames in env vars are rewritten to tunnel URLs.[/dim]",
        title="DEPLOYMENT PLAN",
        border_style="green",
    ))

    # Sandbox mode runs as a LOCAL Python script (not modal run).
    # Images are built locally, sandboxes created via Sandbox.create().
    runner_file = "modal_runner.py"
    with open(runner_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    from rich.syntax import Syntax

    console.print()
    verbose = os.environ.get("MGPUX_VERBOSE", "").strip() in ("1", "true", "yes")
    if verbose:
        console.print(Syntax(script, "python", theme="monokai", line_numbers=True))

    console.print(
        f"[dim]Generated [bold]{runner_file}[/bold] — this runs locally and creates Sandboxes on Modal.[/dim]"
    )

    while True:
        choice = Prompt.ask(
            "[bold cyan][Enter][/bold cyan] run  •  [bold cyan]v[/bold cyan] view code  •  [bold cyan]c[/bold cyan] cancel",
            default="",
        ).strip().lower()
        if choice in ("", "r", "run"):
            break
        if choice in ("c", "cancel", "q", "quit"):
            console.print("[yellow]Cancelled.[/yellow]")
            return
        if choice in ("v", "view", "show"):
            console.print(Syntax(script, "python", theme="monokai", line_numbers=True))
            continue

    console.print(f"[bold green]Starting Sandbox Compose ({active_count} services)...[/bold green]")
    console.print("[dim]Press Ctrl+C to detach (sandboxes keep running on Modal).[/dim]")

    # Save session metadata
    session_metadata = {
        "id": new_session_id(),
        "kind": "compose-sandbox",
        "profile": selected_profile,
        "compute": gpu_spec if gpu_services else "CPU",
        "workspace_volume": workspace_volume,
        "local_dir": os.path.abspath(compose_dir),
        "app_name": "m-gpux-compose-sandbox",
        "services": list(services.keys()),
        "mode": "sandbox",
        "state": "running",
    }
    from m_gpux.core.state import save_session
    saved = save_session(session_metadata)
    console.print(
        f"[green]Tracked session:[/green] [bold]{saved['id']}[/bold] "
        f"([cyan]m-gpux-compose-sandbox[/cyan])"
    )

    # Run locally with python (NOT modal run)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    try:
        result = subprocess.run(["python", runner_file], env=env)
    except KeyboardInterrupt:
        console.print("\n[green]Detached. Sandboxes keep running on Modal.[/green]")
        console.print("[dim]Use `m-gpux compose sandbox ps` to check status.[/dim]")
        console.print("[dim]Use `m-gpux compose sandbox down` to stop all.[/dim]")

    # Cleanup
    del_choice = Prompt.ask(
        f"[bold cyan]Delete {runner_file}?[/bold cyan]",
        choices=["y", "n"], default="y",
    )
    if del_choice.lower() == "y":
        try:
            os.remove(runner_file)
        except OSError:
            pass


def compose_sandbox_exec(
    service: str = typer.Argument(..., help="Service name to exec into"),
    command: str = typer.Argument("bash", help="Command to run"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to docker-compose.yml"),
):
    """
    Execute a command in a running Sandbox service.

    Similar to `docker compose exec`, this runs a command inside
    a running Sandbox container.

    Examples:
        m-gpux compose sandbox exec redis redis-cli
        m-gpux compose sandbox exec prod bash
    """
    console.print(f"[cyan]Looking for sandbox: compose-{service}[/cyan]")

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    # Find the sandbox by listing all sandboxes for the app
    script = f'''
import modal

sb_app = modal.App.lookup("m-gpux-compose-sandbox")
try:
    sb = modal.Sandbox.from_name("m-gpux-compose-sandbox", "compose-{service}")
    print(f"Found sandbox: {{sb.object_id}}")
    p = sb.exec("{command}", timeout=3600, pty=True)
    for line in p.stdout:
        print(line, end="")
    p.wait()
    print(f"\\nExit code: {{p.returncode}}")
except modal.exception.NotFoundError:
    print(f"ERROR: No running sandbox found for service '{service}'")
    print("Make sure the compose stack is running: m-gpux compose sandbox up")
'''

    runner_file = "modal_sandbox_exec.py"
    with open(runner_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    try:
        subprocess.run(["python", runner_file], env=env)
    finally:
        try:
            os.remove(runner_file)
        except OSError:
            pass


def compose_sandbox_logs(
    service: str = typer.Argument(None, help="Service name (omit for all)"),
):
    """
    Stream logs from a running Sandbox service.

    Examples:
        m-gpux compose sandbox logs
        m-gpux compose sandbox logs redis
    """
    script = f'''
import modal
import threading

sb_app = modal.App.lookup("m-gpux-compose-sandbox")

def _stream(name, sb):
    try:
        for line in sb.stdout:
            print(f"[{{name}}] {{line}}", end="")
    except Exception:
        pass

target_service = {repr(service)}

for sb in modal.Sandbox.list(app_id=sb_app.app_id):
    tags = sb.get_tags()
    # Sandboxes created with name= are findable
    if sb.poll() is not None:
        continue
    # We use naming convention compose-<service>
    if target_service:
        try:
            named_sb = modal.Sandbox.from_name("m-gpux-compose-sandbox", f"compose-{{target_service}}")
            t = threading.Thread(target=_stream, args=(target_service, named_sb), daemon=True)
            t.start()
            t.join()
        except modal.exception.NotFoundError:
            print(f"No running sandbox found for service '{{target_service}}'")
        break

if not target_service:
    print("Streaming logs from all services...")
    print("(Use Ctrl+C to stop)")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\\nStopped.")
'''

    runner_file = "modal_sandbox_logs.py"
    with open(runner_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    try:
        subprocess.run(["python", runner_file], env=env)
    finally:
        try:
            os.remove(runner_file)
        except OSError:
            pass


def compose_sandbox_ps(
):
    """
    List running Sandbox services and their status.

    Shows sandbox ID, status, ports, and tunnel URLs for each service.
    Similar to `docker compose ps`.
    """
    script = '''
import modal

try:
    sb_app = modal.App.lookup("m-gpux-compose-sandbox")
except modal.exception.NotFoundError:
    print("No compose-sandbox app found. Run `m-gpux compose sandbox up` first.")
    exit(1)

print(f"{'Service':<20} {'Status':<12} {'Sandbox ID':<30} {'Tunnels'}")
print("-" * 90)

found = False
for sb in modal.Sandbox.list(app_id=sb_app.app_id):
    found = True
    rc = sb.poll()
    status = "running" if rc is None else f"exited({rc})"
    try:
        tunnels = sb.tunnels(timeout=5) if rc is None else {}
        tunnel_str = ", ".join(f"{p}→{t.url}" for p, t in tunnels.items()) if tunnels else "-"
    except Exception:
        tunnel_str = "-"
    print(f"{'?':<20} {status:<12} {sb.object_id:<30} {tunnel_str}")

if not found:
    print("No sandboxes running.")
'''

    runner_file = "modal_sandbox_ps.py"
    with open(runner_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    try:
        subprocess.run(["python", runner_file], env=env)
    finally:
        try:
            os.remove(runner_file)
        except OSError:
            pass


def compose_sandbox_down(
):
    """
    Stop and terminate all Sandbox services.

    Terminates all running sandboxes in the compose-sandbox app.
    Similar to `docker compose down`.
    """
    console.print("[bold cyan]Stopping all compose sandboxes...[/bold cyan]")

    script = '''
import modal

try:
    sb_app = modal.App.lookup("m-gpux-compose-sandbox")
except modal.exception.NotFoundError:
    print("No compose-sandbox app found.")
    exit(0)

count = 0
for sb in modal.Sandbox.list(app_id=sb_app.app_id):
    if sb.poll() is None:
        print(f"Terminating {sb.object_id}...")
        sb.terminate()
        count += 1
    sb.detach()

print(f"\\nTerminated {count} sandbox(es).")
'''

    runner_file = "modal_sandbox_down.py"
    with open(runner_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    try:
        subprocess.run(["python", runner_file], env=env)
    finally:
        try:
            os.remove(runner_file)
        except OSError:
            pass

    console.print("[bold green]Done.[/bold green]")


# ─── Plugin registration ──────────────────────────────────────
from m_gpux.core.plugin import PluginBase as _PluginBase
from m_gpux.core.ignore import to_recursive_ignore


class ComposePlugin(_PluginBase):
    name = "compose"
    help = "Deploy Docker Compose stacks on Modal — subprocess, VM, or sandbox mode."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        compose_app = typer.Typer(
            name=self.name,
            help=self.help,
            no_args_is_help=True,
        )
        compose_app.command("up", help="Deploy a compose stack on Modal (subprocess mode)")(compose_main)
        compose_app.command("check", help="Analyze compose file without deploying")(compose_check)
        compose_app.command("sync", help="Watch & sync local changes to running container")(compose_sync)

        # VM sub-commands — provision on Modal with full image support
        vm_app = typer.Typer(
            name="vm",
            help="Deploy compose stacks on Modal GPU containers (full image mode — Triton, gRPC, etc.).",
            no_args_is_help=True,
        )
        vm_app.command("up", help="Provision Modal GPU container & deploy compose stack")(compose_vm_up)
        vm_app.command("check", help="Analyze compose file for VM deployment")(compose_vm_check)

        # Sandbox sub-commands — true multi-container isolation
        sandbox_app = typer.Typer(
            name="sandbox",
            help="Deploy compose stacks as isolated Modal Sandboxes (true multi-container).",
            no_args_is_help=True,
        )
        sandbox_app.command("up", help="Deploy each service as an isolated Sandbox")(compose_sandbox_up)
        sandbox_app.command("check", help="Analyze compose file for Sandbox deployment")(compose_sandbox_check)
        sandbox_app.command("down", help="Stop and terminate all Sandbox services")(compose_sandbox_down)
        sandbox_app.command("ps", help="List running Sandbox services")(compose_sandbox_ps)
        sandbox_app.command("exec", help="Execute a command in a running Sandbox")(compose_sandbox_exec)
        sandbox_app.command("logs", help="Stream logs from Sandbox services")(compose_sandbox_logs)

        compose_app.add_typer(vm_app)
        compose_app.add_typer(sandbox_app)
        root_app.add_typer(compose_app, rich_help_panel=self.rich_help_panel)
