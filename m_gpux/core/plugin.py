"""Plugin / Provider framework.

m-gpux is built around a tiny plugin architecture. The CLI itself does not
know anything about ``account``, ``hub``, ``serve``, … beyond the fact that
each of those is a *plugin* that exposes a Typer command (or sub-app).

Two flavours of plugin can be loaded:

1. **Built-in plugins** — declared in :data:`m_gpux.plugins.BUILTIN_PLUGINS`
   as dotted-path strings ``"package.module:ClassName"``.
2. **Third-party plugins** — registered via the ``m_gpux.plugins`` Python
   entry-point group in another package's ``pyproject.toml``::

       [project.entry-points."m_gpux.plugins"]
       my_plugin = "my_pkg.plugin:MyPlugin"

Subclass :class:`PluginBase` and implement :meth:`PluginBase.register` to
plug new commands into the CLI.
"""

from __future__ import annotations

import importlib
import importlib.metadata as ilm
import sys
from typing import ClassVar, List

import typer


class PluginBase:
    """Base class every m-gpux plugin must subclass.

    Subclasses set the ``name`` (the CLI command/sub-app name) plus optional
    metadata, and implement :meth:`register` to attach commands to the root
    Typer ``app``.
    """

    name: ClassVar[str] = ""
    help: ClassVar[str] = ""
    short_help: ClassVar[str] = ""
    rich_help_panel: ClassVar[str] = "Tools"

    def register(self, app: typer.Typer) -> None:  # pragma: no cover - abstract
        raise NotImplementedError(
            f"Plugin {type(self).__name__} must implement register(app)."
        )


class PluginRegistry:
    """Holds all loaded :class:`PluginBase` instances and installs them onto
    a Typer app."""

    def __init__(self) -> None:
        self._plugins: List[PluginBase] = []
        self._seen: set[type] = set()

    def add(self, plugin: PluginBase) -> None:
        if not isinstance(plugin, PluginBase):
            raise TypeError(
                f"Expected PluginBase instance, got {type(plugin).__name__}"
            )
        if not plugin.name:
            raise ValueError(
                f"Plugin {type(plugin).__name__} must define a non-empty `name`."
            )
        cls = type(plugin)
        if cls in self._seen:
            return  # idempotent: same plugin class already registered
        self._seen.add(cls)
        self._plugins.append(plugin)

    def all(self) -> List[PluginBase]:
        return list(self._plugins)

    def install(self, app: typer.Typer) -> None:
        for plugin in self._plugins:
            plugin.register(app)


# ─── Discovery ─────────────────────────────────────────────────


def _import_plugin(dotted: str) -> PluginBase:
    module_name, _, attr = dotted.rpartition(":")
    if not module_name:
        module_name, attr = dotted, "Plugin"
    module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    return obj() if isinstance(obj, type) else obj


def discover_plugins(
    registry: PluginRegistry,
    *,
    group: str = "m_gpux.plugins",
    extra: list[str] | None = None,
) -> PluginRegistry:
    """Populate *registry* with built-in + entry-point plugins.

    Built-ins are read from :data:`m_gpux.plugins.BUILTIN_PLUGINS`.
    Third-party plugins are loaded from the ``m_gpux.plugins`` entry-point
    group. The ``extra`` argument is mainly useful for tests.
    """
    from m_gpux.plugins import BUILTIN_PLUGINS

    for dotted in BUILTIN_PLUGINS:
        try:
            registry.add(_import_plugin(dotted))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[m-gpux] failed to load built-in plugin {dotted}: {exc}", file=sys.stderr)

    for dotted in extra or []:
        try:
            registry.add(_import_plugin(dotted))
        except Exception as exc:  # pragma: no cover
            print(f"[m-gpux] failed to load extra plugin {dotted}: {exc}", file=sys.stderr)

    try:
        eps = ilm.entry_points(group=group)
    except TypeError:  # Python <3.10 compatibility
        eps = ilm.entry_points().get(group, [])  # type: ignore[attr-defined]

    for ep in eps:
        try:
            obj = ep.load()
            instance = obj() if isinstance(obj, type) else obj
            registry.add(instance)
        except Exception as exc:  # pragma: no cover
            print(f"[m-gpux] failed to load plugin {ep.name}: {exc}", file=sys.stderr)

    return registry
